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
        summary_layout = QFormLayout(summary_group)
        self.current_counter_value = QLabel("0")
        self.current_catch_value = QLabel("0")
        self.current_event_value = QLabel("none")
        self.current_mode_value = QLabel("N/A")
        self.output_dir_value = QLabel(self.controller.get_output_dir())
        self.output_dir_value.setWordWrap(True)
        summary_layout.addRow("Current counter", self.current_counter_value)
        summary_layout.addRow("Current catch counter", self.current_catch_value)
        summary_layout.addRow("Last event", self.current_event_value)
        summary_layout.addRow("Current mode", self.current_mode_value)
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
                f"{event.get('timestamp', '')} | {event.get('event', '')} | "
                f"encounters={event.get('counter', 0)} | catches={event.get('catch_counter', 0)} | "
                f"+{event.get('encounter_increment', 1)} | "
                f"region=({event.get('capture_left', 0)}, {event.get('capture_top', 0)}, "
                f"{event.get('capture_width', 0)}, {event.get('capture_height', 0)})"
            )
        self.events_view.setPlainText("\n".join(lines))

    def _apply_snapshot(self, snapshot: dict[str, object]) -> None:
        self.current_counter_value.setText(str(snapshot.get("counter", 0)))
        self.current_catch_value.setText(str(snapshot.get("catch_counter", 0)))
        self.current_event_value.setText(str(snapshot.get("last_event", "none")))
        self.current_mode_value.setText(str(snapshot.get("mode_name", "N/A")))

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
