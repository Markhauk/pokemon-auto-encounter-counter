from __future__ import annotations

import os
import shutil
import subprocess
from typing import Optional

import cv2
from PySide6.QtCore import QObject, QThread, Signal

from app.core.capture import compute_brightness_stats, get_monitors, get_physical_monitors, grab_region, save_image
from app.core.display import (
    build_absolute_capture_region,
    build_monitor_cell_mapping,
    format_monitor_summary,
    normalize_display_setup,
)
from app.core.event_logger import EventLogger
from app.core.filters import FILTER_EVENT_TYPES, FilterDefinition
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

    def get_config(self) -> dict[str, object]:
        return self.config_service.load()

    def get_display_setup(self) -> dict[str, object]:
        return self.config_service.get_display_setup()

    def get_filters(self) -> list[FilterDefinition]:
        return self.config_service.get_filters()

    def get_filter(self, filter_id: str) -> FilterDefinition | None:
        return self.config_service.get_filter(filter_id)

    def get_filter_event_types(self) -> tuple[str, ...]:
        return FILTER_EVENT_TYPES

    def create_filter(self, *, name: str | None = None) -> FilterDefinition:
        filter_definition = self.config_service.create_filter(name=name)
        self.config_changed.emit(self.get_config())
        return filter_definition

    def save_filter(self, updated_filter: FilterDefinition) -> dict[str, object]:
        saved = self.config_service.replace_filter(updated_filter)
        self.config_changed.emit(saved)
        return saved

    def save_filters(self, filters: list[FilterDefinition]) -> dict[str, object]:
        saved = self.config_service.save_filters(filters)
        self.config_changed.emit(saved)
        return saved

    def delete_filter(self, filter_id: str) -> dict[str, object]:
        saved = self.config_service.delete_filter(filter_id)
        self.config_changed.emit(saved)
        return saved

    def get_template_statuses(self):
        return self.template_manager.get_filter_template_statuses(self.get_filters())

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

    def get_physical_monitors(self) -> list[dict[str, int]]:
        return get_physical_monitors()

    def get_monitor_cell_mapping(
        self,
        *,
        display_setup: Optional[dict[str, object]] = None,
    ) -> dict[tuple[int, int], dict[str, int]]:
        return build_monitor_cell_mapping(
            display_setup=display_setup or self.get_display_setup(),
            physical_monitors=self.get_physical_monitors(),
        )

    def capture_test_screenshot(
        self,
        *,
        filter_definition: FilterDefinition,
        display_setup: Optional[dict[str, object]] = None,
    ) -> dict[str, object]:
        active_display_setup = normalize_display_setup(display_setup or self.get_display_setup())
        physical_monitors = self.get_physical_monitors()
        absolute_region = build_absolute_capture_region(
            relative_region=filter_definition.capture_region,
            display_setup=active_display_setup,
            physical_monitors=physical_monitors,
        )
        capture_cell = active_display_setup["capture_cell"]
        selected_monitor = self.get_monitor_cell_mapping(display_setup=active_display_setup)[
            (int(capture_cell["row"]), int(capture_cell["column"]))  # type: ignore[index]
        ]

        frame_bgr = grab_region(absolute_region)
        save_image(DEBUG_FRAME_FILE, frame_bgr)
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        stats = compute_brightness_stats(gray)
        payload = {
            "filter_id": filter_definition.id,
            "filter_name": filter_definition.name,
            "event_type": filter_definition.event_type,
            "path": str(DEBUG_FRAME_FILE),
            "region": dict(filter_definition.capture_region),
            "absolute_region": absolute_region,
            "monitor": dict(selected_monitor),
            "monitor_summary": format_monitor_summary(selected_monitor),
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

    def save_filter_template_from_preview(self, filter_id: str) -> str:
        filter_definition = self.get_filter(filter_id)
        if filter_definition is None:
            raise ValueError(f"Unknown filter: {filter_id}")
        if not DEBUG_FRAME_FILE.exists():
            raise FileNotFoundError("No preview image exists yet. Capture a preview first.")

        destination = self.template_manager.get_path(filter_definition.template_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(DEBUG_FRAME_FILE, destination)
        self.config_changed.emit(self.get_config())
        return str(destination)

    def save_capture_settings(
        self,
        *,
        display_setup: dict[str, object],
    ) -> dict[str, object]:
        saved = self.config_service.save_capture_settings(
            display_setup=display_setup,
            filters=self.get_filters(),
        )
        self.config_changed.emit(saved)
        return saved

    def save_dashboard_preferences(
        self,
        *,
        encounter_increment: int,
        save_debug_frames: bool,
        verbose_debug: bool,
    ) -> dict[str, object]:
        config = self.config_service.load()
        config["last_selected_mode"] = "filters"
        config["encounter_increment"] = max(1, int(encounter_increment))
        config["debug"] = {
            "save_debug_frames": bool(save_debug_frames),
            "verbose_debug": bool(verbose_debug),
        }
        saved = self.config_service.save(config)
        self.config_changed.emit(saved)
        return saved

    def start_scan(
        self,
        *,
        encounter_increment: int,
        save_debug_frames: bool,
        verbose_debug: bool,
    ) -> None:
        if self.is_running():
            self.error_occurred.emit("Scanning is already running.")
            return

        display_setup = self.config_service.get_display_setup()
        filters = self.get_filters()
        enabled_filters: list[FilterDefinition] = []
        for filter_definition in filters:
            if not filter_definition.enabled:
                continue
            try:
                absolute_region = build_absolute_capture_region(
                    relative_region=filter_definition.capture_region,
                    display_setup=display_setup,
                    physical_monitors=self.get_physical_monitors(),
                )
            except ValueError as exc:
                self.error_occurred.emit(str(exc))
                return

            enabled_filters.append(
                FilterDefinition(
                    id=filter_definition.id,
                    name=filter_definition.name,
                    enabled=True,
                    event_type=filter_definition.event_type,
                    template_path=filter_definition.template_path,
                    capture_region=absolute_region,
                    threshold=filter_definition.threshold,
                    built_in=filter_definition.built_in,
                    description=filter_definition.description,
                    metadata=dict(filter_definition.metadata),
                )
            )

        if not enabled_filters:
            self.error_occurred.emit("No enabled filters are configured for scanning.")
            return

        self.save_dashboard_preferences(
            encounter_increment=encounter_increment,
            save_debug_frames=save_debug_frames,
            verbose_debug=verbose_debug,
        )

        request = DetectionRequest(
            filters=enabled_filters,
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
        filters = self.get_filters()

        return {
            "status": self._runtime_status,
            "mode_key": "filters",
            "mode_name": "Filter scan",
            "encounter_increment": int(state.get("encounter_increment", self.config_service.get_encounter_increment())),
            "enabled_filter_count": len([filter_definition for filter_definition in filters if filter_definition.enabled]),
            "counter": int(state.get("counter", 0)),
            "catch_counter": int(state.get("catch_counter", 0)),
            "last_event": str(state.get("last_event", "none")),
            "last_event_at": state.get("last_event_at"),
            "last_match_score": float(state.get("last_match_score", 0.0)),
            "last_filter_id": str(state.get("last_filter_id", "")),
            "last_filter_name": str(state.get("last_filter_name", "")),
            "last_filter_event_type": str(state.get("last_filter_event_type", "")),
            "active_label": str(state.get("active_label", "")),
            "last_catch_at_encounter": int(state.get("last_catch_at_encounter", 0)),
            "encounters_since_last_catch": int(state.get("encounters_since_last_catch", 0)),
            "capture_region": state.get("capture_region"),
            "waiting_for_clear": bool(state.get("waiting_for_clear", False)),
            "cooldown_until": float(state.get("cooldown_until", 0.0)),
            "frame_index": 0,
            "filters_runtime": state.get("filters_runtime", {}),
            "error_message": "",
        }

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
