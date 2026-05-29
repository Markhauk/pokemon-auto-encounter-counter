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
from app.core.display import format_monitor_summary
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
        self._loading = False

        controls_group = QGroupBox("Scanner Controls")
        controls_layout = QGridLayout(controls_group)

        self.game_combo = QComboBox()
        self.increment_spin = QSpinBox()
        self.increment_spin.setRange(1, 9999)
        self.save_debug_checkbox = QCheckBox("Save last capture while running")
        self.verbose_debug_checkbox = QCheckBox("Verbose debug logging")
        self.start_button = QPushButton("Start")
        self.stop_button = QPushButton("Stop")
        self.status_value = QLabel("Idle")
        self.setup_summary_label = QLabel("")
        self.setup_summary_label.setWordWrap(True)
        self.setup_summary_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        controls_layout.addWidget(QLabel("Game"), 0, 0)
        controls_layout.addWidget(self.game_combo, 0, 1)
        controls_layout.addWidget(QLabel("Encounter increment"), 0, 2)
        controls_layout.addWidget(self.increment_spin, 0, 3)
        controls_layout.addWidget(self.start_button, 0, 4)
        controls_layout.addWidget(self.stop_button, 0, 5)
        controls_layout.addWidget(QLabel("Status"), 1, 0)
        controls_layout.addWidget(self.status_value, 1, 1)
        controls_layout.addWidget(self.save_debug_checkbox, 1, 4)
        controls_layout.addWidget(self.verbose_debug_checkbox, 1, 5)
        controls_layout.addWidget(self.setup_summary_label, 2, 0, 1, 6)

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
        self.active_game_value = QLabel("N/A")
        self.enabled_filters_value = QLabel("0")
        self.last_event_value = QLabel("none")
        self.last_event_at_value = QLabel("N/A")
        self.last_filter_value = QLabel("N/A")
        self.last_filter_event_value = QLabel("N/A")
        self.active_label_value = QLabel("N/A")
        self.capture_region_value = QLabel("N/A")
        self.capture_region_value.setWordWrap(True)

        details_layout.addRow("Active game", self.active_game_value)
        details_layout.addRow("Enabled filters", self.enabled_filters_value)
        details_layout.addRow("Last event", self.last_event_value)
        details_layout.addRow("Last event time", self.last_event_at_value)
        details_layout.addRow("Last filter", self.last_filter_value)
        details_layout.addRow("Last filter type", self.last_filter_event_value)
        details_layout.addRow("Active label", self.active_label_value)
        details_layout.addRow("Last capture region", self.capture_region_value)

        summary_row.addWidget(counters_group, 1)
        summary_row.addWidget(details_group, 1)

        log_group = QGroupBox("Live Runtime Log")
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
        self.game_combo.currentIndexChanged.connect(self._handle_game_changed)

        self.controller.snapshot_changed.connect(self._apply_snapshot)
        self.controller.runtime_status_changed.connect(self._apply_runtime_status)
        self.controller.log_received.connect(self._append_log_message)
        self.controller.error_occurred.connect(self._show_error)
        self.controller.config_changed.connect(self._handle_config_changed)

    def _load_initial_state(self) -> None:
        config = self.controller.get_config()
        self._refresh_game_selector()
        self.increment_spin.setValue(int(config.get("encounter_increment", 1)))
        debug = config.get("debug", {})
        if isinstance(debug, dict):
            self.save_debug_checkbox.setChecked(bool(debug.get("save_debug_frames", False)))
            self.verbose_debug_checkbox.setChecked(bool(debug.get("verbose_debug", False)))

        snapshot = self.controller.build_idle_snapshot()
        self._apply_snapshot(snapshot)
        self._apply_runtime_status(self.controller.get_runtime_status())
        self._refresh_setup_summary()
        self._load_recent_events()

    def _load_recent_events(self) -> None:
        recent_events = self.controller.get_recent_events(limit=12)
        lines = []
        for event in recent_events:
            filter_name = str(event.get("filter_name", "") or event.get("event", ""))
            lines.append(
                f"{event.get('timestamp', '')} | {filter_name} | "
                f"type={event.get('filter_event_type', event.get('event', ''))} | "
                f"encounters={event.get('counter', 0)} | catches={event.get('catch_counter', 0)}"
            )
        self.log_box.setPlainText("\n".join(lines))

    def _refresh_setup_summary(self) -> None:
        display_setup = self.controller.get_display_setup()
        active_game_id = self.controller.get_active_game_id()
        active_game = self.controller.get_game(active_game_id)
        filters = self.controller.get_filters(game_id=active_game_id)
        enabled_filters = [filter_definition for filter_definition in filters if filter_definition.enabled]
        missing_templates = [
            status.filter_name
            for status in self.controller.get_template_statuses(game_id=active_game_id)
            if status.status_label() != "Found"
        ]

        lines = [
            f"Active game: {active_game.name if active_game is not None else active_game_id}",
            f"Enabled filters: {len(enabled_filters)} of {len(filters)}",
        ]

        try:
            monitor = self.controller.get_selected_capture_monitor(display_setup=display_setup)
        except ValueError as exc:
            lines.append(str(exc))
        else:
            lines.append(f"Capture monitor: Monitor {monitor['index']}")
            lines.append(f"Resolved monitor: {format_monitor_summary(monitor)}")

        if missing_templates:
            lines.append(f"Template warnings: {', '.join(missing_templates)}")

        self.setup_summary_label.setText("\n".join(lines))
        self._update_button_state()

    def _apply_snapshot(self, snapshot: dict[str, object]) -> None:
        self.active_game_value.setText(str(snapshot.get("active_game_name", "N/A") or "N/A"))
        self.encounter_value.setText(str(snapshot.get("counter", 0)))
        self.catch_value.setText(str(snapshot.get("catch_counter", 0)))
        self.since_catch_value.setText(str(snapshot.get("encounters_since_last_catch", 0)))
        self.last_score_value.setText(f"{float(snapshot.get('last_match_score', 0.0)):.3f}")
        self.enabled_filters_value.setText(str(snapshot.get("enabled_filter_count", 0)))
        self.last_event_value.setText(str(snapshot.get("last_event", "none")))
        self.last_event_at_value.setText(str(snapshot.get("last_event_at", "N/A") or "N/A"))
        self.last_filter_value.setText(str(snapshot.get("last_filter_name", "N/A") or "N/A"))
        self.last_filter_event_value.setText(str(snapshot.get("last_filter_event_type", "N/A") or "N/A"))
        self.active_label_value.setText(str(snapshot.get("active_label", "N/A") or "N/A"))

        capture_region = snapshot.get("capture_region")
        if isinstance(capture_region, dict):
            self.capture_region_value.setText(capture_region_summary(capture_region))
        else:
            self.capture_region_value.setText("N/A")

    def _apply_runtime_status(self, status: str) -> None:
        self.status_value.setText(status)
        self._update_button_state()

    def _update_button_state(self) -> None:
        running = self.controller.is_running()
        filters = self.controller.get_filters(game_id=self.controller.get_active_game_id())
        enabled_filters = [filter_definition for filter_definition in filters if filter_definition.enabled]
        can_start = bool(enabled_filters) and not running

        self.start_button.setEnabled(can_start)
        self.stop_button.setEnabled(running)
        self.game_combo.setEnabled(not running)
        self.increment_spin.setEnabled(not running)
        self.save_debug_checkbox.setEnabled(not running)
        self.verbose_debug_checkbox.setEnabled(not running)

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

    def _append_log_message(self, payload: dict[str, object]) -> None:
        timestamp = str(payload.get("timestamp", ""))
        message = str(payload.get("message", ""))
        if message:
            self.log_box.appendPlainText(f"[{timestamp}] {message}")

    def _start_scan(self) -> None:
        self.controller.start_scan(
            encounter_increment=self.increment_spin.value(),
            save_debug_frames=self.save_debug_checkbox.isChecked(),
            verbose_debug=self.verbose_debug_checkbox.isChecked(),
        )

    def _handle_game_changed(self, _index: int) -> None:
        if self._loading or self.controller.is_running():
            return
        selected_game_id = str(self.game_combo.currentData() or "")
        if selected_game_id:
            self.controller.set_active_game_id(selected_game_id)

    def _show_error(self, message: str) -> None:
        QMessageBox.warning(self, "Encounter Counter", message)

    def _handle_config_changed(self, config: dict[str, object]) -> None:
        self._refresh_game_selector()
        debug = config.get("debug", {})
        if isinstance(debug, dict) and not self.controller.is_running():
            self.save_debug_checkbox.setChecked(bool(debug.get("save_debug_frames", False)))
            self.verbose_debug_checkbox.setChecked(bool(debug.get("verbose_debug", False)))
        self.increment_spin.setValue(int(config.get("encounter_increment", self.increment_spin.value())))
        self._refresh_setup_summary()
