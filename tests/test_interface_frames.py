from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, QTimer, Signal
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
from app.gui.main_window import MainWindow
from app.gui.settings_tab import InterfaceFramesDialog, SettingsTab
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

    def test_interface_frame_dialog_selection_applies_immediately(self) -> None:
        controller = SettingsControllerStub()
        dialog = InterfaceFramesDialog(controller)  # type: ignore[arg-type]

        dialog._radio_buttons[20].click()

        self.assertEqual(controller.frame_type, 20)
        self.assertIn("Frame Type 20", dialog.status_label.text())
        self.assertEqual(set(dialog._radio_buttons), set(range(1, 21)))

    def test_settings_shows_current_frame_and_opens_full_picker(self) -> None:
        controller = SettingsControllerStub()
        tab = SettingsTab(controller)  # type: ignore[arg-type]

        self.assertIn("Frame Type 1", tab.status_label.text())
        self.assertTrue(tab.frame_style_group.property("pokemonFrame"))
        self.assertEqual(tab.interface_frames_button.text(), "Interface Frames...")
        self.assertFalse(hasattr(tab, "_radio_buttons"))

        controller.set_interface_frame_type(12)
        self.assertIn("Frame Type 12", tab.status_label.text())

        opened_dialogs: list[InterfaceFramesDialog] = []

        def close_open_picker() -> None:
            dialog = QApplication.activeModalWidget()
            if isinstance(dialog, InterfaceFramesDialog):
                opened_dialogs.append(dialog)
                dialog.reject()

        QTimer.singleShot(0, close_open_picker)
        tab.interface_frames_button.click()
        self.assertEqual(len(opened_dialogs), 1)
        self.assertIs(tab._frame_dialog, opened_dialogs[0])

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
            self.assertTrue(tab.preview_tab.isAncestorOf(tab.enabled_checkbox))
            self.assertFalse(tab.settings_tab.isAncestorOf(tab.enabled_checkbox))

            selected_filter_id = tab._selected_filter_id
            was_enabled = bool(controller.get_filter(selected_filter_id).enabled)
            self.assertEqual(
                tab.enabled_state_label.text(),
                "Enabled" if was_enabled else "Disabled",
            )
            self.assertEqual(
                tab.match_action_label.text(),
                "When matched: Encounter starts",
            )
            self.assertIn("#5fbf70", tab.match_action_label.styleSheet())
            tab.enabled_checkbox.click()
            self.assertEqual(
                controller.get_filter(selected_filter_id).enabled,
                not was_enabled,
            )
            self.assertEqual(
                tab.enabled_state_label.text(),
                "Disabled" if was_enabled else "Enabled",
            )
            self.assertEqual(tab.workspace_tabs.currentWidget(), tab.preview_tab)

            catch_index = tab.event_type_combo.findData("catch")
            tab.event_type_combo.setCurrentIndex(catch_index)
            tab.save_filter_button.click()
            self.assertEqual(
                tab.match_action_label.text(),
                "When matched: Pokemon caught",
            )

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
                        {
                            "Scanner Controls",
                            "Counters",
                            "Live Details",
                            "Live Runtime Log",
                            "Encounter Capture",
                        },
                    ),
                    (CaptureSettingsTab(controller), {"Capture Monitor", "Full Monitor Preview"}),
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
            self.assertEqual(dashboard.obs_counter_button.text(), "OBS Live Counter...")
            self.assertGreaterEqual(dashboard.hunt_combo.count(), 1)
            self.assertEqual(dashboard.hunt_encounter_value.text(), "0")
            self.assertFalse(hasattr(dashboard, "setup_summary_label"))
            self.assertFalse(hasattr(dashboard, "capture_region_value"))
            dashboard_groups = {
                group.title(): group for group in dashboard.findChildren(QGroupBox)
            }
            self.assertEqual(dashboard_groups["Counters"].layout().rowCount(), 6)
            self.assertEqual(dashboard_groups["Live Details"].layout().rowCount(), 6)
            self.assertTrue(
                dashboard_groups["Live Details"].isAncestorOf(dashboard.last_score_value)
            )
            self.assertTrue(dashboard.log_box.isReadOnly())
            self.assertEqual(dashboard.log_box.document().maximumBlockCount(), 200)
            self.assertIn("Full monitor", dashboard.encounter_capture_info.text())
            encounter_snapshot = controller.build_idle_snapshot()
            encounter_snapshot.update(
                {
                    "last_encounter_capture_at": "2026-08-26T16:32:46.987654Z",
                }
            )
            with patch.object(dashboard, "_load_encounter_capture") as load_capture:
                dashboard._apply_snapshot(encounter_snapshot)
                dashboard._apply_snapshot(encounter_snapshot)
            load_capture.assert_called_once_with("2026-08-26T16:32:46.987654Z")

            logs_tab = expectations[3][0]
            self.assertIsInstance(logs_tab, LogsTab)
            self.assertEqual(logs_tab.capture_monitor_value.text(), "Unavailable")
            self.assertTrue(logs_tab.resolved_monitor_value.text())

            window = MainWindow(controller)
            self.assertEqual(window.tabs.tabText(2), "Capture")
            window.close()

    def test_capture_tab_shows_monitor_count_and_saves_active_monitor_immediately(self) -> None:
        monitors = [
            {"index": 1, "left": 0, "top": 0, "width": 1920, "height": 1080},
            {"index": 2, "left": 1920, "top": 0, "width": 2560, "height": 1440},
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_dir = root / "output"
            with (
                patch("app.services.config_service._read_physical_monitors", return_value=monitors),
                patch("app.services.app_controller.get_physical_monitors", return_value=monitors),
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
                with patch.object(
                    controller,
                    "capture_monitor_preview",
                    return_value={
                        "path": str(root / "monitor_preview.png"),
                        "monitor_index": 2,
                    },
                ) as capture_preview:
                    tab = CaptureSettingsTab(controller)
                    self.assertEqual(tab.monitor_count_label.text(), "2 monitors connected")
                    self.assertEqual(tab.monitor_combo.count(), 2)
                    self.assertEqual(tab.monitor_combo.itemText(0), "Monitor 1")
                    self.assertEqual(tab.monitor_combo.itemText(1), "Monitor 2")

                    tab.monitor_combo.setCurrentIndex(1)

                self.assertEqual(
                    controller.get_display_setup()["capture_monitor_index"],
                    2,
                )
                capture_preview.assert_called_once_with(
                    display_setup={"capture_monitor_index": 2}
                )

                logs_tab = LogsTab(controller)
                self.assertEqual(logs_tab.capture_monitor_value.text(), "Monitor 2")
                self.assertIn("2560x1440", logs_tab.resolved_monitor_value.text())
                self.assertTrue(logs_tab.last_capture_region_value.text())

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
