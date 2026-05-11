from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.services.app_controller import AppController


class TemplatesTab(QWidget):
    def __init__(self, controller: AppController) -> None:
        super().__init__()
        self.controller = controller
        self._statuses = []
        self._build_ui()
        self._connect_signals()
        self.refresh()

    def _build_ui(self) -> None:
        root_layout = QHBoxLayout(self)

        left_panel = QVBoxLayout()
        right_panel = QVBoxLayout()

        self.refresh_button = QPushButton("Refresh Template Status")

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Filter", "Template", "Status", "Path"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)

        left_panel.addWidget(self.refresh_button)
        left_panel.addWidget(self.table, 1)

        preview_group = QGroupBox("Template Preview")
        preview_layout = QVBoxLayout(preview_group)
        self.preview_label = QLabel("Select a template row to preview it.")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(420, 240)
        self.preview_label.setStyleSheet("border: 1px solid #666;")
        self.details_label = QLabel("No template selected.")
        self.details_label.setWordWrap(True)
        preview_layout.addWidget(self.preview_label)
        preview_layout.addWidget(self.details_label)

        right_panel.addWidget(preview_group)
        right_panel.addStretch(1)

        root_layout.addLayout(left_panel, 2)
        root_layout.addLayout(right_panel, 1)

    def _connect_signals(self) -> None:
        self.refresh_button.clicked.connect(self.refresh)
        self.table.itemSelectionChanged.connect(self._update_preview_for_selection)

    def refresh(self) -> None:
        self._statuses = self.controller.get_template_statuses()
        self.table.setRowCount(len(self._statuses))

        for row, status in enumerate(self._statuses):
            self.table.setItem(row, 0, QTableWidgetItem(status.filter_name))
            self.table.setItem(row, 1, QTableWidgetItem(status.filename))
            self.table.setItem(row, 2, QTableWidgetItem(status.status_label()))
            self.table.setItem(row, 3, QTableWidgetItem(status.path))

        if self._statuses:
            self.table.selectRow(0)
            self._update_preview_for_selection()

    def _update_preview_for_selection(self) -> None:
        selected_items = self.table.selectedItems()
        if not selected_items:
            return

        row = selected_items[0].row()
        status = self._statuses[row]
        path = Path(status.path)

        if not path.exists():
            self.preview_label.setPixmap(QPixmap())
            self.preview_label.setText(f"Missing file:\n{path}")
        else:
            pixmap = QPixmap(str(path))
            if pixmap.isNull():
                self.preview_label.setPixmap(QPixmap())
                self.preview_label.setText(f"Unable to preview:\n{path.name}")
            else:
                self.preview_label.setPixmap(
                    pixmap.scaled(
                        self.preview_label.size(),
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )

        details = [
            f"Filter: {status.filter_name}",
            f"Event type: {status.event_type}",
            f"Template: {status.filename}",
            f"Status: {status.status_label()}",
            f"Path: {status.path}",
        ]
        if status.error:
            details.append(f"Note: {status.error}")
        self.details_label.setText("\n".join(details))

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().resizeEvent(event)
        self._update_preview_for_selection()
