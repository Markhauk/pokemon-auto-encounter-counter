from __future__ import annotations

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QMainWindow, QMessageBox, QTabWidget

from app.services.app_controller import AppController

from .capture_settings_tab import CaptureSettingsTab
from .dashboard_tab import DashboardTab
from .filters_tab import FiltersTab
from .frame_styles import build_interface_frame_stylesheet
from .logs_tab import LogsTab
from .settings_tab import SettingsTab
from .templates_tab import TemplatesTab


class MainWindow(QMainWindow):
    def __init__(self, controller: AppController) -> None:
        super().__init__()
        self.controller = controller
        self.setWindowTitle("Pokemon Encounter Counter")
        self.resize(1280, 860)

        self.tabs = QTabWidget()
        self.tabs.addTab(DashboardTab(controller), "Dashboard")
        self.tabs.addTab(FiltersTab(controller), "Filters")
        self.tabs.addTab(CaptureSettingsTab(controller), "Capture")
        self.tabs.addTab(TemplatesTab(controller), "Templates")
        self.tabs.addTab(LogsTab(controller), "Logs / State")
        self.tabs.addTab(SettingsTab(controller), "Settings")
        self.setCentralWidget(self.tabs)

        self.statusBar().showMessage("Idle")
        self.controller.runtime_status_changed.connect(self._show_runtime_status)
        self.controller.config_changed.connect(self._apply_interface_config)
        self._apply_interface_config(self.controller.get_config())

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

    def _apply_interface_config(self, config: dict[str, object]) -> None:
        interface = config.get("interface", {})
        frame_type = interface.get("frame_type") if isinstance(interface, dict) else None
        self.setStyleSheet(build_interface_frame_stylesheet(frame_type))
