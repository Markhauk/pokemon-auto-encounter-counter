from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from app.core.constants import EVENT_LOG_CSV_FIELDS
from app.core.event_logger import EventLogger


class EventLoggerSessionMigrationTests(unittest.TestCase):
    def test_migration_preserves_records_and_unknown_json_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            jsonl_file = root / "event_log.jsonl"
            csv_file = root / "encounter_log.csv"
            legacy_events = [
                {
                    "timestamp": "2026-01-01T00:00:00Z",
                    "event": "wild",
                    "counter": 10,
                    "unknown_future_field": {"preserve": True},
                },
                {
                    "timestamp": "2026-01-01T00:01:00Z",
                    "event": "wild",
                    "counter": 11,
                },
            ]
            jsonl_file.write_text(
                "".join(json.dumps(event) + "\n" for event in legacy_events),
                encoding="utf-8",
            )
            csv_file.write_text("timestamp,event,counter\n", encoding="utf-8")

            logger = EventLogger(csv_file=csv_file, jsonl_file=jsonl_file)
            result = logger.migrate_legacy_session(
                game_id="pokemon_red",
                game_name="Pokemon Red",
                session_id="pokemon_red-session-0001",
            )

            self.assertEqual(result.event_count, 2)
            self.assertEqual(result.migrated_count, 2)
            migrated = [
                json.loads(line)
                for line in jsonl_file.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(len(migrated), len(legacy_events))
            self.assertEqual(
                migrated[0]["unknown_future_field"],
                {"preserve": True},
            )
            self.assertEqual(migrated[0]["game_id"], "pokemon_red")
            self.assertEqual(migrated[0]["session_number"], 1)
            self.assertEqual(migrated[1]["session_encounter_count"], 11)

            with csv_file.open("r", newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
                self.assertEqual(handle.closed, False)
            self.assertEqual(len(rows), 2)
            self.assertEqual(list(rows[0]), EVENT_LOG_CSV_FIELDS)
            self.assertEqual(rows[0]["session_id"], "pokemon_red-session-0001")

            backup_dir = Path(result.backup_dir)
            self.assertTrue((backup_dir / "event_log.jsonl").exists())
            self.assertTrue((backup_dir / "encounter_log.csv").exists())

            second_result = logger.migrate_legacy_session(
                game_id="pokemon_red",
                game_name="Pokemon Red",
                session_id="pokemon_red-session-0001",
            )
            self.assertEqual(second_result.migrated_count, 0)
            self.assertEqual(second_result.event_count, 2)

    def test_invalid_json_aborts_before_rewriting(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            jsonl_file = root / "event_log.jsonl"
            csv_file = root / "encounter_log.csv"
            original = '{"counter": 1}\nnot-json\n'
            jsonl_file.write_text(original, encoding="utf-8")
            logger = EventLogger(csv_file=csv_file, jsonl_file=jsonl_file)

            with self.assertRaisesRegex(ValueError, "line 2"):
                logger.migrate_legacy_session(
                    game_id="game",
                    game_name="Game",
                    session_id="game-session-0001",
                )
            self.assertEqual(jsonl_file.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
