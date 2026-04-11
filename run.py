import json
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


# Adjust these values to match the text box area in your OBS preview or capture window.
CAPTURE_REGION = {
    "top": 800,
    "left": 500,
    "width": 900,
    "height": 180,
}

# How often to scan the screen.
SCAN_INTERVAL_SECONDS = 0.50

# Template matching thresholds.
ENCOUNTER_THRESHOLD = 0.88
ESCAPE_THRESHOLD = 0.88

# Prevents repeated triggers while the same text is still visible.
COOLDOWN_SECONDS = 1.5

# Optional debug image output.
SAVE_DEBUG_FRAMES = False
DEBUG_FRAME_FILE = OUTPUT_DIR / "last_capture.png"


@dataclass
class MatchResult:
    found: bool
    score: float
    location: Optional[Tuple[int, int]] = None


class EncounterCounter:
    def __init__(self) -> None:
        self.running = True
        self.state = "waiting_for_encounter"
        self.counter = 0
        self.last_trigger_time = 0.0

        self.ensure_directories()
        self.load_state()

        self.encounter_template = self.load_template("appeared.png")
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
                self.state = data.get("state", self.state)
                self.last_trigger_time = float(data.get("last_trigger_time", 0.0))
            except (json.JSONDecodeError, ValueError, TypeError):
                print("[WARN] state.json was invalid. Using defaults.")

    def save_state(self) -> None:
        COUNTER_FILE.write_text(str(self.counter), encoding="utf-8")
        STATE_FILE.write_text(
            json.dumps(
                {
                    "state": self.state,
                    "counter": self.counter,
                    "last_trigger_time": self.last_trigger_time,
                    "capture_region": CAPTURE_REGION,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    def screenshot_region(self) -> np.ndarray:
        with mss.mss() as sct:
            shot = sct.grab(CAPTURE_REGION)
            frame = np.array(shot)
            frame_bgr = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
            gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)

            if SAVE_DEBUG_FRAMES:
                cv2.imwrite(str(DEBUG_FRAME_FILE), frame_bgr)

            return gray

    def match_template(self, image: np.ndarray, template: np.ndarray, threshold: float) -> MatchResult:
        result = cv2.matchTemplate(image, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        return MatchResult(found=max_val >= threshold, score=float(max_val), location=max_loc)

    def can_trigger(self) -> bool:
        return (time.time() - self.last_trigger_time) >= COOLDOWN_SECONDS

    def increment_counter(self) -> None:
        self.counter += 1
        self.last_trigger_time = time.time()
        self.save_state()
        self.log(f"Encounter detected. Counter is now {self.counter}.")

    def set_state(self, new_state: str) -> None:
        self.state = new_state
        self.last_trigger_time = time.time()
        self.save_state()
        self.log(f"State changed to: {self.state}")

    def log(self, message: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        print(f"[{timestamp}] {message}")

    def handle_frame(self, gray_frame: np.ndarray) -> None:
        encounter_match = self.match_template(gray_frame, self.encounter_template, ENCOUNTER_THRESHOLD)
        escape_match = self.match_template(gray_frame, self.escape_template, ESCAPE_THRESHOLD)

        if self.state == "waiting_for_encounter":
            if encounter_match.found and self.can_trigger():
                self.log(f"Matched appeared.png with score {encounter_match.score:.3f}")
                self.increment_counter()
                self.set_state("waiting_for_escape")

        elif self.state == "waiting_for_escape":
            if escape_match.found and self.can_trigger():
                self.log(f"Matched got_away.png with score {escape_match.score:.3f}")
                self.set_state("waiting_for_encounter")

    def run(self) -> None:
        self.log("Starting Pokémon encounter counter.")
        self.log(f"Current state: {self.state}")
        self.log(f"Current counter: {self.counter}")
        self.log(f"Capture region: {CAPTURE_REGION}")
        self.log("Press Ctrl+C to stop.")

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


def main() -> None:
    counter = EncounterCounter()
    signal.signal(signal.SIGINT, lambda s, f: handle_shutdown(counter, s, f))
    signal.signal(signal.SIGTERM, lambda s, f: handle_shutdown(counter, s, f))
    counter.run()


if __name__ == "__main__":
    main()
