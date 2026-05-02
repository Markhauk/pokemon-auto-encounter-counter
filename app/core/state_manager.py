from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from .exceptions import SingleInstanceError
from .models import CounterSnapshot
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
    ) -> dict[str, object]:
        state: dict[str, object] = {
            "counter": 0,
            "catch_counter": 0,
            "encounter_increment": max(1, int(encounter_increment)),
            "cooldown_until": 0.0,
            "waiting_for_clear": False,
            "last_event": "none",
            "last_event_at": None,
            "last_match_score": 0.0,
            "last_catch_at_encounter": 0,
            "encounters_since_last_catch": 0,
            "capture_region": dict(capture_region),
            "mode_key": mode_key,
            "mode_name": mode_name,
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
                state["last_catch_at_encounter"] = _safe_int(data.get("last_catch_at_encounter"), 0)
                state["encounters_since_last_catch"] = _safe_int(data.get("encounters_since_last_catch"), 0)
            except (json.JSONDecodeError, OSError):
                pass

        counter = int(state["counter"])
        last_catch_at_encounter = int(state["last_catch_at_encounter"])
        if last_catch_at_encounter > 0:
            state["encounters_since_last_catch"] = max(0, counter - last_catch_at_encounter)

        state["encounter_increment"] = max(1, int(encounter_increment))
        state["capture_region"] = dict(capture_region)
        state["mode_key"] = mode_key
        state["mode_name"] = mode_name
        return state

    def save(self, snapshot: CounterSnapshot) -> None:
        self.counter_file.write_text(str(snapshot.counter), encoding="utf-8")
        self.state_file.write_text(
            json.dumps(
                {
                    "counter": snapshot.counter,
                    "catch_counter": snapshot.catch_counter,
                    "encounter_increment": snapshot.encounter_increment,
                    "cooldown_until": snapshot.cooldown_until,
                    "waiting_for_clear": snapshot.waiting_for_clear,
                    "last_event": snapshot.last_event,
                    "last_event_at": snapshot.last_event_at,
                    "last_match_score": snapshot.last_match_score,
                    "last_catch_at_encounter": snapshot.last_catch_at_encounter,
                    "encounters_since_last_catch": snapshot.encounters_since_last_catch,
                    "capture_region": snapshot.capture_region,
                    "mode_key": snapshot.mode_key,
                    "mode_name": snapshot.mode_name,
                    "status": snapshot.status,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

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
