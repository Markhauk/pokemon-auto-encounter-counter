from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.core.display import normalize_display_setup
from app.services.app_controller import AppController

from .frame_styles import mark_as_interface_frame


class CaptureSettingsTab(QWidget):
    def __init__(self, controller: AppController) -> None:
        super().__init__()
        self.controller = controller
        self._loading = False
        self._preview_pending_when_shown = True
        self._preview_path: Path | None = None
        self._monitors: list[dict[str, int]] = []
        self._build_ui()
        self._connect_signals()
        self._load_monitors()

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)

        monitor_group = QGroupBox("Capture Monitor")
        mark_as_interface_frame(monitor_group)
        monitor_layout = QHBoxLayout(monitor_group)

        self.monitor_count_label = QLabel("Detecting monitors...")
        self.monitor_count_label.setStyleSheet("font-size: 14px; font-weight: 600;")
        self.active_monitor_label = QLabel("Active monitor")
        self.monitor_combo = QComboBox()
        self.monitor_combo.setMinimumWidth(180)
        self.detect_button = QPushButton("Detect Again")

        monitor_layout.addWidget(self.monitor_count_label)
        monitor_layout.addStretch(1)
        monitor_layout.addWidget(self.active_monitor_label)
        monitor_layout.addWidget(self.monitor_combo)
        monitor_layout.addWidget(self.detect_button)

        preview_group = QGroupBox("Full Monitor Preview")
        mark_as_interface_frame(preview_group)
        preview_layout = QVBoxLayout(preview_group)

        self.preview_label = QLabel("Open this tab to preview the active monitor.")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(640, 360)
        self.preview_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self.preview_label.setStyleSheet("border: 1px solid #666;")
        preview_layout.addWidget(self.preview_label, 1)

        preview_footer = QHBoxLayout()
        self.preview_info = QLabel("No preview available.")
        self.preview_info.setStyleSheet("color: #b8b8b8;")
        self.refresh_preview_button = QPushButton("Refresh Preview")
        preview_footer.addWidget(self.preview_info)
        preview_footer.addStretch(1)
        preview_footer.addWidget(self.refresh_preview_button)
        preview_layout.addLayout(preview_footer)

        root_layout.addWidget(monitor_group)
        root_layout.addWidget(preview_group, 1)

    def _connect_signals(self) -> None:
        self.monitor_combo.currentIndexChanged.connect(self._handle_monitor_changed)
        self.detect_button.clicked.connect(self._detect_again)
        self.refresh_preview_button.clicked.connect(self._capture_full_monitor_preview)
        self.controller.config_changed.connect(self._handle_config_changed)

    def _load_monitors(self) -> None:
        self._monitors = self.controller.get_physical_monitors()
        display_setup = normalize_display_setup(
            self.controller.get_display_setup(),
            physical_monitors=self._monitors,
        )
        selected_index = int(display_setup["capture_monitor_index"])

        self._loading = True
        try:
            self.monitor_combo.clear()
            for monitor in self._monitors:
                monitor_index = int(monitor["index"])
                self.monitor_combo.addItem(f"Monitor {monitor_index}", monitor_index)
            combo_index = self.monitor_combo.findData(selected_index)
            if combo_index >= 0:
                self.monitor_combo.setCurrentIndex(combo_index)
        finally:
            self._loading = False

        count = len(self._monitors)
        noun = "monitor" if count == 1 else "monitors"
        self.monitor_count_label.setText(f"{count} {noun} connected")
        has_monitors = bool(self._monitors)
        self.monitor_combo.setEnabled(has_monitors)
        self.refresh_preview_button.setEnabled(has_monitors)
        if not has_monitors:
            self.preview_label.clear()
            self.preview_label.setText("No monitors detected.")
            self.preview_info.clear()

    def _current_display_setup(self) -> dict[str, object]:
        monitor_index = self.monitor_combo.currentData()
        return {"capture_monitor_index": int(monitor_index or 1)}

    def _handle_monitor_changed(self, _index: int) -> None:
        if self._loading or not self._monitors:
            return
        self.controller.save_capture_settings(display_setup=self._current_display_setup())
        self._capture_full_monitor_preview()

    def _detect_again(self) -> None:
        self._load_monitors()
        if self._monitors:
            self._capture_full_monitor_preview()

    def _capture_full_monitor_preview(self) -> None:
        if not self._monitors:
            return
        monitor_index = int(self.monitor_combo.currentData() or 0)
        self.preview_label.clear()
        self.preview_label.setText(f"Capturing Monitor {monitor_index}...")
        self.preview_info.clear()
        try:
            payload = self.controller.capture_monitor_preview(
                display_setup=self._current_display_setup()
            )
        except Exception as exc:
            self.preview_label.setText("Monitor preview could not be captured.")
            self.preview_info.setText(str(exc))
            return

        self._preview_path = Path(str(payload["path"]))
        self._load_pixmap(self._preview_path)
        self.preview_info.setText(f"Full-screen preview of Monitor {payload['monitor_index']}")

    def _load_pixmap(self, path: Path) -> None:
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self.preview_label.clear()
            self.preview_label.setText("The monitor preview image could not be loaded.")
            return
        self.preview_label.setPixmap(
            pixmap.scaled(
                self.preview_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def showEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().showEvent(event)
        if self._preview_pending_when_shown and self._monitors:
            self._preview_pending_when_shown = False
            QTimer.singleShot(100, self._capture_if_visible)

    def _capture_if_visible(self) -> None:
        if self.isVisible():
            self._capture_full_monitor_preview()
        else:
            self._preview_pending_when_shown = True

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().resizeEvent(event)
        if self._preview_path is not None and self._preview_path.exists():
            self._load_pixmap(self._preview_path)

    def _handle_config_changed(self, _config: dict[str, object]) -> None:
        if not self._loading:
            self._load_monitors()
