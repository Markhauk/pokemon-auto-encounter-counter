# Auto Encounter Counter Pokemon

A local-first Pokemon encounter counter built in Python. The project now has a reusable detection engine, a retained terminal workflow, and a PySide6 desktop GUI for day-to-day use on Windows.

## What it supports

- Random grass encounter mode via `got_away.png` and `gotcha.png`
- Safari zone mode via `wild.png`
- Egg mode wiring via `huh.png`
- Local state in `output/state.json` and `output/counter.txt`
- Local event logs in `output/encounter_log.csv` and `output/event_log.jsonl`
- Last debug capture output in `output/last_capture.png`
- Per-mode capture region settings in `config.json`
- Single-instance protection while scanning

## Application structure

```text
Auto-Encounter-Counter-Pokemon/
|-- app/
|   |-- core/        # detection, capture, templates, persistence
|   |-- services/    # config, controller, worker thread
|   `-- gui/         # PySide6 desktop UI
|-- config.json
|-- run.py           # terminal entrypoint over the shared core
|-- templates/
`-- output/
```

## Run the GUI

```powershell
python -m app.main
```

Once launched, use:

1. `Dashboard` to pick a mode, set encounter increment, and start or stop scanning.
2. `Capture Settings` to edit per-mode screen regions and test screenshots.
3. `Templates` to verify required template files.
4. `Logs / State` to inspect the local files the engine writes.

## Run the CLI

```powershell
python run.py
```

The CLI still supports:

- monitor listing
- monitor screenshots
- explicit capture region overrides
- debug capture mode

## Notes

- The GUI and CLI both reuse the same detection engine and output files.
- `Soft reset` is present in the UI as a future mode, but is intentionally disabled in v1.
- `Egg mode` requires `templates/huh.png`. If that file is missing, the Templates tab and runtime error handling will surface it clearly.
