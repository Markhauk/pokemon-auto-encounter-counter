from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QLabel,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from app.core.display import (
    choose_default_capture_cell,
    count_active_layout_cells,
    describe_layout_cell,
    list_active_layout_cells,
    normalize_display_setup,
)


class MonitorCellWidget(QFrame):
    active_changed = Signal(int, int, bool)
    capture_requested = Signal(int, int)
    resolution_changed = Signal(int, int, str)

    def __init__(self, row: int, column: int) -> None:
        super().__init__()
        self.row = row
        self.column = column
        self._build_ui()

    def _build_ui(self) -> None:
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setMinimumSize(185, 140)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        self.title_label = QLabel(describe_layout_cell(self.row, self.column))
        self.title_label.setStyleSheet("font-weight: 600; color: #111;")

        self.status_label = QLabel("Unused")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: #111;")

        self.active_checkbox = QCheckBox("Monitor in use")
        self.active_checkbox.setStyleSheet(
            "QCheckBox { color: #111; }"
            "QCheckBox::indicator {"
            "width: 16px;"
            "height: 16px;"
            "border: 1px solid #3d556d;"
            "border-radius: 3px;"
            "background-color: #f7e39a;"
            "}"
            "QCheckBox::indicator:checked {"
            "background-color: #2d7d46;"
            "border: 1px solid #245f36;"
            "}"
        )
        self.capture_radio = QRadioButton("Use for capture")
        self.capture_radio.setStyleSheet(
            "QRadioButton { color: #111; }"
            "QRadioButton::indicator {"
            "width: 16px;"
            "height: 16px;"
            "border: 1px solid #3d556d;"
            "border-radius: 8px;"
            "background-color: #f7e39a;"
            "}"
            "QRadioButton::indicator:checked {"
            "background-color: #2d7d46;"
            "border: 1px solid #245f36;"
            "}"
        )

        self.resolution_label = QLabel("Resolution")
        self.resolution_label.setStyleSheet("color: #111;")
        self.resolution_combo = QComboBox()
        self.resolution_combo.setStyleSheet(
            "QComboBox {"
            "color: #111;"
            "background-color: #fff;"
            "border: 1px solid #666;"
            "border-radius: 4px;"
            "padding: 2px 6px;"
            "}"
        )
        for preset in ("1080p", "1440p", "4k"):
            self.resolution_combo.addItem(preset.upper(), preset)

        layout.addWidget(self.title_label)
        layout.addWidget(self.status_label)
        layout.addStretch(1)
        layout.addWidget(self.active_checkbox)
        layout.addWidget(self.capture_radio)
        layout.addWidget(self.resolution_label)
        layout.addWidget(self.resolution_combo)

        self.active_checkbox.toggled.connect(self._emit_active_changed)
        self.capture_radio.toggled.connect(self._emit_capture_requested)
        self.resolution_combo.currentIndexChanged.connect(self._emit_resolution_changed)
        self._update_style(active=False, selected=False)

    def set_state(
        self,
        *,
        active: bool,
        selected: bool,
        order: int | None,
        show_resolution: bool,
        resolution_preset: str,
    ) -> None:
        self.active_checkbox.blockSignals(True)
        self.capture_radio.blockSignals(True)
        self.resolution_combo.blockSignals(True)

        self.active_checkbox.setChecked(active)
        self.capture_radio.setEnabled(active)
        self.capture_radio.setChecked(active and selected)

        resolution_index = self.resolution_combo.findData(resolution_preset)
        if resolution_index >= 0:
            self.resolution_combo.setCurrentIndex(resolution_index)
        self.resolution_combo.setEnabled(active and show_resolution)
        self.resolution_combo.setVisible(active and show_resolution)
        self.resolution_label.setVisible(active and show_resolution)

        self.active_checkbox.blockSignals(False)
        self.capture_radio.blockSignals(False)
        self.resolution_combo.blockSignals(False)

        if not active:
            self.status_label.setText("Unused")
        elif selected:
            self.status_label.setText(f"Display {order} active\nCurrent capture monitor")
        else:
            self.status_label.setText(f"Display {order} active")

        self._update_style(active=active, selected=selected)

    def _emit_active_changed(self, checked: bool) -> None:
        self.active_changed.emit(self.row, self.column, checked)

    def _emit_capture_requested(self, checked: bool) -> None:
        if checked:
            self.capture_requested.emit(self.row, self.column)

    def _emit_resolution_changed(self, _index: int) -> None:
        self.resolution_changed.emit(self.row, self.column, str(self.resolution_combo.currentData()))

    def _update_style(self, *, active: bool, selected: bool) -> None:
        border_color = "#999"
        background_color = "#f3f3f3"
        if selected:
            border_color = "#2d7d46"
            background_color = "#e6f6ea"
        elif active:
            border_color = "#4a78a6"
            background_color = "#edf4fb"

        self.setStyleSheet(
            "QFrame {"
            f"border: 2px solid {border_color};"
            "border-radius: 10px;"
            f"background-color: {background_color};"
            "color: #111;"
            "}"
            "QLabel, QCheckBox, QRadioButton {"
            "color: #111;"
            "background: transparent;"
            "border: none;"
            "}"
            "QCheckBox::indicator {"
            "width: 16px;"
            "height: 16px;"
            "border: 1px solid #3d556d;"
            "border-radius: 3px;"
            "background-color: #f7e39a;"
            "}"
            "QCheckBox::indicator:checked {"
            "background-color: #2d7d46;"
            "border: 1px solid #245f36;"
            "}"
            "QRadioButton::indicator {"
            "width: 16px;"
            "height: 16px;"
            "border: 1px solid #3d556d;"
            "border-radius: 8px;"
            "background-color: #f7e39a;"
            "}"
            "QRadioButton::indicator:checked {"
            "background-color: #2d7d46;"
            "border: 1px solid #245f36;"
            "}"
        )


class MonitorLayoutWidget(QWidget):
    value_changed = Signal(dict)

    def __init__(self) -> None:
        super().__init__()
        self._display_setup = normalize_display_setup({})
        self._suspend_events = False
        self._cells: dict[tuple[int, int], MonitorCellWidget] = {}
        self._capture_group = QButtonGroup(self)
        self._capture_group.setExclusive(True)
        self._build_ui()
        self._refresh_ui()

    def _build_ui(self) -> None:
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(12)

        for row in range(2):
            for column in range(3):
                cell = MonitorCellWidget(row, column)
                cell.active_changed.connect(self._handle_active_changed)
                cell.capture_requested.connect(self._handle_capture_requested)
                cell.resolution_changed.connect(self._handle_resolution_changed)
                self._capture_group.addButton(cell.capture_radio)
                self._cells[(row, column)] = cell
                layout.addWidget(cell, row, column)

    def value(self) -> dict[str, object]:
        return normalize_display_setup(self._display_setup)

    def set_value(self, display_setup: dict[str, object]) -> None:
        self._display_setup = normalize_display_setup(display_setup)
        self._refresh_ui()

    def apply_screen_count_preset(self, screen_count: int) -> None:
        previous_setup = self.value()
        previous_layout = previous_setup["layout"]
        layout = previous_layout

        preset_layout = normalize_display_setup({"screen_count": screen_count})["layout"]
        if count_active_layout_cells(previous_layout) != screen_count:
            layout = preset_layout

        self._display_setup["screen_count"] = count_active_layout_cells(layout)
        self._display_setup["layout"] = layout
        self._display_setup["capture_cell"] = choose_default_capture_cell(layout)
        self._refresh_ui(emit=True)

    def _handle_active_changed(self, row: int, column: int, checked: bool) -> None:
        if self._suspend_events:
            return

        previous_capture = dict(self._display_setup["capture_cell"])  # type: ignore[index]
        layout = [list(layout_row) for layout_row in self._display_setup["layout"]]  # type: ignore[index]
        layout[row][column] = 1 if checked else 0

        if count_active_layout_cells(layout) == 0:
            self._refresh_ui()
            return

        self._display_setup["layout"] = layout
        self._display_setup["screen_count"] = count_active_layout_cells(layout)
        previous_row = int(previous_capture["row"])
        previous_column = int(previous_capture["column"])
        if layout[previous_row][previous_column]:
            self._display_setup["capture_cell"] = previous_capture
        else:
            self._display_setup["capture_cell"] = choose_default_capture_cell(layout)

        self._refresh_ui(emit=True)

    def _handle_capture_requested(self, row: int, column: int) -> None:
        if self._suspend_events:
            return

        layout = self._display_setup["layout"]  # type: ignore[index]
        if not layout[row][column]:
            return

        self._display_setup["capture_cell"] = {"row": row, "column": column}
        self._refresh_ui(emit=True)

    def _handle_resolution_changed(self, row: int, column: int, preset: str) -> None:
        if self._suspend_events:
            return

        grid = [list(grid_row) for grid_row in self._display_setup["monitor_resolutions"]]  # type: ignore[index]
        grid[row][column] = preset
        self._display_setup["monitor_resolutions"] = grid
        self._refresh_ui(emit=True)

    def _refresh_ui(self, *, emit: bool = False) -> None:
        self._display_setup = normalize_display_setup(self._display_setup)
        active_order = {
            cell: index
            for index, cell in enumerate(list_active_layout_cells(self._display_setup["layout"]), start=1)  # type: ignore[arg-type]
        }
        capture_cell = self._display_setup["capture_cell"]
        selected_key = (int(capture_cell["row"]), int(capture_cell["column"]))  # type: ignore[index]
        show_resolution = bool(self._display_setup["mixed_resolutions"])
        monitor_resolutions = self._display_setup["monitor_resolutions"]

        self._suspend_events = True
        try:
            for key, cell in self._cells.items():
                active = bool(self._display_setup["layout"][key[0]][key[1]])  # type: ignore[index]
                cell.set_state(
                    active=active,
                    selected=key == selected_key,
                    order=active_order.get(key),
                    show_resolution=show_resolution,
                    resolution_preset=str(monitor_resolutions[key[0]][key[1]]),  # type: ignore[index]
                )
        finally:
            self._suspend_events = False

        if emit:
            self.value_changed.emit(self.value())
