from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.core.event_logger import EventLogger
from app.core.filters import GameDefinition
from app.core.state_manager import StateManager
from app.services.session_service import SessionService


class FakeConfigService:
    def __init__(self) -> None:
        self.game = GameDefinition(id="pokemon_red", name="Pokemon Red")

    def get_active_game_id(self) -> str:
        return self.game.id

    def get_game(self, game_id: str) -> GameDefinition | None:
        return self.game if game_id == self.game.id else None


class SessionServiceTests(unittest.TestCase):
    def test_initialize_migrates_history_and_starts_session_two_without_reset(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_dir = root / "output"
            output_dir.mkdir()
            counter_file = output_dir / "counter.txt"
            state_file = output_dir / "state.json"
            jsonl_file = output_dir / "event_log.jsonl"
            csv_file = output_dir / "encounter_log.csv"
            counter_file.write_text("9578", encoding="utf-8")
            state_file.write_text(
                json.dumps({"counter": 9578, "catch_counter": 1}),
                encoding="utf-8",
            )
            jsonl_file.write_text(
                json.dumps(
                    {
                        "timestamp": "2026-01-01T00:00:00Z",
                        "event": "wild",
                        "counter": 9578,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            state_manager = StateManager(
                counter_file=counter_file,
                state_file=state_file,
                output_dir=output_dir,
                templates_dir=root / "templates",
            )
            logger = EventLogger(csv_file=csv_file, jsonl_file=jsonl_file)
            service = SessionService(
                config_service=FakeConfigService(),  # type: ignore[arg-type]
                state_manager=state_manager,
                event_logger=logger,
            )

            context, migration = service.initialize()

            self.assertEqual(migration.event_count, 1)
            self.assertEqual(context.session_number, 2)
            self.assertEqual(context.session_start_counter, 9578)
            self.assertEqual(context.session_encounter_count, 0)
            self.assertEqual(state_manager.read_counter(), 9578)
            state = state_manager.read_state_dict()
            self.assertEqual(state["counter"], 9578)
            self.assertEqual(state["catch_counter"], 1)
            backup_dir = output_dir / "migration_backups" / "session_identity_v1"
            self.assertEqual((backup_dir / "counter.txt").read_text(encoding="utf-8"), "9578")
            backed_up_state = json.loads((backup_dir / "state.json").read_text(encoding="utf-8"))
            self.assertNotIn("session_id", backed_up_state)

            next_context = service.start_new_session()
            self.assertEqual(next_context.session_number, 3)
            self.assertEqual(next_context.session_start_counter, 9578)
            self.assertEqual(state_manager.read_counter(), 9578)


if __name__ == "__main__":
    unittest.main()
