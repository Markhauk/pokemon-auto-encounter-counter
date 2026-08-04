from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .exceptions import SingleInstanceError
from .file_io import atomic_write_bytes, atomic_write_text
from .models import CounterSnapshot, HuntContext, SessionContext
from .paths import COUNTER_FILE, OUTPUT_DIR, STATE_FILE, TEMPLATES_DIR


def _safe_int(value: object, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: object, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class SingleInstanceGuard:
    def __init__(self, lock_file: Path) -> None:
        self.lock_file = lock_file
        self.handle = None

    def __enter__(self) -> "SingleInstanceGuard":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        self.release()

    def acquire(self) -> None:
        self.lock_file.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.lock_file.open("a+", encoding="utf-8")

        try:
            self.handle.seek(0)
            self.handle.write(" ")
            self.handle.flush()
            self.handle.seek(0)

            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            other_pid = self._read_existing_pid()
            self.handle.close()
            self.handle = None
            pid_suffix = f" (PID {other_pid})" if other_pid else ""
            raise SingleInstanceError(f"Another scanning session is already running{pid_suffix}.") from exc

        self.handle.seek(0)
        self.handle.truncate()
        self.handle.write(str(os.getpid()))
        self.handle.flush()

    def release(self) -> None:
        if self.handle is None:
            return

        try:
            self.handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        finally:
            self.handle.close()
            self.handle = None
            try:
                self.lock_file.unlink()
            except OSError:
                pass

    def _read_existing_pid(self) -> Optional[str]:
        try:
            pid = self.lock_file.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        return pid or None


class StateManager:
    def __init__(
        self,
        *,
        counter_file: Path = COUNTER_FILE,
        state_file: Path = STATE_FILE,
        output_dir: Path = OUTPUT_DIR,
        templates_dir: Path = TEMPLATES_DIR,
    ) -> None:
        self.counter_file = counter_file
        self.state_file = state_file
        self.output_dir = output_dir
        self.templates_dir = templates_dir

    def ensure_directories(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.templates_dir.mkdir(parents=True, exist_ok=True)

    def load(
        self,
        *,
        mode_key: str,
        mode_name: str,
        capture_region: dict[str, int],
        encounter_increment: int,
        session_context: SessionContext | None = None,
    ) -> dict[str, object]:
        session_defaults = session_context.as_dict() if session_context is not None else {}
        state: dict[str, object] = {
            "counter": 0,
            "catch_counter": 0,
            "encounter_increment": max(1, int(encounter_increment)),
            "cooldown_until": 0.0,
            "waiting_for_clear": False,
            "last_event": "none",
            "last_event_at": None,
            "last_match_score": 0.0,
            "last_filter_id": "",
            "last_filter_name": "",
            "last_filter_event_type": "",
            "active_label": "",
            "enabled_filter_count": 0,
            "last_catch_at_encounter": 0,
            "encounters_since_last_catch": 0,
            "capture_region": dict(capture_region),
            "filters_runtime": {},
            "mode_key": mode_key,
            "mode_name": mode_name,
            "game_id": str(session_defaults.get("game_id", "")),
            "game_name": str(session_defaults.get("game_name", "")),
            "hunt_id": str(session_defaults.get("hunt_id", "")),
            "hunt_name": str(session_defaults.get("hunt_name", "")),
            "hunt_status": str(session_defaults.get("hunt_status", "active")),
            "hunt_started_at": str(session_defaults.get("hunt_started_at", "")),
            "hunt_completed_at": str(session_defaults.get("hunt_completed_at", "")),
            "hunt_encounter_count": _safe_int(session_defaults.get("hunt_encounter_count"), 0),
            "hunt_catch_counter": _safe_int(session_defaults.get("hunt_catch_counter"), 0),
            "hunt_last_catch_at_encounter": _safe_int(
                session_defaults.get("hunt_last_catch_at_encounter"), 0
            ),
            "hunt_encounters_since_last_catch": _safe_int(
                session_defaults.get("hunt_encounters_since_last_catch"), 0
            ),
            "session_id": str(session_defaults.get("session_id", "")),
            "session_number": _safe_int(session_defaults.get("session_number"), 0),
            "session_started_at": str(session_defaults.get("session_started_at", "")),
            "session_start_counter": _safe_int(session_defaults.get("session_start_counter"), 0),
            "session_start_hunt_counter": _safe_int(
                session_defaults.get("session_start_hunt_counter"), 0
            ),
            "session_encounter_count": _safe_int(session_defaults.get("session_encounter_count"), 0),
        }

        if self.counter_file.exists():
            try:
                state["counter"] = int(self.counter_file.read_text(encoding="utf-8").strip())
            except ValueError:
                state["counter"] = 0

        if self.state_file.exists():
            try:
                data = json.loads(self.state_file.read_text(encoding="utf-8"))
                state["counter"] = _safe_int(data.get("counter"), int(state["counter"]))
                state["catch_counter"] = _safe_int(data.get("catch_counter"), 0)
                state["cooldown_until"] = _safe_float(data.get("cooldown_until"), 0.0)
                state["waiting_for_clear"] = bool(data.get("waiting_for_clear", False))
                state["last_event"] = str(data.get("last_event", "none"))
                state["last_event_at"] = data.get("last_event_at")
                state["last_match_score"] = _safe_float(data.get("last_match_score"), 0.0)
                state["last_filter_id"] = str(data.get("last_filter_id", ""))
                state["last_filter_name"] = str(data.get("last_filter_name", ""))
                state["last_filter_event_type"] = str(data.get("last_filter_event_type", ""))
                state["active_label"] = str(data.get("active_label", ""))
                state["enabled_filter_count"] = _safe_int(data.get("enabled_filter_count"), 0)
                state["last_catch_at_encounter"] = _safe_int(data.get("last_catch_at_encounter"), 0)
                state["encounters_since_last_catch"] = _safe_int(data.get("encounters_since_last_catch"), 0)
                state["hunt_encounter_count"] = _safe_int(
                    data.get("hunt_encounter_count"), int(state["hunt_encounter_count"])
                )
                state["hunt_catch_counter"] = _safe_int(
                    data.get("hunt_catch_counter"), int(state["hunt_catch_counter"])
                )
                state["hunt_last_catch_at_encounter"] = _safe_int(
                    data.get("hunt_last_catch_at_encounter"),
                    int(state["hunt_last_catch_at_encounter"]),
                )
                state["hunt_encounters_since_last_catch"] = _safe_int(
                    data.get("hunt_encounters_since_last_catch"),
                    int(state["hunt_encounters_since_last_catch"]),
                )
                if isinstance(data.get("filters_runtime"), dict):
                    state["filters_runtime"] = data.get("filters_runtime", {})
                if session_context is None:
                    state["game_id"] = str(data.get("game_id", ""))
                    state["game_name"] = str(data.get("game_name", ""))
                    state["hunt_id"] = str(data.get("hunt_id", ""))
                    state["hunt_name"] = str(data.get("hunt_name", ""))
                    state["hunt_status"] = str(data.get("hunt_status", "active"))
                    state["hunt_started_at"] = str(data.get("hunt_started_at", ""))
                    state["hunt_completed_at"] = str(data.get("hunt_completed_at", ""))
                    state["session_id"] = str(data.get("session_id", ""))
                    state["session_number"] = _safe_int(data.get("session_number"), 0)
                    state["session_started_at"] = str(data.get("session_started_at", ""))
                    state["session_start_counter"] = _safe_int(data.get("session_start_counter"), 0)
                    state["session_start_hunt_counter"] = _safe_int(
                        data.get("session_start_hunt_counter"), 0
                    )
                    state["session_encounter_count"] = _safe_int(data.get("session_encounter_count"), 0)
            except (json.JSONDecodeError, OSError):
                pass

        counter = int(state["counter"])
        last_catch_at_encounter = int(state["last_catch_at_encounter"])
        if last_catch_at_encounter > 0:
            state["encounters_since_last_catch"] = max(0, counter - last_catch_at_encounter)

        hunt_counter = int(state["hunt_encounter_count"])
        hunt_last_catch = int(state["hunt_last_catch_at_encounter"])
        if hunt_last_catch > 0:
            state["hunt_encounters_since_last_catch"] = max(0, hunt_counter - hunt_last_catch)
        else:
            state["hunt_encounters_since_last_catch"] = hunt_counter

        state["encounter_increment"] = max(1, int(encounter_increment))
        state["capture_region"] = dict(capture_region)
        state["mode_key"] = mode_key
        state["mode_name"] = mode_name
        return state

    def save(self, snapshot: CounterSnapshot) -> None:
        state = self.read_state_dict()
        state.update(
            {
                "counter": snapshot.counter,
                "catch_counter": snapshot.catch_counter,
                "encounter_increment": snapshot.encounter_increment,
                "cooldown_until": snapshot.cooldown_until,
                "waiting_for_clear": snapshot.waiting_for_clear,
                "last_event": snapshot.last_event,
                "last_event_at": snapshot.last_event_at,
                "last_match_score": snapshot.last_match_score,
                "last_filter_id": snapshot.last_filter_id,
                "last_filter_name": snapshot.last_filter_name,
                "last_filter_event_type": snapshot.last_filter_event_type,
                "active_label": snapshot.active_label,
                "enabled_filter_count": snapshot.enabled_filter_count,
                "last_catch_at_encounter": snapshot.last_catch_at_encounter,
                "encounters_since_last_catch": snapshot.encounters_since_last_catch,
                "capture_region": snapshot.capture_region,
                "filters_runtime": snapshot.filters_runtime,
                "mode_key": snapshot.mode_key,
                "mode_name": snapshot.mode_name,
                "game_id": snapshot.game_id,
                "game_name": snapshot.game_name,
                "active_hunt_id": snapshot.hunt_id,
                "hunt_id": snapshot.hunt_id,
                "hunt_name": snapshot.hunt_name,
                "hunt_status": snapshot.hunt_status,
                "hunt_started_at": snapshot.hunt_started_at,
                "hunt_completed_at": snapshot.hunt_completed_at,
                "hunt_encounter_count": snapshot.hunt_encounter_count,
                "hunt_catch_counter": snapshot.hunt_catch_counter,
                "hunt_last_catch_at_encounter": snapshot.hunt_last_catch_at_encounter,
                "hunt_encounters_since_last_catch": snapshot.hunt_encounters_since_last_catch,
                "session_id": snapshot.session_id,
                "session_number": snapshot.session_number,
                "session_started_at": snapshot.session_started_at,
                "session_start_counter": snapshot.session_start_counter,
                "session_start_hunt_counter": snapshot.session_start_hunt_counter,
                "session_encounter_count": snapshot.session_encounter_count,
                "status": snapshot.status,
            }
        )
        self._upsert_hunt_from_snapshot(state, snapshot)
        state_text = json.dumps(state, indent=2)
        # state.json is canonical; counter.txt is a compatibility mirror.
        atomic_write_text(self.state_file, state_text)
        atomic_write_text(self.counter_file, str(snapshot.counter))

    def write_session_context(self, context: SessionContext) -> dict[str, object]:
        """Update session metadata without changing any persisted counters."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        state = self.read_state_dict()
        state.update(context.as_dict())
        state["active_hunt_id"] = context.hunt_id
        active_by_game = state.get("active_hunt_by_game")
        if not isinstance(active_by_game, dict):
            active_by_game = {}
        active_by_game[context.game_id] = context.hunt_id
        state["active_hunt_by_game"] = active_by_game
        self._upsert_hunt_from_session(state, context)
        if "counter" not in state:
            state["counter"] = self.read_counter()
        atomic_write_text(self.state_file, json.dumps(state, indent=2))
        return state

    def list_hunts(self, *, game_id: str | None = None) -> list[HuntContext]:
        hunts = [self._hunt_context(record) for record in self._hunt_records(self.read_state_dict())]
        if game_id is not None:
            hunts = [hunt for hunt in hunts if hunt.game_id == game_id]
        return hunts

    def get_active_hunt(self, *, game_id: str | None = None) -> HuntContext | None:
        state = self.read_state_dict()
        hunts = self._hunt_records(state)
        active_id = ""
        active_by_game = state.get("active_hunt_by_game")
        if game_id is not None and isinstance(active_by_game, dict):
            active_id = str(active_by_game.get(game_id, ""))
        if not active_id and game_id is None:
            active_id = str(state.get("active_hunt_id", ""))
        for record in hunts:
            if str(record.get("hunt_id", "")) == active_id:
                context = self._hunt_context(record)
                if game_id is None or context.game_id == game_id:
                    return context
        if game_id is not None:
            candidates = [record for record in hunts if str(record.get("game_id", "")) == game_id]
            if candidates:
                return self._hunt_context(candidates[-1])
        return None

    def ensure_hunt_for_game(self, *, game_id: str, game_name: str) -> HuntContext:
        state = self.read_state_dict()
        if "hunts" not in state:
            self.backup_for_migration("hunt_identity_v1")
            started_at = str(state.get("session_started_at", "")) or _now_iso()
            original_counter = max(0, _safe_int(state.get("counter"), self.read_counter()))
            original_last_catch = max(
                0, _safe_int(state.get("last_catch_at_encounter"), 0)
            )
            original_since_catch = (
                max(0, original_counter - original_last_catch)
                if original_last_catch > 0
                else original_counter
            )
            original = HuntContext(
                hunt_id=self._build_hunt_id(game_id, 1),
                hunt_name="Original Hunt",
                game_id=game_id,
                game_name=game_name,
                hunt_status="active",
                hunt_started_at=started_at,
                hunt_encounter_count=original_counter,
                hunt_catch_counter=max(0, _safe_int(state.get("catch_counter"), 0)),
                hunt_last_catch_at_encounter=original_last_catch,
                hunt_encounters_since_last_catch=original_since_catch,
                session_number=max(0, _safe_int(state.get("session_number"), 0)),
            )
            state["hunts"] = [original.as_dict()]
            self._activate_hunt(state, original.hunt_id)
            atomic_write_text(self.state_file, json.dumps(state, indent=2))
            return original

        active = self.get_active_hunt(game_id=game_id)
        if active is not None:
            self._activate_hunt(state, active.hunt_id)
            atomic_write_text(self.state_file, json.dumps(state, indent=2))
            return self._hunt_context(self._find_hunt_record(state, active.hunt_id))

        return self.create_hunt(
            game_id=game_id,
            game_name=game_name,
            name="Hunt 1",
            complete_current=False,
        )

    def create_hunt(
        self,
        *,
        game_id: str,
        game_name: str,
        name: str,
        complete_current: bool,
    ) -> HuntContext:
        cleaned_name = " ".join(name.split()).strip()
        if not cleaned_name:
            raise ValueError("Enter a name for the new hunt.")
        state = self.read_state_dict()
        records = self._hunt_records(state)
        if any(
            str(record.get("game_id", "")) == game_id
            and str(record.get("hunt_name", "")).casefold() == cleaned_name.casefold()
            for record in records
        ):
            raise ValueError(f"A hunt named '{cleaned_name}' already exists for this game.")

        self._sync_active_hunt_from_state(state)
        current_id = str(state.get("active_hunt_id", ""))
        now = _now_iso()
        for record in records:
            if str(record.get("hunt_id", "")) == current_id:
                record["hunt_status"] = "completed" if complete_current else "paused"
                record["hunt_completed_at"] = now if complete_current else ""

        number = 1
        existing_ids = {str(record.get("hunt_id", "")) for record in records}
        while self._build_hunt_id(game_id, number) in existing_ids:
            number += 1
        new_hunt = HuntContext(
            hunt_id=self._build_hunt_id(game_id, number),
            hunt_name=cleaned_name,
            game_id=game_id,
            game_name=game_name,
            hunt_status="active",
            hunt_started_at=now,
        )
        records.append(new_hunt.as_dict())
        state["hunts"] = records
        self._activate_hunt(state, new_hunt.hunt_id)
        atomic_write_text(self.state_file, json.dumps(state, indent=2))
        return new_hunt

    def select_hunt(self, *, hunt_id: str, game_id: str) -> HuntContext:
        state = self.read_state_dict()
        target = self._find_hunt_record(state, hunt_id)
        if str(target.get("game_id", "")) != game_id:
            raise ValueError("The selected hunt does not belong to the active game.")

        self._sync_active_hunt_from_state(state)
        current_id = str(state.get("active_hunt_id", ""))
        for record in self._hunt_records(state):
            record_id = str(record.get("hunt_id", ""))
            if record_id == current_id and record_id != hunt_id and record.get("hunt_status") != "completed":
                record["hunt_status"] = "paused"
            if record_id == hunt_id:
                record["hunt_status"] = "active"
                record["hunt_completed_at"] = ""
        self._activate_hunt(state, hunt_id)
        atomic_write_text(self.state_file, json.dumps(state, indent=2))
        return self._hunt_context(self._find_hunt_record(state, hunt_id))

    def _activate_hunt(self, state: dict[str, object], hunt_id: str) -> None:
        target = self._find_hunt_record(state, hunt_id)
        context = self._hunt_context(target)
        previous_id = str(state.get("active_hunt_id", ""))
        if previous_id and previous_id != hunt_id:
            try:
                previous = self._find_hunt_record(state, previous_id)
            except ValueError:
                pass
            else:
                if previous.get("hunt_status") != "completed":
                    previous["hunt_status"] = "paused"
        target["hunt_status"] = "active"
        target["hunt_completed_at"] = ""
        state["active_hunt_id"] = hunt_id
        active_by_game = state.get("active_hunt_by_game")
        if not isinstance(active_by_game, dict):
            active_by_game = {}
        active_by_game[context.game_id] = hunt_id
        state["active_hunt_by_game"] = active_by_game
        for key in (
            "hunt_id",
            "hunt_name",
            "hunt_status",
            "hunt_started_at",
            "hunt_completed_at",
            "hunt_encounter_count",
            "hunt_catch_counter",
            "hunt_last_catch_at_encounter",
            "hunt_encounters_since_last_catch",
        ):
            state[key] = target.get(key, "" if key.endswith(("id", "name", "at", "status")) else 0)

    def _sync_active_hunt_from_state(self, state: dict[str, object]) -> None:
        active_id = str(state.get("active_hunt_id", ""))
        if not active_id:
            return
        try:
            record = self._find_hunt_record(state, active_id)
        except ValueError:
            return
        for key in (
            "hunt_name",
            "hunt_status",
            "hunt_started_at",
            "hunt_completed_at",
            "hunt_encounter_count",
            "hunt_catch_counter",
            "hunt_last_catch_at_encounter",
            "hunt_encounters_since_last_catch",
        ):
            if key in state:
                record[key] = state[key]
        record["session_number"] = max(
            _safe_int(record.get("session_number"), 0),
            _safe_int(state.get("session_number"), 0),
        )

    def _upsert_hunt_from_snapshot(self, state: dict[str, object], snapshot: CounterSnapshot) -> None:
        if not snapshot.hunt_id:
            return
        try:
            record = self._find_hunt_record(state, snapshot.hunt_id)
        except ValueError:
            record = {}
            records = self._hunt_records(state)
            records.append(record)
            state["hunts"] = records
        record.update(
            {
                "hunt_id": snapshot.hunt_id,
                "hunt_name": snapshot.hunt_name,
                "game_id": snapshot.game_id,
                "game_name": snapshot.game_name,
                "hunt_status": snapshot.hunt_status,
                "hunt_started_at": snapshot.hunt_started_at,
                "hunt_completed_at": snapshot.hunt_completed_at,
                "hunt_encounter_count": snapshot.hunt_encounter_count,
                "hunt_catch_counter": snapshot.hunt_catch_counter,
                "hunt_last_catch_at_encounter": snapshot.hunt_last_catch_at_encounter,
                "hunt_encounters_since_last_catch": snapshot.hunt_encounters_since_last_catch,
                "session_number": snapshot.session_number,
            }
        )

    def _upsert_hunt_from_session(self, state: dict[str, object], context: SessionContext) -> None:
        if not context.hunt_id:
            return
        try:
            record = self._find_hunt_record(state, context.hunt_id)
        except ValueError:
            records = self._hunt_records(state)
            record = {}
            records.append(record)
            state["hunts"] = records
        record.update(
            {
                "hunt_id": context.hunt_id,
                "hunt_name": context.hunt_name,
                "game_id": context.game_id,
                "game_name": context.game_name,
                "hunt_status": context.hunt_status,
                "hunt_started_at": context.hunt_started_at,
                "hunt_completed_at": context.hunt_completed_at,
                "hunt_encounter_count": context.hunt_encounter_count,
                "hunt_catch_counter": context.hunt_catch_counter,
                "hunt_last_catch_at_encounter": context.hunt_last_catch_at_encounter,
                "hunt_encounters_since_last_catch": context.hunt_encounters_since_last_catch,
                "session_number": context.session_number,
            }
        )

    @staticmethod
    def _hunt_records(state: dict[str, object]) -> list[dict[str, object]]:
        raw_hunts = state.get("hunts")
        if not isinstance(raw_hunts, list):
            return []
        return [record for record in raw_hunts if isinstance(record, dict)]

    def _find_hunt_record(self, state: dict[str, object], hunt_id: str) -> dict[str, object]:
        for record in self._hunt_records(state):
            if str(record.get("hunt_id", "")) == hunt_id:
                return record
        raise ValueError(f"Unknown hunt: {hunt_id}")

    @staticmethod
    def _hunt_context(record: dict[str, object]) -> HuntContext:
        return HuntContext(
            hunt_id=str(record.get("hunt_id", "")),
            hunt_name=str(record.get("hunt_name", "Unnamed Hunt")),
            game_id=str(record.get("game_id", "")),
            game_name=str(record.get("game_name", "")),
            hunt_status=str(record.get("hunt_status", "paused")),
            hunt_started_at=str(record.get("hunt_started_at", "")),
            hunt_completed_at=str(record.get("hunt_completed_at", "")),
            hunt_encounter_count=max(0, _safe_int(record.get("hunt_encounter_count"), 0)),
            hunt_catch_counter=max(0, _safe_int(record.get("hunt_catch_counter"), 0)),
            hunt_last_catch_at_encounter=max(
                0, _safe_int(record.get("hunt_last_catch_at_encounter"), 0)
            ),
            hunt_encounters_since_last_catch=max(
                0, _safe_int(record.get("hunt_encounters_since_last_catch"), 0)
            ),
            session_number=max(0, _safe_int(record.get("session_number"), 0)),
        )

    @staticmethod
    def _build_hunt_id(game_id: str, hunt_number: int) -> str:
        return f"{game_id}-hunt-{max(1, int(hunt_number)):04d}"

    def backup_for_migration(self, migration_name: str) -> Path:
        """Keep one immutable copy of state mirrors before a named migration."""
        backup_dir = self.output_dir / "migration_backups" / migration_name
        for source in (self.state_file, self.counter_file):
            destination = backup_dir / source.name
            if source.exists() and not destination.exists():
                atomic_write_bytes(destination, source.read_bytes())
        return backup_dir

    def read_counter(self) -> int:
        state = self.read_state_dict()
        if "counter" in state:
            return _safe_int(state.get("counter"), 0)
        if not self.counter_file.exists():
            return 0
        try:
            return int(self.counter_file.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            return 0

    def read_state_dict(self) -> dict[str, object]:
        if not self.state_file.exists():
            return {}
        try:
            data = json.loads(self.state_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        return data if isinstance(data, dict) else {}

    def read_state_text(self) -> str:
        if not self.state_file.exists():
            return "{}"
        try:
            return self.state_file.read_text(encoding="utf-8")
        except OSError:
            return "{}"
