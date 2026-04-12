# Auto Encounter Counter Pokémon

A local screen-monitoring utility that uses OpenCV template matching to count Pokémon battle results from on-screen text.

## Features

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
