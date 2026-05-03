from __future__ import annotations

from typing import Any


DISPLAY_GRID_ROWS = 2
DISPLAY_GRID_COLUMNS = 3
DEFAULT_RESOLUTION_PRESET = "1440p"
DEFAULT_MIXED_RESOLUTIONS = False

RESOLUTION_PRESETS: dict[str, dict[str, int | str]] = {
    "1080p": {"width": 1920, "height": 1080, "label": "1920 x 1080"},
    "1440p": {"width": 2560, "height": 1440, "label": "2560 x 1440"},
    "4k": {"width": 3840, "height": 2160, "label": "3840 x 2160"},
}

_DEFAULT_LAYOUTS: dict[int, tuple[tuple[int, int, int], tuple[int, int, int]]] = {
    1: ((0, 0, 0), (0, 1, 0)),
    2: ((0, 0, 0), (1, 1, 0)),
    3: ((0, 1, 0), (1, 1, 0)),
    4: ((0, 1, 1), (0, 1, 1)),
    5: ((0, 1, 1), (1, 1, 1)),
    6: ((1, 1, 1), (1, 1, 1)),
}

_ROW_LABELS = ("Top", "Bottom")
_COLUMN_LABELS = ("Left", "Center", "Right")


def _safe_int(value: object, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def normalize_resolution_preset(value: object) -> str:
    preset = str(value).strip().lower()
    if preset in RESOLUTION_PRESETS:
        return preset
    return DEFAULT_RESOLUTION_PRESET


def get_resolution_dimensions(resolution_preset: object) -> dict[str, int]:
    preset = normalize_resolution_preset(resolution_preset)
    resolution = RESOLUTION_PRESETS[preset]
    return {
        "width": int(resolution["width"]),
        "height": int(resolution["height"]),
    }


def get_resolution_label(resolution_preset: object) -> str:
    preset = normalize_resolution_preset(resolution_preset)
    return str(RESOLUTION_PRESETS[preset]["label"])


def build_resolution_grid(default_preset: object = DEFAULT_RESOLUTION_PRESET) -> list[list[str]]:
    preset = normalize_resolution_preset(default_preset)
    return [
        [preset for _ in range(DISPLAY_GRID_COLUMNS)]
        for _ in range(DISPLAY_GRID_ROWS)
    ]


def build_layout_preset(screen_count: object) -> list[list[int]]:
    count = _safe_int(screen_count, 1)
    count = max(1, min(count, DISPLAY_GRID_ROWS * DISPLAY_GRID_COLUMNS))
    layout = _DEFAULT_LAYOUTS[count]
    return [list(row) for row in layout]


def count_active_layout_cells(layout: list[list[int]]) -> int:
    return sum(int(bool(cell)) for row in layout for cell in row)


def list_active_layout_cells(layout: list[list[int]]) -> list[tuple[int, int]]:
    cells: list[tuple[int, int]] = []
    for row_index, row in enumerate(layout):
        for column_index, cell in enumerate(row):
            if cell:
                cells.append((row_index, column_index))
    return cells


def describe_layout_cell(row: int, column: int) -> str:
    return f"{_ROW_LABELS[row]} {_COLUMN_LABELS[column]}"


def choose_default_capture_cell(layout: list[list[int]]) -> dict[str, int]:
    active_cells = list_active_layout_cells(layout)
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


def normalize_layout(raw_layout: object, fallback_count: object = 1) -> list[list[int]]:
    fallback_layout = build_layout_preset(fallback_count)
    if not isinstance(raw_layout, list):
        return fallback_layout

    layout: list[list[int]] = []
    for row_index in range(DISPLAY_GRID_ROWS):
        row_value = raw_layout[row_index] if row_index < len(raw_layout) else []
        if not isinstance(row_value, list):
            row_value = []

        row: list[int] = []
        for column_index in range(DISPLAY_GRID_COLUMNS):
            cell_value = row_value[column_index] if column_index < len(row_value) else 0
            row.append(1 if bool(cell_value) else 0)
        layout.append(row)

    if count_active_layout_cells(layout) == 0:
        return fallback_layout
    return layout


def normalize_capture_cell(raw_capture_cell: object, layout: list[list[int]]) -> dict[str, int]:
    default_cell = choose_default_capture_cell(layout)
    if not isinstance(raw_capture_cell, dict):
        return default_cell

    row = _safe_int(raw_capture_cell.get("row"), default_cell["row"])
    column = _safe_int(raw_capture_cell.get("column"), default_cell["column"])
    if row < 0 or row >= DISPLAY_GRID_ROWS or column < 0 or column >= DISPLAY_GRID_COLUMNS:
        return default_cell
    if not layout[row][column]:
        return default_cell
    return {"row": row, "column": column}


def normalize_monitor_resolutions(
    raw_monitor_resolutions: object,
    *,
    fallback_preset: object = DEFAULT_RESOLUTION_PRESET,
) -> list[list[str]]:
    fallback_grid = build_resolution_grid(fallback_preset)
    if not isinstance(raw_monitor_resolutions, list):
        return fallback_grid

    grid: list[list[str]] = []
    for row_index in range(DISPLAY_GRID_ROWS):
        row_value = raw_monitor_resolutions[row_index] if row_index < len(raw_monitor_resolutions) else []
        if not isinstance(row_value, list):
            row_value = []

        row: list[str] = []
        for column_index in range(DISPLAY_GRID_COLUMNS):
            cell_value = row_value[column_index] if column_index < len(row_value) else fallback_preset
            row.append(normalize_resolution_preset(cell_value))
        grid.append(row)
    return grid


def build_default_display_setup(
    *,
    screen_count: object = 1,
    resolution_preset: object = DEFAULT_RESOLUTION_PRESET,
) -> dict[str, object]:
    layout = build_layout_preset(screen_count)
    normalized_resolution_preset = normalize_resolution_preset(resolution_preset)
    return {
        "screen_count": count_active_layout_cells(layout),
        "resolution_preset": normalized_resolution_preset,
        "mixed_resolutions": DEFAULT_MIXED_RESOLUTIONS,
        "layout": layout,
        "capture_cell": choose_default_capture_cell(layout),
        "monitor_resolutions": build_resolution_grid(normalized_resolution_preset),
    }


def normalize_display_setup(raw_display_setup: object) -> dict[str, object]:
    if not isinstance(raw_display_setup, dict):
        return build_default_display_setup()

    requested_count = _safe_int(raw_display_setup.get("screen_count"), 1)
    requested_count = max(1, min(requested_count, DISPLAY_GRID_ROWS * DISPLAY_GRID_COLUMNS))

    layout = normalize_layout(raw_display_setup.get("layout"), requested_count)
    resolution_preset = normalize_resolution_preset(raw_display_setup.get("resolution_preset"))
    mixed_resolutions = bool(raw_display_setup.get("mixed_resolutions", DEFAULT_MIXED_RESOLUTIONS))
    capture_cell = normalize_capture_cell(raw_display_setup.get("capture_cell"), layout)
    monitor_resolutions = normalize_monitor_resolutions(
        raw_display_setup.get("monitor_resolutions"),
        fallback_preset=resolution_preset,
    )

    return {
        "screen_count": count_active_layout_cells(layout),
        "resolution_preset": resolution_preset,
        "mixed_resolutions": mixed_resolutions,
        "layout": layout,
        "capture_cell": capture_cell,
        "monitor_resolutions": monitor_resolutions,
    }


def get_monitor_resolution_preset(
    display_setup: dict[str, object],
    *,
    row: int,
    column: int,
) -> str:
    normalized_setup = normalize_display_setup(display_setup)
    if not normalized_setup["mixed_resolutions"]:
        return str(normalized_setup["resolution_preset"])

    grid = normalized_setup["monitor_resolutions"]
    return str(grid[row][column])  # type: ignore[index]


def get_capture_resolution_preset(display_setup: dict[str, object]) -> str:
    normalized_setup = normalize_display_setup(display_setup)
    capture_cell = normalized_setup["capture_cell"]
    return get_monitor_resolution_preset(
        normalized_setup,
        row=int(capture_cell["row"]),  # type: ignore[index]
        column=int(capture_cell["column"]),  # type: ignore[index]
    )


def scale_region_for_resolution(
    region: dict[str, int],
    *,
    from_preset: object,
    to_preset: object,
) -> dict[str, int]:
    source = get_resolution_dimensions(from_preset)
    target = get_resolution_dimensions(to_preset)

    if source == target:
        return {
            "left": int(region.get("left", 0)),
            "top": int(region.get("top", 0)),
            "width": int(region.get("width", 0)),
            "height": int(region.get("height", 0)),
        }

    x_scale = target["width"] / source["width"]
    y_scale = target["height"] / source["height"]

    width = int(region.get("width", 0))
    height = int(region.get("height", 0))

    return {
        "left": max(0, round(int(region.get("left", 0)) * x_scale)),
        "top": max(0, round(int(region.get("top", 0)) * y_scale)),
        "width": max(1, round(width * x_scale)) if width > 0 else 0,
        "height": max(1, round(height * y_scale)) if height > 0 else 0,
    }


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

    prepared.sort(key=lambda monitor: (monitor["top"], monitor["left"]))
    return prepared


def build_monitor_cell_mapping(
    *,
    display_setup: dict[str, object],
    physical_monitors: list[dict[str, Any]],
) -> dict[tuple[int, int], dict[str, int]]:
    normalized_setup = normalize_display_setup(display_setup)
    active_cells = list_active_layout_cells(normalized_setup["layout"])  # type: ignore[arg-type]
    monitors = prepare_physical_monitors(physical_monitors)

    if len(monitors) != len(active_cells):
        raise ValueError(
            "Display layout mismatch: "
            f"settings expect {len(active_cells)} monitor(s), but Windows detected {len(monitors)}."
        )

    return {
        cell: monitor
        for cell, monitor in zip(active_cells, monitors)
    }


def resolve_capture_monitor(
    *,
    display_setup: dict[str, object],
    physical_monitors: list[dict[str, Any]],
) -> dict[str, int]:
    normalized_setup = normalize_display_setup(display_setup)
    cell = normalized_setup["capture_cell"]
    row = int(cell["row"])  # type: ignore[index]
    column = int(cell["column"])  # type: ignore[index]
    mapping = build_monitor_cell_mapping(display_setup=normalized_setup, physical_monitors=physical_monitors)

    selected_cell = (row, column)
    if selected_cell not in mapping:
        raise ValueError(
            "Selected capture monitor is not enabled in the current layout: "
            f"{describe_layout_cell(row, column)}."
        )
    return mapping[selected_cell]


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
