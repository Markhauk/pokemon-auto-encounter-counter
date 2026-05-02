from __future__ import annotations

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QMainWindow, QMessageBox, QTabWidget

from app.services.app_controller import AppController

from .capture_settings_tab import CaptureSettingsTab
from .dashboard_tab import DashboardTab
from .logs_tab import LogsTab
from .templates_tab import TemplatesTab


class MainWindow(QMainWindow):
    def __init__(self, controller: AppController) -> None:
        super().__init__()
        self.controller = controller
        self.setWindowTitle("Pokemon Encounter Counter")
        self.resize(1280, 860)

        tabs = QTabWidget()
        tabs.addTab(DashboardTab(controller), "Dashboard")
        tabs.addTab(CaptureSettingsTab(controller), "Capture Settings")
        tabs.addTab(TemplatesTab(controller), "Templates")
        tabs.addTab(LogsTab(controller), "Logs / State")
        self.setCentralWidget(tabs)

        self.statusBar().showMessage("Idle")
        self.controller.runtime_status_changed.connect(self._show_runtime_status)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.controller.is_running():
            QMessageBox.warning(
                self,
                "Pokemon Encounter Counter",
                "Stop scanning before closing the application.",
            )
            event.ignore()
            return
        super().closeEvent(event)

    def _show_runtime_status(self, status: str) -> None:
        self.statusBar().showMessage(f"Status: {status}")
