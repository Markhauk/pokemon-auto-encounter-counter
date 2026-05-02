from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Callable, Optional

import cv2
import numpy as np

from .capture import compute_brightness_stats, grab_region, is_nearly_black, save_image
from .constants import (
    BLACK_FRAME_WARNING_COOLDOWN_SECONDS,
    DEBUG_SAVE_EVERY_N_FRAMES,
    ESCAPE_THRESHOLD,
    GOTCHA_THRESHOLD,
    HUH_THRESHOLD,
    MATCH_LOG_EVERY_N_FRAMES,
    POST_DETECTION_COOLDOWN_SECONDS,
    PREVIEW_MATCH_THRESHOLD,
    SAVE_DEBUG_FRAMES,
    SCAN_INTERVAL_SECONDS,
    WILD_THRESHOLD,
)
from .event_logger import EventLogger
from .exceptions import ModeNotImplementedError
from .models import CounterSnapshot, MatchResult
from .modes import (
    MODE_EGG_KEY,
    MODE_RANDOM_GRASS_KEY,
    MODE_SAFARI_ZONE_KEY,
    get_default_capture_region,
    get_mode,
)
from .paths import DEBUG_FRAME_FILE
from .state_manager import StateManager
from .templates import TemplateManager


LogHandler = Callable[[dict[str, object]], None]
StatusHandler = Callable[[dict[str, object]], None]
StopRequested = Callable[[], bool]


class EncounterCounterEngine:
    def __init__(
        self,
        *,
        capture_region: Optional[dict[str, int]] = None,
        save_debug_frames: bool = SAVE_DEBUG_FRAMES,
        debug_once: bool = False,
        verbose_debug: bool = False,
        mode_key: str = MODE_RANDOM_GRASS_KEY,
        encounter_increment: int = 1,
        state_manager: Optional[StateManager] = None,
        event_logger: Optional[EventLogger] = None,
        template_manager: Optional[TemplateManager] = None,
        log_handler: Optional[LogHandler] = None,
        status_handler: Optional[StatusHandler] = None,
    ) -> None:
        self.mode = get_mode(mode_key)
        if not self.mode.implemented:
            raise ModeNotImplementedError(f"{self.mode.name} is not implemented yet.")

        self.running = True
        self.mode_key = self.mode.key
        self.mode_name = self.mode.name
        self.encounter_increment = max(1, int(encounter_increment))

        self.counter = 0
        self.catch_counter = 0

        self.last_event = "none"
        self.last_event_at: Optional[str] = None
        self.last_match_score = 0.0

        self.last_catch_at_encounter = 0
        self.encounters_since_last_catch = 0

        self.capture_region = dict(capture_region or get_default_capture_region(mode_key))
        self.save_debug_frames = save_debug_frames
        self.debug_once = debug_once
        self.verbose_debug = verbose_debug
        self.last_black_frame_warning_time = 0.0
        self.frame_index = 0
        self.last_match_log_frame = 0
        self.cooldown_until = 0.0
        self.waiting_for_clear = False

        self.got_away_template: Optional[np.ndarray] = None
        self.gotcha_template: Optional[np.ndarray] = None
        self.wild_template: Optional[np.ndarray] = None
        self.huh_template: Optional[np.ndarray] = None

        self.state_manager = state_manager or StateManager()
        self.event_logger = event_logger or EventLogger()
        self.template_manager = template_manager or TemplateManager()
        self.log_handler = log_handler
        self.status_handler = status_handler

        self.state_manager.ensure_directories()
        self.template_manager.ensure_directory()
        self.event_logger.ensure_files()
        self.load_state()
        self.save_state(status="Idle")

        if not self.debug_once:
            self.load_mode_templates()

    def load_mode_templates(self) -> None:
        if self.mode_key == MODE_RANDOM_GRASS_KEY:
            self.got_away_template = self.template_manager.load_grayscale("got_away.png")
            self.gotcha_template = self.template_manager.load_grayscale("gotcha.png")
        elif self.mode_key == MODE_SAFARI_ZONE_KEY:
            self.wild_template = self.template_manager.load_grayscale("wild.png")
        elif self.mode_key == MODE_EGG_KEY:
            self.huh_template = self.template_manager.load_grayscale("huh.png")
        else:
            raise RuntimeError(f"Unsupported mode: {self.mode_name}")

    def load_state(self) -> None:
        state = self.state_manager.load(
            mode_key=self.mode_key,
            mode_name=self.mode_name,
            capture_region=self.capture_region,
            encounter_increment=self.encounter_increment,
        )
        self.counter = int(state["counter"])
        self.catch_counter = int(state["catch_counter"])
        self.cooldown_until = float(state["cooldown_until"])
        self.waiting_for_clear = bool(state["waiting_for_clear"])
        self.last_event = str(state["last_event"])
        self.last_event_at = state["last_event_at"]
        self.last_match_score = float(state["last_match_score"])
        self.last_catch_at_encounter = int(state["last_catch_at_encounter"])
        self.encounters_since_last_catch = int(state["encounters_since_last_catch"])

    def set_log_handler(self, handler: Optional[LogHandler]) -> None:
        self.log_handler = handler

    def set_status_handler(self, handler: Optional[StatusHandler]) -> None:
        self.status_handler = handler

    def _emit_log(self, level: str, message: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        payload = {"timestamp": timestamp, "level": level, "message": message}
        if self.log_handler is not None:
            self.log_handler(payload)
            return
        print(f"[{timestamp}] {message}")

    def log_debug(self, message: str) -> None:
        if self.verbose_debug or self.debug_once:
            self._emit_log("debug", message)

    def log_event(self, message: str) -> None:
        self._emit_log("info", message)

    def log_error(self, message: str) -> None:
        self._emit_log("error", message)

    def snapshot(self, *, status: str, error_message: str = "") -> CounterSnapshot:
        return CounterSnapshot(
            status=status,
            mode_key=self.mode_key,
            mode_name=self.mode_name,
            encounter_increment=self.encounter_increment,
            counter=self.counter,
            catch_counter=self.catch_counter,
            last_event=self.last_event,
            last_event_at=self.last_event_at,
            last_match_score=self.last_match_score,
            last_catch_at_encounter=self.last_catch_at_encounter,
            encounters_since_last_catch=self.encounters_since_last_catch,
            capture_region=dict(self.capture_region),
            waiting_for_clear=self.waiting_for_clear,
            cooldown_until=self.cooldown_until,
            frame_index=self.frame_index,
            error_message=error_message,
        )

    def emit_status(self, *, status: str, error_message: str = "") -> None:
        if self.status_handler is not None:
            self.status_handler(self.snapshot(status=status, error_message=error_message).as_dict())

    def save_state(self, *, status: str) -> None:
        self.state_manager.save(self.snapshot(status=status))

    def now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def build_event_payload(self, event_name: str, score: float) -> dict[str, object]:
        return {
            "timestamp": self.now_iso(),
            "event": event_name,
            "counter": self.counter,
            "catch_counter": self.catch_counter,
            "encounter_increment": self.encounter_increment,
            "last_event": self.last_event,
            "last_event_at": self.last_event_at or "",
            "last_match_score": round(float(score), 6),
            "last_catch_at_encounter": self.last_catch_at_encounter,
            "encounters_since_last_catch": self.encounters_since_last_catch,
            "capture_top": self.capture_region["top"],
            "capture_left": self.capture_region["left"],
            "capture_width": self.capture_region["width"],
            "capture_height": self.capture_region["height"],
        }

    def append_event_log(self, event_name: str, score: float) -> None:
        self.event_logger.append(self.build_event_payload(event_name, score))

    def screenshot_region(self) -> np.ndarray:
        frame_bgr = grab_region(self.capture_region)
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        stats = compute_brightness_stats(gray)
        self.frame_index += 1

        self.log_debug(
            "Capture stats: "
            f"shape={frame_bgr.shape}, min={stats.min_value}, max={stats.max_value}, "
            f"mean={stats.mean_value:.2f}, std={stats.std_value:.2f}, "
            f"nonzero_ratio={stats.nonzero_ratio:.4f}"
        )

        if self.save_debug_frames and (self.frame_index % DEBUG_SAVE_EVERY_N_FRAMES == 0):
            save_image(DEBUG_FRAME_FILE, frame_bgr)

        if is_nearly_black(stats):
            now = time.time()
            if (now - self.last_black_frame_warning_time) >= BLACK_FRAME_WARNING_COOLDOWN_SECONDS:
                self.last_black_frame_warning_time = now
                self.log_debug(
                    "[WARN] Capture is black or nearly black. Possible causes: wrong monitor/region, "
                    "OBS preview on another monitor, minimized window, protected or hardware-accelerated content."
                )

        return gray

    def match_template(self, image: np.ndarray, template: np.ndarray, threshold: float) -> MatchResult:
        result = cv2.matchTemplate(image, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        return MatchResult(found=max_val >= threshold, score=float(max_val), location=max_loc)

    def in_cooldown(self) -> bool:
        return time.time() < self.cooldown_until

    def start_cooldown(self) -> None:
        self.cooldown_until = time.time() + POST_DETECTION_COOLDOWN_SECONDS
        self.waiting_for_clear = True
        self.save_state(status="Running")
        self.log_debug(f"Cooldown started for {POST_DETECTION_COOLDOWN_SECONDS:.1f} seconds.")

    def _calculate_encounters_since_last_catch(self) -> int:
        if self.last_catch_at_encounter > 0:
            return max(0, self.counter - self.last_catch_at_encounter)
        return self.counter

    def record_got_away(self, score: float) -> None:
        self.counter += self.encounter_increment
        self.last_event = "got_away"
        self.last_event_at = self.now_iso()
        self.last_match_score = score
        self.encounters_since_last_catch = self._calculate_encounters_since_last_catch()
        self.save_state(status="Running")
        self.append_event_log("got_away", score)
        self.log_event(
            f"GOT_AWAY | +{self.encounter_increment} encounters={self.counter} "
            f"catches={self.catch_counter} since_last_catch={self.encounters_since_last_catch} "
            f"score={score:.3f}"
        )

    def record_gotcha(self, score: float) -> None:
        self.counter += self.encounter_increment
        self.catch_counter += 1
        self.last_catch_at_encounter = self.counter
        self.encounters_since_last_catch = 0
        self.last_event = "gotcha"
        self.last_event_at = self.now_iso()
        self.last_match_score = score
        self.save_state(status="Running")
        self.append_event_log("gotcha", score)
        self.log_event(
            f"GOTCHA | +{self.encounter_increment} encounters={self.counter} "
            f"catches={self.catch_counter} score={score:.3f}"
        )

    def record_wild(self, score: float) -> None:
        self.counter += self.encounter_increment
        self.last_event = "wild"
        self.last_event_at = self.now_iso()
        self.last_match_score = score
        self.encounters_since_last_catch = self._calculate_encounters_since_last_catch()
        self.save_state(status="Running")
        self.append_event_log("wild", score)
        self.log_event(f"WILD | +{self.encounter_increment} encounters={self.counter} score={score:.3f}")

    def record_huh(self, score: float) -> None:
        self.counter += self.encounter_increment
        self.last_event = "huh"
        self.last_event_at = self.now_iso()
        self.last_match_score = score
        self.encounters_since_last_catch = self._calculate_encounters_since_last_catch()
        self.save_state(status="Running")
        self.append_event_log("huh", score)
        self.log_event(f"HUH | +{self.encounter_increment} encounters={self.counter} score={score:.3f}")

    def handle_random_grass_frame(self, gray_frame: np.ndarray) -> None:
        if self.got_away_template is None or self.gotcha_template is None:
            raise RuntimeError("Random grass templates are not loaded.")

        got_away_match = self.match_template(gray_frame, self.got_away_template, ESCAPE_THRESHOLD)
        gotcha_match = self.match_template(gray_frame, self.gotcha_template, GOTCHA_THRESHOLD)

        should_log_preview = self.verbose_debug and (
            self.frame_index - self.last_match_log_frame >= MATCH_LOG_EVERY_N_FRAMES
            or got_away_match.score >= PREVIEW_MATCH_THRESHOLD
            or gotcha_match.score >= PREVIEW_MATCH_THRESHOLD
        )

        if should_log_preview:
            self.last_match_log_frame = self.frame_index
            cooldown_remaining = max(0.0, self.cooldown_until - time.time())
            self.log_debug(
                "Match score: "
                f"got_away={got_away_match.score:.3f} (found={got_away_match.found}), "
                f"gotcha={gotcha_match.score:.3f} (found={gotcha_match.found}), "
                f"cooldown_remaining={cooldown_remaining:.2f}s, "
                f"waiting_for_clear={self.waiting_for_clear}"
            )

        if self.in_cooldown():
            return

        if self.waiting_for_clear:
            if not got_away_match.found and not gotcha_match.found:
                self.waiting_for_clear = False
                self.save_state(status="Running")
                self.log_debug("Battle result text cleared. Re-armed for next encounter.")
            return

        if got_away_match.found and gotcha_match.found:
            if gotcha_match.score >= got_away_match.score:
                self.record_gotcha(gotcha_match.score)
            else:
                self.record_got_away(got_away_match.score)
            self.start_cooldown()
            return

        if gotcha_match.found:
            self.record_gotcha(gotcha_match.score)
            self.start_cooldown()
            return

        if got_away_match.found:
            self.record_got_away(got_away_match.score)
            self.start_cooldown()

    def handle_safari_zone_frame(self, gray_frame: np.ndarray) -> None:
        if self.wild_template is None:
            raise RuntimeError("Safari Zone template is not loaded.")

        wild_match = self.match_template(gray_frame, self.wild_template, WILD_THRESHOLD)

        should_log_preview = self.verbose_debug and (
            self.frame_index - self.last_match_log_frame >= MATCH_LOG_EVERY_N_FRAMES
            or wild_match.score >= PREVIEW_MATCH_THRESHOLD
        )

        if should_log_preview:
            self.last_match_log_frame = self.frame_index
            cooldown_remaining = max(0.0, self.cooldown_until - time.time())
            self.log_debug(
                "Match score: "
                f"wild={wild_match.score:.3f} (found={wild_match.found}), "
                f"cooldown_remaining={cooldown_remaining:.2f}s, "
                f"waiting_for_clear={self.waiting_for_clear}"
            )

        if self.in_cooldown():
            return

        if self.waiting_for_clear:
            if not wild_match.found:
                self.waiting_for_clear = False
                self.save_state(status="Running")
                self.log_debug("Wild text cleared. Re-armed for next Safari encounter.")
            return

        if wild_match.found:
            self.record_wild(wild_match.score)
            self.start_cooldown()

    def handle_egg_frame(self, gray_frame: np.ndarray) -> None:
        if self.huh_template is None:
            raise RuntimeError("Egg template is not loaded.")

        huh_match = self.match_template(gray_frame, self.huh_template, HUH_THRESHOLD)

        should_log_preview = self.verbose_debug and (
            self.frame_index - self.last_match_log_frame >= MATCH_LOG_EVERY_N_FRAMES
            or huh_match.score >= PREVIEW_MATCH_THRESHOLD
        )

        if should_log_preview:
            self.last_match_log_frame = self.frame_index
            cooldown_remaining = max(0.0, self.cooldown_until - time.time())
            self.log_debug(
                "Match score: "
                f"huh={huh_match.score:.3f} (found={huh_match.found}), "
                f"cooldown_remaining={cooldown_remaining:.2f}s, "
                f"waiting_for_clear={self.waiting_for_clear}"
            )

        if self.in_cooldown():
            return

        if self.waiting_for_clear:
            if not huh_match.found:
                self.waiting_for_clear = False
                self.save_state(status="Running")
                self.log_debug("Huh text cleared. Re-armed for next egg encounter.")
            return

        if huh_match.found:
            self.record_huh(huh_match.score)
            self.start_cooldown()

    def handle_frame(self, gray_frame: np.ndarray) -> None:
        if self.mode_key == MODE_RANDOM_GRASS_KEY:
            self.handle_random_grass_frame(gray_frame)
        elif self.mode_key == MODE_SAFARI_ZONE_KEY:
            self.handle_safari_zone_frame(gray_frame)
        elif self.mode_key == MODE_EGG_KEY:
            self.handle_egg_frame(gray_frame)
        else:
            raise RuntimeError(f"Unsupported mode: {self.mode_name}")

    def run(
        self,
        *,
        stop_requested: Optional[StopRequested] = None,
        status_handler: Optional[StatusHandler] = None,
        log_handler: Optional[LogHandler] = None,
    ) -> None:
        if status_handler is not None:
            self.set_status_handler(status_handler)
        if log_handler is not None:
            self.set_log_handler(log_handler)

        should_stop = stop_requested or (lambda: False)

        if self.debug_once:
            self.log_debug("Running single debug capture.")
            self.log_debug(f"Capture region: {self.capture_region}")
            self.screenshot_region()
            self.log_debug(f"Saved debug frame to: {DEBUG_FRAME_FILE}")
            self.save_state(status="Stopped")
            self.emit_status(status="Stopped")
            return

        self.emit_status(status="Running")
        self.log_debug(f"Mode: {self.mode_name}")
        self.log_debug(f"Encounter increment: {self.encounter_increment}")
        self.log_debug(f"Current encounters: {self.counter}")
        self.log_debug(f"Current catches: {self.catch_counter}")
        self.log_debug(f"Capture region: {self.capture_region}")
        self.log_debug("Press Ctrl+C to stop. On Windows, Ctrl+Break also works.")

        while self.running and not should_stop():
            try:
                frame = self.screenshot_region()
                self.handle_frame(frame)
                self.emit_status(status="Running")
                time.sleep(SCAN_INTERVAL_SECONDS)
            except KeyboardInterrupt:
                self.stop(status="Stopped")
            except Exception as exc:
                self.log_error(f"[ERROR] {exc}")
                self.emit_status(status="Error", error_message=str(exc))
                time.sleep(1)

        self.stop(status="Stopped")
        self.emit_status(status="Stopped")

    def stop(self, *, status: str = "Stopped") -> None:
        self.running = False
        self.save_state(status=status)
        self.log_debug("State saved. Exiting.")
