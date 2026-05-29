from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QButtonGroup, QFrame, QGridLayout, QLabel, QRadioButton, QVBoxLayout, QWidget

from app.core.display import normalize_display_setup


class MonitorCardWidget(QFrame):
    capture_requested = Signal(int)

    def __init__(self, monitor_index: int) -> None:
        super().__init__()
        self.monitor_index = monitor_index
        self._build_ui()

    def _build_ui(self) -> None:
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setMinimumSize(240, 140)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        self.title_label = QLabel(f"Monitor {self.monitor_index}")
        self.title_label.setStyleSheet("font-weight: 600; color: #111;")

        self.summary_label = QLabel("")
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet("color: #111;")

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: #111;")

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

        layout.addWidget(self.title_label)
        layout.addWidget(self.summary_label)
        layout.addStretch(1)
        layout.addWidget(self.status_label)
        layout.addWidget(self.capture_radio)

        self.capture_radio.toggled.connect(self._emit_capture_requested)
        self._update_style(selected=False)

    def set_state(self, *, monitor: dict[str, int], selected: bool) -> None:
        self.capture_radio.blockSignals(True)
        self.capture_radio.setChecked(selected)
        self.capture_radio.blockSignals(False)

        self.title_label.setText(f"Monitor {monitor['index']}")
        self.summary_label.setText(
            f"{monitor['width']} x {monitor['height']}\n"
            f"left={monitor['left']}, top={monitor['top']}"
        )
        self.status_label.setText("Current capture monitor" if selected else "Available monitor")
        self._update_style(selected=selected)

    def _emit_capture_requested(self, checked: bool) -> None:
        if checked:
            self.capture_requested.emit(self.monitor_index)

    def _update_style(self, *, selected: bool) -> None:
        border_color = "#4a78a6"
        background_color = "#edf4fb"
        if selected:
            border_color = "#2d7d46"
            background_color = "#e6f6ea"

        self.setStyleSheet(
            "QFrame {"
            f"border: 2px solid {border_color};"
            "border-radius: 10px;"
            f"background-color: {background_color};"
            "color: #111;"
            "}"
            "QLabel, QRadioButton {"
            "color: #111;"
            "background: transparent;"
            "border: none;"
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
        self._physical_monitors: list[dict[str, int]] = []
        self._suspend_events = False
        self._cards: dict[int, MonitorCardWidget] = {}
        self._capture_group = QButtonGroup(self)
        self._capture_group.setExclusive(True)
        self._build_ui()
        self._refresh_ui()

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.empty_label = QLabel("No monitors detected.")
        self.empty_label.setWordWrap(True)

        self.grid_layout = QGridLayout()
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        self.grid_layout.setHorizontalSpacing(12)
        self.grid_layout.setVerticalSpacing(12)

        root_layout.addWidget(self.empty_label)
        root_layout.addLayout(self.grid_layout)

    def value(self) -> dict[str, object]:
        return normalize_display_setup(self._display_setup, physical_monitors=self._physical_monitors)

    def set_value(
        self,
        display_setup: dict[str, object],
        *,
        physical_monitors: list[dict[str, int]] | None = None,
    ) -> None:
        if physical_monitors is not None:
            self._physical_monitors = [dict(monitor) for monitor in physical_monitors]
        self._display_setup = normalize_display_setup(display_setup, physical_monitors=self._physical_monitors)
        self._refresh_ui()

    def _handle_capture_requested(self, monitor_index: int) -> None:
        if self._suspend_events:
            return

        self._display_setup["capture_monitor_index"] = monitor_index
        self._refresh_ui(emit=True)

    def _refresh_ui(self, *, emit: bool = False) -> None:
        self._display_setup = normalize_display_setup(self._display_setup, physical_monitors=self._physical_monitors)
        selected_monitor_index = int(self._display_setup["capture_monitor_index"])

        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        self._capture_group = QButtonGroup(self)
        self._capture_group.setExclusive(True)
        self._cards = {}

        self._suspend_events = True
        try:
            for position, monitor in enumerate(self._physical_monitors):
                card = MonitorCardWidget(int(monitor["index"]))
                card.capture_requested.connect(self._handle_capture_requested)
                self._capture_group.addButton(card.capture_radio)
                card.set_state(
                    monitor=monitor,
                    selected=int(monitor["index"]) == selected_monitor_index,
                )
                self._cards[int(monitor["index"])] = card
                row = position // 2
                column = position % 2
                self.grid_layout.addWidget(card, row, column)
        finally:
            self._suspend_events = False

        self.empty_label.setVisible(not self._physical_monitors)
        if emit:
            self.value_changed.emit(self.value())
