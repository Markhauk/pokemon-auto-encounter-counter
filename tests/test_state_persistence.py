from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.core.models import CounterSnapshot
from app.core.state_manager import StateManager


def _snapshot(counter: int) -> CounterSnapshot:
    return CounterSnapshot(
        status="Stopped",
        mode_key="filters",
        mode_name="Filters",
        game_id="game",
        game_name="Game",
        session_id="game-session-0001",
        session_number=1,
        session_started_at="2026-01-01T00:00:00Z",
        session_start_counter=40,
        session_encounter_count=counter - 40,
        encounter_increment=1,
        enabled_filter_count=1,
        counter=counter,
        catch_counter=2,
        last_event="wild",
        last_event_at="2026-01-01T00:01:00Z",
        last_match_score=0.91,
        last_filter_id="wild",
        last_filter_name="Wild",
        last_filter_event_type="encounter_start",
        active_label="",
        last_catch_at_encounter=20,
        encounters_since_last_catch=counter - 20,
        capture_region={"left": 0, "top": 0, "width": 100, "height": 50},
        waiting_for_clear=False,
        cooldown_until=0.0,
        frame_index=1,
        filters_runtime={},
    )


class StatePersistenceTests(unittest.TestCase):
    def test_state_is_canonical_when_counter_mirror_is_stale(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manager = StateManager(
                counter_file=root / "output" / "counter.txt",
                state_file=root / "output" / "state.json",
                output_dir=root / "output",
                templates_dir=root / "templates",
            )
            manager.save(_snapshot(42))
            manager.counter_file.write_text("5", encoding="utf-8")

            self.assertEqual(manager.read_counter(), 42)
            self.assertEqual(manager.read_state_dict()["counter"], 42)

    def test_obs_counter_mirrors_the_active_hunt_total(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manager = StateManager(
                counter_file=root / "output" / "counter.txt",
                state_file=root / "output" / "state.json",
                output_dir=root / "output",
                templates_dir=root / "templates",
            )
            snapshot = _snapshot(9578)
            snapshot.hunt_encounter_count = 327

            manager.save(snapshot)

            self.assertEqual(manager.obs_counter_file.name, "obs_counter.txt")
            self.assertEqual(manager.obs_counter_file.read_text(encoding="utf-8"), "327")
            self.assertEqual(manager.counter_file.read_text(encoding="utf-8"), "9578")


if __name__ == "__main__":
    unittest.main()
