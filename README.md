- Template matching with `OpenCV`
- Counts encounters from `got_away.png`
- Counts catches from `gotcha.png`
- Saves persistent state to `output/state.json`
- Saves encounter count to `output/counter.txt`
- Writes a CSV event log to `output/encounter_log.csv`
- Writes a JSONL event log to `output/event_log.jsonl`
- Prevents duplicate launches with a lock file
- Supports custom monitor and region selection
- Debug capture tools for tuning the detection area

---

## How it works

The script repeatedly captures a defined screen region and compares it against two grayscale template images:

- `templates/got_away.png`
- `templates/gotcha.png`

When a template match passes the configured threshold:

- `got_away` increases the encounter counter
- `gotcha` increases both the encounter counter and the catch counter

A cooldown is applied after detection so the same result text is not counted multiple times while it stays visible on screen.

---

## Project structure

```text
Auto-Encounter-Counter-Pokemon/
├─ run.py
├─ templates/
│  ├─ got_away.png
│  └─ gotcha.png
└─ output/
   ├─ counter.txt
   ├─ state.json
   ├─ encounter_log.csv
   ├─ event_log.jsonl
   ├─ last_capture.png
   └─ encounter_counter.lock
Requirements
Python 3.10+
Windows recommended
A visible game window or capture source on screen
Template screenshots for the result text

Python packages:

opencv-python
mss
numpy
Installation

Clone the repo:

git clone https://github.com/YOUR_USERNAME/Auto-Encounter-Counter-Pokemon.git
cd Auto-Encounter-Counter-Pokemon

Create and activate a virtual environment:

Windows PowerShell
python -m venv .venv
.venv\Scripts\Activate.ps1
macOS / Linux
python3 -m venv .venv
source .venv/bin/activate

Install dependencies:

pip install opencv-python mss numpy
Template setup

Create a templates folder and place these files inside it:

got_away.png
gotcha.png

These should be small, clean screenshots of the exact result text as it appears in your game layout.

Tips:

crop tightly around the text
avoid extra background if possible
keep the same scale and UI layout as the live game
use clean screenshots from the same capture source you will monitor
First-time setup

Before running full detection, use the debug tools to find the correct capture region.

List detected monitors
python run.py --list-monitors
Save screenshots of all monitors
python run.py --save-all-monitors
Save one full monitor
python run.py --save-monitor 1
Capture one frame from your configured region
python run.py --debug-once

This writes:

output/last_capture.png

Use that image to confirm the result text appears inside the selected region.

Running the script

Standard run:

python run.py

The script will:

start scanning the configured region
detect got_away and gotcha
update local state files
write event logs
keep running until stopped

Stop with:

Ctrl + C
Ctrl + Break on Windows
Choosing a capture region

There are 3 ways to set the region.

1. Use the default hardcoded region

Edit CAPTURE_REGION in run.py:

CAPTURE_REGION = {
    "top": 1100,
    "left": 282,
    "width": 935,
    "height": 132,
}
2. Use a full detected monitor
python run.py --monitor 1
3. Use explicit desktop coordinates
python run.py --region 282 1100 935 132
4. Use monitor-relative coordinates
python run.py --monitor-region 1 282 1100 935 132

Format:

MONITOR LEFT TOP WIDTH HEIGHT
Output files
output/counter.txt

Stores the current encounter count only.

Example:

30
output/state.json

Stores the latest full state.

Example:

{
  "counter": 30,
  "catch_counter": 3,
  "cooldown_until": 1775998805.167136,
  "waiting_for_clear": true,
  "last_event": "gotcha",
  "last_event_at": "2026-04-12T13:00:00.166630Z",
  "last_match_score": 0.934059,
  "last_catch_at_encounter": 29,
  "encounters_since_last_catch": 0,
  "capture_region": {
    "top": 1100,
    "left": 282,
    "width": 935,
    "height": 132
  }
}
output/encounter_log.csv

Appends one row per detected event.

Example:

timestamp,event,counter,catch_counter,last_event,last_event_at,last_match_score,last_catch_at_encounter,encounters_since_last_catch,capture_top,capture_left,capture_width,capture_height
2026-04-12T13:39:36.723Z,gotcha,30,2,gotcha,2026-04-12T13:00:00.166630Z,0.934059,29,0,1100,282,935,132
output/event_log.jsonl

Appends one JSON object per detected event.

Example:

{"timestamp":"2026-04-12T13:39:36.723Z","event":"gotcha","counter":30,"catch_counter":2,"last_event":"gotcha","last_event_at":"2026-04-12T13:00:00.166630Z","last_match_score":0.934059,"last_catch_at_encounter":29,"encounters_since_last_catch":0,"capture_top":1100,"capture_left":282,"capture_width":935,"capture_height":132}
output/last_capture.png

Stores the latest debug frame.

output/encounter_counter.lock

Used to prevent multiple copies of the script from running at the same time.

CLI options
python run.py --help

Available options include:

--debug
--debug-once
--verbose-debug
--list-monitors
--save-all-monitors
--save-monitor N
--monitor N
--region LEFT TOP WIDTH HEIGHT
--monitor-region MONITOR LEFT TOP WIDTH HEIGHT
Detection behavior
Encounter counting
got_away.png → counter += 1
gotcha.png → counter += 1 and catch_counter += 1
Cooldown

After a detection, the script waits briefly before allowing another one. This prevents repeated counting while the same text remains on screen.

Re-arming

The script waits until the battle result text disappears before allowing the next encounter to be counted.

Troubleshooting
Black or nearly black capture

You may see warnings like:

Capture is black or nearly black

Common causes:

wrong monitor or region selected
minimized game window
hardware-accelerated or protected content
OBS preview on a different monitor than expected

Use:

python run.py --debug-once

and inspect output/last_capture.png.

Missing template error

If you get:

[ERROR] Missing template: ...

make sure these exist:

templates/got_away.png
templates/gotcha.png
False positives or missed detections

Tune these values in run.py:

ESCAPE_THRESHOLD = 0.85
GOTCHA_THRESHOLD = 0.85

Lower values increase sensitivity. Higher values reduce false positives.

Also make sure:

the template is cropped tightly
the text on screen matches the template scale
the capture region includes the result text cleanly
Counter not resetting

State is persisted on disk. Delete the files in output/ for a clean restart:

counter.txt
state.json
encounter_log.csv
event_log.jsonl
Local-only design

This project is intentionally local-first.

It does not require:

Google Sheets
cloud sync
browser login
OCR services
external APIs

Everything is stored as local files on your PC.

Future ideas

Possible next improvements:

shiny detection
species logging
per-session stats
session start/stop summaries
OBS text output files
Discord or local webhook notifications
optional n8n integration using local files only
Disclaimer

This project is a personal utility script for local screen monitoring and event counting. Use it responsibly and make sure it fits the rules of the game and platform you are using.
