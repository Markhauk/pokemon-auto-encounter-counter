from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
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

from .frame_styles import mark_as_frame_preview, mark_as_interface_frame


class InterfaceFramesDialog(QDialog):
    """Full Generation 3 frame picker opened from the compact Settings tab."""

    def __init__(self, controller: AppController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self._loading = False
        self._radio_buttons: dict[int, QRadioButton] = {}
        self.setWindowTitle("Interface Frames")
        self.setModal(True)
        self.resize(1040, 720)
        self._build_ui()
        self._connect_signals()
        self._apply_frame_type(self.controller.get_interface_frame_type())

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)

        heading = QLabel("Generation 3 Interface Frames")
        heading.setStyleSheet("font-size: 20px; font-weight: 600;")
        explanation = QLabel(
            "Choose a frame below. The change is applied immediately and saved "
            "for the next launch."
        )
        explanation.setWordWrap(True)

        self.choices_scroll = QScrollArea()
        self.choices_scroll.setWidgetResizable(True)
        self.choices_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        choices_container = QWidget()
        choices_layout = QGridLayout(choices_container)
        choices_layout.setContentsMargins(0, 0, 0, 0)
        choices_layout.setHorizontalSpacing(10)
        choices_layout.setVerticalSpacing(10)
        self.choices_scroll.setWidget(choices_container)
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
            choices_layout.addWidget(choice, index // 4, index % 4)

        for column in range(4):
            choices_layout.setColumnStretch(column, 1)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        dialog_buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        dialog_buttons.rejected.connect(self.reject)

        root_layout.addWidget(heading)
        root_layout.addWidget(explanation)
        root_layout.addSpacing(8)
        root_layout.addWidget(self.choices_scroll, 1)
        root_layout.addWidget(self.status_label)
        root_layout.addWidget(dialog_buttons)

    def _connect_signals(self) -> None:
        self.frame_buttons.idToggled.connect(self._handle_frame_toggled)
        self.controller.config_changed.connect(self._handle_config_changed)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._scroll_to_active_frame()

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
        finally:
            self._loading = False

        definition = get_interface_frame_definition(normalized)
        self.status_label.setText(f"Active frame: {definition.name}")
        if self.isVisible():
            self._scroll_to_active_frame()

    def _scroll_to_active_frame(self) -> None:
        selected = self.frame_buttons.checkedButton()
        if selected is not None:
            self.choices_scroll.ensureWidgetVisible(selected, 12, 12)


class SettingsTab(QWidget):
    def __init__(self, controller: AppController) -> None:
        super().__init__()
        self.controller = controller
        self._frame_dialog: InterfaceFramesDialog | None = None
        self._build_ui()
        self._connect_signals()
        self._apply_frame_type(self.controller.get_interface_frame_type())

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)

        heading = QLabel("Settings")
        heading.setStyleSheet("font-size: 20px; font-weight: 600;")
        explanation = QLabel("Manage the appearance and preferences for the application.")
        explanation.setWordWrap(True)

        self.frame_style_group = QGroupBox("Generation 3 Frame Style")
        mark_as_interface_frame(self.frame_style_group)
        frame_style_layout = QHBoxLayout(self.frame_style_group)

        frame_details_layout = QVBoxLayout()
        self.status_label = QLabel()
        self.status_label.setStyleSheet("font-size: 16px; font-weight: 600;")
        self.frame_description_label = QLabel()
        self.frame_description_label.setWordWrap(True)
        frame_details_layout.addWidget(self.status_label)
        frame_details_layout.addWidget(self.frame_description_label)

        self.interface_frames_button = QPushButton("Interface Frames...")
        self.interface_frames_button.setMinimumWidth(170)

        frame_style_layout.addLayout(frame_details_layout, 1)
        frame_style_layout.addWidget(
            self.interface_frames_button,
            0,
            Qt.AlignmentFlag.AlignVCenter,
        )

        root_layout.addWidget(heading)
        root_layout.addWidget(explanation)
        root_layout.addSpacing(8)
        root_layout.addWidget(self.frame_style_group)
        root_layout.addStretch(1)

    def _connect_signals(self) -> None:
        self.interface_frames_button.clicked.connect(self._open_interface_frames)
        self.controller.config_changed.connect(self._handle_config_changed)

    def _open_interface_frames(self) -> None:
        if self._frame_dialog is None:
            self._frame_dialog = InterfaceFramesDialog(self.controller, self)
        self._frame_dialog.exec()

    def _handle_config_changed(self, config: dict[str, object]) -> None:
        interface = config.get("interface", {})
        if not isinstance(interface, dict):
            interface = {}
        self._apply_frame_type(interface.get("frame_type"))

    def _apply_frame_type(self, frame_type: object) -> None:
        definition = get_interface_frame_definition(frame_type)
        self.status_label.setText(f"Current interface frame: {definition.name}")
        self.frame_description_label.setText(definition.description)
