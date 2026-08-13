from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, sentinel

from app.core.event_logger import EventLogger
from app.core.paths import MONITOR_PREVIEW_FILE
from app.core.state_manager import StateManager
from app.services.app_controller import AppController
from app.services.config_service import ConfigService


class CaptureMonitorPreviewTests(unittest.TestCase):
    def test_preview_captures_the_entire_selected_monitor(self) -> None:
        monitors = [
            {"index": 1, "left": 0, "top": 0, "width": 1920, "height": 1080},
            {"index": 2, "left": -2560, "top": 40, "width": 2560, "height": 1440},
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_dir = root / "output"
            with patch("app.services.config_service._read_physical_monitors", return_value=monitors):
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

            with (
                patch.object(controller, "get_physical_monitors", return_value=monitors),
                patch("app.services.app_controller.grab_region", return_value=sentinel.frame) as grab,
                patch("app.services.app_controller.save_image") as save_image,
            ):
                payload = controller.capture_monitor_preview(
                    display_setup={"capture_monitor_index": 2}
                )

            expected_region = {
                "left": -2560,
                "top": 40,
                "width": 2560,
                "height": 1440,
            }
            grab.assert_called_once_with(expected_region)
            save_image.assert_called_once_with(MONITOR_PREVIEW_FILE, sentinel.frame)
            self.assertEqual(payload["monitor_index"], 2)
            self.assertEqual(payload["monitor"], monitors[1])
            self.assertEqual(payload["path"], str(MONITOR_PREVIEW_FILE))


if __name__ == "__main__":
    unittest.main()
