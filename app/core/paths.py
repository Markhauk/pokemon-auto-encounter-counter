from __future__ import annotations

import sys
from pathlib import Path


def resolve_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


BASE_DIR = resolve_base_dir()
TEMPLATES_DIR = BASE_DIR / "templates"
OUTPUT_DIR = BASE_DIR / "output"
CONFIG_FILE = BASE_DIR / "config.json"

COUNTER_FILE = OUTPUT_DIR / "counter.txt"
STATE_FILE = OUTPUT_DIR / "state.json"
LOCK_FILE = OUTPUT_DIR / "encounter_counter.lock"
DEBUG_FRAME_FILE = OUTPUT_DIR / "last_capture.png"

ENCOUNTER_LOG_CSV_FILE = OUTPUT_DIR / "encounter_log.csv"
EVENT_LOG_JSONL_FILE = OUTPUT_DIR / "event_log.jsonl"
