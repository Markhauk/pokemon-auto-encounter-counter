from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)


class NewHuntDialog(QDialog):
    def __init__(self, current_hunt: dict[str, object], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Start New Hunt")
        self.setMinimumWidth(430)

        layout = QVBoxLayout(self)
        explanation = QLabel(
            "The current hunt is saved automatically. The new hunt starts at 0, "
            "while the all-time encounter total keeps counting."
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)

        summary_layout = QFormLayout()
        summary_layout.addRow("Current hunt", QLabel(str(current_hunt.get("hunt_name", "N/A"))))
        summary_layout.addRow(
            "Saved encounters",
            QLabel(str(current_hunt.get("hunt_encounter_count", 0))),
        )
        layout.addLayout(summary_layout)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Example: Shiny Rayquaza")
        self.name_edit.setMaxLength(80)
        layout.addWidget(QLabel("New hunt name"))
        layout.addWidget(self.name_edit)

        self.complete_current_checkbox = QCheckBox("Mark the current hunt as completed")
        self.complete_current_checkbox.setChecked(True)
        self.complete_current_checkbox.setToolTip(
            "Completed hunts are kept and can still be resumed later from the Hunt list."
        )
        layout.addWidget(self.complete_current_checkbox)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        save_button = buttons.button(QDialogButtonBox.StandardButton.Save)
        save_button.setText("Start Hunt")
        buttons.accepted.connect(self._accept_if_valid)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.name_edit.setFocus()

    @property
    def hunt_name(self) -> str:
        return " ".join(self.name_edit.text().split()).strip()

    @property
    def complete_current(self) -> bool:
        return self.complete_current_checkbox.isChecked()

    def _accept_if_valid(self) -> None:
        if not self.hunt_name:
            QMessageBox.warning(self, "Start New Hunt", "Enter a name for the new hunt.")
            self.name_edit.setFocus()
            return
        self.accept()
