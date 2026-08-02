# Pokemon Auto Encounter Counter 

**Alpha release**

A local-first Windows desktop utility for counting Pokemon encounters from on-screen battle text using OpenCV template matching.

This project started as a terminal-based Python script and has now been reorganized into a structured desktop application built with `PySide6`, while keeping the original detection workflow and local file outputs.

## Status

This project is currently in **Alpha**.

What that means:

- the desktop application is working and usable
- the architecture has been split into core, services, and GUI layers
- the file-based workflow is still the source of truth
- future modes and setup tools are planned, but not all are implemented yet

## Features

- Windows desktop GUI built with `PySide6`
- Reusable Python detection engine
- Local screen capture with `mss`
- Template matching with `OpenCV`
- Start and stop scanning from the GUI
- Per-mode encounter increment setting
- Per-filter cooldown setting
- Per-mode capture region settings stored in `config.json`
- Live counter and runtime status updates
- Test screenshot workflow with preview
- In-app template creator with a draggable and resizable crop selection
- Automatic padded search regions around tightly cropped text templates
- Live template-match score in the preview workflow
- Game identity and numbered sessions without resetting the lifetime counter
- Template status and preview tab
- Local logs and state viewer
- Single-instance protection while scanning

## Supported Modes

### Available now

- **Random grass encounter**
  Detects:
  - `templates/got_away.png`
  - `templates/gotcha.png`

- **Safari zone**
  Detects:
  - `templates/wild.png`

- **Egg mode**
  Counts the egg `Huh?` prompt. The filter is included in the release, and the
  template can be created for the user's game and display setup with
  `Filters -> Huh -> Make Template`.

### Planned

- **Soft reset**
  Present in the GUI structure, but not implemented in this alpha version.

## Local-First Workflow

The application does not use cloud services or remote storage.

It works entirely from local files:

- templates are loaded from `templates/`
- runtime output is written to `output/`
- capture settings are stored in `config.json`

The desktop app is a frontend over the existing local workflow, not a replacement for it.

## Output Files

The application continues to use these files:

- `output/counter.txt`
- `output/state.json`
- `output/encounter_log.csv`
- `output/event_log.jsonl`
- `output/last_capture.png`
- `output/template_source.png`
- `output/encounter_counter.lock`

`state.json`, CSV, and JSONL events include the active game and session. The
lifetime counter remains in `counter.txt`; `session_encounter_count` starts at
zero for each new session.

## Project Structure

```text
Auto-Encounter-Counter-Pokemon/
|-- app/
|   |-- core/
|   |   |-- capture.py
|   |   |-- constants.py
|   |   |-- detector.py
|   |   |-- event_logger.py
|   |   |-- exceptions.py
|   |   |-- modes.py
|   |   |-- models.py
|   |   |-- paths.py
|   |   |-- regions.py
|   |   |-- state_manager.py
|   |   `-- templates.py
|   |-- gui/
|   |   |-- capture_settings_tab.py
|   |   |-- dashboard_tab.py
|   |   |-- filters_tab.py
|   |   |-- logs_tab.py
|   |   |-- main_window.py
|   |   |-- monitor_layout_widget.py
|   |   |-- template_crop_dialog.py
|   |   `-- templates_tab.py
|   |-- services/
|   |   |-- app_controller.py
|   |   |-- config_service.py
|   |   |-- session_service.py
|   |   `-- worker.py
|   `-- main.py
|-- config.json
|-- run.py
|-- templates/
|-- output/
|-- pyproject.toml
`-- README.md
```

## Architecture

The project is now split into three layers.

### 1. Core engine

Located in `app/core/`

Responsibilities:

- screen capture
- template loading
- template matching
- cooldown logic
- encounter counting
- mode behavior
- state persistence
- event logging

This layer does not depend on the GUI.

### 2. Services / controller layer

Located in `app/services/`

Responsibilities:

- loading and saving config
- starting and stopping scans
- running detection in a worker thread
- exposing structured updates to the GUI
- coordinating engine state, screenshots, templates, and logs

### 3. GUI layer

Located in `app/gui/`

Responsibilities:

- dashboard and controls
- capture settings editor
- template status view
- logs and state view
- preview and status presentation

The GUI does not contain encounter detection logic.

## Requirements

- Windows
- Python `>= 3.14`
- PowerShell or another terminal

Dependencies:

- `PySide6`
- `opencv-python`
- `mss`
- `numpy`

## Installation

From the project root in **Windows PowerShell**:

```powershell
cd <repo-root>
uv sync
```

This installs the dependencies into the local virtual environment.

You can also launch the app through the helper script:

```powershell
.\start.ps1
```

## Quick Start

1. Open **Windows PowerShell**.
2. Go to the project folder:

```powershell
cd <repo-root>
```

3. Launch the desktop app:

```powershell
.\start.ps1
```

If the local virtual environment does not exist yet, the script runs `uv sync` first.

## Run the Desktop App

From the project root in **Windows PowerShell**:

```powershell
cd <repo-root>
.\start.ps1
```

To force a dependency refresh before launch:

```powershell
.\start.ps1 -Sync
```

The script also supports the older terminal flow:

```powershell
.\start.ps1 -Cli
```

## Run the CLI Version

The terminal version still exists and now uses the shared core engine.

From the project root:

```powershell
cd <repo-root>
.\.venv\Scripts\python run.py
```

## GUI Tabs

### Dashboard

Main operating view for:

- game selection and numbered sessions
- encounter increment
- start and stop controls
- live counters
- status display
- live runtime log

### Capture Settings

Used for:

- choosing the monitor used for capture
- reviewing the latest filter preview
- saving display settings to `config.json`

### Filters

Used for:

- organizing filters by game
- choosing event type, threshold, cooldown, and enabled state
- creating a template from a full-monitor screenshot
- moving and resizing the template crop before saving it
- checking a live template-match score against the current preview

### Templates

Used for:

- checking which required template files are present
- identifying missing or unreadable templates
- previewing template images

Template creation lives in the Filters tab because it updates both the image
file and the selected filter's search region.

### Logs / State

Used for:

- viewing recent event history
- viewing current local state
- locating the output folder

## Typical User Flow

1. Open the desktop application.
2. Go to `Capture Settings` and choose the monitor containing the game.
3. Open `Filters`, select the game and the filter you want to configure.
4. Click `Make Template` and drag the yellow rectangle tightly around the
   battle text. Drag inside it to move it or use its handles to resize it.
5. Keep the default search padding or adjust it if the text can move slightly.
6. Save the template, then run `Capture Preview` to see its live match score.
7. Enable the filter when its preview is reliable.
8. Go to `Dashboard`, set the encounter increment, and click `Start`.
9. Click `Stop` when finished.

## Templates

Templates can be created and replaced from the Filters tab. The selected crop
is saved tightly around the text; the app automatically expands the filter's
capture region using the chosen search padding. This lets OpenCV search for the
text within a small area instead of requiring exact manual pixel coordinates.

Starter template names by mode:

- Random grass encounter:
  - `got_away.png`
  - `gotcha.png`
- Safari zone:
  - `wild.png`
- Egg mode:
  - `huh.png`

Egg counting remains supported when `huh.png` has not been created yet: select
the Huh filter and make it from a live monitor preview. If a required template
is missing or unreadable, the application surfaces that in the Templates tab
and through runtime error handling.

## Games and Sessions

The lifetime encounter and catch counters never reset when a session changes.
A session adds a second counter for a particular stretch of play:

- switching to another game starts a new session for that game
- `New Session` on the Dashboard starts another session for the current game
- stopping and restarting scanning continues the current session
- every new event stores game and session identity alongside the existing data

Events created before session tracking are retained as session 1. During the
one-time migration the original CSV and JSONL files are copied to
`output/migration_backups/session_identity_v1/`. The application then begins
session 2 at the existing lifetime counter without resetting encounters or
catches. The pre-migration `state.json` and `counter.txt` are retained in the
same versioned backup folder. Older configuration versions are backed up under
`output/migration_backups/config_<old>_to_v<new>/` before normalization.

## Configuration

The main local config file is:

- `config.json`
- `config.example.json`

It stores:

- active game
- encounter increment
- debug preferences
- per-filter templates, capture regions, thresholds, and cooldowns

Notes:

- `config.json` is local machine-specific and is intended to stay uncommitted
- `config.example.json` is the safe committed reference for default app settings

## Known Limitations

- This is still an **Alpha** release.
- `Soft reset` is not implemented yet.
- Egg mode needs a `huh.png` made from the user's own game preview before its
  filter can be enabled.
- The template picker uses a full-monitor screenshot inside the application; a
  transparent live desktop overlay may be considered later.
- There is no cloud sync, OCR, or overlay tool in this version.

## Development Notes

The current design is intended to make future expansion easier.

Run the built-in test suite from the project root with:

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

Persistent JSON and text files are written through a flushed same-directory
temporary file and replaced atomically. `output/event_log.jsonl` is the
authoritative event history; `output/encounter_log.csv` is checked against it
at startup and rebuilt automatically when rows or fields differ.

Adding a new mode should mainly involve:

- defining the mode in `app/core/modes.py`
- adding templates and detection rules in the core engine
- adding capture settings support in `config.json`
- exposing the mode in the GUI

## Packaging Direction

The application can be packaged as a Windows desktop app with `PyInstaller`.

Install the build dependency:

```powershell
uv sync --extra build
```

Build the packaged app:

```powershell
uv run --extra build pyinstaller pokemon-encounter-counter.spec --noconfirm
```

Run the non-capturing source or packaged smoke test with:

```powershell
uv run python -B -m app.main --smoke-test
dist\PokemonEncounterCounter\PokemonEncounterCounter.exe --smoke-test
```

The packaged output is written to:

```text
dist/PokemonEncounterCounter/
```

Notes:

- the build uses a one-folder layout so bundled templates live next to the executable
- built-in templates are bundled automatically
- `output/` is created on first run
- `.github/workflows/windows-ci.yml` tests on Python 3.14, runs Qt offscreen,
  builds the application, smoke-tests the executable, and uploads the folder
  as a workflow artifact
- `config.json` is created on first run if it does not already exist

## License

No license file is currently included in this repository.
