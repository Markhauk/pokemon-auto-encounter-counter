from __future__ import annotations

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QGridLayout,
    QGroupBox,
    QLabel,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.core.interface import (
    INTERFACE_FRAME_DEFINITIONS,
    get_interface_frame_definition,
    normalize_frame_type,
)
from app.services.app_controller import AppController

from .frame_styles import mark_as_frame_preview


class SettingsTab(QWidget):
    def __init__(self, controller: AppController) -> None:
        super().__init__()
        self.controller = controller
        self._loading = False
        self._radio_buttons: dict[int, QRadioButton] = {}
        self._build_ui()
        self._connect_signals()
        self._apply_frame_type(self.controller.get_interface_frame_type())

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)

        heading = QLabel("Interface Frames")
        heading.setStyleSheet("font-size: 20px; font-weight: 600;")
        explanation = QLabel(
            "Choose the border used around the main information sections. "
            "The change is applied immediately and saved for the next launch. Existing buttons are unchanged."
        )
        explanation.setWordWrap(True)

        choices_group = QGroupBox("Generation 3 Frame Style")
        choices_group_layout = QVBoxLayout(choices_group)
        self.choices_scroll = QScrollArea()
        self.choices_scroll.setWidgetResizable(True)
        self.choices_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        choices_container = QWidget()
        choices_layout = QGridLayout(choices_container)
        choices_layout.setContentsMargins(0, 0, 0, 0)
        choices_layout.setHorizontalSpacing(10)
        choices_layout.setVerticalSpacing(10)
        self.choices_scroll.setWidget(choices_container)
        choices_group_layout.addWidget(self.choices_scroll)
        self.frame_buttons = QButtonGroup(self)
        self.frame_buttons.setExclusive(True)

        for index, definition in enumerate(INTERFACE_FRAME_DEFINITIONS):
            choice = QWidget()
            choice_layout = QVBoxLayout(choice)
            choice_layout.setContentsMargins(4, 4, 4, 4)

            radio = QRadioButton(definition.name)
            radio.setToolTip(definition.description)
            self.frame_buttons.addButton(radio, definition.frame_type)
            self._radio_buttons[definition.frame_type] = radio

            preview = QGroupBox("Preview")
            mark_as_frame_preview(preview, definition.frame_type)
            preview_layout = QVBoxLayout(preview)
            preview_title = QLabel("FILTER DETAILS")
            preview_title.setStyleSheet("font-weight: 600;")
            preview_copy = QLabel("Wild encounter\nTemplate ready\nMatch score 0.910")
            preview_copy.setWordWrap(True)
            preview_layout.addWidget(preview_title)
            preview_layout.addWidget(preview_copy)
            preview_layout.addStretch(1)

            description = QLabel(definition.description)
            description.setWordWrap(True)
            description.setAlignment(Qt.AlignmentFlag.AlignTop)

            choice_layout.addWidget(radio)
            choice_layout.addWidget(preview, 1)
            choice_layout.addWidget(description)
            choices_layout.addWidget(choice, index // 5, index % 5)

        for column in range(5):
            choices_layout.setColumnStretch(column, 1)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        future_note = QLabel(
            "All 20 Generation 3 frame types are available."
        )
        future_note.setWordWrap(True)

        root_layout.addWidget(heading)
        root_layout.addWidget(explanation)
        root_layout.addSpacing(8)
        root_layout.addWidget(choices_group, 1)
        root_layout.addWidget(self.status_label)
        root_layout.addWidget(future_note)

    def _connect_signals(self) -> None:
        self.frame_buttons.idToggled.connect(self._handle_frame_toggled)
        self.controller.config_changed.connect(self._handle_config_changed)

    def _handle_frame_toggled(self, frame_type: int, checked: bool) -> None:
        if self._loading or not checked:
            return
        self.controller.set_interface_frame_type(frame_type)

    def _handle_config_changed(self, config: dict[str, object]) -> None:
        interface = config.get("interface", {})
        if not isinstance(interface, dict):
            interface = {}
        self._apply_frame_type(interface.get("frame_type"))

    def _apply_frame_type(self, frame_type: object) -> None:
        normalized = normalize_frame_type(frame_type)
        self._loading = True
        try:
            button = self._radio_buttons.get(normalized)
            if button is not None:
                button.setChecked(True)
                QTimer.singleShot(
                    0,
                    lambda selected=button: self.choices_scroll.ensureWidgetVisible(
                        selected,
                        12,
                        12,
                    ),
                )
        finally:
            self._loading = False

        definition = get_interface_frame_definition(normalized)
        self.status_label.setText(f"Active frame: {definition.name}")
