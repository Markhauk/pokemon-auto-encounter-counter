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
  Detects:
  - `templates/huh.png`

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
- `output/encounter_counter.lock`

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
|   |   |-- state_manager.py
|   |   `-- templates.py
|   |-- gui/
|   |   |-- capture_settings_tab.py
|   |   |-- dashboard_tab.py
|   |   |-- logs_tab.py
|   |   |-- main_window.py
|   |   `-- templates_tab.py
|   |-- services/
|   |   |-- app_controller.py
|   |   |-- config_service.py
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

- mode selection
- encounter increment
- start and stop controls
- live counters
- status display
- live runtime log

### Capture Settings

Used for:

- editing per-mode screen regions
- testing screenshots
- saving settings to `config.json`
- restoring default regions

### Templates

Used for:

- checking which required template files are present
- identifying missing or unreadable templates
- previewing template images

### Logs / State

Used for:

- viewing recent event history
- viewing current local state
- locating the output folder

## Typical User Flow

1. Open the desktop application.
2. Go to `Capture Settings`.
3. Adjust the capture region for your mode if needed.
4. Run `Test Screenshot` and confirm the preview looks correct.
5. Save settings.
6. Go to `Dashboard`.
7. Choose the mode.
8. Set the encounter increment.
9. Click `Start`.
10. Click `Stop` when finished.

## Templates

Current required templates by mode:

- Random grass encounter:
  - `got_away.png`
  - `gotcha.png`
- Safari zone:
  - `wild.png`
- Egg mode:
  - `huh.png`

If a required template is missing or unreadable, the application surfaces that in the Templates tab and through runtime error handling.

## Configuration

The main local config file is:

- `config.json`
- `config.example.json`

It stores:

- last selected mode
- encounter increment
- debug preferences
- per-mode capture regions

Notes:

- `config.json` is local machine-specific and is intended to stay uncommitted
- `config.example.json` is the safe committed reference for default app settings

## Known Limitations

- This is still an **Alpha** release.
- `Soft reset` is not implemented yet.
- `Egg mode` is wired into the application structure, but requires `templates/huh.png` to be present.
- There is no interactive drag-to-select region picker yet.
- There is no cloud sync, OCR, or overlay tool in this version.

## Development Notes

The current design is intended to make future expansion easier.

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

The packaged output is written to:

```text
dist/PokemonEncounterCounter/
```

Notes:

- the build uses a one-folder layout so bundled templates live next to the executable
- built-in templates are bundled automatically
- `output/` is created on first run
- `config.json` is created on first run if it does not already exist

## License

No license file is currently included in this repository.
