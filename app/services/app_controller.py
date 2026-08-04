from __future__ import annotations

import os
import subprocess
from typing import Optional

import cv2
from PySide6.QtCore import QObject, QThread, Signal

from app.core.capture import compute_brightness_stats, get_monitors, get_physical_monitors, grab_region, save_image
from app.core.display import (
    build_absolute_capture_region,
    format_monitor_summary,
    normalize_display_setup,
    resolve_capture_monitor,
)
from app.core.event_logger import EventLogger
from app.core.filters import FILTER_EVENT_TYPES, FilterDefinition, GameDefinition
from app.core.paths import DEBUG_FRAME_FILE, OUTPUT_DIR, TEMPLATE_SOURCE_FILE
from app.core.regions import clamp_region, expand_region
from app.core.state_manager import StateManager
from app.core.templates import TemplateManager

from .config_service import ConfigService
from .session_service import SessionService
from .worker import DetectionRequest, DetectionWorker


class AppController(QObject):
    snapshot_changed = Signal(dict)
    runtime_status_changed = Signal(str)
    log_received = Signal(dict)
    error_occurred = Signal(str)
    preview_captured = Signal(dict)
    session_changed = Signal(dict)
    hunt_changed = Signal(dict)
    config_changed = Signal(dict)

    def __init__(
        self,
        *,
        config_service: Optional[ConfigService] = None,
        state_manager: Optional[StateManager] = None,
        event_logger: Optional[EventLogger] = None,
        template_manager: Optional[TemplateManager] = None,
        session_service: Optional[SessionService] = None,
    ) -> None:
        super().__init__()
        self.config_service = config_service or ConfigService()
        self.state_manager = state_manager or StateManager()
        self.event_logger = event_logger or EventLogger()
        self.template_manager = template_manager or TemplateManager()
        self.session_service = session_service or SessionService(
            config_service=self.config_service,
            state_manager=self.state_manager,
            event_logger=self.event_logger,
        )

        self._thread: QThread | None = None
        self._worker: DetectionWorker | None = None
        self._runtime_status = "Idle"
        self._current_snapshot: dict[str, object] | None = None

        self._session_context, self._session_migration = self.session_service.initialize()

        self.config_changed.emit(self.get_config())

    def get_config(self) -> dict[str, object]:
        return self.config_service.load()

    def get_display_setup(self) -> dict[str, object]:
        return self.config_service.get_display_setup()

    def get_interface_frame_type(self) -> int:
        return self.config_service.get_interface_frame_type()

    def set_interface_frame_type(self, frame_type: object) -> dict[str, object]:
        saved = self.config_service.set_interface_frame_type(frame_type)
        self.config_changed.emit(saved)
        return saved

    def get_games(self) -> list[GameDefinition]:
        return self.config_service.get_games()

    def get_game(self, game_id: str) -> GameDefinition | None:
        return self.config_service.get_game(game_id)

    def get_active_game_id(self) -> str:
        return self.config_service.get_active_game_id()

    def set_active_game_id(self, game_id: str) -> dict[str, object]:
        saved = self.config_service.set_active_game_id(game_id)
        self._session_context = self.session_service.ensure_for_active_game()
        self._emit_progress_context()
        self.config_changed.emit(saved)
        self._emit_idle_snapshot_if_needed()
        return saved

    def create_game(self, *, name: str | None = None) -> GameDefinition:
        game_definition = self.config_service.create_game(name=name)
        self._session_context = self.session_service.ensure_for_active_game()
        self._emit_progress_context()
        self.config_changed.emit(self.get_config())
        self._emit_idle_snapshot_if_needed()
        return game_definition

    def delete_game(self, game_id: str) -> dict[str, object]:
        saved = self.config_service.delete_game(game_id)
        self._session_context = self.session_service.ensure_for_active_game()
        self._emit_progress_context()
        self.config_changed.emit(saved)
        self._emit_idle_snapshot_if_needed()
        return saved

    def get_filters(self, *, game_id: str | None = None) -> list[FilterDefinition]:
        return self.config_service.get_filters(game_id=game_id)

    def get_filter(self, filter_id: str) -> FilterDefinition | None:
        return self.config_service.get_filter(filter_id)

    def get_filter_event_types(self) -> tuple[str, ...]:
        return FILTER_EVENT_TYPES

    def create_filter(self, *, name: str | None = None, game_id: str | None = None) -> FilterDefinition:
        filter_definition = self.config_service.create_filter(name=name, game_id=game_id)
        self.config_changed.emit(self.get_config())
        self._emit_idle_snapshot_if_needed()
        return filter_definition

    def save_filter(self, updated_filter: FilterDefinition) -> dict[str, object]:
        saved = self.config_service.replace_filter(updated_filter)
        self.config_changed.emit(saved)
        self._emit_idle_snapshot_if_needed()
        return saved

    def save_filters(self, filters: list[FilterDefinition]) -> dict[str, object]:
        saved = self.config_service.save_filters(filters)
        self.config_changed.emit(saved)
        self._emit_idle_snapshot_if_needed()
        return saved

    def delete_filter(self, filter_id: str) -> dict[str, object]:
        saved = self.config_service.delete_filter(filter_id)
        self.config_changed.emit(saved)
        self._emit_idle_snapshot_if_needed()
        return saved

    def get_template_statuses(self, *, game_id: str | None = None):
        return self.template_manager.get_filter_template_statuses(self.get_filters(game_id=game_id))

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

    def get_session_context(self) -> dict[str, object]:
        current = self.session_service.current_context()
        if current is None:
            current, _ = self.session_service.initialize()
        self._session_context = current
        return current.as_dict()

    def get_hunts(self, *, game_id: str | None = None) -> list[dict[str, object]]:
        return [hunt.as_dict() for hunt in self.session_service.list_hunts(game_id=game_id)]

    def get_active_hunt(self) -> dict[str, object]:
        return self.session_service.active_hunt().as_dict()

    def set_active_hunt_id(self, hunt_id: str) -> dict[str, object]:
        if self.is_running():
            raise RuntimeError("Stop scanning before switching hunts.")
        self._session_context = self.session_service.select_hunt(hunt_id)
        payload = self._session_context.as_dict()
        self._emit_progress_context()
        self._emit_idle_snapshot_if_needed()
        return payload

    def start_new_hunt(self, *, name: str, complete_current: bool) -> dict[str, object]:
        if self.is_running():
            raise RuntimeError("Stop scanning before starting a new hunt.")
        self._session_context = self.session_service.start_new_hunt(
            name=name,
            complete_current=complete_current,
        )
        payload = self._session_context.as_dict()
        self._emit_progress_context()
        self._emit_idle_snapshot_if_needed()
        return payload

    def start_new_session(self) -> dict[str, object]:
        if self.is_running():
            raise RuntimeError("Stop scanning before starting a new session.")
        self._session_context = self.session_service.start_new_session()
        payload = self._session_context.as_dict()
        self._emit_progress_context()
        self._emit_idle_snapshot_if_needed()
        return payload

    def get_monitors(self) -> list[dict[str, int]]:
        return get_monitors()

    def get_physical_monitors(self) -> list[dict[str, int]]:
        return get_physical_monitors()

    def get_selected_capture_monitor(
        self,
        *,
        display_setup: Optional[dict[str, object]] = None,
    ) -> dict[str, int]:
        physical_monitors = self.get_physical_monitors()
        active_display_setup = normalize_display_setup(
            display_setup if display_setup is not None else self.get_display_setup(),
            physical_monitors=physical_monitors,
        )
        return resolve_capture_monitor(
            display_setup=active_display_setup,
            physical_monitors=physical_monitors,
        )

    def capture_test_screenshot(
        self,
        *,
        filter_definition: FilterDefinition,
        display_setup: Optional[dict[str, object]] = None,
    ) -> dict[str, object]:
        physical_monitors = self.get_physical_monitors()
        active_display_setup = normalize_display_setup(
            display_setup if display_setup is not None else self.get_display_setup(),
            physical_monitors=physical_monitors,
        )
        absolute_region = build_absolute_capture_region(
            relative_region=filter_definition.capture_region,
            display_setup=active_display_setup,
            physical_monitors=physical_monitors,
        )
        selected_monitor = self.get_selected_capture_monitor(display_setup=active_display_setup)

        frame_bgr = grab_region(absolute_region)
        save_image(DEBUG_FRAME_FILE, frame_bgr)
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        stats = compute_brightness_stats(gray)
        template_match: dict[str, object]
        try:
            template = self.template_manager.load_grayscale(filter_definition.template_path)
            if template.shape[0] > gray.shape[0] or template.shape[1] > gray.shape[1]:
                template_match = {
                    "available": False,
                    "error": "Template is larger than the configured capture region.",
                }
            else:
                result = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
                _, max_score, _, _ = cv2.minMaxLoc(result)
                template_match = {
                    "available": True,
                    "score": round(float(max_score), 6),
                    "threshold": float(filter_definition.threshold),
                    "found": bool(max_score >= filter_definition.threshold),
                }
        except Exception as exc:
            template_match = {"available": False, "error": str(exc)}

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
            "template_match": template_match,
        }
        self.preview_captured.emit(payload)
        return payload

    def capture_template_source(self, filter_id: str) -> dict[str, object]:
        if self.is_running():
            raise RuntimeError("Stop scanning before creating a template.")
        filter_definition = self.get_filter(filter_id)
        if filter_definition is None:
            raise ValueError(f"Unknown filter: {filter_id}")

        monitor = self.get_selected_capture_monitor()
        monitor_region = {
            "left": int(monitor["left"]),
            "top": int(monitor["top"]),
            "width": int(monitor["width"]),
            "height": int(monitor["height"]),
        }
        frame_bgr = grab_region(monitor_region)
        save_image(TEMPLATE_SOURCE_FILE, frame_bgr)
        bounds_width = int(monitor["width"])
        bounds_height = int(monitor["height"])

        raw_template_region = filter_definition.metadata.get("template_region")
        if not isinstance(raw_template_region, dict):
            raw_template_region = filter_definition.capture_region
        initial_region = clamp_region(
            {
                "left": int(raw_template_region.get("left", 0)),
                "top": int(raw_template_region.get("top", 0)),
                "width": int(raw_template_region.get("width", 1)),
                "height": int(raw_template_region.get("height", 1)),
            },
            bounds_width=bounds_width,
            bounds_height=bounds_height,
        )
        return {
            "filter_id": filter_definition.id,
            "filter_name": filter_definition.name,
            "source_path": str(TEMPLATE_SOURCE_FILE),
            "monitor": dict(monitor),
            "monitor_summary": format_monitor_summary(monitor),
            "initial_region": initial_region,
            "search_padding": max(0, int(filter_definition.metadata.get("search_padding", 20))),
        }

    def save_template_crop(
        self,
        *,
        filter_id: str,
        template_region: dict[str, int],
        search_padding: int,
    ) -> dict[str, object]:
        filter_definition = self.get_filter(filter_id)
        if filter_definition is None:
            raise ValueError(f"Unknown filter: {filter_id}")
        if not TEMPLATE_SOURCE_FILE.exists():
            raise FileNotFoundError("The full-monitor template source is no longer available.")

        source = cv2.imread(str(TEMPLATE_SOURCE_FILE), cv2.IMREAD_COLOR)
        if source is None:
            raise RuntimeError("OpenCV could not read the template source screenshot.")
        source_height, source_width = source.shape[:2]
        selected = clamp_region(
            template_region,
            bounds_width=source_width,
            bounds_height=source_height,
        )
        x1 = selected["left"]
        y1 = selected["top"]
        x2 = x1 + selected["width"]
        y2 = y1 + selected["height"]
        cropped = source[y1:y2, x1:x2].copy()
        gray = cv2.cvtColor(cropped, cv2.COLOR_BGR2GRAY)
        stats = compute_brightness_stats(gray)
        if stats.std_value < 1.0:
            raise ValueError("The selected template is nearly uniform. Select the visible battle text more tightly.")

        destination = self.template_manager.get_path(filter_definition.template_path)
        save_image(destination, cropped)
        capture_region = expand_region(
            selected,
            padding=search_padding,
            bounds_width=source_width,
            bounds_height=source_height,
        )
        metadata = dict(filter_definition.metadata)
        metadata["template_region"] = dict(selected)
        metadata["search_padding"] = max(0, int(search_padding))
        updated_filter = FilterDefinition(
            id=filter_definition.id,
            name=filter_definition.name,
            enabled=filter_definition.enabled,
            event_type=filter_definition.event_type,
            template_path=filter_definition.template_path,
            capture_region=capture_region,
            threshold=filter_definition.threshold,
            cooldown_seconds=filter_definition.cooldown_seconds,
            built_in=filter_definition.built_in,
            description=filter_definition.description,
            metadata=metadata,
        )
        saved = self.config_service.replace_filter(updated_filter)
        self.config_changed.emit(saved)
        self._emit_idle_snapshot_if_needed()
        return {
            "path": str(destination),
            "template_region": selected,
            "capture_region": capture_region,
            "stats": {
                "mean": round(stats.mean_value, 2),
                "std": round(stats.std_value, 2),
                "min": stats.min_value,
                "max": stats.max_value,
            },
        }

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
        self._emit_idle_snapshot_if_needed()
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
        self._emit_idle_snapshot_if_needed()
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
        active_game_id = self.get_active_game_id()
        active_game = self.get_game(active_game_id)
        filters = self.get_filters(game_id=active_game_id)
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
                    cooldown_seconds=filter_definition.cooldown_seconds,
                    built_in=filter_definition.built_in,
                    description=filter_definition.description,
                    metadata=dict(filter_definition.metadata),
                )
            )

        if not enabled_filters:
            if active_game is None:
                self.error_occurred.emit("No enabled filters are configured for scanning.")
            else:
                self.error_occurred.emit(f"No enabled filters are configured for '{active_game.name}'.")
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
            session_context=self.session_service.ensure_for_active_game(),
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
        active_game_id = self.get_active_game_id()
        active_game = self.get_game(active_game_id)
        filters = self.get_filters(game_id=active_game_id)

        return {
            "status": self._runtime_status,
            "mode_key": "filters",
            "mode_name": f"{active_game.name} scan" if active_game is not None else "Filter scan",
            "active_game_id": active_game_id,
            "active_game_name": active_game.name if active_game is not None else active_game_id,
            "game_id": str(state.get("game_id", active_game_id)),
            "game_name": str(state.get("game_name", active_game.name if active_game is not None else active_game_id)),
            "hunt_id": str(state.get("hunt_id", "")),
            "hunt_name": str(state.get("hunt_name", "")),
            "hunt_status": str(state.get("hunt_status", "active")),
            "hunt_started_at": str(state.get("hunt_started_at", "")),
            "hunt_completed_at": str(state.get("hunt_completed_at", "")),
            "hunt_encounter_count": int(state.get("hunt_encounter_count", 0)),
            "hunt_catch_counter": int(state.get("hunt_catch_counter", 0)),
            "hunt_last_catch_at_encounter": int(state.get("hunt_last_catch_at_encounter", 0)),
            "hunt_encounters_since_last_catch": int(
                state.get("hunt_encounters_since_last_catch", 0)
            ),
            "session_id": str(state.get("session_id", "")),
            "session_number": int(state.get("session_number", 0)),
            "session_started_at": str(state.get("session_started_at", "")),
            "session_start_counter": int(state.get("session_start_counter", 0)),
            "session_start_hunt_counter": int(state.get("session_start_hunt_counter", 0)),
            "session_encounter_count": int(state.get("session_encounter_count", 0)),
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
        snapshot.setdefault("active_game_id", snapshot.get("game_id", ""))
        snapshot.setdefault("active_game_name", snapshot.get("game_name", ""))
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

    def _emit_idle_snapshot_if_needed(self) -> None:
        if self.is_running():
            return
        self._current_snapshot = self.build_idle_snapshot()
        self.snapshot_changed.emit(self._current_snapshot)

    def _emit_progress_context(self) -> None:
        payload = self._session_context.as_dict()
        self.session_changed.emit(payload)
        self.hunt_changed.emit(payload)
