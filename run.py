import argparse
import json
import os
import signal
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import cv2
import mss
import numpy as np


BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
OUTPUT_DIR = BASE_DIR / "output"
COUNTER_FILE = OUTPUT_DIR / "counter.txt"
STATE_FILE = OUTPUT_DIR / "state.json"
LOCK_FILE = OUTPUT_DIR / "encounter_counter.lock"
DEBUG_FRAME_FILE = OUTPUT_DIR / "last_capture.png"

CAPTURE_REGION = {
    "top": 1100,
    "left": 250,
    "width": 1390,
    "height": 150,
}

BLACK_FRAME_WARNING_COOLDOWN_SECONDS = 1000.0
SCAN_INTERVAL_SECONDS = 0.10
ESCAPE_THRESHOLD = 0.85
POST_DETECTION_COOLDOWN_SECONDS = 5.0
SAVE_DEBUG_FRAMES = True
DEBUG_SAVE_EVERY_N_FRAMES = 1
MATCH_LOG_EVERY_N_FRAMES = 5
PREVIEW_MATCH_THRESHOLD = 0.60
NEAR_BLACK_MEAN_THRESHOLD = 5.0
NEAR_BLACK_MAX_THRESHOLD = 20


@dataclass
class MatchResult:
    found: bool
    score: float
    location: Optional[Tuple[int, int]] = None


@dataclass
class BrightnessStats:
    min_value: int
    max_value: int
    mean_value: float
    std_value: float
    nonzero_ratio: float


class SingleInstanceGuard:
    def __init__(self, lock_file: Path) -> None:
        self.lock_file = lock_file
        self.handle = None

    def __enter__(self) -> "SingleInstanceGuard":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        self.release()

    def acquire(self) -> None:
        self.lock_file.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.lock_file.open("a+", encoding="utf-8")

        try:
            self.handle.seek(0)
            self.handle.write(" ")
            self.handle.flush()
            self.handle.seek(0)

            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            other_pid = self._read_existing_pid()
            self.handle.close()
            self.handle = None
            pid_suffix = f" (PID {other_pid})" if other_pid else ""
            raise RuntimeError(f"Another copy of run.py is already running{pid_suffix}.")

        self.handle.seek(0)
        self.handle.truncate()
        self.handle.write(str(os.getpid()))
        self.handle.flush()

    def release(self) -> None:
        if self.handle is None:
            return

        try:
            self.handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        finally:
            self.handle.close()
            self.handle = None
            try:
                self.lock_file.unlink()
            except OSError:
                pass

    def _read_existing_pid(self) -> Optional[str]:
        try:
            pid = self.lock_file.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        return pid or None


class EncounterCounter:
    def __init__(
        self,
        *,
        capture_region: Optional[dict[str, int]] = None,
        save_debug_frames: bool = SAVE_DEBUG_FRAMES,
        debug_once: bool = False,
        verbose_debug: bool = False,
    ) -> None:
        self.running = True
        self.counter = 0
        self.capture_region = dict(capture_region or CAPTURE_REGION)
        self.save_debug_frames = save_debug_frames
        self.debug_once = debug_once
        self.verbose_debug = verbose_debug
        self.last_black_frame_warning_time = 0.0
        self.frame_index = 0
        self.last_match_log_frame = 0
        self.cooldown_until = 0.0
        self.waiting_for_clear = False

        self.ensure_directories()
        self.load_state()
        self.save_state()

        self.escape_template: Optional[np.ndarray] = None
        if not self.debug_once:
            self.escape_template = self.load_template("got_away.png")

    def ensure_directories(self) -> None:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

    def load_template(self, filename: str) -> np.ndarray:
        path = TEMPLATES_DIR / filename
        if not path.exists():
            print(f"[ERROR] Missing template: {path}")
            print("Create the template image and try again.")
            sys.exit(1)

        template = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if template is None:
            print(f"[ERROR] Failed to load template: {path}")
            sys.exit(1)
        return template

    def load_state(self) -> None:
        if COUNTER_FILE.exists():
            try:
                self.counter = int(COUNTER_FILE.read_text(encoding="utf-8").strip())
            except ValueError:
                print("[WARN] counter.txt was invalid. Starting from 0.")
                self.counter = 0

        if STATE_FILE.exists():
            try:
                data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
                self.cooldown_until = float(data.get("cooldown_until", 0.0))
                self.waiting_for_clear = bool(data.get("waiting_for_clear", False))
            except (json.JSONDecodeError, ValueError, TypeError):
                print("[WARN] state.json was invalid. Using defaults.")

    def save_state(self) -> None:
        COUNTER_FILE.write_text(str(self.counter), encoding="utf-8")
        STATE_FILE.write_text(
            json.dumps(
                {
                    "counter": self.counter,
                    "cooldown_until": self.cooldown_until,
                    "waiting_for_clear": self.waiting_for_clear,
                    "capture_region": self.capture_region,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    def log(self, message: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        print(f"[{timestamp}] {message}")

    def screenshot_region(self) -> np.ndarray:
        with mss.mss() as sct:
            shot = sct.grab(self.capture_region)
            frame = np.array(shot)
            frame_bgr = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
            gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)

            stats = compute_brightness_stats(gray)
            self.frame_index += 1

            if self.verbose_debug or self.debug_once:
                self.log(
                    "Capture stats: "
                    f"shape={frame_bgr.shape}, min={stats.min_value}, max={stats.max_value}, "
                    f"mean={stats.mean_value:.2f}, std={stats.std_value:.2f}, "
                    f"nonzero_ratio={stats.nonzero_ratio:.4f}"
                )

            if self.save_debug_frames and (self.frame_index % DEBUG_SAVE_EVERY_N_FRAMES == 0):
                try:
                    save_image(DEBUG_FRAME_FILE, frame_bgr)
                except RuntimeError:
                    self.log(f"[WARN] Failed to save debug frame to: {DEBUG_FRAME_FILE}")

            if is_nearly_black(stats):
                now = time.time()
                if (now - self.last_black_frame_warning_time) >= BLACK_FRAME_WARNING_COOLDOWN_SECONDS:
                    self.last_black_frame_warning_time = now
                    self.log(
                        "[WARN] Capture is black or nearly black. Possible causes: wrong monitor/region, "
                        "OBS preview on another monitor, minimized window, protected/hardware-accelerated content."
                    )

            return gray

    def match_template(self, image: np.ndarray, template: np.ndarray, threshold: float) -> MatchResult:
        result = cv2.matchTemplate(image, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        return MatchResult(found=max_val >= threshold, score=float(max_val), location=max_loc)

    def in_cooldown(self) -> bool:
        return time.time() < self.cooldown_until

    def start_cooldown(self) -> None:
        self.cooldown_until = time.time() + POST_DETECTION_COOLDOWN_SECONDS
        self.waiting_for_clear = True
        self.save_state()
        self.log(f"Cooldown started for {POST_DETECTION_COOLDOWN_SECONDS:.1f} seconds.")

    def increment_counter(self) -> None:
        self.counter += 1
        self.save_state()
        self.log(f"Got away detected. Counter is now {self.counter}.")

    def handle_frame(self, gray_frame: np.ndarray) -> None:
        if self.escape_template is None:
            raise RuntimeError("Template is not loaded.")

        escape_match = self.match_template(gray_frame, self.escape_template, ESCAPE_THRESHOLD)

        should_log_preview = (
            self.verbose_debug
            and (
                self.frame_index - self.last_match_log_frame >= MATCH_LOG_EVERY_N_FRAMES
                or escape_match.score >= PREVIEW_MATCH_THRESHOLD
            )
        )

        if should_log_preview:
            self.last_match_log_frame = self.frame_index
            cooldown_remaining = max(0.0, self.cooldown_until - time.time())
            self.log(
                "Match score: "
                f"got_away={escape_match.score:.3f} "
                f"(found={escape_match.found}), "
                f"cooldown_remaining={cooldown_remaining:.2f}s, "
                f"waiting_for_clear={self.waiting_for_clear}"
            )

        if self.in_cooldown():
            return

        if self.waiting_for_clear:
            if not escape_match.found:
                self.waiting_for_clear = False
                self.save_state()
                self.log("Got-away text cleared. Re-armed for next encounter.")
            return

        if escape_match.found:
            self.log(f"Matched got_away.png with score {escape_match.score:.3f}")
            self.increment_counter()
            self.start_cooldown()

    def run(self) -> None:
        if self.debug_once:
            self.log("Running single debug capture.")
            self.log(f"Capture region: {self.capture_region}")
            self.screenshot_region()
            self.log(f"Saved debug frame to: {DEBUG_FRAME_FILE}")
            return

        self.log("Starting Pokemon encounter counter.")
        self.log(f"Current counter: {self.counter}")
        self.log(f"Capture region: {self.capture_region}")
        self.log("Mode: got-away-only")
        self.log("Press Ctrl+C to stop. On Windows, Ctrl+Break also works.")

        while self.running:
            try:
                frame = self.screenshot_region()
                self.handle_frame(frame)
                time.sleep(SCAN_INTERVAL_SECONDS)
            except KeyboardInterrupt:
                self.stop()
            except Exception as exc:
                self.log(f"[ERROR] {exc}")
                time.sleep(1)

    def stop(self) -> None:
        self.running = False
        self.save_state()
        self.log("State saved. Exiting.")


def handle_shutdown(counter: EncounterCounter, signum, frame) -> None:  # type: ignore[no-untyped-def]
    counter.log(f"Received signal {signum}. Shutting down.")
    counter.stop()
    sys.exit(0)


def list_monitors() -> None:
    with mss.mss() as sct:
        print("Detected monitor regions:")
        for index, monitor in enumerate(sct.monitors):
            label = "all monitors" if index == 0 else f"monitor {index}"
            print(f"  {index}: {label} -> {monitor}")


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


def save_all_monitors() -> None:
    with mss.mss() as sct:
        for index, monitor in enumerate(sct.monitors[1:], start=1):
            frame_bgr = grab_region(monitor)
            out_path = OUTPUT_DIR / f"monitor_{index}.png"
            save_image(out_path, frame_bgr)
            gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
            stats = compute_brightness_stats(gray)
            print(f"Saved {out_path} -> region={monitor}, mean={stats.mean_value:.2f}, max={stats.max_value}")


def save_monitor(index: int) -> None:
    with mss.mss() as sct:
        if index < 1 or index >= len(sct.monitors):
            raise ValueError(f"Monitor index {index} is out of range. Use --list-monitors first.")
        region = sct.monitors[index]

    frame_bgr = grab_region(region)
    out_path = OUTPUT_DIR / f"monitor_{index}.png"
    save_image(out_path, frame_bgr)
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    stats = compute_brightness_stats(gray)
    print(f"Saved {out_path} -> region={region}, mean={stats.mean_value:.2f}, max={stats.max_value}")


def resolve_capture_region(
    monitor_index: Optional[int],
    region_values: Optional[list[int]],
    monitor_region_values: Optional[list[int]],
) -> dict[str, int]:
    if monitor_region_values is not None:
        monitor_idx, left, top, width, height = monitor_region_values
        if width <= 0 or height <= 0:
            raise ValueError("Monitor-relative region width and height must be greater than 0.")

        with mss.mss() as sct:
            if monitor_idx < 1 or monitor_idx >= len(sct.monitors):
                raise ValueError(f"Monitor index {monitor_idx} is out of range. Use --list-monitors first.")
            monitor = sct.monitors[monitor_idx]

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
        return dict(CAPTURE_REGION)

    with mss.mss() as sct:
        if monitor_index < 1 or monitor_index >= len(sct.monitors):
            raise ValueError(
                f"Monitor index {monitor_index} is out of range. Run with --list-monitors to inspect valid values."
            )
        monitor = sct.monitors[monitor_index]
        return {
            "left": monitor["left"],
            "top": monitor["top"],
            "width": monitor["width"],
            "height": monitor["height"],
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Pokemon encounter counter (got-away-only)")
    parser.add_argument("--debug", action="store_true", help="Continuously update output/last_capture.png while running.")
    parser.add_argument("--debug-once", action="store_true", help="Capture one frame to output/last_capture.png and exit.")
    parser.add_argument("--verbose-debug", action="store_true", help="Print detailed image stats for each capture.")
    parser.add_argument("--list-monitors", action="store_true", help="Print detected monitor regions and exit.")
    parser.add_argument("--save-all-monitors", action="store_true", help="Save one screenshot for every monitor and exit.")
    parser.add_argument("--save-monitor", type=int, help="Save one screenshot for the selected full monitor and exit.")
    parser.add_argument("--monitor", type=int, help="Use an entire detected monitor as the capture region.")
    parser.add_argument(
        "--region",
        nargs=4,
        type=int,
        metavar=("LEFT", "TOP", "WIDTH", "HEIGHT"),
        help="Use explicit desktop coordinates as the capture region.",
    )
    parser.add_argument(
        "--monitor-region",
        nargs=5,
        type=int,
        metavar=("MONITOR", "LEFT", "TOP", "WIDTH", "HEIGHT"),
        help="Use coordinates relative to a selected monitor.",
    )
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.list_monitors:
        list_monitors()
        return

    try:
        if args.save_all_monitors:
            save_all_monitors()
            return

        if args.save_monitor is not None:
            save_monitor(args.save_monitor)
            return

        capture_region = resolve_capture_region(args.monitor, args.region, args.monitor_region)
    except ValueError as exc:
        print(f"[ERROR] {exc}")
        sys.exit(1)

    try:
        with SingleInstanceGuard(LOCK_FILE):
            counter = EncounterCounter(
                capture_region=capture_region,
                save_debug_frames=True,
                debug_once=args.debug_once,
                verbose_debug=True,
            )
            signal.signal(signal.SIGINT, lambda s, f: handle_shutdown(counter, s, f))
            signal.signal(signal.SIGTERM, lambda s, f: handle_shutdown(counter, s, f))
            if hasattr(signal, "SIGBREAK"):
                signal.signal(signal.SIGBREAK, lambda s, f: handle_shutdown(counter, s, f))
            counter.run()
    except RuntimeError as exc:
        print(f"[ERROR] {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()