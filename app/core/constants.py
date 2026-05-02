BLACK_FRAME_WARNING_COOLDOWN_SECONDS = 1000.0
SCAN_INTERVAL_SECONDS = 0.10

ESCAPE_THRESHOLD = 0.85
GOTCHA_THRESHOLD = 0.85
WILD_THRESHOLD = 0.85
HUH_THRESHOLD = 0.85

POST_DETECTION_COOLDOWN_SECONDS = 5.0
SAVE_DEBUG_FRAMES = False
DEBUG_SAVE_EVERY_N_FRAMES = 1
MATCH_LOG_EVERY_N_FRAMES = 5
PREVIEW_MATCH_THRESHOLD = 0.60

NEAR_BLACK_MEAN_THRESHOLD = 5.0
NEAR_BLACK_MAX_THRESHOLD = 20

DEFAULT_RECENT_EVENT_LIMIT = 50

EVENT_LOG_CSV_FIELDS = [
    "timestamp",
    "event",
    "counter",
    "catch_counter",
    "encounter_increment",
    "last_event",
    "last_event_at",
    "last_match_score",
    "last_catch_at_encounter",
    "encounters_since_last_catch",
    "capture_top",
    "capture_left",
    "capture_width",
    "capture_height",
]
