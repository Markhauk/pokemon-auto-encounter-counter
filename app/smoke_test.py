from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path


def run_smoke_test() -> int:
    """Validate packaged resources and writable persistence without screen capture."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    try:
        from PySide6.QtGui import QImage
        from PySide6.QtWidgets import QApplication, QLabel

        from app.core.event_logger import EventLogger
        from app.core.file_io import atomic_write_text
        from app.core.interface import INTERFACE_FRAME_DEFINITIONS
        from app.core.models import SessionContext
        from app.core.paths import INTERFACE_FRAMES_DIR
        from app.core.templates import TemplateManager
        from app.services.config_service import ConfigService
        from app.core.state_manager import StateManager

        application = QApplication.instance() or QApplication(["PokemonEncounterCounter"])
        application.setApplicationName("Pokemon Encounter Counter Smoke Test")

        probe_widget = QLabel("Qt smoke test")
        probe_widget.resize(160, 40)
        application.processEvents()

        template_manager = TemplateManager()
        required_templates = ("got_away.png", "gotcha.png", "wild.png")
        for template_name in required_templates:
            template_manager.load_grayscale(template_name)

        for definition in INTERFACE_FRAME_DEFINITIONS:
            frame_asset = INTERFACE_FRAMES_DIR / definition.asset_filename
            image = QImage(str(frame_asset))
            if image.isNull() or image.width() != 40 or image.height() != 40:
                raise RuntimeError(f"Interface frame asset is missing or invalid: {frame_asset}")

        with tempfile.TemporaryDirectory(prefix="pokemon-counter-smoke-") as temp_dir:
            root = Path(temp_dir)
            output_dir = root / "output"
            config_service = ConfigService(config_path=root / "config.json")
            config = config_service.load()
            if config_service.get_filter("huh") is None:
                raise RuntimeError("The Egg/Huh filter is missing from the default configuration.")

            state_manager = StateManager(
                counter_file=output_dir / "counter.txt",
                state_file=output_dir / "state.json",
                output_dir=output_dir,
                templates_dir=root / "templates",
            )
            state_manager.ensure_directories()
            state_manager.write_session_context(
                SessionContext(
                    game_id="smoke_test",
                    game_name="Smoke Test",
                    session_id="smoke_test-session-0001",
                    session_number=1,
                    session_started_at="smoke-test",
                    session_start_counter=0,
                )
            )

            event_logger = EventLogger(
                csv_file=output_dir / "encounter_log.csv",
                jsonl_file=output_dir / "event_log.jsonl",
            )
            event_logger.append(
                {
                    "timestamp": "smoke-test",
                    "event": "smoke_test",
                    "game_id": "smoke_test",
                    "session_id": "smoke_test-session-0001",
                }
            )
            if len(event_logger.read_recent_events(limit=1)) != 1:
                raise RuntimeError("The event log could not be read back.")

            probe_file = output_dir / "atomic-write-probe.txt"
            atomic_write_text(probe_file, "ok")
            if probe_file.read_text(encoding="utf-8") != "ok":
                raise RuntimeError("The temporary output directory is not writable.")

            summary = {
                "status": "ok",
                "qt_platform": os.environ["QT_QPA_PLATFORM"],
                "config_version": config.get("version"),
                "templates_checked": list(required_templates),
                "interface_frames_checked": len(INTERFACE_FRAME_DEFINITIONS),
            }

        probe_widget.close()
        print(json.dumps(summary))
        return 0
    except Exception as exc:
        print(f"Smoke test failed: {exc}", file=sys.stderr)
        return 1
