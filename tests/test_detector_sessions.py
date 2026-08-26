from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, sentinel

import cv2
import numpy as np

from app.core.detector import EncounterCounterEngine
from app.core.event_logger import EventLogger
from app.core.filters import EVENT_TYPE_ENCOUNTER_START, FilterDefinition
from app.core.models import SessionContext
from app.core.state_manager import StateManager
from app.core.templates import TemplateManager


class DetectorSessionTests(unittest.TestCase):
    def test_counting_updates_lifetime_and_session_counters(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_dir = root / "output"
            templates_dir = root / "templates"
            output_dir.mkdir()
            templates_dir.mkdir()
            (output_dir / "counter.txt").write_text("100", encoding="utf-8")
            template = np.array(
                [[0, 255, 0], [255, 0, 255], [0, 255, 0]],
                dtype=np.uint8,
            )
            self.assertTrue(cv2.imwrite(str(templates_dir / "wild.png"), template))

            state_manager = StateManager(
                counter_file=output_dir / "counter.txt",
                state_file=output_dir / "state.json",
                output_dir=output_dir,
                templates_dir=templates_dir,
            )
            event_logger = EventLogger(
                csv_file=output_dir / "encounter_log.csv",
                jsonl_file=output_dir / "event_log.jsonl",
            )
            filter_definition = FilterDefinition(
                id="wild",
                name="Wild",
                enabled=True,
                event_type=EVENT_TYPE_ENCOUNTER_START,
                template_path="wild.png",
                capture_region={"left": 0, "top": 0, "width": 5, "height": 5},
                threshold=0.85,
            )
            context = SessionContext(
                game_id="pokemon_red",
                game_name="Pokemon Red",
                session_id="pokemon_red-session-0002",
                session_number=2,
                session_started_at="2026-01-02T00:00:00Z",
                session_start_counter=100,
                hunt_id="pokemon_red-hunt-0001",
                hunt_name="Charmander",
                hunt_started_at="2026-01-01T00:00:00Z",
                hunt_encounter_count=40,
                hunt_catch_counter=1,
                session_start_hunt_counter=40,
            )
            runtime_logs: list[dict[str, object]] = []
            encounter_capture_path = output_dir / "last_encounter_monitor.png"
            encounter_capture_region = {
                "left": -2560,
                "top": 40,
                "width": 2560,
                "height": 1440,
            }
            engine = EncounterCounterEngine(
                filters=[filter_definition],
                encounter_increment=3,
                state_manager=state_manager,
                event_logger=event_logger,
                template_manager=TemplateManager(templates_dir),
                session_context=context,
                log_handler=runtime_logs.append,
                encounter_capture_region=encounter_capture_region,
                encounter_capture_path=encounter_capture_path,
            )

            with (
                patch("app.core.detector.grab_region", return_value=sentinel.monitor_frame) as grab,
                patch("app.core.detector.save_image") as save_image,
            ):
                engine.record_filter_event(filter_definition, 0.91)

            grab.assert_called_once_with(encounter_capture_region)
            save_image.assert_called_once_with(encounter_capture_path, sentinel.monitor_frame)

            self.assertEqual(engine.counter, 103)
            self.assertEqual(engine.hunt_encounter_count, 43)
            self.assertEqual(engine.session_encounter_count, 3)
            snapshot = engine.snapshot(status="Running")
            self.assertEqual(snapshot.game_id, "pokemon_red")
            self.assertEqual(snapshot.session_number, 2)
            self.assertEqual(snapshot.session_encounter_count, 3)
            self.assertEqual(snapshot.last_encounter_capture_at, snapshot.last_event_at)
            event = event_logger.read_recent_events(limit=1)[0]
            self.assertEqual(event["game_id"], "pokemon_red")
            self.assertEqual(event["session_id"], "pokemon_red-session-0002")
            self.assertEqual(event["session_encounter_count"], 3)
            self.assertEqual(event["hunt_id"], "pokemon_red-hunt-0001")
            self.assertEqual(event["hunt_encounter_count"], 43)
            self.assertEqual(event["session_start_hunt_counter"], 40)
            self.assertEqual(
                runtime_logs[-1]["message"],
                "WILD [encounter_start] | +3 | Hunt encounters: 43 | Score: 0.9",
            )
            self.assertNotIn("all_time", str(runtime_logs[-1]["message"]))
            self.assertNotIn("catch", str(runtime_logs[-1]["message"]).lower())

            successful_capture_at = engine.last_encounter_capture_at
            with patch("app.core.detector.grab_region", side_effect=OSError("capture failed")):
                engine.record_filter_event(filter_definition, 0.92)

            self.assertEqual(engine.last_encounter_capture_at, successful_capture_at)
            self.assertEqual(engine.hunt_encounter_count, 46)
            self.assertEqual(event_logger.read_recent_events(limit=1)[0]["hunt_encounter_count"], 46)


if __name__ == "__main__":
    unittest.main()
