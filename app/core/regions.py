from __future__ import annotations


def clamp_region(
    region: dict[str, int],
    *,
    bounds_width: int,
    bounds_height: int,
) -> dict[str, int]:
    """Clamp a positive-sized region to image or monitor-relative bounds."""
    if bounds_width <= 0 or bounds_height <= 0:
        raise ValueError("Region bounds must be greater than zero.")

    left = max(0, min(int(region.get("left", 0)), bounds_width - 1))
    top = max(0, min(int(region.get("top", 0)), bounds_height - 1))
    width = max(1, int(region.get("width", 1)))
    height = max(1, int(region.get("height", 1)))

    return {
        "left": left,
        "top": top,
        "width": min(width, bounds_width - left),
        "height": min(height, bounds_height - top),
    }


def expand_region(
    region: dict[str, int],
    *,
    padding: int,
    bounds_width: int,
    bounds_height: int,
) -> dict[str, int]:
    """Expand a template rectangle into a bounded template-search region."""
    selected = clamp_region(
        region,
        bounds_width=bounds_width,
        bounds_height=bounds_height,
    )
    safe_padding = max(0, int(padding))
    left = max(0, selected["left"] - safe_padding)
    top = max(0, selected["top"] - safe_padding)
    right = min(
        bounds_width,
        selected["left"] + selected["width"] + safe_padding,
    )
    bottom = min(
        bounds_height,
        selected["top"] + selected["height"] + safe_padding,
    )
    return {
        "left": left,
        "top": top,
        "width": max(1, right - left),
        "height": max(1, bottom - top),
    }
