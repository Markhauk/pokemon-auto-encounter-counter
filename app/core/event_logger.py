from __future__ import annotations

import csv
import json
from collections import deque
from pathlib import Path

from .constants import DEFAULT_RECENT_EVENT_LIMIT, EVENT_LOG_CSV_FIELDS
from .paths import ENCOUNTER_LOG_CSV_FILE, EVENT_LOG_JSONL_FILE


class EventLogger:
    def __init__(
        self,
        *,
        csv_file: Path = ENCOUNTER_LOG_CSV_FILE,
        jsonl_file: Path = EVENT_LOG_JSONL_FILE,
    ) -> None:
        self.csv_file = csv_file
        self.jsonl_file = jsonl_file

    def ensure_files(self) -> None:
        self.csv_file.parent.mkdir(parents=True, exist_ok=True)

        if not self.jsonl_file.exists():
            self.jsonl_file.write_text("", encoding="utf-8")

        if not self.csv_file.exists() or self.csv_file.stat().st_size == 0:
            self._write_csv_header()
            return

        current_header = self._read_csv_header()
        if current_header != EVENT_LOG_CSV_FIELDS:
            self._rebuild_csv_from_jsonl()

    def append(self, payload: dict[str, object]) -> None:
        normalized = self._normalize_payload(payload)
        self.ensure_files()

        with self.csv_file.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=EVENT_LOG_CSV_FIELDS)
            writer.writerow(normalized)

        with self.jsonl_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(normalized, ensure_ascii=False) + "\n")

    def read_recent_events(self, limit: int = DEFAULT_RECENT_EVENT_LIMIT) -> list[dict[str, object]]:
        if limit <= 0 or not self.jsonl_file.exists():
            return []

        rows: deque[dict[str, object]] = deque(maxlen=limit)
        with self.jsonl_file.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict):
                    rows.append(self._normalize_payload(payload))
        return list(rows)

    def _write_csv_header(self) -> None:
        with self.csv_file.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=EVENT_LOG_CSV_FIELDS)
            writer.writeheader()

    def _read_csv_header(self) -> list[str]:
        try:
            with self.csv_file.open("r", newline="", encoding="utf-8") as handle:
                reader = csv.reader(handle)
                return next(reader, [])
        except OSError:
            return []

    def _rebuild_csv_from_jsonl(self) -> None:
        self._write_csv_header()
        events = self.read_recent_events(limit=1_000_000)
        if not events:
            return

        with self.csv_file.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=EVENT_LOG_CSV_FIELDS)
            writer.writerows(events)

    def _normalize_payload(self, payload: dict[str, object]) -> dict[str, object]:
        capture_region = payload.get("capture_region")
        capture_top = payload.get("capture_top", 0)
        capture_left = payload.get("capture_left", 0)
        capture_width = payload.get("capture_width", 0)
        capture_height = payload.get("capture_height", 0)

        if isinstance(capture_region, dict):
            capture_top = int(capture_region.get("top", capture_top))
            capture_left = int(capture_region.get("left", capture_left))
            capture_width = int(capture_region.get("width", capture_width))
            capture_height = int(capture_region.get("height", capture_height))

        return {
            "timestamp": str(payload.get("timestamp", "")),
            "event": str(payload.get("event", "")),
            "filter_id": str(payload.get("filter_id", "")),
            "filter_name": str(payload.get("filter_name", "")),
            "filter_event_type": str(payload.get("filter_event_type", "")),
            "filter_threshold": round(float(payload.get("filter_threshold", 0.0)), 6),
            "template_path": str(payload.get("template_path", "")),
            "active_label": str(payload.get("active_label", "")),
            "counter": int(payload.get("counter", 0)),
            "catch_counter": int(payload.get("catch_counter", 0)),
            "encounter_increment": int(payload.get("encounter_increment", 1)),
            "last_event": str(payload.get("last_event", "")),
            "last_event_at": str(payload.get("last_event_at", "")),
            "last_match_score": round(float(payload.get("last_match_score", 0.0)), 6),
            "last_catch_at_encounter": int(payload.get("last_catch_at_encounter", 0)),
            "encounters_since_last_catch": int(payload.get("encounters_since_last_catch", 0)),
            "capture_top": int(capture_top),
            "capture_left": int(capture_left),
            "capture_width": int(capture_width),
            "capture_height": int(capture_height),
        }
