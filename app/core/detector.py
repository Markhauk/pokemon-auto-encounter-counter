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
    MATCH_LOG_EVERY_N_FRAMES,
    PREVIEW_MATCH_THRESHOLD,
    SAVE_DEBUG_FRAMES,
    SCAN_INTERVAL_SECONDS,
)
from .event_logger import EventLogger
from .filters import (
    EVENT_TYPE_CATCH,
    EVENT_TYPE_ENCOUNTER_START,
    EVENT_TYPE_FLED,
    EVENT_TYPE_INFO,
    EVENT_TYPE_LABEL,
    FilterDefinition,
    build_legacy_mode_filters,
)
from .models import CounterSnapshot, FilterRuntimeState, MatchResult
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
        filters: Optional[list[FilterDefinition]] = None,
        capture_region: Optional[dict[str, int]] = None,
        save_debug_frames: bool = SAVE_DEBUG_FRAMES,
        debug_once: bool = False,
        verbose_debug: bool = False,
        mode_key: str = "filters",
        encounter_increment: int = 1,
        state_manager: Optional[StateManager] = None,
        event_logger: Optional[EventLogger] = None,
        template_manager: Optional[TemplateManager] = None,
        log_handler: Optional[LogHandler] = None,
        status_handler: Optional[StatusHandler] = None,
    ) -> None:
        self.running = True
        self.mode_key = mode_key if filters is None else "filters"
        self.mode_name = "Filter scan" if filters is not None else mode_key
        self.encounter_increment = max(1, int(encounter_increment))

        self.counter = 0
        self.catch_counter = 0

        self.last_event = "none"
        self.last_event_at: Optional[str] = None
        self.last_match_score = 0.0
        self.last_filter_id = ""
        self.last_filter_name = ""
        self.last_filter_event_type = ""
        self.active_label = ""

        self.last_catch_at_encounter = 0
        self.encounters_since_last_catch = 0

        self.save_debug_frames = save_debug_frames
        self.debug_once = debug_once
        self.verbose_debug = verbose_debug
        self.last_black_frame_warning_time = 0.0
        self.frame_index = 0
        self.last_match_log_frame = 0

        self.state_manager = state_manager or StateManager()
        self.event_logger = event_logger or EventLogger()
        self.template_manager = template_manager or TemplateManager()
        self.log_handler = log_handler
        self.status_handler = status_handler

        configured_filters = list(filters or [])
        if not configured_filters and capture_region is not None:
            configured_filters = build_legacy_mode_filters(
                mode_key=mode_key,
                capture_region=capture_region,
            )
            self.mode_name = mode_key.replace("_", " ").title()

        self.filters = configured_filters
        self.enabled_filters = [filter_definition for filter_definition in self.filters if filter_definition.enabled]
        self.capture_region = (
            dict(self.enabled_filters[0].capture_region) if self.enabled_filters else dict(capture_region or {})
        )

        self.loaded_templates: dict[str, np.ndarray] = {}
        self.filter_runtime: dict[str, FilterRuntimeState] = {}

        self.state_manager.ensure_directories()
        self.template_manager.ensure_directory()
        self.event_logger.ensure_files()
        self.load_state()
        self.load_mode_templates()
        self.save_state(status="Idle")

    def load_mode_templates(self) -> None:
        self.loaded_templates = {}
        self.enabled_filters = [filter_definition for filter_definition in self.filters if filter_definition.enabled]
        for filter_definition in self.enabled_filters:
            self.loaded_templates[filter_definition.id] = self.template_manager.load_grayscale(
                filter_definition.template_path
            )
            self.filter_runtime.setdefault(filter_definition.id, FilterRuntimeState())

    def load_state(self) -> None:
        state = self.state_manager.load(
            mode_key=self.mode_key,
            mode_name=self.mode_name,
            capture_region=self.capture_region,
            encounter_increment=self.encounter_increment,
        )
        self.counter = int(state["counter"])
        self.catch_counter = int(state["catch_counter"])
        self.last_event = str(state["last_event"])
        self.last_event_at = state["last_event_at"]
        self.last_match_score = float(state["last_match_score"])
        self.last_filter_id = str(state.get("last_filter_id", ""))
        self.last_filter_name = str(state.get("last_filter_name", ""))
        self.last_filter_event_type = str(state.get("last_filter_event_type", ""))
        self.active_label = str(state.get("active_label", ""))
        self.last_catch_at_encounter = int(state["last_catch_at_encounter"])
        self.encounters_since_last_catch = int(state["encounters_since_last_catch"])

        filters_runtime = state.get("filters_runtime", {})
        if isinstance(filters_runtime, dict):
            for filter_id, raw_runtime in filters_runtime.items():
                if not isinstance(raw_runtime, dict):
                    continue
                self.filter_runtime[str(filter_id)] = FilterRuntimeState(
                    cooldown_until=float(raw_runtime.get("cooldown_until", 0.0)),
                    waiting_for_clear=bool(raw_runtime.get("waiting_for_clear", False)),
                    last_match_score=float(raw_runtime.get("last_match_score", 0.0)),
                    last_event_at=raw_runtime.get("last_event_at"),
                )

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
        representative_region = None
        if self.last_filter_id:
            matching_filter = next(
                (filter_definition for filter_definition in self.filters if filter_definition.id == self.last_filter_id),
                None,
            )
            if matching_filter is not None:
                representative_region = dict(matching_filter.capture_region)
        elif self.enabled_filters:
            representative_region = dict(self.enabled_filters[0].capture_region)

        first_runtime = next(iter(self.filter_runtime.values()), FilterRuntimeState())

        return CounterSnapshot(
            status=status,
            mode_key="filters",
            mode_name="Filter scan",
            encounter_increment=self.encounter_increment,
            enabled_filter_count=len(self.enabled_filters),
            counter=self.counter,
            catch_counter=self.catch_counter,
            last_event=self.last_event,
            last_event_at=self.last_event_at,
            last_match_score=self.last_match_score,
            last_filter_id=self.last_filter_id,
            last_filter_name=self.last_filter_name,
            last_filter_event_type=self.last_filter_event_type,
            active_label=self.active_label,
            last_catch_at_encounter=self.last_catch_at_encounter,
            encounters_since_last_catch=self.encounters_since_last_catch,
            capture_region=representative_region,
            waiting_for_clear=first_runtime.waiting_for_clear,
            cooldown_until=first_runtime.cooldown_until,
            frame_index=self.frame_index,
            filters_runtime={
                filter_id: runtime_state.as_dict()
                for filter_id, runtime_state in self.filter_runtime.items()
            },
            error_message=error_message,
        )

    def emit_status(self, *, status: str, error_message: str = "") -> None:
        if self.status_handler is not None:
            self.status_handler(self.snapshot(status=status, error_message=error_message).as_dict())

    def save_state(self, *, status: str) -> None:
        self.state_manager.save(self.snapshot(status=status))

    def now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def build_event_payload(self, filter_definition: FilterDefinition, score: float) -> dict[str, object]:
        return {
            "timestamp": self.now_iso(),
            "event": filter_definition.event_type,
            "filter_id": filter_definition.id,
            "filter_name": filter_definition.name,
            "filter_event_type": filter_definition.event_type,
            "filter_threshold": filter_definition.threshold,
            "filter_cooldown_seconds": filter_definition.cooldown_seconds,
            "template_path": str(self.template_manager.get_path(filter_definition.template_path)),
            "active_label": self.active_label,
            "counter": self.counter,
            "catch_counter": self.catch_counter,
            "encounter_increment": self.encounter_increment,
            "last_event": self.last_event,
            "last_event_at": self.last_event_at or "",
            "last_match_score": round(float(score), 6),
            "last_catch_at_encounter": self.last_catch_at_encounter,
            "encounters_since_last_catch": self.encounters_since_last_catch,
            "capture_top": filter_definition.capture_region["top"],
            "capture_left": filter_definition.capture_region["left"],
            "capture_width": filter_definition.capture_region["width"],
            "capture_height": filter_definition.capture_region["height"],
        }

    def append_event_log(self, filter_definition: FilterDefinition, score: float) -> None:
        self.event_logger.append(self.build_event_payload(filter_definition, score))

    def screenshot_region(self, filter_definition: FilterDefinition) -> np.ndarray:
        frame_bgr = grab_region(filter_definition.capture_region)
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        stats = compute_brightness_stats(gray)
        self.frame_index += 1

        self.log_debug(
            f"[{filter_definition.name}] Capture stats: "
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
                    f"[WARN] [{filter_definition.name}] Capture is black or nearly black. Possible causes: "
                    "wrong monitor or region, minimized window, OBS preview on another monitor, or protected content."
                )

        return gray

    def match_template(self, image: np.ndarray, template: np.ndarray, threshold: float) -> MatchResult:
        result = cv2.matchTemplate(image, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        return MatchResult(found=max_val >= threshold, score=float(max_val), location=max_loc)

    def _runtime_state_for(self, filter_id: str) -> FilterRuntimeState:
        return self.filter_runtime.setdefault(filter_id, FilterRuntimeState())

    def in_cooldown(self, filter_id: str) -> bool:
        return time.time() < self._runtime_state_for(filter_id).cooldown_until

    def start_cooldown(self, filter_definition: FilterDefinition) -> None:
        runtime_state = self._runtime_state_for(filter_definition.id)
        cooldown_seconds = max(0.0, float(filter_definition.cooldown_seconds))
        runtime_state.cooldown_until = time.time() + cooldown_seconds
        runtime_state.waiting_for_clear = True
        self.save_state(status="Running")
        self.log_debug(
            f"[{filter_definition.id}] Cooldown started for {cooldown_seconds:.1f} seconds."
        )

    def _calculate_encounters_since_last_catch(self) -> int:
        if self.last_catch_at_encounter > 0:
            return max(0, self.counter - self.last_catch_at_encounter)
        return self.counter

    def record_filter_event(self, filter_definition: FilterDefinition, score: float) -> None:
        event_type = filter_definition.event_type
        self.last_event = event_type
        self.last_event_at = self.now_iso()
        self.last_match_score = score
        self.last_filter_id = filter_definition.id
        self.last_filter_name = filter_definition.name
        self.last_filter_event_type = event_type

        if event_type == EVENT_TYPE_LABEL:
            self.active_label = filter_definition.name
        elif event_type == EVENT_TYPE_CATCH:
            self.counter += self.encounter_increment
            self.catch_counter += 1
            self.last_catch_at_encounter = self.counter
            self.encounters_since_last_catch = 0
        elif event_type in {EVENT_TYPE_ENCOUNTER_START, EVENT_TYPE_FLED}:
            self.counter += self.encounter_increment
            self.encounters_since_last_catch = self._calculate_encounters_since_last_catch()
        elif event_type == EVENT_TYPE_INFO:
            self.encounters_since_last_catch = self._calculate_encounters_since_last_catch()

        runtime_state = self._runtime_state_for(filter_definition.id)
        runtime_state.last_match_score = score
        runtime_state.last_event_at = self.last_event_at

        self.save_state(status="Running")
        self.append_event_log(filter_definition, score)
        self.log_event(self._build_runtime_message(filter_definition, score))

    def _build_runtime_message(self, filter_definition: FilterDefinition, score: float) -> str:
        prefix = f"{filter_definition.name.upper()} [{filter_definition.event_type}]"
        if filter_definition.event_type == EVENT_TYPE_CATCH:
            return (
                f"{prefix} | +{self.encounter_increment} encounters={self.counter} "
                f"catches={self.catch_counter} score={score:.3f}"
            )
        if filter_definition.event_type in {EVENT_TYPE_ENCOUNTER_START, EVENT_TYPE_FLED}:
            return (
                f"{prefix} | +{self.encounter_increment} encounters={self.counter} "
                f"catches={self.catch_counter} since_last_catch={self.encounters_since_last_catch} "
                f"score={score:.3f}"
            )
        if filter_definition.event_type == EVENT_TYPE_LABEL:
            return f"{prefix} | label={filter_definition.name} score={score:.3f}"
        return f"{prefix} | info score={score:.3f}"

    def evaluate_filter(self, filter_definition: FilterDefinition, gray_frame: np.ndarray) -> None:
        template = self.loaded_templates.get(filter_definition.id)
        if template is None:
            raise RuntimeError(f"Template for filter '{filter_definition.name}' is not loaded.")

        match_result = self.match_template(gray_frame, template, filter_definition.threshold)
        runtime_state = self._runtime_state_for(filter_definition.id)

        should_log_preview = self.verbose_debug and (
            self.frame_index - self.last_match_log_frame >= MATCH_LOG_EVERY_N_FRAMES
            or match_result.score >= PREVIEW_MATCH_THRESHOLD
        )
        if should_log_preview:
            self.last_match_log_frame = self.frame_index
            cooldown_remaining = max(0.0, runtime_state.cooldown_until - time.time())
            self.log_debug(
                f"[{filter_definition.name}] Match score={match_result.score:.3f} "
                f"(found={match_result.found}), cooldown_remaining={cooldown_remaining:.2f}s, "
                f"waiting_for_clear={runtime_state.waiting_for_clear}"
            )

        if self.in_cooldown(filter_definition.id):
            return

        if runtime_state.waiting_for_clear:
            if not match_result.found:
                runtime_state.waiting_for_clear = False
                self.save_state(status="Running")
                self.log_debug(f"[{filter_definition.name}] Template cleared. Re-armed for the next match.")
            return

        if match_result.found:
            self.record_filter_event(filter_definition, match_result.score)
            self.start_cooldown(filter_definition)

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

        if self.debug_once and self.enabled_filters:
            selected_filter = self.enabled_filters[0]
            self.log_debug("Running single debug capture.")
            self.log_debug(
                f"Filter: {selected_filter.name} | region={selected_filter.capture_region}"
            )
            self.screenshot_region(selected_filter)
            self.log_debug(f"Saved debug frame to: {DEBUG_FRAME_FILE}")
            self.save_state(status="Stopped")
            self.emit_status(status="Stopped")
            return

        if not self.enabled_filters:
            raise RuntimeError("No enabled filters are available for scanning.")

        self.emit_status(status="Running")
        self.log_debug(f"Enabled filters: {len(self.enabled_filters)}")
        self.log_debug(f"Encounter increment: {self.encounter_increment}")
        self.log_debug(f"Current encounters: {self.counter}")
        self.log_debug(f"Current catches: {self.catch_counter}")
        self.log_debug("Press Ctrl+C to stop. On Windows, Ctrl+Break also works.")

        while self.running and not should_stop():
            try:
                for filter_definition in self.enabled_filters:
                    gray_frame = self.screenshot_region(filter_definition)
                    self.evaluate_filter(filter_definition, gray_frame)
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
