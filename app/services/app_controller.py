from __future__ import annotations

import os
import subprocess
from typing import Optional

import cv2
from PySide6.QtCore import QObject, QThread, Signal

from app.core.capture import compute_brightness_stats, get_monitors, grab_region, save_image
from app.core.event_logger import EventLogger
from app.core.modes import MODE_SOFT_RESET_KEY, get_default_capture_region, get_mode, list_modes
from app.core.paths import DEBUG_FRAME_FILE, OUTPUT_DIR
from app.core.state_manager import StateManager
from app.core.templates import TemplateManager

from .config_service import ConfigService
from .worker import DetectionRequest, DetectionWorker


class AppController(QObject):
    snapshot_changed = Signal(dict)
    runtime_status_changed = Signal(str)
    log_received = Signal(dict)
    error_occurred = Signal(str)
    preview_captured = Signal(dict)
    config_changed = Signal(dict)

    def __init__(
        self,
        *,
        config_service: Optional[ConfigService] = None,
        state_manager: Optional[StateManager] = None,
        event_logger: Optional[EventLogger] = None,
        template_manager: Optional[TemplateManager] = None,
    ) -> None:
        super().__init__()
        self.config_service = config_service or ConfigService()
        self.state_manager = state_manager or StateManager()
        self.event_logger = event_logger or EventLogger()
        self.template_manager = template_manager or TemplateManager()

        self._thread: QThread | None = None
        self._worker: DetectionWorker | None = None
        self._runtime_status = "Idle"
        self._current_snapshot: dict[str, object] | None = None

        self.config_changed.emit(self.get_config())

    def get_modes(self, *, include_unimplemented: bool = True):
        return list_modes(include_unimplemented=include_unimplemented)

    def get_mode(self, mode_key_or_name: str):
        return get_mode(mode_key_or_name)

    def get_config(self) -> dict[str, object]:
        return self.config_service.load()

    def get_mode_region(self, mode_key: str) -> dict[str, int]:
        return self.config_service.get_mode_region(mode_key)

    def save_capture_regions(self, regions: dict[str, dict[str, int]]) -> dict[str, object]:
        config = self.config_service.load()
        modes = config.setdefault("modes", {})
        if not isinstance(modes, dict):
            modes = {}
            config["modes"] = modes

        for mode_key, region in regions.items():
            modes[mode_key] = {"capture_region": dict(region)}

        saved = self.config_service.save(config)
        self.config_changed.emit(saved)
        return saved

    def restore_default_region(self, mode_key: str) -> dict[str, int]:
        self.config_service.restore_default_region(mode_key)
        config = self.config_service.load()
        self.config_changed.emit(config)
        return self.config_service.get_mode_region(mode_key)

    def save_dashboard_preferences(
        self,
        *,
        mode_key: str,
        encounter_increment: int,
        save_debug_frames: bool,
        verbose_debug: bool,
    ) -> dict[str, object]:
        config = self.config_service.load()
        config["last_selected_mode"] = mode_key
        config["encounter_increment"] = max(1, int(encounter_increment))
        config["debug"] = {
            "save_debug_frames": bool(save_debug_frames),
            "verbose_debug": bool(verbose_debug),
        }
        saved = self.config_service.save(config)
        self.config_changed.emit(saved)
        return saved

    def get_template_statuses(self):
        return self.template_manager.get_required_template_statuses()

    def get_recent_events(self, limit: int = 50) -> list[dict[str, object]]:
        return self.event_logger.read_recent_events(limit=limit)

    def get_state_text(self) -> str:
        return self.state_manager.read_state_text()

    def get_state_dict(self) -> dict[str, object]:
        return self.state_manager.read_state_dict()

    def get_config_text(self) -> str:
        return self.config_service.read_text()

    def get_output_dir(self) -> str:
        return str(OUTPUT_DIR)

    def get_debug_frame_path(self) -> str:
        return str(DEBUG_FRAME_FILE)

    def get_monitors(self) -> list[dict[str, int]]:
        return get_monitors()

    def capture_test_screenshot(self, *, mode_key: str, region: dict[str, int]) -> dict[str, object]:
        frame_bgr = grab_region(region)
        save_image(DEBUG_FRAME_FILE, frame_bgr)
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        stats = compute_brightness_stats(gray)
        payload = {
            "mode_key": mode_key,
            "mode_name": get_mode(mode_key).name,
            "path": str(DEBUG_FRAME_FILE),
            "region": dict(region),
            "stats": {
                "min": stats.min_value,
                "max": stats.max_value,
                "mean": round(stats.mean_value, 2),
                "std": round(stats.std_value, 2),
                "nonzero_ratio": round(stats.nonzero_ratio, 4),
            },
        }
        self.preview_captured.emit(payload)
        return payload

    def start_scan(
        self,
        *,
        mode_key: str,
        encounter_increment: int,
        save_debug_frames: bool,
        verbose_debug: bool,
    ) -> None:
        if self.is_running():
            self.error_occurred.emit("Scanning is already running.")
            return

        mode = get_mode(mode_key)
        if not mode.implemented:
            self.error_occurred.emit(f"{mode.name} is not implemented yet.")
            return

        self.save_dashboard_preferences(
            mode_key=mode_key,
            encounter_increment=encounter_increment,
            save_debug_frames=save_debug_frames,
            verbose_debug=verbose_debug,
        )

        request = DetectionRequest(
            mode_key=mode_key,
            capture_region=self.config_service.get_mode_region(mode_key),
            encounter_increment=max(1, int(encounter_increment)),
            save_debug_frames=save_debug_frames,
            verbose_debug=verbose_debug,
        )

        self._thread = QThread(self)
        self._worker = DetectionWorker(request)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.status_changed.connect(self._handle_worker_status)
        self._worker.log_received.connect(self.log_received.emit)
        self._worker.error_occurred.connect(self._handle_worker_error)
        self._worker.completed.connect(self._thread.quit)
        self._worker.completed.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._handle_thread_finished)
        self._thread.finished.connect(self._thread.deleteLater)

        self._runtime_status = "Starting"
        self.runtime_status_changed.emit(self._runtime_status)
        self._thread.start()

    def stop_scan(self) -> None:
        if self._worker is None:
            return
        self._runtime_status = "Stopping"
        self.runtime_status_changed.emit(self._runtime_status)
        self._worker.stop()

    def is_running(self) -> bool:
        return self._worker is not None and self._runtime_status in {"Starting", "Running", "Stopping", "Error"}

    def get_runtime_status(self) -> str:
        return self._runtime_status

    def get_current_snapshot(self) -> dict[str, object] | None:
        return self._current_snapshot

    def open_output_folder(self) -> None:
        output_dir = str(OUTPUT_DIR)
        if hasattr(os, "startfile"):
            os.startfile(output_dir)  # type: ignore[attr-defined]
            return
        subprocess.Popen(["xdg-open", output_dir])

    def build_idle_snapshot(self) -> dict[str, object]:
        state = self.get_state_dict()
        mode_key = str(state.get("mode_key", self.config_service.get_last_selected_mode()))
        try:
            mode = get_mode(mode_key)
        except ValueError:
            mode = get_mode(self.config_service.get_last_selected_mode())

        capture_region = state.get("capture_region")
        if not isinstance(capture_region, dict):
            capture_region = self.config_service.get_mode_region(mode.key)

        return {
            "status": self._runtime_status,
            "mode_key": mode.key,
            "mode_name": mode.name,
            "encounter_increment": int(state.get("encounter_increment", self.config_service.get_encounter_increment())),
            "counter": int(state.get("counter", 0)),
            "catch_counter": int(state.get("catch_counter", 0)),
            "last_event": str(state.get("last_event", "none")),
            "last_event_at": state.get("last_event_at"),
            "last_match_score": float(state.get("last_match_score", 0.0)),
            "last_catch_at_encounter": int(state.get("last_catch_at_encounter", 0)),
            "encounters_since_last_catch": int(state.get("encounters_since_last_catch", 0)),
            "capture_region": dict(capture_region),
            "waiting_for_clear": bool(state.get("waiting_for_clear", False)),
            "cooldown_until": float(state.get("cooldown_until", 0.0)),
            "frame_index": 0,
            "error_message": "",
        }

    def get_default_region(self, mode_key: str) -> dict[str, int]:
        return get_default_capture_region(mode_key)

    def mode_is_enabled(self, mode_key: str) -> bool:
        return mode_key != MODE_SOFT_RESET_KEY and get_mode(mode_key).implemented

    def _handle_worker_status(self, snapshot: dict[str, object]) -> None:
        self._current_snapshot = snapshot
        next_status = str(snapshot.get("status", "Idle"))
        if next_status != self._runtime_status:
            self._runtime_status = next_status
            self.runtime_status_changed.emit(self._runtime_status)
        self.snapshot_changed.emit(snapshot)

    def _handle_worker_error(self, message: str) -> None:
        self._runtime_status = "Error"
        self.runtime_status_changed.emit(self._runtime_status)
        self.error_occurred.emit(message)

    def _handle_thread_finished(self) -> None:
        self._thread = None
        self._worker = None
        if self._runtime_status != "Error":
            self._runtime_status = "Stopped"
            self.runtime_status_changed.emit(self._runtime_status)
        if self._current_snapshot is None:
            self._current_snapshot = self.build_idle_snapshot()
        self.snapshot_changed.emit(self._current_snapshot)
