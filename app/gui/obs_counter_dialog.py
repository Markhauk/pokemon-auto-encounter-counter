from __future__ import annotations

from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.services.app_controller import AppController


class ObsCounterDialog(QDialog):
    """Small setup guide for connecting the active hunt counter to OBS."""

    def __init__(self, controller: AppController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.setWindowTitle("OBS Live Counter")
        self.setModal(True)
        self.setMinimumWidth(680)
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)

        heading = QLabel("Connect the active hunt counter to OBS")
        heading.setStyleSheet("font-size: 20px; font-weight: 600;")
        explanation = QLabel(
            "This plain-text file updates after every counted encounter and when "
            "you switch hunts. The all-time counter is not changed."
        )
        explanation.setWordWrap(True)

        summary_layout = QFormLayout()
        self.hunt_value = QLabel("N/A")
        self.counter_value = QLabel("0")
        self.counter_value.setStyleSheet("font-size: 18px; font-weight: 600;")
        summary_layout.addRow("Active hunt", self.hunt_value)
        summary_layout.addRow("Current OBS value", self.counter_value)

        instructions = QLabel(
            "1. In OBS, add a Text (GDI+) source.\n"
            "2. Enable Read from file.\n"
            "3. Browse to the file below, or copy its path and paste it into OBS."
        )
        instructions.setWordWrap(True)

        self.path_edit = QLineEdit()
        self.path_edit.setReadOnly(True)
        self.path_edit.setPlaceholderText("OBS counter file path")

        action_layout = QHBoxLayout()
        self.copy_path_button = QPushButton("Copy Path")
        self.open_folder_button = QPushButton("Open Output Folder")
        action_layout.addWidget(self.copy_path_button)
        action_layout.addWidget(self.open_folder_button)
        action_layout.addStretch(1)

        self.copy_status_label = QLabel("")
        self.copy_status_label.setStyleSheet("color: #5fbf70; font-weight: 600;")

        dialog_buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        dialog_buttons.rejected.connect(self.reject)

        root_layout.addWidget(heading)
        root_layout.addWidget(explanation)
        root_layout.addSpacing(8)
        root_layout.addLayout(summary_layout)
        root_layout.addSpacing(8)
        root_layout.addWidget(instructions)
        root_layout.addWidget(self.path_edit)
        root_layout.addLayout(action_layout)
        root_layout.addWidget(self.copy_status_label)
        root_layout.addWidget(dialog_buttons)

        self.copy_path_button.clicked.connect(self._copy_path)
        self.open_folder_button.clicked.connect(self._open_output_folder)

    def refresh(self) -> None:
        payload = self.controller.prepare_obs_counter_file()
        self.hunt_value.setText(str(payload.get("hunt_name", "N/A") or "N/A"))
        self.counter_value.setText(str(payload.get("encounter_count", 0)))
        self.path_edit.setText(str(payload.get("path", "")))
        self.copy_status_label.clear()

    def _copy_path(self) -> None:
        path = self.path_edit.text()
        QApplication.clipboard().setText(path)
        self.copy_status_label.setText("Path copied. Paste it into the OBS file field.")

    def _open_output_folder(self) -> None:
        try:
            self.controller.open_output_folder()
        except Exception as exc:
            QMessageBox.warning(self, "OBS Live Counter", str(exc))
