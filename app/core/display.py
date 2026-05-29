from __future__ import annotations

from typing import Any


REFERENCE_CAPTURE_WIDTH = 2560
REFERENCE_CAPTURE_HEIGHT = 1440

_LEGACY_DISPLAY_GRID_ROWS = 2
_LEGACY_DISPLAY_GRID_COLUMNS = 3
_LEGACY_DEFAULT_LAYOUTS: dict[int, tuple[tuple[int, int, int], tuple[int, int, int]]] = {
    1: ((0, 0, 0), (0, 1, 0)),
    2: ((0, 0, 0), (1, 1, 0)),
    3: ((0, 1, 0), (1, 1, 0)),
    4: ((0, 1, 1), (0, 1, 1)),
    5: ((0, 1, 1), (1, 1, 1)),
    6: ((1, 1, 1), (1, 1, 1)),
}


def _safe_int(value: object, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _build_legacy_layout_preset(screen_count: object) -> list[list[int]]:
    count = _safe_int(screen_count, 1)
    count = max(1, min(count, _LEGACY_DISPLAY_GRID_ROWS * _LEGACY_DISPLAY_GRID_COLUMNS))
    layout = _LEGACY_DEFAULT_LAYOUTS[count]
    return [list(row) for row in layout]


def _count_active_legacy_layout_cells(layout: list[list[int]]) -> int:
    return sum(int(bool(cell)) for row in layout for cell in row)


def _list_active_legacy_layout_cells(layout: list[list[int]]) -> list[tuple[int, int]]:
    cells: list[tuple[int, int]] = []
    for row_index, row in enumerate(layout):
        for column_index, cell in enumerate(row):
            if cell:
                cells.append((row_index, column_index))
    return cells


def _choose_default_legacy_capture_cell(layout: list[list[int]]) -> dict[str, int]:
    active_cells = _list_active_legacy_layout_cells(layout)
    if not active_cells:
        return {"row": 1, "column": 1}

    target_row = 1
    target_column = 1
    row, column = min(
        active_cells,
        key=lambda cell: (
            abs(cell[0] - target_row) + abs(cell[1] - target_column),
            abs(cell[0] - target_row),
            abs(cell[1] - target_column),
        ),
    )
    return {"row": row, "column": column}


def _normalize_legacy_layout(raw_layout: object, fallback_count: object) -> list[list[int]]:
    fallback_layout = _build_legacy_layout_preset(fallback_count)
    if not isinstance(raw_layout, list):
        return fallback_layout

    layout: list[list[int]] = []
    for row_index in range(_LEGACY_DISPLAY_GRID_ROWS):
        row_value = raw_layout[row_index] if row_index < len(raw_layout) else []
        if not isinstance(row_value, list):
            row_value = []

        row: list[int] = []
        for column_index in range(_LEGACY_DISPLAY_GRID_COLUMNS):
            cell_value = row_value[column_index] if column_index < len(row_value) else 0
            row.append(1 if bool(cell_value) else 0)
        layout.append(row)

    if _count_active_legacy_layout_cells(layout) == 0:
        return fallback_layout
    return layout


def _normalize_legacy_capture_cell(raw_capture_cell: object, layout: list[list[int]]) -> dict[str, int]:
    default_cell = _choose_default_legacy_capture_cell(layout)
    if not isinstance(raw_capture_cell, dict):
        return default_cell

    row = _safe_int(raw_capture_cell.get("row"), default_cell["row"])
    column = _safe_int(raw_capture_cell.get("column"), default_cell["column"])
    if row < 0 or row >= _LEGACY_DISPLAY_GRID_ROWS or column < 0 or column >= _LEGACY_DISPLAY_GRID_COLUMNS:
        return default_cell
    if not layout[row][column]:
        return default_cell
    return {"row": row, "column": column}


def _prepare_monitors_for_legacy_mapping(monitors: list[dict[str, Any]]) -> list[dict[str, int]]:
    prepared = prepare_physical_monitors(monitors)
    prepared.sort(key=lambda monitor: (monitor["top"], monitor["left"]))
    return prepared


def _infer_legacy_capture_monitor_index(
    raw_display_setup: dict[str, object],
    physical_monitors: list[dict[str, Any]],
) -> int | None:
    monitors = _prepare_monitors_for_legacy_mapping(physical_monitors)
    if not monitors:
        return None

    requested_count = _safe_int(raw_display_setup.get("screen_count"), 1)
    layout = _normalize_legacy_layout(raw_display_setup.get("layout"), requested_count)
    active_cells = _list_active_legacy_layout_cells(layout)
    if len(active_cells) != len(monitors):
        return None

    capture_cell = _normalize_legacy_capture_cell(raw_display_setup.get("capture_cell"), layout)
    mapping = {
        cell: monitor
        for cell, monitor in zip(active_cells, monitors)
    }
    selected_cell = (int(capture_cell["row"]), int(capture_cell["column"]))
    selected_monitor = mapping.get(selected_cell)
    if selected_monitor is None:
        return None
    return int(selected_monitor["index"])


def prepare_physical_monitors(monitors: list[dict[str, Any]]) -> list[dict[str, int]]:
    prepared: list[dict[str, int]] = []
    for index, monitor in enumerate(monitors, start=1):
        prepared.append(
            {
                "index": _safe_int(monitor.get("index"), index),
                "left": _safe_int(monitor.get("left"), 0),
                "top": _safe_int(monitor.get("top"), 0),
                "width": _safe_int(monitor.get("width"), 0),
                "height": _safe_int(monitor.get("height"), 0),
            }
        )

    prepared.sort(key=lambda monitor: monitor["index"])
    return prepared


def build_default_display_setup(
    *,
    physical_monitors: list[dict[str, Any]] | None = None,
) -> dict[str, object]:
    monitors = prepare_physical_monitors(physical_monitors or [])
    capture_monitor_index = monitors[0]["index"] if monitors else 1
    return {"capture_monitor_index": capture_monitor_index}


def normalize_display_setup(
    raw_display_setup: object,
    *,
    physical_monitors: list[dict[str, Any]] | None = None,
) -> dict[str, object]:
    monitors = prepare_physical_monitors(physical_monitors or [])

    if not isinstance(raw_display_setup, dict):
        return build_default_display_setup(physical_monitors=monitors)

    raw_capture_monitor_index = raw_display_setup.get("capture_monitor_index")
    if raw_capture_monitor_index is None:
        raw_capture_monitor_index = raw_display_setup.get("monitor_index")
    if raw_capture_monitor_index is None:
        raw_capture_monitor_index = raw_display_setup.get("selected_monitor_index")

    capture_monitor_index = _safe_int(raw_capture_monitor_index, 0)

    if capture_monitor_index <= 0:
        legacy_capture_monitor_index = _infer_legacy_capture_monitor_index(raw_display_setup, monitors)
        if legacy_capture_monitor_index is not None:
            capture_monitor_index = legacy_capture_monitor_index

    if not monitors:
        if capture_monitor_index <= 0:
            capture_monitor_index = 1
        return {"capture_monitor_index": capture_monitor_index}

    available_indexes = {monitor["index"] for monitor in monitors}
    if capture_monitor_index not in available_indexes:
        capture_monitor_index = monitors[0]["index"]

    return {"capture_monitor_index": capture_monitor_index}


def get_capture_monitor_index(display_setup: dict[str, object]) -> int:
    normalized_setup = normalize_display_setup(display_setup)
    return int(normalized_setup["capture_monitor_index"])


def scale_region_for_dimensions(
    region: dict[str, int],
    *,
    from_width: int,
    from_height: int,
    to_width: int,
    to_height: int,
) -> dict[str, int]:
    if from_width <= 0 or from_height <= 0 or to_width <= 0 or to_height <= 0:
        return {
            "left": int(region.get("left", 0)),
            "top": int(region.get("top", 0)),
            "width": int(region.get("width", 0)),
            "height": int(region.get("height", 0)),
        }

    if from_width == to_width and from_height == to_height:
        return {
            "left": int(region.get("left", 0)),
            "top": int(region.get("top", 0)),
            "width": int(region.get("width", 0)),
            "height": int(region.get("height", 0)),
        }

    x_scale = to_width / from_width
    y_scale = to_height / from_height

    width = int(region.get("width", 0))
    height = int(region.get("height", 0))

    return {
        "left": max(0, round(int(region.get("left", 0)) * x_scale)),
        "top": max(0, round(int(region.get("top", 0)) * y_scale)),
        "width": max(1, round(width * x_scale)) if width > 0 else 0,
        "height": max(1, round(height * y_scale)) if height > 0 else 0,
    }


def resolve_capture_monitor(
    *,
    display_setup: dict[str, object],
    physical_monitors: list[dict[str, Any]],
) -> dict[str, int]:
    monitors = prepare_physical_monitors(physical_monitors)
    if not monitors:
        raise ValueError("Windows did not report any monitors.")

    normalized_setup = normalize_display_setup(display_setup, physical_monitors=monitors)
    selected_index = int(normalized_setup["capture_monitor_index"])

    for monitor in monitors:
        if monitor["index"] == selected_index:
            return monitor

    raise ValueError("Selected capture monitor is not currently available.")


def build_absolute_capture_region(
    *,
    relative_region: dict[str, int],
    display_setup: dict[str, object],
    physical_monitors: list[dict[str, Any]],
) -> dict[str, int]:
    monitor = resolve_capture_monitor(display_setup=display_setup, physical_monitors=physical_monitors)
    return {
        "left": int(monitor["left"]) + int(relative_region.get("left", 0)),
        "top": int(monitor["top"]) + int(relative_region.get("top", 0)),
        "width": int(relative_region.get("width", 0)),
        "height": int(relative_region.get("height", 0)),
    }


def format_monitor_summary(monitor: dict[str, int]) -> str:
    return (
        f"Monitor {monitor['index']} "
        f"({monitor['width']}x{monitor['height']} at left={monitor['left']}, top={monitor['top']})"
    )
