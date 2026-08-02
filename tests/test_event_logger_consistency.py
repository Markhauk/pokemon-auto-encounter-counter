from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core.constants import EVENT_LOG_CSV_FIELDS
from app.core.event_logger import EventLogger


def _event(counter: int) -> dict[str, object]:
    return {
        "timestamp": f"2026-01-01T00:00:0{counter}Z",
        "event": "wild",
        "filter_id": "wild",
        "counter": counter,
    }


class EventLoggerConsistencyTests(unittest.TestCase):
    def test_startup_rebuilds_stale_csv_from_authoritative_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            jsonl_file = root / "event_log.jsonl"
            csv_file = root / "encounter_log.csv"
            events = [_event(1), _event(2)]
            jsonl_file.write_text(
                "".join(json.dumps(event) + "\n" for event in events),
                encoding="utf-8",
            )
            csv_file.write_text("timestamp,event,counter\nold,wild,99\n", encoding="utf-8")

            EventLogger(csv_file=csv_file, jsonl_file=jsonl_file).ensure_files()

            with csv_file.open("r", newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                rows = list(reader)
                self.assertEqual(reader.fieldnames, EVENT_LOG_CSV_FIELDS)
            self.assertEqual([row["counter"] for row in rows], ["1", "2"])

    def test_csv_append_failure_is_repaired_from_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logger = EventLogger(
                csv_file=root / "encounter_log.csv",
                jsonl_file=root / "event_log.jsonl",
            )

            with patch.object(logger, "_append_csv", side_effect=OSError("disk full")):
                with self.assertRaisesRegex(OSError, "disk full"):
                    logger.append(_event(1))

            json_rows = [
                json.loads(line)
                for line in logger.jsonl_file.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(len(json_rows), 1)

            repaired = EventLogger(csv_file=logger.csv_file, jsonl_file=logger.jsonl_file)
            repaired.ensure_files()
            with repaired.csv_file.open("r", newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["counter"], "1")

    def test_malformed_jsonl_aborts_without_overwriting_csv(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            jsonl_file = root / "event_log.jsonl"
            csv_file = root / "encounter_log.csv"
            jsonl_file.write_text('{"counter": 1}\nnot-json\n', encoding="utf-8")
            original_csv = "keep,this,csv\n"
            csv_file.write_text(original_csv, encoding="utf-8")

            logger = EventLogger(csv_file=csv_file, jsonl_file=jsonl_file)
            with self.assertRaisesRegex(ValueError, "line 2"):
                logger.ensure_files()

            self.assertEqual(csv_file.read_text(encoding="utf-8"), original_csv)


if __name__ == "__main__":
    unittest.main()
