from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.gui.obs_counter_dialog import ObsCounterDialog


class ObsControllerStub:
    def __init__(self) -> None:
        self.prepare_calls = 0
        self.opened_output_folder = False

    def prepare_obs_counter_file(self) -> dict[str, object]:
        self.prepare_calls += 1
        return {
            "path": r"C:\PokemonCounter\output\obs_counter.txt",
            "hunt_name": "Shiny Rayquaza",
            "encounter_count": 327,
        }

    def open_output_folder(self) -> None:
        self.opened_output_folder = True


class ObsCounterDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication(["obs-counter-tests"])

    def test_dialog_shows_and_copies_the_obs_counter_path(self) -> None:
        controller = ObsControllerStub()
        dialog = ObsCounterDialog(controller)  # type: ignore[arg-type]

        self.assertEqual(controller.prepare_calls, 1)
        self.assertEqual(dialog.hunt_value.text(), "Shiny Rayquaza")
        self.assertEqual(dialog.counter_value.text(), "327")
        self.assertTrue(dialog.path_edit.text().endswith("obs_counter.txt"))

        dialog.copy_path_button.click()

        self.assertEqual(QApplication.clipboard().text(), dialog.path_edit.text())
        self.assertIn("Path copied", dialog.copy_status_label.text())

        dialog.open_folder_button.click()
        self.assertTrue(controller.opened_output_folder)


if __name__ == "__main__":
    unittest.main()
