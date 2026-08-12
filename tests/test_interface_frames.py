from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QGroupBox

from app.core.event_logger import EventLogger
from app.core.interface import FRAME_TYPE_1, FRAME_TYPE_2, SUPPORTED_FRAME_TYPES
from app.core.state_manager import StateManager
from app.gui.capture_settings_tab import CaptureSettingsTab
from app.gui.dashboard_tab import DashboardTab
from app.gui.filters_tab import FiltersTab
from app.gui.frame_styles import build_interface_frame_stylesheet, get_frame_asset_path
from app.gui.logs_tab import LogsTab
from app.gui.settings_tab import SettingsTab
from app.gui.templates_tab import TemplatesTab
from app.services.app_controller import AppController
from app.services.config_service import CONFIG_VERSION, ConfigService


class SettingsControllerStub(QObject):
    config_changed = Signal(dict)

    def __init__(self) -> None:
        super().__init__()
        self.frame_type = FRAME_TYPE_1

    def get_interface_frame_type(self) -> int:
        return self.frame_type

    def set_interface_frame_type(self, frame_type: object) -> dict[str, object]:
        self.frame_type = int(frame_type)
        config: dict[str, object] = {"interface": {"frame_type": self.frame_type}}
        self.config_changed.emit(config)
        return config


class InterfaceFrameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication(["interface-frame-tests"])

    def test_frame_preference_is_normalized_and_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text(
                json.dumps({"version": CONFIG_VERSION, "interface": {"frame_type": 99}}),
                encoding="utf-8",
            )
            with patch("app.services.config_service._read_physical_monitors", return_value=[]):
                service = ConfigService(config_path=config_path)
                self.assertEqual(service.get_interface_frame_type(), FRAME_TYPE_1)
                service.set_interface_frame_type(20)
                reloaded = ConfigService(config_path=config_path)
                self.assertEqual(reloaded.get_interface_frame_type(), 20)

    def test_settings_selection_applies_immediately(self) -> None:
        controller = SettingsControllerStub()
        tab = SettingsTab(controller)  # type: ignore[arg-type]

        tab._radio_buttons[20].click()

        self.assertEqual(controller.frame_type, 20)
        self.assertIn("Frame Type 20", tab.status_label.text())
        self.assertEqual(set(tab._radio_buttons), set(range(1, 21)))

    def test_filter_sections_are_marked_for_interface_frames(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_dir = root / "output"
            config_service = ConfigService(config_path=root / "config.json")
            state_manager = StateManager(
                counter_file=output_dir / "counter.txt",
                state_file=output_dir / "state.json",
                output_dir=output_dir,
                templates_dir=root / "templates",
            )
            event_logger = EventLogger(
                csv_file=output_dir / "encounter_log.csv",
                jsonl_file=output_dir / "event_log.jsonl",
            )
            with patch("app.services.config_service._read_physical_monitors", return_value=[]):
                controller = AppController(
                    config_service=config_service,
                    state_manager=state_manager,
                    event_logger=event_logger,
                )
                tab = FiltersTab(controller)

            framed_titles = {
                group.title()
                for group in tab.findChildren(QGroupBox)
                if bool(group.property("pokemonFrame"))
            }
            self.assertEqual(
                framed_titles,
                {"Filter Library", "Selected Filter"},
            )
            self.assertTrue(tab.advanced_widget.isHidden())
            self.assertEqual(tab.advanced_toggle.text(), "Show advanced settings")
            tab.advanced_toggle.click()
            self.assertFalse(tab.advanced_widget.isHidden())
            self.assertEqual(tab.advanced_toggle.text(), "Hide advanced settings")
            self.assertIn("Template", tab.filter_status_label.text())
            self.assertNotIn("\n", tab.filter_list.item(0).text())
            self.assertEqual(tab.workspace_tabs.count(), 2)
            self.assertEqual(tab.workspace_tabs.tabText(0), "Preview")
            self.assertEqual(tab.workspace_tabs.tabText(1), "Settings")

    def test_filter_selection_queues_an_automatic_preview_when_tab_opens(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_dir = root / "output"
            with patch("app.services.config_service._read_physical_monitors", return_value=[]):
                controller = AppController(
                    config_service=ConfigService(config_path=root / "config.json"),
                    state_manager=StateManager(
                        counter_file=output_dir / "counter.txt",
                        state_file=output_dir / "state.json",
                        output_dir=output_dir,
                        templates_dir=root / "templates",
                    ),
                    event_logger=EventLogger(
                        csv_file=output_dir / "encounter_log.csv",
                        jsonl_file=output_dir / "event_log.jsonl",
                    ),
                )
                tab = FiltersTab(controller)

            self.assertTrue(tab._preview_pending_when_shown)
            with patch.object(tab, "_capture_preview_for_filter") as capture_preview:
                tab.show()
                QTest.qWait(220)
                self.application.processEvents()

            capture_preview.assert_called_once_with(
                tab._selected_filter_id,
                show_error_dialog=False,
            )
            tab.close()

    def test_requested_sections_across_other_tabs_are_marked(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_dir = root / "output"
            with (
                patch("app.services.config_service._read_physical_monitors", return_value=[]),
                patch("app.services.app_controller.get_physical_monitors", return_value=[]),
            ):
                controller = AppController(
                    config_service=ConfigService(config_path=root / "config.json"),
                    state_manager=StateManager(
                        counter_file=output_dir / "counter.txt",
                        state_file=output_dir / "state.json",
                        output_dir=output_dir,
                        templates_dir=root / "templates",
                    ),
                    event_logger=EventLogger(
                        csv_file=output_dir / "encounter_log.csv",
                        jsonl_file=output_dir / "event_log.jsonl",
                    ),
                )
                expectations = (
                    (
                        DashboardTab(controller),
                        {"Scanner Controls", "Counters", "Live Details", "Live Runtime Log"},
                    ),
                    (CaptureSettingsTab(controller), {"Display Setup", "Last Preview"}),
                    (TemplatesTab(controller), {"Template Preview"}),
                    (LogsTab(controller), {"Logs and State"}),
                )

            for tab, expected_titles in expectations:
                framed_titles = {
                    group.title()
                    for group in tab.findChildren(QGroupBox)
                    if bool(group.property("pokemonFrame"))
                }
                self.assertEqual(framed_titles, expected_titles)

            dashboard = expectations[0][0]
            self.assertIsInstance(dashboard, DashboardTab)
            self.assertEqual(dashboard.new_hunt_button.text(), "New Hunt...")
            self.assertGreaterEqual(dashboard.hunt_combo.count(), 1)
            self.assertEqual(dashboard.hunt_encounter_value.text(), "0")

    def test_styles_only_target_frame_group_boxes(self) -> None:
        type_1 = build_interface_frame_stylesheet(FRAME_TYPE_1)
        type_2 = build_interface_frame_stylesheet(FRAME_TYPE_2)
        type_20 = build_interface_frame_stylesheet(20)

        self.assertIn('QGroupBox[pokemonFrame="true"]', type_1)
        self.assertIn("border-image", type_1)
        self.assertIn("frame_01.png", type_1)
        self.assertIn("frame_02.png", type_2)
        self.assertIn("frame_20.png", type_20)
        self.assertIn('QGroupBox[framePreview="20"]', type_1)
        self.assertNotIn("QPushButton", type_1)
        self.assertNotEqual(type_1, type_2)

    def test_all_twenty_frame_assets_are_valid_nine_slices(self) -> None:
        self.assertEqual(SUPPORTED_FRAME_TYPES, tuple(range(1, 21)))
        for frame_type in SUPPORTED_FRAME_TYPES:
            image = QImage(str(get_frame_asset_path(frame_type)))
            self.assertFalse(image.isNull(), msg=f"Frame {frame_type} could not be loaded")
            self.assertEqual((image.width(), image.height()), (40, 40))
            self.assertTrue(image.hasAlphaChannel())


if __name__ == "__main__":
    unittest.main()
