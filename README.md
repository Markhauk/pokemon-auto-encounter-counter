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
- Named, resumable hunts with their own counters under each game
- Game and hunt identity plus numbered sessions without resetting all-time totals
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

`state.json`, CSV, and JSONL events include the active game, hunt, and session.
`state.json` also keeps every hunt and its saved totals. The all-time encounter
counter remains mirrored in `counter.txt`; hunt and session counters can start
at zero without changing that all-time total.

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
|   |   |-- new_hunt_dialog.py
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

- game and hunt selection plus numbered sessions
- starting a named hunt while preserving completed or paused hunts
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

Organized as two simple areas:

- `Filter Library` combines game selection and that game's filter list.
- `Selected Filter` contains a large automatic Preview and a separate Settings
  tab, so configuration fields are hidden while checking the captured image.

The Preview tab includes an `Enabled for scanning` checkbox that saves
immediately, so turning a filter on or off does not require opening Settings or
pressing Save. The selected-filter header also keeps a green `Enabled` status
badge for quick confirmation. Template health is shown as one compact line.

Exact template filenames and capture coordinates are hidden by default under
`Show advanced settings`. The automatic preview still shows the saved capture
area and clearly reports a missing or unreadable template.

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
3. Open `Filters`, select the game, then select the filter you want to configure.
   The saved capture area is previewed automatically.
4. If its template is missing or needs replacement, click `Make Template` or
   `Replace Template` and drag the yellow rectangle tightly around the
   battle text. Drag inside it to move it or use its handles to resize it.
5. Keep the default search padding or adjust it if the text can move slightly.
6. Save the template. The selected filter refreshes with its live match score;
   use `Refresh Preview` whenever you want another screenshot.
7. Enable the filter directly on the Preview tab when its preview is reliable.
8. Go to `Dashboard`, set the encounter increment, and click `Start`.
9. Click `Stop` when finished.
10. After finishing a shiny hunt, click `New Hunt...`, name the next hunt, and
    optionally mark the current one completed. Use the Hunt list to resume any
    saved hunt later.

## Interface Frames

The Settings tab includes a live Generation 3-style frame selector with all 20
frame types. Each option uses a pixel-art nine-slice asset so its original
corners and repeating edge details stay sharp without stretching across large
desktop panels. The selected frame is applied to the main sections throughout
the application: Scanner Controls, Counters, Live Details, Live Runtime Log,
the two Filters workspace panels, Display Setup, Last Preview, Template Preview,
and Logs and State. The choice is saved in `config.json` for the next launch.

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

## Games, Hunts, and Sessions

Progress is organized as `Game -> Hunt -> Session`. The all-time encounter and
catch counters never reset. Each hunt has its own encounter and catch totals,
and each session measures one stretch of play inside that hunt:

- `New Hunt...` saves the current hunt and starts a named hunt at zero
- marking a hunt completed never deletes it; selecting it later resumes it
- switching games restores that game's last selected hunt
- switching hunts restores its saved counter and starts a new session
- `New Session` starts another session inside the current hunt
- stopping and restarting scanning continues the current session
- every event stores game, hunt, session, hunt totals, and all-time totals

Events created before session tracking are retained as session 1. During the
one-time migration the original CSV and JSONL files are copied to
`output/migration_backups/session_identity_v1/`. The application then begins
session 2 at the existing lifetime counter without resetting encounters or
catches. The pre-migration `state.json` and `counter.txt` are retained in the
same versioned backup folder. Older configuration versions are backed up under
`output/migration_backups/config_<old>_to_v<new>/` before normalization.

On the first launch with hunt tracking, existing state and events are assigned
to `Original Hunt` at their current encounter number. Pre-migration state and
logs are retained under `output/migration_backups/hunt_identity_v1/`. No
encounter, catch, event, or old hunt is deleted by this migration.

## Configuration

The main local config file is:

- `config.json`
- `config.example.json`

It stores:

- active game
- encounter increment
- debug preferences
- per-filter templates, capture regions, thresholds, and cooldowns

Hunts are user progress rather than configuration, so they are stored in the
local `output/state.json` file.

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
