from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
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

from app.core.display import (
    describe_layout_cell,
    format_monitor_summary,
    get_capture_resolution_preset,
    get_resolution_label,
    get_monitor_resolution_preset,
    normalize_display_setup,
    scale_region_for_resolution,
)
from app.core.modes import get_default_capture_region
from app.services.app_controller import AppController

from .monitor_layout_widget import MonitorLayoutWidget


class CaptureSettingsTab(QWidget):
    def __init__(self, controller: AppController) -> None:
        super().__init__()
        self.controller = controller
        self.region_editors: dict[str, dict[str, QSpinBox]] = {}
        self.page_order: list[str] = []
        self._loading = False
        self._last_capture_resolution_preset = "1440p"
        self._build_ui()
        self._connect_signals()
        self._load_from_config()

    def _build_ui(self) -> None:
        root_layout = QHBoxLayout(self)

        left_panel = QVBoxLayout()
        right_panel = QVBoxLayout()

        display_group = QGroupBox("Display Setup")
        display_layout = QVBoxLayout(display_group)
        display_form = QFormLayout()

        self.screen_count_spin = QSpinBox()
        self.screen_count_spin.setRange(1, 6)

        self.resolution_combo = QComboBox()
        for preset in ("1080p", "1440p", "4k"):
            self.resolution_combo.addItem(f"{preset.upper()} ({get_resolution_label(preset)})", preset)

        self.mixed_resolution_checkbox = QCheckBox("Monitors use different resolutions")

        display_form.addRow("Connected screens", self.screen_count_spin)
        display_form.addRow("Resolution preset", self.resolution_combo)
        display_form.addRow("", self.mixed_resolution_checkbox)

        self.display_help_label = QLabel(
            "Toggle the monitors that are in use, then choose which one should be used for capture. "
            "The capture region fields below are relative to that selected monitor."
        )
        self.display_help_label.setWordWrap(True)

        self.monitor_layout_widget = MonitorLayoutWidget()

        self.layout_status_label = QLabel("Waiting for monitor layout.")
        self.layout_status_label.setWordWrap(True)

        display_layout.addLayout(display_form)
        display_layout.addWidget(self.display_help_label)
        display_layout.addWidget(self.monitor_layout_widget)
        display_layout.addWidget(self.layout_status_label)

        self.mode_tabs = QTabWidget()
        for mode in self.controller.get_modes(include_unimplemented=False):
            page = QWidget()
            page_layout = QVBoxLayout(page)

            mode_hint = QLabel("Region values are relative to the selected capture monitor.")
            mode_hint.setWordWrap(True)

            form_layout = QFormLayout()
            editors: dict[str, QSpinBox] = {}
            for field_name in ("left", "top", "width", "height"):
                spin = QSpinBox()
                spin.setRange(0, 10000)
                if field_name in {"width", "height"}:
                    spin.setRange(1, 10000)
                form_layout.addRow(field_name.title(), spin)
                editors[field_name] = spin

            page_layout.addWidget(mode_hint)
            page_layout.addLayout(form_layout)
            page_layout.addStretch(1)

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

        left_panel.addWidget(display_group)
        left_panel.addWidget(self.mode_tabs, 1)
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

        root_layout.addLayout(left_panel, 2)
        root_layout.addLayout(right_panel, 1)

    def _connect_signals(self) -> None:
        self.test_button.clicked.connect(self._test_screenshot)
        self.save_button.clicked.connect(self._save_regions)
        self.restore_button.clicked.connect(self._restore_defaults)
        self.screen_count_spin.valueChanged.connect(self._apply_screen_count_preset)
        self.resolution_combo.currentIndexChanged.connect(self._handle_resolution_changed)
        self.mixed_resolution_checkbox.toggled.connect(self._handle_mixed_resolution_toggled)
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
        display_setup = normalize_display_setup(config.get("display_setup"))
        self._loading = True
        try:
            self.screen_count_spin.setValue(int(display_setup["screen_count"]))

            preset_index = self.resolution_combo.findData(display_setup["resolution_preset"])
            if preset_index >= 0:
                self.resolution_combo.setCurrentIndex(preset_index)

            self.mixed_resolution_checkbox.setChecked(bool(display_setup["mixed_resolutions"]))
            self.monitor_layout_widget.set_value(display_setup)
            self._last_capture_resolution_preset = get_capture_resolution_preset(display_setup)

            for mode_key, editors in self.region_editors.items():
                region = self.controller.get_mode_region(mode_key)
                for field_name, editor in editors.items():
                    editor.setValue(int(region[field_name]))
        finally:
            self._loading = False

        self._refresh_resolution_controls()
        self._refresh_layout_status()

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

    def _current_display_setup(self) -> dict[str, object]:
        display_setup = self.monitor_layout_widget.value()
        display_setup["screen_count"] = self.screen_count_spin.value()
        display_setup["resolution_preset"] = str(self.resolution_combo.currentData())
        display_setup["mixed_resolutions"] = self.mixed_resolution_checkbox.isChecked()
        return normalize_display_setup(display_setup)

    def _rescale_regions_if_needed(self, new_display_setup: dict[str, object]) -> None:
        new_capture_resolution_preset = get_capture_resolution_preset(new_display_setup)
        if new_capture_resolution_preset == self._last_capture_resolution_preset:
            return

        for editors in self.region_editors.values():
            region = {
                "left": editors["left"].value(),
                "top": editors["top"].value(),
                "width": editors["width"].value(),
                "height": editors["height"].value(),
            }
            scaled = scale_region_for_resolution(
                region,
                from_preset=self._last_capture_resolution_preset,
                to_preset=new_capture_resolution_preset,
            )
            for field_name, editor in editors.items():
                editor.setValue(int(scaled[field_name]))

        self._last_capture_resolution_preset = new_capture_resolution_preset

    def _refresh_resolution_controls(self) -> None:
        mixed_resolutions = self.mixed_resolution_checkbox.isChecked()
        self.resolution_combo.setEnabled(not mixed_resolutions)
        if mixed_resolutions:
            self.display_help_label.setText(
                "Toggle the monitors that are in use, choose the capture monitor, and set a resolution for each active "
                "monitor. The capture region fields below stay relative to the selected capture monitor."
            )
        else:
            self.display_help_label.setText(
                "Toggle the monitors that are in use, then choose which one should be used for capture. "
                "The capture region fields below are relative to that selected monitor."
            )

    def _apply_screen_count_preset(self, value: int) -> None:
        if self._loading:
            return
        self.monitor_layout_widget.apply_screen_count_preset(value)

    def _handle_layout_changed(self, display_setup: dict[str, object]) -> None:
        if self._loading:
            return

        self._loading = True
        try:
            self.screen_count_spin.setValue(int(display_setup["screen_count"]))
        finally:
            self._loading = False

        self._rescale_regions_if_needed(self._current_display_setup())
        self._refresh_layout_status()

    def _handle_resolution_changed(self, _index: int) -> None:
        new_preset = str(self.resolution_combo.currentData())
        if self._loading or not new_preset or self.mixed_resolution_checkbox.isChecked():
            return

        self._rescale_regions_if_needed(self._current_display_setup())
        self.monitor_layout_widget.set_value(self._current_display_setup())
        self._refresh_layout_status()

    def _handle_mixed_resolution_toggled(self, _checked: bool) -> None:
        if self._loading:
            return

        display_setup = self._current_display_setup()
        self.monitor_layout_widget.set_value(display_setup)
        self._refresh_resolution_controls()
        self._rescale_regions_if_needed(display_setup)
        self._refresh_layout_status()

    def _refresh_layout_status(self) -> None:
        display_setup = self._current_display_setup()
        capture_cell = display_setup["capture_cell"]
        capture_label = describe_layout_cell(int(capture_cell["row"]), int(capture_cell["column"]))  # type: ignore[index]
        resolution_preset = str(display_setup["resolution_preset"])
        capture_resolution_preset = get_capture_resolution_preset(display_setup)

        lines = [
            (
                f"Resolution mode: mixed per monitor (capture monitor uses {capture_resolution_preset.upper()} "
                f"/ {get_resolution_label(capture_resolution_preset)})"
                if display_setup["mixed_resolutions"]
                else f"Preset resolution: {resolution_preset.upper()} ({get_resolution_label(resolution_preset)})"
            ),
            f"Capture monitor cell: {capture_label}",
        ]

        physical_monitors = self.controller.get_physical_monitors()
        lines.append(f"Windows detected {len(physical_monitors)} monitor(s).")

        try:
            mapping = self.controller.get_monitor_cell_mapping(display_setup=display_setup)
        except ValueError as exc:
            lines.append(str(exc))
        else:
            for (row, column), monitor in mapping.items():
                monitor_resolution_preset = get_monitor_resolution_preset(display_setup, row=row, column=column)
                lines.append(
                    f"{describe_layout_cell(row, column)} -> {format_monitor_summary(monitor)} | "
                    f"{monitor_resolution_preset.upper()} ({get_resolution_label(monitor_resolution_preset)})"
                )

        self.layout_status_label.setText("\n".join(lines))

    def _test_screenshot(self) -> None:
        try:
            payload = self.controller.capture_test_screenshot(
                mode_key=self._current_mode_key(),
                region=self._current_region(),
                display_setup=self._current_display_setup(),
            )
        except Exception as exc:
            self._show_error(str(exc))
            return
        self._apply_preview(payload)

    def _save_regions(self) -> None:
        self.controller.save_capture_settings(
            display_setup=self._current_display_setup(),
            regions=self._all_regions(),
        )
        QMessageBox.information(self, "Capture Settings", "Display layout and capture regions saved to config.json.")

    def _restore_defaults(self) -> None:
        mode_key = self._current_mode_key()
        resolution_preset = get_capture_resolution_preset(self._current_display_setup())
        region = get_default_capture_region(mode_key, resolution_preset=resolution_preset)
        editors = self.region_editors[mode_key]
        for field_name, editor in editors.items():
            editor.setValue(int(region[field_name]))

    def _apply_preview(self, payload: dict[str, object]) -> None:
        preview_path = Path(str(payload.get("path", self.controller.get_debug_frame_path())))
        self._load_pixmap(preview_path)

        stats = payload.get("stats", {})
        region = payload.get("region", {})
        absolute_region = payload.get("absolute_region", {})
        monitor_summary = str(payload.get("monitor_summary", "Unknown monitor"))
        self.preview_info.setText(
            f"Saved to {preview_path}\n"
            f"Selected monitor: {monitor_summary}\n"
            f"Relative region: {region}\n"
            f"Absolute region: {absolute_region}\n"
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

    def _handle_config_changed(self, config: dict[str, object]) -> None:
        self._apply_config(config)

    def _show_error(self, message: str) -> None:
        QMessageBox.warning(self, "Capture Settings", message)
