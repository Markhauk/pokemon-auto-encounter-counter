from __future__ import annotations

from app.core.interface import (
    INTERFACE_FRAME_DEFINITIONS,
    get_interface_frame_definition,
    normalize_frame_type,
)
from app.core.paths import INTERFACE_FRAMES_DIR


def mark_as_interface_frame(widget) -> None:  # type: ignore[no-untyped-def]
    widget.setProperty("pokemonFrame", True)


def mark_as_frame_preview(widget, frame_type: int) -> None:  # type: ignore[no-untyped-def]
    widget.setProperty("framePreview", str(normalize_frame_type(frame_type)))


_TITLE_COLORS = {
    1: "#f4f2ff",
    2: "#ffffff",
    3: "#ffe9e6",
    4: "#f4f7ef",
    5: "#fff1ce",
    6: "#edf5ed",
    7: "#ffe9e9",
    8: "#fff4d8",
    9: "#eaf8ff",
    10: "#fff0bd",
    11: "#ffeaff",
    12: "#fff0a6",
    13: "#e8f4ff",
    14: "#fff2d7",
    15: "#fff4ff",
    16: "#fff0c9",
    17: "#ffffff",
    18: "#fff9c9",
    19: "#efffdc",
    20: "#ffe9ef",
}


def get_frame_asset_path(frame_type: object):  # type: ignore[no-untyped-def]
    definition = get_interface_frame_definition(frame_type)
    return INTERFACE_FRAMES_DIR / definition.asset_filename


def _group_box_rules(selector: str, frame_type: object) -> str:
    normalized = normalize_frame_type(frame_type)
    asset_url = get_frame_asset_path(normalized).as_posix()
    title_color = _TITLE_COLORS[normalized]

    return f"""
    {selector} {{
        border: 8px solid transparent;
        border-image: url("{asset_url}") 8 8 8 8 repeat repeat;
        border-radius: 0;
        margin-top: 12px;
        padding: 13px 10px 10px 10px;
        background-color: #2b2b2b;
    }}
    {selector}::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 10px;
        padding: 0 5px;
        color: {title_color};
        background-color: #2b2b2b;
    }}
    """


def build_interface_frame_stylesheet(frame_type: object) -> str:
    selected = normalize_frame_type(frame_type)
    rules = [_group_box_rules('QGroupBox[pokemonFrame="true"]', selected)]
    preview_selectors: list[str] = []
    for definition in INTERFACE_FRAME_DEFINITIONS:
        selector = f'QGroupBox[framePreview="{definition.frame_type}"]'
        preview_selectors.append(selector)
        rules.append(_group_box_rules(selector, definition.frame_type))
    rules.append(
        f"""
        {", ".join(preview_selectors)} {{
            min-height: 78px;
        }}
        """
    )
    return "\n".join(rules)
