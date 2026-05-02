from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.core.capture import capture_region_summary
from app.core.modes import MODE_SOFT_RESET_KEY
from app.services.app_controller import AppController


class DashboardTab(QWidget):
    def __init__(self, controller: AppController) -> None:
        super().__init__()
        self.controller = controller
        self._build_ui()
        self._connect_signals()
        self._load_initial_state()

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)

        controls_group = QGroupBox("Controls")
        controls_layout = QGridLayout(controls_group)

        self.mode_combo = QComboBox()
        for mode in self.controller.get_modes(include_unimplemented=True):
            label = mode.name if mode.implemented else f"{mode.name} (Not implemented)"
            self.mode_combo.addItem(label, mode.key)

        self.increment_spin = QSpinBox()
        self.increment_spin.setRange(1, 9999)

        self.save_debug_checkbox = QCheckBox("Save last capture while running")
        self.verbose_debug_checkbox = QCheckBox("Verbose debug logging")

        self.start_button = QPushButton("Start")
        self.stop_button = QPushButton("Stop")
        self.status_value = QLabel("Idle")
        self.mode_hint = QLabel("")
        self.mode_hint.setWordWrap(True)
        self.mode_hint.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        controls_layout.addWidget(QLabel("Mode"), 0, 0)
        controls_layout.addWidget(self.mode_combo, 0, 1)
        controls_layout.addWidget(QLabel("Encounter increment"), 0, 2)
        controls_layout.addWidget(self.increment_spin, 0, 3)
        controls_layout.addWidget(self.start_button, 0, 4)
        controls_layout.addWidget(self.stop_button, 0, 5)
        controls_layout.addWidget(QLabel("Status"), 1, 0)
        controls_layout.addWidget(self.status_value, 1, 1)
        controls_layout.addWidget(self.save_debug_checkbox, 1, 2, 1, 2)
        controls_layout.addWidget(self.verbose_debug_checkbox, 1, 4, 1, 2)
        controls_layout.addWidget(self.mode_hint, 2, 0, 1, 6)

        summary_row = QHBoxLayout()

        counters_group = QGroupBox("Counters")
        counters_layout = QFormLayout(counters_group)
        self.encounter_value = QLabel("0")
        self.catch_value = QLabel("0")
        self.since_catch_value = QLabel("0")
        self.last_score_value = QLabel("0.000")
        counters_layout.addRow("Encounters", self.encounter_value)
        counters_layout.addRow("Catches", self.catch_value)
        counters_layout.addRow("Since last catch", self.since_catch_value)
        counters_layout.addRow("Last match score", self.last_score_value)

        details_group = QGroupBox("Live Details")
        details_layout = QFormLayout(details_group)
        self.last_event_value = QLabel("none")
        self.last_event_at_value = QLabel("N/A")
        self.current_mode_value = QLabel("N/A")
        self.capture_region_value = QLabel("N/A")
        self.capture_region_value.setWordWrap(True)
        details_layout.addRow("Last event", self.last_event_value)
        details_layout.addRow("Last event time", self.last_event_at_value)
        details_layout.addRow("Engine mode", self.current_mode_value)
        details_layout.addRow("Capture region", self.capture_region_value)

        summary_row.addWidget(counters_group, 1)
        summary_row.addWidget(details_group, 1)

        log_group = QGroupBox("Live Event Log")
        log_layout = QVBoxLayout(log_group)
        self.log_box = QPlainTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.document().setMaximumBlockCount(200)
        log_layout.addWidget(self.log_box)

        root_layout.addWidget(controls_group)
        root_layout.addLayout(summary_row)
        root_layout.addWidget(log_group, 1)

    def _connect_signals(self) -> None:
        self.start_button.clicked.connect(self._start_scan)
        self.stop_button.clicked.connect(self.controller.stop_scan)
        self.mode_combo.currentIndexChanged.connect(self._refresh_mode_hint)

        self.controller.snapshot_changed.connect(self._apply_snapshot)
        self.controller.runtime_status_changed.connect(self._apply_runtime_status)
        self.controller.log_received.connect(self._append_log_message)
        self.controller.error_occurred.connect(self._show_error)
        self.controller.config_changed.connect(self._handle_config_changed)

    def _load_initial_state(self) -> None:
        config = self.controller.get_config()
        mode_key = str(config.get("last_selected_mode", "random_grass"))
        index = self.mode_combo.findData(mode_key)
        if index >= 0:
            self.mode_combo.setCurrentIndex(index)

        self.increment_spin.setValue(int(config.get("encounter_increment", 1)))
        debug = config.get("debug", {})
        if isinstance(debug, dict):
            self.save_debug_checkbox.setChecked(bool(debug.get("save_debug_frames", False)))
            self.verbose_debug_checkbox.setChecked(bool(debug.get("verbose_debug", False)))

        snapshot = self.controller.build_idle_snapshot()
        self._apply_snapshot(snapshot)
        self._apply_runtime_status(self.controller.get_runtime_status())
        self._refresh_mode_hint()
        self._load_recent_events()

    def _load_recent_events(self) -> None:
        recent_events = self.controller.get_recent_events(limit=12)
        lines = []
        for event in recent_events:
            lines.append(
                f"{event.get('timestamp', '')} | {event.get('event', '')} | "
                f"encounters={event.get('counter', 0)} | catches={event.get('catch_counter', 0)} | "
                f"+{event.get('encounter_increment', 1)}"
            )
        self.log_box.setPlainText("\n".join(lines))

    def _selected_mode_key(self) -> str:
        return str(self.mode_combo.currentData())

    def _refresh_mode_hint(self) -> None:
        mode = self.controller.get_mode(self._selected_mode_key())
        region = self.controller.get_mode_region(mode.key)
        template_statuses = [
            status
            for status in self.controller.get_template_statuses()
            if status.mode_key == mode.key
        ]
        problems = [status.filename for status in template_statuses if status.status_label() != "Found"]

        if mode.key == MODE_SOFT_RESET_KEY:
            message = "Soft reset is present in the UI as a future mode, but it is disabled in v1."
        elif problems:
            message = (
                f"{mode.description}\nMissing or unreadable templates: {', '.join(problems)}."
            )
        else:
            message = mode.description

        message = f"{message}\nConfigured region: {capture_region_summary(region)}"
        self.mode_hint.setText(message)
        self.capture_region_value.setText(capture_region_summary(region))
        self._update_button_state()

    def _apply_snapshot(self, snapshot: dict[str, object]) -> None:
        self.encounter_value.setText(str(snapshot.get("counter", 0)))
        self.catch_value.setText(str(snapshot.get("catch_counter", 0)))
        self.since_catch_value.setText(str(snapshot.get("encounters_since_last_catch", 0)))
        self.last_score_value.setText(f"{float(snapshot.get('last_match_score', 0.0)):.3f}")
        self.last_event_value.setText(str(snapshot.get("last_event", "none")))
        self.last_event_at_value.setText(str(snapshot.get("last_event_at", "N/A") or "N/A"))
        self.current_mode_value.setText(str(snapshot.get("mode_name", "N/A")))

        capture_region = snapshot.get("capture_region")
        if isinstance(capture_region, dict):
            self.capture_region_value.setText(capture_region_summary(capture_region))

    def _apply_runtime_status(self, status: str) -> None:
        self.status_value.setText(status)
        self._update_button_state()

    def _update_button_state(self) -> None:
        running = self.controller.is_running()
        selected_mode_key = self._selected_mode_key()
        can_start = self.controller.mode_is_enabled(selected_mode_key) and not running

        self.start_button.setEnabled(can_start)
        self.stop_button.setEnabled(running)
        self.mode_combo.setEnabled(not running)
        self.increment_spin.setEnabled(not running)
        self.save_debug_checkbox.setEnabled(not running)
        self.verbose_debug_checkbox.setEnabled(not running)

    def _append_log_message(self, payload: dict[str, object]) -> None:
        timestamp = str(payload.get("timestamp", ""))
        message = str(payload.get("message", ""))
        if not message:
            return
        self.log_box.appendPlainText(f"[{timestamp}] {message}")

    def _start_scan(self) -> None:
        self.controller.start_scan(
            mode_key=self._selected_mode_key(),
            encounter_increment=self.increment_spin.value(),
            save_debug_frames=self.save_debug_checkbox.isChecked(),
            verbose_debug=self.verbose_debug_checkbox.isChecked(),
        )

    def _show_error(self, message: str) -> None:
        QMessageBox.warning(self, "Encounter Counter", message)

    def _handle_config_changed(self, _config: dict[str, object]) -> None:
        self._refresh_mode_hint()
