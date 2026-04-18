import argparse
import csv
import json
import os
import signal
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

import cv2
import mss
import numpy as np


BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
OUTPUT_DIR = BASE_DIR / "output"

COUNTER_FILE = OUTPUT_DIR / "counter.txt"
STATE_FILE = OUTPUT_DIR / "state.json"
LOCK_FILE = OUTPUT_DIR / "encounter_counter.lock"
DEBUG_FRAME_FILE = OUTPUT_DIR / "last_capture.png"

ENCOUNTER_LOG_CSV_FILE = OUTPUT_DIR / "encounter_log.csv"
EVENT_LOG_JSONL_FILE = OUTPUT_DIR / "event_log.jsonl"

RANDOM_GRASS_CAPTURE_REGION = {
    "top": 1060,
    "left": 282,
    "width": 935,
    "height": 132,
}

SAFARI_ZONE_CAPTURE_REGION = {
    "top": 1060,
    "left": 282,
    "width": 253,
    "height": 132,
}

BLACK_FRAME_WARNING_COOLDOWN_SECONDS = 1000.0
SCAN_INTERVAL_SECONDS = 0.10
ESCAPE_THRESHOLD = 0.85
GOTCHA_THRESHOLD = 0.85
WILD_THRESHOLD = 0.85
POST_DETECTION_COOLDOWN_SECONDS = 5.0
SAVE_DEBUG_FRAMES = False
DEBUG_SAVE_EVERY_N_FRAMES = 1
MATCH_LOG_EVERY_N_FRAMES = 5
PREVIEW_MATCH_THRESHOLD = 0.60
NEAR_BLACK_MEAN_THRESHOLD = 5.0
NEAR_BLACK_MAX_THRESHOLD = 20

MODE_RANDOM_GRASS = "Random grass encounter"
MODE_SAFARI_ZONE = "Safari zone"

EVENT_LOG_CSV_FIELDS = [
    "timestamp",
    "event",
    "counter",
    "catch_counter",
    "last_event",
    "last_event_at",
    "last_match_score",
    "last_catch_at_encounter",
    "encounters_since_last_catch",
    "capture_top",
    "capture_left",
    "capture_width",
    "capture_height",
]


@dataclass
class MatchResult:
    found: bool
    score: float
    location: Optional[Tuple[int, int]] = None


@dataclass
class BrightnessStats:
    min_value: int
    max_value: int
    mean_value: float
    std_value: float
    nonzero_ratio: float


class SingleInstanceGuard:
    def __init__(self, lock_file: Path) -> None:
        self.lock_file = lock_file
        self.handle = None

    def __enter__(self) -> "SingleInstanceGuard":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        self.release()

    def acquire(self) -> None:
        self.lock_file.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.lock_file.open("a+", encoding="utf-8")

        try:
            self.handle.seek(0)
            self.handle.write(" ")
            self.handle.flush()
            self.handle.seek(0)

            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            other_pid = self._read_existing_pid()
            self.handle.close()
            self.handle = None
            pid_suffix = f" (PID {other_pid})" if other_pid else ""
            raise RuntimeError(f"Another copy of run.py is already running{pid_suffix}.")

        self.handle.seek(0)
        self.handle.truncate()
        self.handle.write(str(os.getpid()))
        self.handle.flush()

    def release(self) -> None:
        if self.handle is None:
            return

        try:
            self.handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        finally:
            self.handle.close()
            self.handle = None
            try:
                self.lock_file.unlink()
            except OSError:
                pass

    def _read_existing_pid(self) -> Optional[str]:
        try:
            pid = self.lock_file.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        return pid or None


def get_default_capture_region(mode_name: str) -> dict[str, int]:
    if mode_name == MODE_SAFARI_ZONE:
        return dict(SAFARI_ZONE_CAPTURE_REGION)
    return dict(RANDOM_GRASS_CAPTURE_REGION)


class EncounterCounter:
    def __init__(
        self,
        *,
        capture_region: Optional[dict[str, int]] = None,
        save_debug_frames: bool = SAVE_DEBUG_FRAMES,
        debug_once: bool = False,
        verbose_debug: bool = False,
        mode_name: str = MODE_RANDOM_GRASS,
    ) -> None:
        self.running = True
        self.mode_name = mode_name

        self.counter = 0
        self.catch_counter = 0

        self.last_event = "none"
        self.last_event_at: Optional[str] = None
        self.last_match_score = 0.0

        self.last_catch_at_encounter = 0
        self.encounters_since_last_catch = 0

        self.capture_region = dict(capture_region or get_default_capture_region(mode_name))
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

        self.ensure_directories()
        self.ensure_log_files()
        self.load_state()
        self.save_state()

        if not self.debug_once:
            self.load_mode_templates()

    def ensure_directories(self) -> None:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

    def ensure_log_files(self) -> None:
        if not ENCOUNTER_LOG_CSV_FILE.exists() or ENCOUNTER_LOG_CSV_FILE.stat().st_size == 0:
            with ENCOUNTER_LOG_CSV_FILE.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=EVENT_LOG_CSV_FIELDS)
                writer.writeheader()

        if not EVENT_LOG_JSONL_FILE.exists():
            EVENT_LOG_JSONL_FILE.write_text("", encoding="utf-8")

    def _print(self, message: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        print(f"[{timestamp}] {message}")

    def log_debug(self, message: str) -> None:
        if self.verbose_debug or self.debug_once:
            self._print(message)

    def log_event(self, message: str) -> None:
        self._print(message)

    def log_error(self, message: str) -> None:
        self._print(message)

    def load_template(self, filename: str) -> np.ndarray:
        path = TEMPLATES_DIR / filename
        if not path.exists():
            self.log_error(f"[ERROR] Missing template: {path}")
            self.log_error("Create the template image and try again.")
            sys.exit(1)

        template = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if template is None:
            self.log_error(f"[ERROR] Failed to load template: {path}")
            sys.exit(1)
        return template

    def load_mode_templates(self) -> None:
        if self.mode_name == MODE_RANDOM_GRASS:
            self.got_away_template = self.load_template("got_away.png")
            self.gotcha_template = self.load_template("gotcha.png")
        elif self.mode_name == MODE_SAFARI_ZONE:
            self.wild_template = self.load_template("wild.png")
        else:
            raise RuntimeError(f"Unsupported mode: {self.mode_name}")

    def load_state(self) -> None:
        if COUNTER_FILE.exists():
            try:
                self.counter = int(COUNTER_FILE.read_text(encoding="utf-8").strip())
            except ValueError:
                self.log_error("[WARN] counter.txt was invalid. Starting from 0.")
                self.counter = 0

        if STATE_FILE.exists():
            try:
                data = json.loads(STATE_FILE.read_text(encoding="utf-8"))

                self.counter = int(data.get("counter", self.counter))
                self.catch_counter = int(data.get("catch_counter", 0))
                self.cooldown_until = float(data.get("cooldown_until", 0.0))
                self.waiting_for_clear = bool(data.get("waiting_for_clear", False))

                self.last_event = str(data.get("last_event", "none"))
                self.last_event_at = data.get("last_event_at")
                self.last_match_score = float(data.get("last_match_score", 0.0))

                self.last_catch_at_encounter = int(data.get("last_catch_at_encounter", 0))
                self.encounters_since_last_catch = int(
                    data.get("encounters_since_last_catch", 0)
                )

            except (json.JSONDecodeError, ValueError, TypeError):
                self.log_error("[WARN] state.json was invalid. Using defaults.")

        if self.last_catch_at_encounter > 0:
            self.encounters_since_last_catch = max(
                0, self.counter - self.last_catch_at_encounter
            )

    def save_state(self) -> None:
        COUNTER_FILE.write_text(str(self.counter), encoding="utf-8")
        STATE_FILE.write_text(
            json.dumps(
                {
                    "counter": self.counter,
                    "catch_counter": self.catch_counter,
                    "cooldown_until": self.cooldown_until,
                    "waiting_for_clear": self.waiting_for_clear,
                    "last_event": self.last_event,
                    "last_event_at": self.last_event_at,
                    "last_match_score": self.last_match_score,
                    "last_catch_at_encounter": self.last_catch_at_encounter,
                    "encounters_since_last_catch": self.encounters_since_last_catch,
                    "capture_region": self.capture_region,
                    "mode_name": self.mode_name,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    def now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def build_event_payload(self, event_name: str, score: float) -> dict[str, object]:
        return {
            "timestamp": self.now_iso(),
            "event": event_name,
            "counter": self.counter,
            "catch_counter": self.catch_counter,
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
        payload = self.build_event_payload(event_name, score)

        with ENCOUNTER_LOG_CSV_FILE.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=EVENT_LOG_CSV_FIELDS)
            writer.writerow(payload)

        with EVENT_LOG_JSONL_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def screenshot_region(self) -> np.ndarray:
        with mss.mss() as sct:
            shot = sct.grab(self.capture_region)
            frame = np.array(shot)
            frame_bgr = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
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
                try:
                    save_image(DEBUG_FRAME_FILE, frame_bgr)
                except RuntimeError:
                    self.log_debug(f"[WARN] Failed to save debug frame to: {DEBUG_FRAME_FILE}")

            if is_nearly_black(stats):
                now = time.time()
                if (now - self.last_black_frame_warning_time) >= BLACK_FRAME_WARNING_COOLDOWN_SECONDS:
                    self.last_black_frame_warning_time = now
                    self.log_debug(
                        "[WARN] Capture is black or nearly black. Possible causes: wrong monitor/region, "
                        "OBS preview on another monitor, minimized window, protected/hardware-accelerated content."
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
        self.save_state()
        self.log_debug(f"Cooldown started for {POST_DETECTION_COOLDOWN_SECONDS:.1f} seconds.")

    def record_got_away(self, score: float) -> None:
        self.counter += 1
        self.last_event = "got_away"
        self.last_event_at = self.now_iso()
        self.last_match_score = score

        if self.last_catch_at_encounter > 0:
            self.encounters_since_last_catch = self.counter - self.last_catch_at_encounter
        else:
            self.encounters_since_last_catch = self.counter

        self.save_state()
        self.append_event_log("got_away", score)

        self.log_event(
            f"GOT_AWAY | encounters={self.counter} catches={self.catch_counter} "
            f"since_last_catch={self.encounters_since_last_catch} score={score:.3f}"
        )

    def record_gotcha(self, score: float) -> None:
        self.counter += 1
        self.catch_counter += 1
        self.last_catch_at_encounter = self.counter
        self.encounters_since_last_catch = 0
        self.last_event = "gotcha"
        self.last_event_at = self.now_iso()
        self.last_match_score = score

        self.save_state()
        self.append_event_log("gotcha", score)

        self.log_event(
            f"GOTCHA | encounters={self.counter} catches={self.catch_counter} "
            f"since_last_catch={self.encounters_since_last_catch} score={score:.3f}"
        )

    def record_wild(self, score: float) -> None:
        self.counter += 1
        self.last_event = "wild"
        self.last_event_at = self.now_iso()
        self.last_match_score = score

        if self.last_catch_at_encounter > 0:
            self.encounters_since_last_catch = self.counter - self.last_catch_at_encounter
        else:
            self.encounters_since_last_catch = self.counter

        self.save_state()
        self.append_event_log("wild", score)

        self.log_event(f"WILD | encounters={self.counter} score={score:.3f}")

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
                f"got_away={got_away_match.score:.3f} "
                f"(found={got_away_match.found}), "
                f"gotcha={gotcha_match.score:.3f} "
                f"(found={gotcha_match.found}), "
                f"cooldown_remaining={cooldown_remaining:.2f}s, "
                f"waiting_for_clear={self.waiting_for_clear}"
            )

        if self.in_cooldown():
            return

        if self.waiting_for_clear:
            if not got_away_match.found and not gotcha_match.found:
                self.waiting_for_clear = False
                self.save_state()
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
                f"wild={wild_match.score:.3f} "
                f"(found={wild_match.found}), "
                f"cooldown_remaining={cooldown_remaining:.2f}s, "
                f"waiting_for_clear={self.waiting_for_clear}"
            )

        if self.in_cooldown():
            return

        if self.waiting_for_clear:
            if not wild_match.found:
                self.waiting_for_clear = False
                self.save_state()
                self.log_debug("Wild text cleared. Re-armed for next Safari encounter.")
            return

        if wild_match.found:
            self.record_wild(wild_match.score)
            self.start_cooldown()

    def handle_frame(self, gray_frame: np.ndarray) -> None:
        if self.mode_name == MODE_RANDOM_GRASS:
            self.handle_random_grass_frame(gray_frame)
        elif self.mode_name == MODE_SAFARI_ZONE:
            self.handle_safari_zone_frame(gray_frame)
        else:
            raise RuntimeError(f"Unsupported mode: {self.mode_name}")

    def run(self) -> None:
        if self.debug_once:
            self.log_debug("Running single debug capture.")
            self.log_debug(f"Capture region: {self.capture_region}")
            self.screenshot_region()
            self.log_debug(f"Saved debug frame to: {DEBUG_FRAME_FILE}")
            return

        self.log_debug(f"Mode: {self.mode_name}")
        self.log_debug(f"Current encounters: {self.counter}")
        self.log_debug(f"Current catches: {self.catch_counter}")
        self.log_debug(f"Capture region: {self.capture_region}")
        self.log_debug(f"CSV log: {ENCOUNTER_LOG_CSV_FILE}")
        self.log_debug(f"JSONL log: {EVENT_LOG_JSONL_FILE}")
        self.log_debug("Press Ctrl+C to stop. On Windows, Ctrl+Break also works.")

        while self.running:
            try:
                frame = self.screenshot_region()
                self.handle_frame(frame)
                time.sleep(SCAN_INTERVAL_SECONDS)
            except KeyboardInterrupt:
                self.stop()
            except Exception as exc:
                self.log_error(f"[ERROR] {exc}")
                time.sleep(1)

    def stop(self) -> None:
        self.running = False
        self.save_state()
        self.log_debug("State saved. Exiting.")


def handle_shutdown(counter: EncounterCounter, signum, frame) -> None:  # type: ignore[no-untyped-def]
    counter.log_debug(f"Received signal {signum}. Shutting down.")
    counter.stop()
    sys.exit(0)


def list_monitors() -> None:
    with mss.mss() as sct:
        print("Detected monitor regions:")
        for index, monitor in enumerate(sct.monitors):
            label = "all monitors" if index == 0 else f"monitor {index}"
            print(f"  {index}: {label} -> {monitor}")


def compute_brightness_stats(gray_image: np.ndarray) -> BrightnessStats:
    return BrightnessStats(
        min_value=int(np.min(gray_image)),
        max_value=int(np.max(gray_image)),
        mean_value=float(np.mean(gray_image)),
        std_value=float(np.std(gray_image)),
        nonzero_ratio=float(np.count_nonzero(gray_image) / gray_image.size),
    )


def is_nearly_black(stats: BrightnessStats) -> bool:
    return stats.mean_value <= NEAR_BLACK_MEAN_THRESHOLD and stats.max_value <= NEAR_BLACK_MAX_THRESHOLD


def save_image(path: Path, frame_bgr: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp.png")
    if not cv2.imwrite(str(tmp_path), frame_bgr):
        raise RuntimeError(f"Failed to save image to {tmp_path}")
    tmp_path.replace(path)


def grab_region(region: dict[str, int]) -> np.ndarray:
    with mss.mss() as sct:
        shot = sct.grab(region)
    frame = np.array(shot)
    return cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)


def save_all_monitors() -> None:
    with mss.mss() as sct:
        for index, monitor in enumerate(sct.monitors[1:], start=1):
            frame_bgr = grab_region(monitor)
            out_path = OUTPUT_DIR / f"monitor_{index}.png"
            save_image(out_path, frame_bgr)
            gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
            stats = compute_brightness_stats(gray)
            print(f"Saved {out_path} -> region={monitor}, mean={stats.mean_value:.2f}, max={stats.max_value}")


def save_monitor(index: int) -> None:
    with mss.mss() as sct:
        if index < 1 or index >= len(sct.monitors):
            raise ValueError(f"Monitor index {index} is out of range. Use --list-monitors first.")
        region = sct.monitors[index]

    frame_bgr = grab_region(region)
    out_path = OUTPUT_DIR / f"monitor_{index}.png"
    save_image(out_path, frame_bgr)
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    stats = compute_brightness_stats(gray)
    print(f"Saved {out_path} -> region={region}, mean={stats.mean_value:.2f}, max={stats.max_value}")


def resolve_capture_region(
    monitor_index: Optional[int],
    region_values: Optional[list[int]],
    monitor_region_values: Optional[list[int]],
    default_region: Optional[dict[str, int]] = None,
) -> dict[str, int]:
    if monitor_region_values is not None:
        monitor_idx, left, top, width, height = monitor_region_values
        if width <= 0 or height <= 0:
            raise ValueError("Monitor-relative region width and height must be greater than 0.")

        with mss.mss() as sct:
            if monitor_idx < 1 or monitor_idx >= len(sct.monitors):
                raise ValueError(f"Monitor index {monitor_idx} is out of range. Use --list-monitors first.")
            monitor = sct.monitors[monitor_idx]

        return {
            "left": monitor["left"] + left,
            "top": monitor["top"] + top,
            "width": width,
            "height": height,
        }

    if region_values is not None:
        left, top, width, height = region_values
        if width <= 0 or height <= 0:
            raise ValueError("Region width and height must be greater than 0.")
        return {"left": left, "top": top, "width": width, "height": height}

    if monitor_index is None:
        return dict(default_region or RANDOM_GRASS_CAPTURE_REGION)

    with mss.mss() as sct:
        if monitor_index < 1 or monitor_index >= len(sct.monitors):
            raise ValueError(
                f"Monitor index {monitor_index} is out of range. Run with --list-monitors to inspect valid values."
            )
        monitor = sct.monitors[monitor_index]
        return {
            "left": monitor["left"],
            "top": monitor["top"],
            "width": monitor["width"],
            "height": monitor["height"],
        }


def print_main_menu() -> None:
    print()
    print("=== Pokemon Counter Menu ===")
    print("1) Random grass encounter")
    print("2) Safari zone")
    print("3) Soft reset")
    print("4) Go back to screen settings (future plan)")
    print("Q) Quit")
    print()


def select_main_menu_option() -> str:
    while True:
        print_main_menu()
        choice = input("Select option: ").strip().lower()

        match choice:
            case "1" | "2" | "3" | "4" | "q" | "quit" | "exit":
                return choice
            case _:
                print("Invalid selection. Try again.")


def configure_signal_handlers(counter: EncounterCounter) -> None:
    signal.signal(signal.SIGINT, lambda s, f: handle_shutdown(counter, s, f))
    signal.signal(signal.SIGTERM, lambda s, f: handle_shutdown(counter, s, f))
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, lambda s, f: handle_shutdown(counter, s, f))


def run_random_grass_mode(
    *,
    args: argparse.Namespace,
) -> None:
    capture_region = resolve_capture_region(
        args.monitor,
        args.region,
        args.monitor_region,
        default_region=RANDOM_GRASS_CAPTURE_REGION,
    )

    with SingleInstanceGuard(LOCK_FILE):
        counter = EncounterCounter(
            capture_region=capture_region,
            save_debug_frames=args.debug or args.debug_once,
            debug_once=args.debug_once,
            verbose_debug=args.verbose_debug,
            mode_name=MODE_RANDOM_GRASS,
        )
        configure_signal_handlers(counter)
        counter.run()


def run_safari_zone_mode(
    *,
    args: argparse.Namespace,
) -> None:
    capture_region = resolve_capture_region(
        args.monitor,
        args.region,
        args.monitor_region,
        default_region=SAFARI_ZONE_CAPTURE_REGION,
    )

    with SingleInstanceGuard(LOCK_FILE):
        counter = EncounterCounter(
            capture_region=capture_region,
            save_debug_frames=args.debug or args.debug_once,
            debug_once=args.debug_once,
            verbose_debug=args.verbose_debug,
            mode_name=MODE_SAFARI_ZONE,
        )
        configure_signal_handlers(counter)
        counter.run()


def run_soft_reset_mode() -> None:
    print()
    print("[TODO] Soft reset mode is not implemented yet.")
    print("Planned: reset/session tracking flow.")
    print()


def run_screen_settings_menu() -> None:
    print()
    print("[TODO] Screen settings menu is not implemented yet.")
    print("Planned: interactive capture-region setup from inside the script.")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Pokemon encounter counter")
    parser.add_argument("--debug", action="store_true", help="Continuously update output/last_capture.png while running.")
    parser.add_argument("--debug-once", action="store_true", help="Capture one frame to output/last_capture.png and exit.")
    parser.add_argument("--verbose-debug", action="store_true", help="Print detailed image stats for each capture.")
    parser.add_argument("--list-monitors", action="store_true", help="Print detected monitor regions and exit.")
    parser.add_argument("--save-all-monitors", action="store_true", help="Save one screenshot for every monitor and exit.")
    parser.add_argument("--save-monitor", type=int, help="Save one screenshot for the selected full monitor and exit.")
    parser.add_argument("--monitor", type=int, help="Use an entire detected monitor as the capture region.")
    parser.add_argument(
        "--region",
        nargs=4,
        type=int,
        metavar=("LEFT", "TOP", "WIDTH", "HEIGHT"),
        help="Use explicit desktop coordinates as the capture region.",
    )
    parser.add_argument(
        "--monitor-region",
        nargs=5,
        type=int,
        metavar=("MONITOR", "LEFT", "TOP", "WIDTH", "HEIGHT"),
        help="Use coordinates relative to a selected monitor.",
    )
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.list_monitors:
        list_monitors()
        return

    try:
        if args.save_all_monitors:
            save_all_monitors()
            return

        if args.save_monitor is not None:
            save_monitor(args.save_monitor)
            return
    except ValueError as exc:
        print(f"[ERROR] {exc}")
        sys.exit(1)

    while True:
        choice = select_main_menu_option()

        try:
            match choice:
                case "1":
                    run_random_grass_mode(args=args)
                    return

                case "2":
                    run_safari_zone_mode(args=args)
                    return

                case "3":
                    run_soft_reset_mode()

                case "4":
                    run_screen_settings_menu()

                case "q" | "quit" | "exit":
                    print("Goodbye.")
                    return

        except RuntimeError as exc:
            print(f"[ERROR] {exc}")
            return
        except ValueError as exc:
            print(f"[ERROR] {exc}")
            return


if __name__ == "__main__":
    main()