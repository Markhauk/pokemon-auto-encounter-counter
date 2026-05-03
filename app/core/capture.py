from __future__ import annotations

from pathlib import Path
from typing import Optional

import cv2
import mss
import numpy as np

from .constants import NEAR_BLACK_MAX_THRESHOLD, NEAR_BLACK_MEAN_THRESHOLD
from .models import BrightnessStats


def compute_brightness_stats(gray_image: np.ndarray) -> BrightnessStats:
    return BrightnessStats(
        min_value=int(np.min(gray_image)),
        max_value=int(np.max(gray_image)),
        mean_value=float(np.mean(gray_image)),
        std_value=float(np.std(gray_image)),
        nonzero_ratio=float(np.count_nonzero(gray_image) / gray_image.size),
    )


def is_nearly_black(stats: BrightnessStats) -> bool:
    return stats.mean_value <= NEAR_BLACK_MEAN_THRESHOLD and stats.max_value <= NEAR_BLACK_MAX_THRESHOLD


def save_image(path: Path, frame_bgr: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp.png")
    if not cv2.imwrite(str(tmp_path), frame_bgr):
        raise RuntimeError(f"Failed to save image to {tmp_path}")
    tmp_path.replace(path)


def grab_region(region: dict[str, int]) -> np.ndarray:
    with mss.mss() as sct:
        shot = sct.grab(region)
    frame = np.array(shot)
    return cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)


def capture_region_summary(region: dict[str, int]) -> str:
    return (
        f"left={region['left']}, top={region['top']}, "
        f"width={region['width']}, height={region['height']}"
    )


def get_monitors() -> list[dict[str, int]]:
    with mss.mss() as sct:
        return [dict(monitor) for monitor in sct.monitors]


def get_physical_monitors() -> list[dict[str, int]]:
    monitors = get_monitors()
    physical_monitors: list[dict[str, int]] = []
    for index, monitor in enumerate(monitors[1:], start=1):
        physical_monitors.append(
            {
                "index": index,
                "left": int(monitor["left"]),
                "top": int(monitor["top"]),
                "width": int(monitor["width"]),
                "height": int(monitor["height"]),
            }
        )
    return physical_monitors


def save_all_monitors(output_dir: Path) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    monitors = get_monitors()

    for index, monitor in enumerate(monitors[1:], start=1):
        frame_bgr = grab_region(monitor)
        out_path = output_dir / f"monitor_{index}.png"
        save_image(out_path, frame_bgr)
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        stats = compute_brightness_stats(gray)
        results.append(
            {
                "index": index,
                "path": str(out_path),
                "region": monitor,
                "mean": stats.mean_value,
                "max": stats.max_value,
            }
        )

    return results


def save_monitor(output_dir: Path, index: int) -> dict[str, object]:
    monitors = get_monitors()
    if index < 1 or index >= len(monitors):
        raise ValueError(f"Monitor index {index} is out of range. Use --list-monitors first.")

    region = monitors[index]
    frame_bgr = grab_region(region)
    out_path = output_dir / f"monitor_{index}.png"
    save_image(out_path, frame_bgr)
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    stats = compute_brightness_stats(gray)
    return {
        "index": index,
        "path": str(out_path),
        "region": region,
        "mean": stats.mean_value,
        "max": stats.max_value,
    }


def resolve_capture_region(
    monitor_index: Optional[int],
    region_values: Optional[list[int]],
    monitor_region_values: Optional[list[int]],
    default_region: Optional[dict[str, int]] = None,
) -> dict[str, int]:
    if monitor_region_values is not None:
        monitor_idx, left, top, width, height = monitor_region_values
        if width <= 0 or height <= 0:
            raise ValueError("Monitor-relative region width and height must be greater than 0.")

        monitors = get_monitors()
        if monitor_idx < 1 or monitor_idx >= len(monitors):
            raise ValueError(f"Monitor index {monitor_idx} is out of range. Use --list-monitors first.")

        monitor = monitors[monitor_idx]
        return {
            "left": monitor["left"] + left,
            "top": monitor["top"] + top,
            "width": width,
            "height": height,
        }

    if region_values is not None:
        left, top, width, height = region_values
        if width <= 0 or height <= 0:
            raise ValueError("Region width and height must be greater than 0.")
        return {"left": left, "top": top, "width": width, "height": height}

    if monitor_index is None:
        return dict(default_region or {})

    monitors = get_monitors()
    if monitor_index < 1 or monitor_index >= len(monitors):
        raise ValueError(
            f"Monitor index {monitor_index} is out of range. Run with --list-monitors to inspect valid values."
        )

    monitor = monitors[monitor_index]
    return {
        "left": monitor["left"],
        "top": monitor["top"],
        "width": monitor["width"],
        "height": monitor["height"],
    }
