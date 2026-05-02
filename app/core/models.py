from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional


@dataclass
class MatchResult:
    found: bool
    score: float
    location: Optional[tuple[int, int]] = None


@dataclass
class BrightnessStats:
    min_value: int
    max_value: int
    mean_value: float
    std_value: float
    nonzero_ratio: float


@dataclass
class CounterSnapshot:
    status: str
    mode_key: str
    mode_name: str
    encounter_increment: int
    counter: int
    catch_counter: int
    last_event: str
    last_event_at: Optional[str]
    last_match_score: float
    last_catch_at_encounter: int
    encounters_since_last_catch: int
    capture_region: dict[str, int]
    waiting_for_clear: bool
    cooldown_until: float
    frame_index: int
    error_message: str = ""

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class TemplateStatus:
    mode_key: str
    mode_name: str
    filename: str
    path: str
    exists: bool
    readable: bool
    error: str = ""

    def status_label(self) -> str:
        if not self.exists:
            return "Missing"
        if not self.readable:
            return "Unreadable"
        return "Found"
