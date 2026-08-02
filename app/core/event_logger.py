from __future__ import annotations

import csv
import io
import json
import os
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from .constants import DEFAULT_RECENT_EVENT_LIMIT, EVENT_LOG_CSV_FIELDS
from .file_io import atomic_write_bytes, atomic_write_text
from .paths import ENCOUNTER_LOG_CSV_FILE, EVENT_LOG_JSONL_FILE


@dataclass(frozen=True)
class SessionMigrationResult:
    event_count: int
    migrated_count: int
    legacy_session_started_at: str
    max_session_number: int
    backup_dir: str = ""


class EventLogger:
    def __init__(
        self,
        *,
        csv_file: Path = ENCOUNTER_LOG_CSV_FILE,
        jsonl_file: Path = EVENT_LOG_JSONL_FILE,
    ) -> None:
        self.csv_file = csv_file
        self.jsonl_file = jsonl_file
        self._files_ensured = False

    def migrate_legacy_session(
        self,
        *,
        game_id: str,
        game_name: str,
        session_id: str,
        session_number: int = 1,
    ) -> SessionMigrationResult:
        """Backfill session fields without dropping any existing JSON fields."""
        self.jsonl_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.jsonl_file.exists():
            atomic_write_text(self.jsonl_file, "")

        raw_events = self._read_all_jsonl_events_strict(
            error_prefix="Cannot migrate event log because"
        )
        first_timestamp = str(raw_events[0].get("timestamp", "")) if raw_events else ""
        migrated_count = 0
        for payload in raw_events:
            changed = False
            legacy_values: dict[str, object] = {
                "game_id": game_id,
                "game_name": game_name,
                "session_id": session_id,
                "session_number": max(1, int(session_number)),
                "session_started_at": first_timestamp,
                "session_start_counter": 0,
                "session_encounter_count": int(payload.get("counter", 0)),
            }
            for key, value in legacy_values.items():
                if key not in payload or payload.get(key) in (None, ""):
                    payload[key] = value
                    changed = True
            if changed:
                migrated_count += 1

        backup_dir = ""
        if migrated_count:
            backup_path = self.jsonl_file.parent / "migration_backups" / "session_identity_v1"
            backup_path.mkdir(parents=True, exist_ok=True)
            jsonl_backup = backup_path / self.jsonl_file.name
            csv_backup = backup_path / self.csv_file.name
            if not jsonl_backup.exists():
                atomic_write_bytes(jsonl_backup, self.jsonl_file.read_bytes())
            if self.csv_file.exists() and not csv_backup.exists():
                atomic_write_bytes(csv_backup, self.csv_file.read_bytes())
            backup_dir = str(backup_path)

            atomic_write_text(
                self.jsonl_file,
                "".join(json.dumps(payload, ensure_ascii=False) + "\n" for payload in raw_events),
            )

        if migrated_count or not self._csv_is_consistent(raw_events):
            self._write_csv_rows(raw_events)

        self._files_ensured = True
        return SessionMigrationResult(
            event_count=len(raw_events),
            migrated_count=migrated_count,
            legacy_session_started_at=first_timestamp,
            max_session_number=max(
                (int(payload.get("session_number", 0)) for payload in raw_events),
                default=0,
            ),
            backup_dir=backup_dir,
        )

    def ensure_files(self) -> None:
        if self._files_ensured:
            return

        self.jsonl_file.parent.mkdir(parents=True, exist_ok=True)
        self.csv_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.jsonl_file.exists():
            atomic_write_text(self.jsonl_file, "")

        events = self._read_all_jsonl_events_strict()
        if not self._csv_is_consistent(events):
            self._write_csv_rows(events)
        self._files_ensured = True

    def append(self, payload: dict[str, object]) -> None:
        normalized = self._normalize_payload(payload)
        self.ensure_files()

        # JSONL is authoritative. If the CSV append fails, startup reconciliation
        # recreates the missing derived row from this durable event.
        self._append_jsonl(normalized)
        try:
            self._append_csv(normalized)
        except BaseException:
            self._files_ensured = False
            raise

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

    def _append_jsonl(self, payload: dict[str, object]) -> None:
        with self.jsonl_file.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def _append_csv(self, payload: dict[str, object]) -> None:
        with self.csv_file.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=EVENT_LOG_CSV_FIELDS)
            writer.writerow(payload)
            handle.flush()
            os.fsync(handle.fileno())

    def _write_csv_header(self) -> None:
        self._write_csv_rows([])

    def _write_csv_rows(self, events: list[dict[str, object]]) -> None:
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=EVENT_LOG_CSV_FIELDS)
        writer.writeheader()
        writer.writerows(self._normalize_payload(event) for event in events)
        atomic_write_text(self.csv_file, buffer.getvalue())

    def _read_csv_header(self) -> list[str]:
        try:
            with self.csv_file.open("r", newline="", encoding="utf-8") as handle:
                reader = csv.reader(handle)
                return next(reader, [])
        except OSError:
            return []

    def _csv_is_consistent(self, events: list[dict[str, object]]) -> bool:
        if not self.csv_file.exists():
            return False
        try:
            with self.csv_file.open("r", newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                if reader.fieldnames != EVENT_LOG_CSV_FIELDS:
                    return False
                actual_rows = list(reader)
        except (csv.Error, OSError, UnicodeError):
            return False

        if len(actual_rows) != len(events):
            return False
        for actual, event in zip(actual_rows, events, strict=True):
            expected = self._normalize_payload(event)
            for field in EVENT_LOG_CSV_FIELDS:
                expected_text = "" if expected[field] is None else str(expected[field])
                if actual.get(field, "") != expected_text:
                    return False
        return True

    def _rebuild_csv_from_jsonl(self) -> None:
        self._write_csv_rows(self._read_all_jsonl_events_strict())

    def _read_all_jsonl_events_strict(
        self,
        *,
        error_prefix: str = "Cannot reconcile event log because",
    ) -> list[dict[str, object]]:
        events: list[dict[str, object]] = []
        try:
            lines = self.jsonl_file.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise ValueError(f"{error_prefix} JSONL could not be read.") from exc

        for line_number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"{error_prefix} line {line_number} is invalid JSON."
                ) from exc
            if not isinstance(payload, dict):
                raise ValueError(
                    f"{error_prefix} line {line_number} is not an object."
                )
            events.append(payload)
        return events

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
            "filter_cooldown_seconds": round(float(payload.get("filter_cooldown_seconds", 0.0)), 6),
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
            "game_id": str(payload.get("game_id", "")),
            "game_name": str(payload.get("game_name", "")),
            "session_id": str(payload.get("session_id", "")),
            "session_number": int(payload.get("session_number", 0)),
            "session_started_at": str(payload.get("session_started_at", "")),
            "session_start_counter": int(payload.get("session_start_counter", 0)),
            "session_encounter_count": int(payload.get("session_encounter_count", 0)),
        }
