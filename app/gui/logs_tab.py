from __future__ import annotations

from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app.services.app_controller import AppController

from .frame_styles import mark_as_interface_frame


class LogsTab(QWidget):
    def __init__(self, controller: AppController) -> None:
        super().__init__()
        self.controller = controller
        self._build_ui()
        self._connect_signals()
        self.refresh()

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)

        summary_group = QGroupBox("Logs and State")
        mark_as_interface_frame(summary_group)
        summary_layout = QFormLayout(summary_group)
        self.current_counter_value = QLabel("0")
        self.current_catch_value = QLabel("0")
        self.current_event_value = QLabel("none")
        self.current_game_value = QLabel("N/A")
        self.current_hunt_value = QLabel("N/A")
        self.current_hunt_counter_value = QLabel("0")
        self.current_hunt_catch_value = QLabel("0")
        self.current_session_value = QLabel("N/A")
        self.current_session_counter_value = QLabel("0")
        self.current_filter_value = QLabel("N/A")
        self.current_label_value = QLabel("N/A")
        self.output_dir_value = QLabel(self.controller.get_output_dir())
        self.output_dir_value.setWordWrap(True)
        summary_layout.addRow("All-time encounters", self.current_counter_value)
        summary_layout.addRow("All-time catches", self.current_catch_value)
        summary_layout.addRow("Game", self.current_game_value)
        summary_layout.addRow("Hunt", self.current_hunt_value)
        summary_layout.addRow("Hunt encounters", self.current_hunt_counter_value)
        summary_layout.addRow("Hunt catches", self.current_hunt_catch_value)
        summary_layout.addRow("Session", self.current_session_value)
        summary_layout.addRow("Session encounters", self.current_session_counter_value)
        summary_layout.addRow("Last event", self.current_event_value)
        summary_layout.addRow("Last filter", self.current_filter_value)
        summary_layout.addRow("Active label", self.current_label_value)
        summary_layout.addRow("Output folder", self.output_dir_value)

        button_row = QHBoxLayout()
        self.refresh_button = QPushButton("Refresh")
        self.open_output_button = QPushButton("Open Output Folder")
        button_row.addWidget(self.refresh_button)
        button_row.addWidget(self.open_output_button)
        button_row.addStretch(1)

        splitter = QSplitter()
        self.events_view = QPlainTextEdit()
        self.events_view.setReadOnly(True)
        self.raw_state_view = QPlainTextEdit()
        self.raw_state_view.setReadOnly(True)
        splitter.addWidget(self.events_view)
        splitter.addWidget(self.raw_state_view)
        splitter.setSizes([700, 500])

        root_layout.addWidget(summary_group)
        root_layout.addLayout(button_row)
        root_layout.addWidget(splitter, 1)

    def _connect_signals(self) -> None:
        self.refresh_button.clicked.connect(self.refresh)
        self.open_output_button.clicked.connect(self._open_output_folder)
        self.controller.snapshot_changed.connect(self._apply_snapshot)
        self.controller.log_received.connect(self._append_live_log)

    def refresh(self) -> None:
        state = self.controller.get_state_dict()
        self._apply_snapshot(state)
        self.raw_state_view.setPlainText(self.controller.get_state_text())

        recent_events = self.controller.get_recent_events(limit=50)
        lines = []
        for event in recent_events:
            lines.append(
                f"{event.get('timestamp', '')} | {event.get('filter_name', event.get('event', ''))} | "
                f"type={event.get('filter_event_type', event.get('event', ''))} | "
                f"game={event.get('game_name', event.get('game_id', ''))} | "
                f"hunt={event.get('hunt_name', '')} | "
                f"session=#{event.get('session_number', 0)} | "
                f"hunt_encounters={event.get('hunt_encounter_count', 0)} | "
                f"all_time={event.get('counter', 0)} | catches={event.get('catch_counter', 0)} | "
                f"+{event.get('encounter_increment', 1)} | "
                f"region=({event.get('capture_left', 0)}, {event.get('capture_top', 0)}, "
                f"{event.get('capture_width', 0)}, {event.get('capture_height', 0)})"
            )
        self.events_view.setPlainText("\n".join(lines))

    def _apply_snapshot(self, snapshot: dict[str, object]) -> None:
        self.current_counter_value.setText(str(snapshot.get("counter", 0)))
        self.current_catch_value.setText(str(snapshot.get("catch_counter", 0)))
        self.current_event_value.setText(str(snapshot.get("last_event", "none")))
        self.current_game_value.setText(
            str(snapshot.get("game_name", snapshot.get("active_game_name", "N/A")) or "N/A")
        )
        self.current_hunt_value.setText(str(snapshot.get("hunt_name", "N/A") or "N/A"))
        self.current_hunt_counter_value.setText(str(snapshot.get("hunt_encounter_count", 0)))
        self.current_hunt_catch_value.setText(str(snapshot.get("hunt_catch_counter", 0)))
        session_number = int(snapshot.get("session_number", 0))
        self.current_session_value.setText(f"#{session_number}" if session_number else "N/A")
        self.current_session_counter_value.setText(str(snapshot.get("session_encounter_count", 0)))
        self.current_filter_value.setText(str(snapshot.get("last_filter_name", "N/A") or "N/A"))
        self.current_label_value.setText(str(snapshot.get("active_label", "N/A") or "N/A"))

    def _append_live_log(self, payload: dict[str, object]) -> None:
        timestamp = str(payload.get("timestamp", ""))
        message = str(payload.get("message", ""))
        if message:
            self.events_view.appendPlainText(f"[runtime {timestamp}] {message}")

    def _open_output_folder(self) -> None:
        try:
            self.controller.open_output_folder()
        except Exception as exc:
            QMessageBox.warning(self, "Logs and State", str(exc))
