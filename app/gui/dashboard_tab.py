from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.services.app_controller import AppController

from .frame_styles import mark_as_interface_frame
from .new_hunt_dialog import NewHuntDialog
from .obs_counter_dialog import ObsCounterDialog


_FRACTIONAL_TIMESTAMP = re.compile(
    r"^(?P<whole>.*\d{2}:\d{2}:\d{2})\.(?P<fraction>\d+)(?P<suffix>Z|[+-]\d{2}:\d{2})?$"
)
_COUNTING_EVENT_TYPES = {"catch", "encounter_start", "fled"}


def compact_log_timestamp(value: object) -> str:
    """Limit fractional seconds to one digit without changing the timezone."""
    timestamp = str(value or "")
    match = _FRACTIONAL_TIMESTAMP.match(timestamp)
    if match is None:
        return timestamp
    suffix = match.group("suffix") or ""
    return f"{match.group('whole')}.{match.group('fraction')[0]}{suffix}"


def format_dashboard_log_event(event: dict[str, object]) -> str:
    """Build the compact hunt-focused line used by the Dashboard history."""
    timestamp = compact_log_timestamp(event.get("timestamp", ""))
    filter_name = str(event.get("filter_name", "") or event.get("event", "Event"))
    event_type = str(event.get("filter_event_type", event.get("event", "info")))
    parts = [f"[{timestamp}] {filter_name.upper()} [{event_type}]"]
    if event_type in _COUNTING_EVENT_TYPES:
        parts.append(f"+{max(1, int(event.get('encounter_increment', 1)))}")
    parts.append(f"Hunt encounters: {int(event.get('hunt_encounter_count', 0))}")
    parts.append(f"Score: {float(event.get('last_match_score', 0.0)):.1f}")
    return " | ".join(parts)


class DashboardTab(QWidget):
    def __init__(self, controller: AppController) -> None:
        super().__init__()
        self.controller = controller
        self._encounter_capture_path = Path(self.controller.get_encounter_capture_path())
        self._last_capture_event_at = ""
        self._build_ui()
        self._connect_signals()
        self._load_initial_state()

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        self._loading = False

        controls_group = QGroupBox("Scanner Controls")
        mark_as_interface_frame(controls_group)
        controls_layout = QGridLayout(controls_group)

        self.game_combo = QComboBox()
        self.hunt_combo = QComboBox()
        self.increment_spin = QSpinBox()
        self.increment_spin.setRange(1, 9999)
        self.save_debug_checkbox = QCheckBox("Save last capture while running")
        self.verbose_debug_checkbox = QCheckBox("Verbose debug logging")
        self.start_button = QPushButton("Start")
        self.stop_button = QPushButton("Stop")
        self.new_session_button = QPushButton("New Session")
        self.new_hunt_button = QPushButton("New Hunt...")
        self.obs_counter_button = QPushButton("OBS Live Counter...")
        self._obs_counter_dialog: ObsCounterDialog | None = None
        self.status_value = QLabel("Idle")
        self.session_value = QLabel("N/A")

        controls_layout.addWidget(QLabel("Game"), 0, 0)
        controls_layout.addWidget(self.game_combo, 0, 1)
        controls_layout.addWidget(QLabel("Hunt"), 0, 2)
        controls_layout.addWidget(self.hunt_combo, 0, 3)
        controls_layout.addWidget(self.start_button, 0, 4)
        controls_layout.addWidget(self.stop_button, 0, 5)
        controls_layout.addWidget(QLabel("Encounter increment"), 1, 0)
        controls_layout.addWidget(self.increment_spin, 1, 1)
        controls_layout.addWidget(QLabel("Status"), 1, 2)
        controls_layout.addWidget(self.status_value, 1, 3)
        controls_layout.addWidget(self.new_session_button, 1, 4)
        controls_layout.addWidget(self.new_hunt_button, 1, 5)
        controls_layout.addWidget(QLabel("Session"), 2, 0)
        controls_layout.addWidget(self.session_value, 2, 1)
        controls_layout.addWidget(self.save_debug_checkbox, 2, 2)
        controls_layout.addWidget(self.verbose_debug_checkbox, 2, 3)
        controls_layout.addWidget(self.obs_counter_button, 2, 4, 1, 2)
        controls_layout.setColumnStretch(1, 1)
        controls_layout.setColumnStretch(3, 1)
        controls_layout.setColumnStretch(4, 1)
        controls_layout.setColumnStretch(5, 1)

        summary_row = QHBoxLayout()

        counters_group = QGroupBox("Counters")
        mark_as_interface_frame(counters_group)
        counters_layout = QFormLayout(counters_group)
        self.hunt_encounter_value = QLabel("0")
        self.encounter_value = QLabel("0")
        self.hunt_catch_value = QLabel("0")
        self.catch_value = QLabel("0")
        self.since_catch_value = QLabel("0")
        self.session_encounter_value = QLabel("0")
        counters_layout.addRow("Hunt encounters", self.hunt_encounter_value)
        counters_layout.addRow("This session", self.session_encounter_value)
        counters_layout.addRow("All-time encounters", self.encounter_value)
        counters_layout.addRow("Since last hunt catch", self.since_catch_value)
        counters_layout.addRow("Hunt catches", self.hunt_catch_value)
        counters_layout.addRow("All-time catches", self.catch_value)

        details_group = QGroupBox("Live Details")
        mark_as_interface_frame(details_group)
        details_layout = QFormLayout(details_group)
        self.enabled_filters_value = QLabel("0")
        self.last_event_value = QLabel("none")
        self.last_event_at_value = QLabel("N/A")
        self.last_filter_value = QLabel("N/A")
        self.active_label_value = QLabel("N/A")
        self.last_score_value = QLabel("0.000")

        details_layout.addRow("Enabled filters", self.enabled_filters_value)
        details_layout.addRow("Last event", self.last_event_value)
        details_layout.addRow("Last event time", self.last_event_at_value)
        details_layout.addRow("Last filter", self.last_filter_value)
        details_layout.addRow("Active label", self.active_label_value)
        details_layout.addRow("Last match score", self.last_score_value)

        summary_row.addWidget(counters_group, 1)
        summary_row.addWidget(details_group, 1)

        log_group = QGroupBox("Live Runtime Log")
        mark_as_interface_frame(log_group)
        log_layout = QVBoxLayout(log_group)
        self.log_box = QPlainTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.document().setMaximumBlockCount(200)
        log_layout.addWidget(self.log_box)

        capture_group = QGroupBox("Encounter Capture")
        mark_as_interface_frame(capture_group)
        capture_layout = QVBoxLayout(capture_group)
        self.encounter_capture_label = QLabel("Waiting for the next encounter.")
        self.encounter_capture_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.encounter_capture_label.setMinimumSize(300, 170)
        self.encounter_capture_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self.encounter_capture_label.setStyleSheet("border: 1px solid #666;")
        self.encounter_capture_info = QLabel("Full monitor image updates after a counted encounter.")
        self.encounter_capture_info.setWordWrap(True)
        self.encounter_capture_info.setStyleSheet("color: #b8b8b8;")
        capture_layout.addWidget(self.encounter_capture_label, 1)
        capture_layout.addWidget(self.encounter_capture_info)

        runtime_row = QHBoxLayout()
        runtime_row.addWidget(log_group, 2)
        runtime_row.addWidget(capture_group, 1)

        root_layout.addWidget(controls_group)
        root_layout.addLayout(summary_row)
        root_layout.addLayout(runtime_row, 1)

    def _connect_signals(self) -> None:
        self.start_button.clicked.connect(self._start_scan)
        self.stop_button.clicked.connect(self.controller.stop_scan)
        self.new_session_button.clicked.connect(self._start_new_session)
        self.new_hunt_button.clicked.connect(self._start_new_hunt)
        self.obs_counter_button.clicked.connect(self._open_obs_counter_setup)
        self.game_combo.currentIndexChanged.connect(self._handle_game_changed)
        self.hunt_combo.currentIndexChanged.connect(self._handle_hunt_changed)

        self.controller.snapshot_changed.connect(self._apply_snapshot)
        self.controller.runtime_status_changed.connect(self._apply_runtime_status)
        self.controller.log_received.connect(self._append_log_message)
        self.controller.error_occurred.connect(self._show_error)
        self.controller.config_changed.connect(self._handle_config_changed)
        self.controller.hunt_changed.connect(self._handle_hunt_context_changed)

    def _load_initial_state(self) -> None:
        config = self.controller.get_config()
        self._refresh_game_selector()
        self._refresh_hunt_selector()
        self.increment_spin.setValue(int(config.get("encounter_increment", 1)))
        debug = config.get("debug", {})
        if isinstance(debug, dict):
            self.save_debug_checkbox.setChecked(bool(debug.get("save_debug_frames", False)))
            self.verbose_debug_checkbox.setChecked(bool(debug.get("verbose_debug", False)))

        snapshot = self.controller.build_idle_snapshot()
        self._apply_snapshot(snapshot)
        if self._encounter_capture_path.exists() and not self._last_capture_event_at:
            self._last_capture_event_at = "saved"
            self._load_encounter_capture("")
        self._apply_runtime_status(self.controller.get_runtime_status())
        self._load_recent_events()

    def _load_recent_events(self) -> None:
        recent_events = self.controller.get_recent_events(limit=12)
        lines = [format_dashboard_log_event(event) for event in recent_events]
        self.log_box.setPlainText("\n".join(lines))

    def _apply_snapshot(self, snapshot: dict[str, object]) -> None:
        self.hunt_encounter_value.setText(str(snapshot.get("hunt_encounter_count", 0)))
        self.encounter_value.setText(str(snapshot.get("counter", 0)))
        self.hunt_catch_value.setText(str(snapshot.get("hunt_catch_counter", 0)))
        self.catch_value.setText(str(snapshot.get("catch_counter", 0)))
        self.since_catch_value.setText(str(snapshot.get("hunt_encounters_since_last_catch", 0)))
        self.session_encounter_value.setText(str(snapshot.get("session_encounter_count", 0)))
        session_number = int(snapshot.get("session_number", 0))
        self.session_value.setText(f"#{session_number}" if session_number else "N/A")
        self.last_score_value.setText(f"{float(snapshot.get('last_match_score', 0.0)):.3f}")
        self.enabled_filters_value.setText(str(snapshot.get("enabled_filter_count", 0)))
        self.last_event_value.setText(str(snapshot.get("last_event", "none")))
        self.last_event_at_value.setText(str(snapshot.get("last_event_at", "N/A") or "N/A"))
        self.last_filter_value.setText(str(snapshot.get("last_filter_name", "N/A") or "N/A"))
        self.active_label_value.setText(str(snapshot.get("active_label", "N/A") or "N/A"))

        capture_at = str(snapshot.get("last_encounter_capture_at", "") or "")
        if capture_at and capture_at != self._last_capture_event_at:
            self._last_capture_event_at = capture_at
            self._load_encounter_capture(capture_at)

    def _load_encounter_capture(self, event_at: str) -> None:
        pixmap = QPixmap(str(self._encounter_capture_path))
        if pixmap.isNull():
            self.encounter_capture_label.clear()
            self.encounter_capture_label.setText("Encounter captured, but the image is unavailable.")
            self.encounter_capture_info.setText(
                compact_log_timestamp(event_at)
                if event_at and event_at != "saved"
                else "Last saved encounter capture"
            )
            return
        self.encounter_capture_label.setPixmap(
            pixmap.scaled(
                self.encounter_capture_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        if event_at and event_at != "saved":
            self.encounter_capture_info.setText(
                f"Full monitor captured at {compact_log_timestamp(event_at)}"
            )
        else:
            self.encounter_capture_info.setText("Last saved encounter capture")

    def _apply_runtime_status(self, status: str) -> None:
        self.status_value.setText(status)
        self._update_button_state()
        if not self.controller.is_running():
            self._refresh_hunt_selector()

    def _update_button_state(self) -> None:
        running = self.controller.is_running()
        filters = self.controller.get_filters(game_id=self.controller.get_active_game_id())
        enabled_filters = [filter_definition for filter_definition in filters if filter_definition.enabled]
        can_start = bool(enabled_filters) and not running

        self.start_button.setEnabled(can_start)
        self.stop_button.setEnabled(running)
        self.game_combo.setEnabled(not running)
        self.hunt_combo.setEnabled(not running)
        self.increment_spin.setEnabled(not running)
        self.save_debug_checkbox.setEnabled(not running)
        self.verbose_debug_checkbox.setEnabled(not running)
        self.new_session_button.setEnabled(not running)
        self.new_hunt_button.setEnabled(not running)

    def _refresh_game_selector(self) -> None:
        active_game_id = self.controller.get_active_game_id()
        games = self.controller.get_games()

        self._loading = True
        try:
            self.game_combo.clear()
            for game_definition in games:
                self.game_combo.addItem(game_definition.name, game_definition.id)

            selected_index = self.game_combo.findData(active_game_id)
            if selected_index >= 0:
                self.game_combo.setCurrentIndex(selected_index)
        finally:
            self._loading = False

    def _refresh_hunt_selector(self) -> None:
        active_game_id = self.controller.get_active_game_id()
        active_hunt = self.controller.get_active_hunt()
        active_hunt_id = str(active_hunt.get("hunt_id", ""))
        hunts = self.controller.get_hunts(game_id=active_game_id)

        self._loading = True
        try:
            self.hunt_combo.clear()
            for hunt in hunts:
                status = str(hunt.get("hunt_status", "paused"))
                suffix = f" [{status}]" if status != "active" else ""
                label = (
                    f"{hunt.get('hunt_name', 'Unnamed Hunt')} — "
                    f"{int(hunt.get('hunt_encounter_count', 0)):,} encounters{suffix}"
                )
                self.hunt_combo.addItem(label, str(hunt.get("hunt_id", "")))
            selected_index = self.hunt_combo.findData(active_hunt_id)
            if selected_index >= 0:
                self.hunt_combo.setCurrentIndex(selected_index)
        finally:
            self._loading = False

    def _append_log_message(self, payload: dict[str, object]) -> None:
        timestamp = compact_log_timestamp(payload.get("timestamp", ""))
        message = str(payload.get("message", ""))
        if message:
            self.log_box.appendPlainText(f"[{timestamp}] {message}")

    def _start_scan(self) -> None:
        self.controller.start_scan(
            encounter_increment=self.increment_spin.value(),
            save_debug_frames=self.save_debug_checkbox.isChecked(),
            verbose_debug=self.verbose_debug_checkbox.isChecked(),
        )

    def _start_new_session(self) -> None:
        response = QMessageBox.question(
            self,
            "Start New Session",
            "Start a new session for the selected game? The lifetime encounter and catch counters will not reset.",
        )
        if response != QMessageBox.StandardButton.Yes:
            return
        try:
            self.controller.start_new_session()
        except Exception as exc:
            self._show_error(str(exc))

    def _start_new_hunt(self) -> None:
        try:
            current_hunt = self.controller.get_active_hunt()
            dialog = NewHuntDialog(current_hunt, self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            self.controller.start_new_hunt(
                name=dialog.hunt_name,
                complete_current=dialog.complete_current,
            )
        except Exception as exc:
            self._show_error(str(exc))

    def _open_obs_counter_setup(self) -> None:
        try:
            if self._obs_counter_dialog is None:
                self._obs_counter_dialog = ObsCounterDialog(self.controller, self)
            else:
                self._obs_counter_dialog.refresh()
            self._obs_counter_dialog.exec()
        except Exception as exc:
            self._show_error(f"Could not prepare the OBS counter file: {exc}")

    def _handle_game_changed(self, _index: int) -> None:
        if self._loading or self.controller.is_running():
            return
        selected_game_id = str(self.game_combo.currentData() or "")
        if selected_game_id:
            self.controller.set_active_game_id(selected_game_id)

    def _handle_hunt_changed(self, _index: int) -> None:
        if self._loading or self.controller.is_running():
            return
        selected_hunt_id = str(self.hunt_combo.currentData() or "")
        if not selected_hunt_id:
            return
        try:
            self.controller.set_active_hunt_id(selected_hunt_id)
        except Exception as exc:
            self._show_error(str(exc))
            self._refresh_hunt_selector()

    def _handle_hunt_context_changed(self, _hunt: dict[str, object]) -> None:
        self._refresh_hunt_selector()
        self._update_button_state()

    def _show_error(self, message: str) -> None:
        QMessageBox.warning(self, "Encounter Counter", message)

    def _handle_config_changed(self, config: dict[str, object]) -> None:
        self._refresh_game_selector()
        self._refresh_hunt_selector()
        debug = config.get("debug", {})
        if isinstance(debug, dict) and not self.controller.is_running():
            self.save_debug_checkbox.setChecked(bool(debug.get("save_debug_frames", False)))
            self.verbose_debug_checkbox.setChecked(bool(debug.get("verbose_debug", False)))
        self.increment_spin.setValue(int(config.get("encounter_increment", self.increment_spin.value())))
        self._update_button_state()

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().resizeEvent(event)
        if self._last_capture_event_at and self._encounter_capture_path.exists():
            self._load_encounter_capture(self._last_capture_event_at)
