from __future__ import annotations

from dataclasses import dataclass


MODE_RANDOM_GRASS_KEY = "random_grass"
MODE_SAFARI_ZONE_KEY = "safari_zone"
MODE_EGG_KEY = "egg_mode"
MODE_SOFT_RESET_KEY = "soft_reset"

MODE_RANDOM_GRASS = "Random grass encounter"
MODE_SAFARI_ZONE = "Safari zone"
MODE_EGG = "Egg mode"
MODE_SOFT_RESET = "Soft reset"


@dataclass(frozen=True)
class ModeDefinition:
    key: str
    name: str
    template_files: tuple[str, ...]
    default_capture_region: dict[str, int]
    implemented: bool = True
    description: str = ""


MODE_DEFINITIONS = (
    ModeDefinition(
        key=MODE_RANDOM_GRASS_KEY,
        name=MODE_RANDOM_GRASS,
        template_files=("got_away.png", "gotcha.png"),
        default_capture_region={
            "top": 1060,
            "left": 282,
            "width": 935,
            "height": 132,
        },
        description="Counts random grass encounters from got away and gotcha result text.",
    ),
    ModeDefinition(
        key=MODE_SAFARI_ZONE_KEY,
        name=MODE_SAFARI_ZONE,
        template_files=("wild.png",),
        default_capture_region={
            "top": 1068,
            "left": 282,
            "width": 243,
            "height": 114,
        },
        description="Counts Safari Zone encounters from the wild text prompt.",
    ),
    ModeDefinition(
        key=MODE_EGG_KEY,
        name=MODE_EGG,
        template_files=("huh.png",),
        default_capture_region={
            "top": 1040,
            "left": 260,
            "width": 420,
            "height": 120,
        },
        description="Counts egg hatching encounters from the huh prompt.",
    ),
    ModeDefinition(
        key=MODE_SOFT_RESET_KEY,
        name=MODE_SOFT_RESET,
        template_files=(),
        default_capture_region={
            "top": 0,
            "left": 0,
            "width": 0,
            "height": 0,
        },
        implemented=False,
        description="Reserved for future soft reset tracking.",
    ),
)

MODES_BY_KEY = {mode.key: mode for mode in MODE_DEFINITIONS}
MODE_KEY_BY_NAME = {mode.name: mode.key for mode in MODE_DEFINITIONS}


def list_modes(*, include_unimplemented: bool = True) -> list[ModeDefinition]:
    if include_unimplemented:
        return list(MODE_DEFINITIONS)
    return [mode for mode in MODE_DEFINITIONS if mode.implemented]


def get_mode(mode_key_or_name: str) -> ModeDefinition:
    if mode_key_or_name in MODES_BY_KEY:
        return MODES_BY_KEY[mode_key_or_name]
    if mode_key_or_name in MODE_KEY_BY_NAME:
        return MODES_BY_KEY[MODE_KEY_BY_NAME[mode_key_or_name]]
    valid_modes = ", ".join(mode.key for mode in MODE_DEFINITIONS)
    raise ValueError(f"Unknown mode '{mode_key_or_name}'. Expected one of: {valid_modes}")


def get_default_capture_region(mode_key_or_name: str) -> dict[str, int]:
    return dict(get_mode(mode_key_or_name).default_capture_region)
