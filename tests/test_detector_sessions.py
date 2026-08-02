from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

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
            )
            engine = EncounterCounterEngine(
                filters=[filter_definition],
                encounter_increment=3,
                state_manager=state_manager,
                event_logger=event_logger,
                template_manager=TemplateManager(templates_dir),
                session_context=context,
            )

            engine.record_filter_event(filter_definition, 0.91)

            self.assertEqual(engine.counter, 103)
            self.assertEqual(engine.session_encounter_count, 3)
            snapshot = engine.snapshot(status="Running")
            self.assertEqual(snapshot.game_id, "pokemon_red")
            self.assertEqual(snapshot.session_number, 2)
            self.assertEqual(snapshot.session_encounter_count, 3)
            event = event_logger.read_recent_events(limit=1)[0]
            self.assertEqual(event["game_id"], "pokemon_red")
            self.assertEqual(event["session_id"], "pokemon_red-session-0002")
            self.assertEqual(event["session_encounter_count"], 3)


if __name__ == "__main__":
    unittest.main()
