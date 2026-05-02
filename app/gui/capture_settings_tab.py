from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.services.app_controller import AppController


class CaptureSettingsTab(QWidget):
    def __init__(self, controller: AppController) -> None:
        super().__init__()
        self.controller = controller
        self.region_editors: dict[str, dict[str, QSpinBox]] = {}
        self.page_order: list[str] = []
        self._build_ui()
        self._connect_signals()
        self._load_from_config()

    def _build_ui(self) -> None:
        root_layout = QHBoxLayout(self)

        left_panel = QVBoxLayout()
        right_panel = QVBoxLayout()

        self.mode_tabs = QTabWidget()
        for mode in self.controller.get_modes(include_unimplemented=False):
            page = QWidget()
            page_layout = QFormLayout(page)
            editors: dict[str, QSpinBox] = {}
            for field_name in ("left", "top", "width", "height"):
                spin = QSpinBox()
                spin.setRange(0, 10000)
                if field_name in {"width", "height"}:
                    spin.setRange(1, 10000)
                page_layout.addRow(field_name.title(), spin)
                editors[field_name] = spin

            self.region_editors[mode.key] = editors
            self.page_order.append(mode.key)
            self.mode_tabs.addTab(page, mode.name)

        button_row = QHBoxLayout()
        self.test_button = QPushButton("Test Screenshot")
        self.save_button = QPushButton("Save Settings")
        self.restore_button = QPushButton("Restore Defaults")

        button_row.addWidget(self.test_button)
        button_row.addWidget(self.save_button)
        button_row.addWidget(self.restore_button)

        left_panel.addWidget(self.mode_tabs)
        left_panel.addLayout(button_row)

        preview_group = QGroupBox("Last Capture Preview")
        preview_layout = QVBoxLayout(preview_group)
        self.preview_label = QLabel("Run a test screenshot to update the preview.")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(420, 240)
        self.preview_label.setStyleSheet("border: 1px solid #666;")
        self.preview_info = QLabel("No preview captured yet.")
        self.preview_info.setWordWrap(True)

        preview_layout.addWidget(self.preview_label)
        preview_layout.addWidget(self.preview_info)

        right_panel.addWidget(preview_group)
        right_panel.addStretch(1)

        root_layout.addLayout(left_panel, 1)
        root_layout.addLayout(right_panel, 1)

    def _connect_signals(self) -> None:
        self.test_button.clicked.connect(self._test_screenshot)
        self.save_button.clicked.connect(self._save_regions)
        self.restore_button.clicked.connect(self._restore_defaults)

        self.controller.preview_captured.connect(self._apply_preview)
        self.controller.config_changed.connect(self._handle_config_changed)
        self.controller.error_occurred.connect(self._show_error)

    def _load_from_config(self) -> None:
        config = self.controller.get_config()
        for mode_key, editors in self.region_editors.items():
            region = self.controller.get_mode_region(mode_key)
            for field_name, editor in editors.items():
                editor.setValue(int(region[field_name]))

        preview_path = Path(self.controller.get_debug_frame_path())
        if preview_path.exists():
            self._load_pixmap(preview_path)
            self.preview_info.setText(f"Preview path: {preview_path}")

    def _current_mode_key(self) -> str:
        return self.page_order[self.mode_tabs.currentIndex()]

    def _current_region(self) -> dict[str, int]:
        editors = self.region_editors[self._current_mode_key()]
        return {
            "left": editors["left"].value(),
            "top": editors["top"].value(),
            "width": editors["width"].value(),
            "height": editors["height"].value(),
        }

    def _all_regions(self) -> dict[str, dict[str, int]]:
        regions: dict[str, dict[str, int]] = {}
        for mode_key, editors in self.region_editors.items():
            regions[mode_key] = {
                "left": editors["left"].value(),
                "top": editors["top"].value(),
                "width": editors["width"].value(),
                "height": editors["height"].value(),
            }
        return regions

    def _test_screenshot(self) -> None:
        payload = self.controller.capture_test_screenshot(
            mode_key=self._current_mode_key(),
            region=self._current_region(),
        )
        self._apply_preview(payload)

    def _save_regions(self) -> None:
        self.controller.save_capture_regions(self._all_regions())
        QMessageBox.information(self, "Capture Settings", "Capture settings saved to config.json.")

    def _restore_defaults(self) -> None:
        mode_key = self._current_mode_key()
        region = self.controller.restore_default_region(mode_key)
        editors = self.region_editors[mode_key]
        for field_name, editor in editors.items():
            editor.setValue(int(region[field_name]))

    def _apply_preview(self, payload: dict[str, object]) -> None:
        preview_path = Path(str(payload.get("path", self.controller.get_debug_frame_path())))
        self._load_pixmap(preview_path)

        stats = payload.get("stats", {})
        region = payload.get("region", {})
        self.preview_info.setText(
            f"Saved to {preview_path}\n"
            f"Region: {region}\n"
            f"Stats: {stats}"
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

    def _handle_config_changed(self, _config: dict[str, object]) -> None:
        for mode_key, editors in self.region_editors.items():
            region = self.controller.get_mode_region(mode_key)
            for field_name, editor in editors.items():
                if editor.value() != int(region[field_name]):
                    editor.setValue(int(region[field_name]))

    def _show_error(self, message: str) -> None:
        QMessageBox.warning(self, "Capture Settings", message)
