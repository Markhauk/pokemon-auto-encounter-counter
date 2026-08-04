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
            self.assertEqual(context.hunt_name, "Original Hunt")
            self.assertEqual(context.hunt_encounter_count, 9578)
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

    def test_hunts_can_be_completed_created_and_resumed_without_resetting_all_time(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_dir = root / "output"
            output_dir.mkdir()
            state_file = output_dir / "state.json"
            counter_file = output_dir / "counter.txt"
            state_file.write_text(
                json.dumps({"counter": 250, "catch_counter": 2}),
                encoding="utf-8",
            )
            counter_file.write_text("250", encoding="utf-8")
            state_manager = StateManager(
                counter_file=counter_file,
                state_file=state_file,
                output_dir=output_dir,
                templates_dir=root / "templates",
            )
            service = SessionService(
                config_service=FakeConfigService(),  # type: ignore[arg-type]
                state_manager=state_manager,
                event_logger=EventLogger(
                    csv_file=output_dir / "encounter_log.csv",
                    jsonl_file=output_dir / "event_log.jsonl",
                ),
            )
            original_context, _ = service.initialize()

            new_context = service.start_new_hunt(
                name="Shiny Rayquaza",
                complete_current=True,
            )

            self.assertEqual(new_context.hunt_name, "Shiny Rayquaza")
            self.assertEqual(new_context.hunt_encounter_count, 0)
            self.assertEqual(new_context.session_number, 1)
            self.assertEqual(state_manager.read_counter(), 250)
            hunts = state_manager.list_hunts(game_id="pokemon_red")
            self.assertEqual(len(hunts), 2)
            original = next(hunt for hunt in hunts if hunt.hunt_id == original_context.hunt_id)
            self.assertEqual(original.hunt_status, "completed")
            self.assertEqual(original.hunt_encounter_count, 250)

            active_state = state_manager.read_state_dict()
            active_state["hunt_encounter_count"] = 12
            active_state["hunt_catch_counter"] = 1
            state_file.write_text(json.dumps(active_state), encoding="utf-8")

            resumed = service.select_hunt(original_context.hunt_id)
            self.assertEqual(resumed.hunt_name, "Original Hunt")
            self.assertEqual(resumed.hunt_encounter_count, 250)
            self.assertEqual(resumed.session_number, 2)
            self.assertEqual(state_manager.read_counter(), 250)
            self.assertEqual(len(state_manager.list_hunts(game_id="pokemon_red")), 2)

            resumed_new_hunt = service.select_hunt(new_context.hunt_id)
            self.assertEqual(resumed_new_hunt.hunt_encounter_count, 12)
            self.assertEqual(resumed_new_hunt.hunt_catch_counter, 1)
            self.assertEqual(state_manager.read_counter(), 250)


if __name__ == "__main__":
    unittest.main()
