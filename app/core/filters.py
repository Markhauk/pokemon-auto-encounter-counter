from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

from .constants import ESCAPE_THRESHOLD, GOTCHA_THRESHOLD, HUH_THRESHOLD, WILD_THRESHOLD
from .display import DEFAULT_RESOLUTION_PRESET
from .modes import get_default_capture_region


EVENT_TYPE_ENCOUNTER_START = "encounter_start"
EVENT_TYPE_CATCH = "catch"
EVENT_TYPE_FLED = "fled"
EVENT_TYPE_INFO = "info"
EVENT_TYPE_LABEL = "label"

FILTER_EVENT_TYPES = (
    EVENT_TYPE_ENCOUNTER_START,
    EVENT_TYPE_CATCH,
    EVENT_TYPE_FLED,
    EVENT_TYPE_INFO,
    EVENT_TYPE_LABEL,
)

FILTER_ID_WILD = "wild"
FILTER_ID_GOTCHA = "gotcha"
FILTER_ID_FLED = "fled"
FILTER_ID_HUH = "huh"

DEFAULT_FILTER_VERSION = 1
DEFAULT_GAME_ID = "testgamefilters"


@dataclass(frozen=True)
class GameDefinition:
    id: str
    name: str
    built_in: bool = False
    description: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "built_in": self.built_in,
            "description": self.description,
        }


@dataclass(frozen=True)
class FilterDefinition:
    id: str
    name: str
    enabled: bool
    event_type: str
    template_path: str
    capture_region: dict[str, int]
    threshold: float
    built_in: bool = False
    description: str = ""
    metadata: dict[str, object] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "enabled": self.enabled,
            "event_type": self.event_type,
            "template_path": self.template_path,
            "capture_region": dict(self.capture_region),
            "threshold": float(self.threshold),
            "built_in": self.built_in,
            "description": self.description,
            "metadata": dict(self.metadata),
        }


def normalize_event_type(value: object) -> str:
    event_type = str(value).strip().lower()
    if event_type in FILTER_EVENT_TYPES:
        return event_type
    return EVENT_TYPE_INFO


def slugify_filter_name(name: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", name.strip().lower())
    normalized = normalized.strip("_")
    return normalized or "filter"


def slugify_game_name(name: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", name.strip().lower())
    normalized = normalized.strip("_")
    return normalized or "game"


def build_builtin_games() -> list[GameDefinition]:
    return [
        GameDefinition(
            id=DEFAULT_GAME_ID,
            name=DEFAULT_GAME_ID,
            built_in=True,
            description="Default game bucket for migrated and starter filters.",
        )
    ]


def normalize_game_definition(
    raw_game: object,
    *,
    fallback_games: dict[str, GameDefinition] | None = None,
) -> GameDefinition:
    fallback_map = fallback_games or {game.id: game for game in build_builtin_games()}
    if not isinstance(raw_game, dict):
        return build_builtin_games()[0]

    game_id = slugify_game_name(str(raw_game.get("id", DEFAULT_GAME_ID)))
    fallback = fallback_map.get(game_id)
    if fallback is None:
        fallback = GameDefinition(
            id=game_id,
            name=str(raw_game.get("name", "New Game")).strip() or "New Game",
            built_in=False,
            description="Custom game filter group.",
        )

    return GameDefinition(
        id=game_id,
        name=str(raw_game.get("name", fallback.name)).strip() or fallback.name,
        built_in=bool(raw_game.get("built_in", fallback.built_in)),
        description=str(raw_game.get("description", fallback.description)).strip(),
    )


def normalize_game_definitions(raw_games: object) -> list[GameDefinition]:
    built_ins = build_builtin_games()
    built_in_map = {game.id: game for game in built_ins}

    if isinstance(raw_games, dict):
        iterable: Iterable[object] = raw_games.values()
    elif isinstance(raw_games, list):
        iterable = raw_games
    else:
        return built_ins

    normalized: list[GameDefinition] = []
    seen_ids: set[str] = set()
    for raw_game in iterable:
        game_definition = normalize_game_definition(raw_game, fallback_games=built_in_map)
        if game_definition.id in seen_ids:
            continue
        seen_ids.add(game_definition.id)
        normalized.append(game_definition)

    for builtin in built_ins:
        if builtin.id not in seen_ids:
            normalized.append(builtin)

    return normalized


def normalize_game_id(value: object) -> str:
    normalized = slugify_game_name(str(value or DEFAULT_GAME_ID))
    return normalized or DEFAULT_GAME_ID


def get_filter_game_id(filter_definition: FilterDefinition) -> str:
    return normalize_game_id(filter_definition.metadata.get("game_id", DEFAULT_GAME_ID))


def build_builtin_filters(
    *,
    resolution_preset: str = DEFAULT_RESOLUTION_PRESET,
    legacy_mode_regions: dict[str, dict[str, int]] | None = None,
) -> list[FilterDefinition]:
    legacy_regions = legacy_mode_regions or {}

    def _region(mode_key: str) -> dict[str, int]:
        if mode_key in legacy_regions:
            region = legacy_regions[mode_key]
            return {
                "left": int(region.get("left", 0)),
                "top": int(region.get("top", 0)),
                "width": int(region.get("width", 0)),
                "height": int(region.get("height", 0)),
            }
        return get_default_capture_region(mode_key, resolution_preset=resolution_preset)

    return [
        FilterDefinition(
            id=FILTER_ID_WILD,
            name="Wild",
            enabled=True,
            event_type=EVENT_TYPE_ENCOUNTER_START,
            template_path="wild.png",
            capture_region=_region("safari_zone"),
            threshold=WILD_THRESHOLD,
            built_in=True,
            description="Encounter-start filter for Safari-style wild battle text.",
            metadata={"game_id": DEFAULT_GAME_ID},
        ),
        FilterDefinition(
            id=FILTER_ID_GOTCHA,
            name="Gotcha",
            enabled=True,
            event_type=EVENT_TYPE_CATCH,
            template_path="gotcha.png",
            capture_region=_region("random_grass"),
            threshold=GOTCHA_THRESHOLD,
            built_in=True,
            description="Catch filter that increments encounter count and catch count.",
            metadata={"game_id": DEFAULT_GAME_ID},
        ),
        FilterDefinition(
            id=FILTER_ID_FLED,
            name="Fled",
            enabled=True,
            event_type=EVENT_TYPE_FLED,
            template_path="got_away.png",
            capture_region=_region("random_grass"),
            threshold=ESCAPE_THRESHOLD,
            built_in=True,
            description="Separate fled event filter based on the got away battle result.",
            metadata={"game_id": DEFAULT_GAME_ID},
        ),
        FilterDefinition(
            id=FILTER_ID_HUH,
            name="Huh",
            enabled=False,
            event_type=EVENT_TYPE_ENCOUNTER_START,
            template_path="huh.png",
            capture_region=_region("egg_mode"),
            threshold=HUH_THRESHOLD,
            built_in=True,
            description="Egg encounter event filter based on the huh prompt.",
            metadata={"game_id": DEFAULT_GAME_ID},
        ),
    ]


def _normalize_region(raw_region: object) -> dict[str, int]:
    region = raw_region if isinstance(raw_region, dict) else {}
    return {
        "left": int(region.get("left", 0)),
        "top": int(region.get("top", 0)),
        "width": max(1, int(region.get("width", 1))),
        "height": max(1, int(region.get("height", 1))),
    }


def normalize_filter_definition(
    raw_filter: object,
    *,
    resolution_preset: str = DEFAULT_RESOLUTION_PRESET,
    fallback_filters: dict[str, FilterDefinition] | None = None,
) -> FilterDefinition:
    fallback_map = fallback_filters or {flt.id: flt for flt in build_builtin_filters(resolution_preset=resolution_preset)}
    if not isinstance(raw_filter, dict):
        default = build_builtin_filters(resolution_preset=resolution_preset)[0]
        return default

    filter_id = slugify_filter_name(str(raw_filter.get("id", "filter")))
    fallback = fallback_map.get(filter_id)

    if fallback is None:
        fallback = FilterDefinition(
            id=filter_id,
            name=str(raw_filter.get("name", "New Filter")).strip() or "New Filter",
            enabled=True,
            event_type=EVENT_TYPE_INFO,
            template_path=f"{filter_id}.png",
            capture_region={
                "left": 0,
                "top": 0,
                "width": 100,
                "height": 100,
            },
            threshold=0.85,
            built_in=False,
            description="Custom template filter.",
        )

    name = str(raw_filter.get("name", fallback.name)).strip() or fallback.name
    metadata = (
        dict(raw_filter.get("metadata", fallback.metadata))
        if isinstance(raw_filter.get("metadata"), dict)
        else dict(fallback.metadata)
    )
    metadata["game_id"] = normalize_game_id(metadata.get("game_id", fallback.metadata.get("game_id", DEFAULT_GAME_ID)))

    return FilterDefinition(
        id=filter_id,
        name=name,
        enabled=bool(raw_filter.get("enabled", fallback.enabled)),
        event_type=normalize_event_type(raw_filter.get("event_type", fallback.event_type)),
        template_path=str(raw_filter.get("template_path", fallback.template_path)).strip() or fallback.template_path,
        capture_region=_normalize_region(raw_filter.get("capture_region", fallback.capture_region)),
        threshold=float(raw_filter.get("threshold", fallback.threshold)),
        built_in=bool(raw_filter.get("built_in", fallback.built_in)),
        description=str(raw_filter.get("description", fallback.description)).strip(),
        metadata=metadata,
    )


def normalize_filter_definitions(
    raw_filters: object,
    *,
    resolution_preset: str = DEFAULT_RESOLUTION_PRESET,
    legacy_mode_regions: dict[str, dict[str, int]] | None = None,
) -> list[FilterDefinition]:
    built_ins = build_builtin_filters(
        resolution_preset=resolution_preset,
        legacy_mode_regions=legacy_mode_regions,
    )
    built_in_map = {flt.id: flt for flt in built_ins}

    if isinstance(raw_filters, dict):
        iterable: Iterable[object] = raw_filters.values()
    elif isinstance(raw_filters, list):
        iterable = raw_filters
    else:
        return built_ins

    normalized: list[FilterDefinition] = []
    seen_ids: set[str] = set()
    for raw_filter in iterable:
        filter_definition = normalize_filter_definition(
            raw_filter,
            resolution_preset=resolution_preset,
            fallback_filters=built_in_map,
        )
        if filter_definition.id in seen_ids:
            continue
        seen_ids.add(filter_definition.id)
        normalized.append(filter_definition)

    for builtin in built_ins:
        if builtin.id not in seen_ids:
            normalized.append(builtin)

    return normalized


def build_legacy_mode_filters(
    *,
    mode_key: str,
    capture_region: dict[str, int],
) -> list[FilterDefinition]:
    if mode_key == "random_grass":
        return [
            FilterDefinition(
                id=FILTER_ID_GOTCHA,
                name="Gotcha",
                enabled=True,
                event_type=EVENT_TYPE_CATCH,
                template_path="gotcha.png",
                capture_region=dict(capture_region),
                threshold=GOTCHA_THRESHOLD,
                built_in=True,
                description="Legacy random grass catch filter.",
                metadata={"game_id": DEFAULT_GAME_ID},
            ),
            FilterDefinition(
                id=FILTER_ID_FLED,
                name="Fled",
                enabled=True,
                event_type=EVENT_TYPE_FLED,
                template_path="got_away.png",
                capture_region=dict(capture_region),
                threshold=ESCAPE_THRESHOLD,
                built_in=True,
                description="Legacy random grass fled filter.",
                metadata={"game_id": DEFAULT_GAME_ID},
            ),
        ]

    if mode_key == "safari_zone":
        return [
            FilterDefinition(
                id=FILTER_ID_WILD,
                name="Wild",
                enabled=True,
                event_type=EVENT_TYPE_ENCOUNTER_START,
                template_path="wild.png",
                capture_region=dict(capture_region),
                threshold=WILD_THRESHOLD,
                built_in=True,
                description="Legacy Safari wild filter.",
                metadata={"game_id": DEFAULT_GAME_ID},
            )
        ]

    if mode_key == "egg_mode":
        return [
            FilterDefinition(
                id=FILTER_ID_HUH,
                name="Huh",
                enabled=True,
                event_type=EVENT_TYPE_ENCOUNTER_START,
                template_path="huh.png",
                capture_region=dict(capture_region),
                threshold=HUH_THRESHOLD,
                built_in=True,
                description="Legacy egg filter.",
                metadata={"game_id": DEFAULT_GAME_ID},
            )
        ]

    return []
