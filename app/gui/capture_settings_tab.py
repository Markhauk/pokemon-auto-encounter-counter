from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.core.display import format_monitor_summary, normalize_display_setup
from app.services.app_controller import AppController

from .monitor_layout_widget import MonitorLayoutWidget


class CaptureSettingsTab(QWidget):
    def __init__(self, controller: AppController) -> None:
        super().__init__()
        self.controller = controller
        self._loading = False
        self._build_ui()
        self._connect_signals()
        self._load_from_config()

    def _build_ui(self) -> None:
        root_layout = QHBoxLayout(self)

        left_panel = QVBoxLayout()
        right_panel = QVBoxLayout()

        display_group = QGroupBox("Display Setup")
        display_layout = QVBoxLayout(display_group)

        self.display_help_label = QLabel(
            "Detected monitors are shown below. Choose the monitor used for capture. "
            "Filter regions stay relative to that capture monitor."
        )
        self.display_help_label.setWordWrap(True)

        self.monitor_count_label = QLabel("Detecting monitors...")
        self.monitor_count_label.setWordWrap(True)

        self.monitor_layout_widget = MonitorLayoutWidget()
        self.layout_status_label = QLabel("Waiting for monitor detection.")
        self.layout_status_label.setWordWrap(True)

        button_row = QHBoxLayout()
        self.save_button = QPushButton("Save Display Setup")
        self.refresh_button = QPushButton("Refresh")
        button_row.addWidget(self.save_button)
        button_row.addWidget(self.refresh_button)
        button_row.addStretch(1)

        display_layout.addWidget(self.display_help_label)
        display_layout.addWidget(self.monitor_count_label)
        display_layout.addWidget(self.monitor_layout_widget)
        display_layout.addWidget(self.layout_status_label)
        display_layout.addLayout(button_row)

        preview_group = QGroupBox("Last Preview")
        preview_layout = QVBoxLayout(preview_group)
        self.preview_label = QLabel("Use the Filters tab to capture a preview for a selected filter.")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(420, 240)
        self.preview_label.setStyleSheet("border: 1px solid #666;")
        self.preview_info = QLabel("No preview available.")
        self.preview_info.setWordWrap(True)
        preview_layout.addWidget(self.preview_label)
        preview_layout.addWidget(self.preview_info)

        left_panel.addWidget(display_group, 1)
        right_panel.addWidget(preview_group, 1)

        root_layout.addLayout(left_panel, 2)
        root_layout.addLayout(right_panel, 1)

    def _connect_signals(self) -> None:
        self.save_button.clicked.connect(self._save_display_setup)
        self.refresh_button.clicked.connect(self._load_from_config)
        self.monitor_layout_widget.value_changed.connect(self._handle_layout_changed)
        self.controller.preview_captured.connect(self._apply_preview)
        self.controller.config_changed.connect(self._handle_config_changed)
        self.controller.error_occurred.connect(self._show_error)

    def _load_from_config(self) -> None:
        self._apply_config(self.controller.get_config())
        preview_path = Path(self.controller.get_debug_frame_path())
        if preview_path.exists():
            self._load_pixmap(preview_path)
            self.preview_info.setText(f"Preview path: {preview_path}")

    def _apply_config(self, config: dict[str, object]) -> None:
        physical_monitors = self.controller.get_physical_monitors()
        display_setup = normalize_display_setup(
            config.get("display_setup"),
            physical_monitors=physical_monitors,
        )

        self._loading = True
        try:
            self.monitor_layout_widget.set_value(
                display_setup,
                physical_monitors=physical_monitors,
            )
        finally:
            self._loading = False

        self._refresh_layout_status()

    def _current_display_setup(self) -> dict[str, object]:
        physical_monitors = self.controller.get_physical_monitors()
        return normalize_display_setup(
            self.monitor_layout_widget.value(),
            physical_monitors=physical_monitors,
        )

    def _handle_layout_changed(self, _display_setup: dict[str, object]) -> None:
        if self._loading:
            return
        self._refresh_layout_status()

    def _refresh_layout_status(self) -> None:
        physical_monitors = self.controller.get_physical_monitors()
        display_setup = normalize_display_setup(
            self._current_display_setup(),
            physical_monitors=physical_monitors,
        )

        monitor_count = len(physical_monitors)
        self.monitor_count_label.setText(f"Windows detected {monitor_count} monitor(s).")

        if not physical_monitors:
            self.layout_status_label.setText("No monitors were detected by Windows.")
            return

        selected_monitor = self.controller.get_selected_capture_monitor(display_setup=display_setup)
        lines = [
            f"Capture monitor: Monitor {selected_monitor['index']}",
            f"Selected monitor details: {format_monitor_summary(selected_monitor)}",
            "",
            "Detected monitors:",
        ]
        for monitor in physical_monitors:
            prefix = "[Capture] " if int(monitor["index"]) == int(selected_monitor["index"]) else ""
            lines.append(f"{prefix}{format_monitor_summary(monitor)}")

        self.layout_status_label.setText("\n".join(lines))

    def _save_display_setup(self) -> None:
        self.controller.save_capture_settings(display_setup=self._current_display_setup())
        QMessageBox.information(self, "Capture Settings", "Display setup saved to config.json.")

    def _apply_preview(self, payload: dict[str, object]) -> None:
        preview_path = Path(str(payload.get("path", self.controller.get_debug_frame_path())))
        self._load_pixmap(preview_path)
        self.preview_info.setText(
            f"Filter: {payload.get('filter_name', '')}\n"
            f"Monitor: {payload.get('monitor_summary', '')}\n"
            f"Relative region: {payload.get('region', {})}\n"
            f"Absolute region: {payload.get('absolute_region', {})}\n"
            f"Stats: {payload.get('stats', {})}"
        )

    def _load_pixmap(self, path: Path) -> None:
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self.preview_label.setText(f"Could not load preview image from {path}")
            return
        self.preview_label.setPixmap(
            pixmap.scaled(
                self.preview_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().resizeEvent(event)
        preview_path = Path(self.controller.get_debug_frame_path())
        if preview_path.exists():
            self._load_pixmap(preview_path)

    def _handle_config_changed(self, config: dict[str, object]) -> None:
        self._apply_config(config)

    def _show_error(self, message: str) -> None:
        QMessageBox.warning(self, "Capture Settings", message)
