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
class FilterRuntimeState:
    cooldown_until: float = 0.0
    waiting_for_clear: bool = False
    last_match_score: float = 0.0
    last_event_at: Optional[str] = None

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class CounterSnapshot:
    status: str
    mode_key: str
    mode_name: str
    encounter_increment: int
    enabled_filter_count: int
    counter: int
    catch_counter: int
    last_event: str
    last_event_at: Optional[str]
    last_match_score: float
    last_filter_id: str
    last_filter_name: str
    last_filter_event_type: str
    active_label: str
    last_catch_at_encounter: int
    encounters_since_last_catch: int
    capture_region: dict[str, int] | None
    waiting_for_clear: bool
    cooldown_until: float
    frame_index: int
    filters_runtime: dict[str, dict[str, object]]
    error_message: str = ""

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class TemplateStatus:
    filter_id: str
    filter_name: str
    filename: str
    path: str
    exists: bool
    readable: bool
    event_type: str
    error: str = ""

    def status_label(self) -> str:
        if not self.exists:
            return "Missing"
        if not self.readable:
            return "Unreadable"
        return "Found"
