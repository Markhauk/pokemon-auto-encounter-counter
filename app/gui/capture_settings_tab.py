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
    QVBoxLayout,
    QWidget,
)

from app.core.display import (
    describe_layout_cell,
    format_monitor_summary,
    get_capture_resolution_preset,
    get_monitor_resolution_preset,
    get_resolution_label,
    normalize_display_setup,
    scale_region_for_resolution,
)
from app.services.app_controller import AppController

from .monitor_layout_widget import MonitorLayoutWidget


class CaptureSettingsTab(QWidget):
    def __init__(self, controller: AppController) -> None:
        super().__init__()
        self.controller = controller
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
            "Configure the active monitors, then choose which one is used for capture. "
            "Filter regions are relative to that capture monitor."
        )
        self.display_help_label.setWordWrap(True)

        self.monitor_layout_widget = MonitorLayoutWidget()
        self.layout_status_label = QLabel("Waiting for monitor layout.")
        self.layout_status_label.setWordWrap(True)

        button_row = QHBoxLayout()
        self.save_button = QPushButton("Save Display Setup")
        self.refresh_button = QPushButton("Refresh")
        button_row.addWidget(self.save_button)
        button_row.addWidget(self.refresh_button)
        button_row.addStretch(1)

        display_layout.addLayout(display_form)
        display_layout.addWidget(self.display_help_label)
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
        finally:
            self._loading = False

        self._refresh_resolution_controls()
        self._refresh_layout_status()

    def _current_display_setup(self) -> dict[str, object]:
        display_setup = self.monitor_layout_widget.value()
        display_setup["screen_count"] = self.screen_count_spin.value()
        display_setup["resolution_preset"] = str(self.resolution_combo.currentData())
        display_setup["mixed_resolutions"] = self.mixed_resolution_checkbox.isChecked()
        return normalize_display_setup(display_setup)

    def _refresh_resolution_controls(self) -> None:
        mixed_resolutions = self.mixed_resolution_checkbox.isChecked()
        self.resolution_combo.setEnabled(not mixed_resolutions)
        if mixed_resolutions:
            self.display_help_label.setText(
                "Configure active monitors, choose the capture monitor, and assign per-monitor resolutions. "
                "Filter regions stay relative to that capture monitor."
            )
        else:
            self.display_help_label.setText(
                "Configure active monitors, then choose which one is used for capture. "
                "All filter regions stay relative to that capture monitor."
            )

    def _rescale_filters_if_needed(self, display_setup: dict[str, object]) -> None:
        new_capture_resolution_preset = get_capture_resolution_preset(display_setup)
        if new_capture_resolution_preset == self._last_capture_resolution_preset:
            return

        rewritten_filters = []
        for filter_definition in self.controller.get_filters():
            rewritten_filters.append(
                filter_definition.__class__(
                    id=filter_definition.id,
                    name=filter_definition.name,
                    enabled=filter_definition.enabled,
                    event_type=filter_definition.event_type,
                    template_path=filter_definition.template_path,
                    capture_region=scale_region_for_resolution(
                        filter_definition.capture_region,
                        from_preset=self._last_capture_resolution_preset,
                        to_preset=new_capture_resolution_preset,
                    ),
                    threshold=filter_definition.threshold,
                    built_in=filter_definition.built_in,
                    description=filter_definition.description,
                    metadata=dict(filter_definition.metadata),
                )
            )

        self._last_capture_resolution_preset = new_capture_resolution_preset
        self.controller.save_filters(rewritten_filters)

    def _apply_screen_count_preset(self, value: int) -> None:
        if self._loading:
            return
        self.monitor_layout_widget.apply_screen_count_preset(value)

    def _handle_layout_changed(self, _display_setup: dict[str, object]) -> None:
        if self._loading:
            return
        self._rescale_filters_if_needed(self._current_display_setup())
        self._refresh_layout_status()

    def _handle_resolution_changed(self, _index: int) -> None:
        if self._loading or self.mixed_resolution_checkbox.isChecked():
            return
        self._rescale_filters_if_needed(self._current_display_setup())
        self.monitor_layout_widget.set_value(self._current_display_setup())
        self._refresh_layout_status()

    def _handle_mixed_resolution_toggled(self, _checked: bool) -> None:
        if self._loading:
            return
        self.monitor_layout_widget.set_value(self._current_display_setup())
        self._refresh_resolution_controls()
        self._rescale_filters_if_needed(self._current_display_setup())
        self._refresh_layout_status()

    def _refresh_layout_status(self) -> None:
        display_setup = self._current_display_setup()
        capture_cell = display_setup["capture_cell"]
        capture_label = describe_layout_cell(int(capture_cell["row"]), int(capture_cell["column"]))  # type: ignore[index]
        resolution_preset = str(display_setup["resolution_preset"])
        capture_resolution_preset = get_capture_resolution_preset(display_setup)

        lines = [
            (
                f"Resolution mode: mixed per monitor (capture uses {capture_resolution_preset.upper()} / "
                f"{get_resolution_label(capture_resolution_preset)})"
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
