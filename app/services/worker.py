from __future__ import annotations

import threading
from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal, Slot

from app.core.detector import EncounterCounterEngine
from app.core.filters import FilterDefinition
from app.core.paths import LOCK_FILE
from app.core.state_manager import SingleInstanceGuard


@dataclass(frozen=True)
class DetectionRequest:
    filters: list[FilterDefinition]
    encounter_increment: int
    save_debug_frames: bool = False
    verbose_debug: bool = False


class DetectionWorker(QObject):
    status_changed = Signal(dict)
    log_received = Signal(dict)
    error_occurred = Signal(str)
    completed = Signal()

    def __init__(self, request: DetectionRequest) -> None:
        super().__init__()
        self.request = request
        self._stop_event = threading.Event()
        self._engine: EncounterCounterEngine | None = None

    @Slot()
    def run(self) -> None:
        try:
            with SingleInstanceGuard(LOCK_FILE):
                self._engine = EncounterCounterEngine(
                    filters=self.request.filters,
                    save_debug_frames=self.request.save_debug_frames,
                    verbose_debug=self.request.verbose_debug,
                    encounter_increment=self.request.encounter_increment,
                    log_handler=self._emit_log,
                    status_handler=self._emit_status,
                )
                self._engine.run(stop_requested=self._stop_event.is_set)
        except Exception as exc:
            self.error_occurred.emit(str(exc))
        finally:
            self.completed.emit()

    @Slot()
    def stop(self) -> None:
        self._stop_event.set()
        if self._engine is not None:
            self._engine.stop(status="Stopped")

    def _emit_log(self, payload: dict[str, object]) -> None:
        self.log_received.emit(payload)

    def _emit_status(self, payload: dict[str, object]) -> None:
        self.status_changed.emit(payload)
