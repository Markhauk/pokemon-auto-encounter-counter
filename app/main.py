from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from app.gui.main_window import MainWindow
from app.services.app_controller import AppController


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Pokemon Encounter Counter")
    app.setOrganizationName("Local Utility")

    controller = AppController()
    window = MainWindow(controller)
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
