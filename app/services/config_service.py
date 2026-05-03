from __future__ import annotations

import copy
import json
from pathlib import Path

from app.core.display import (
    build_default_display_setup,
    get_capture_resolution_preset,
    normalize_display_setup,
)
from app.core.modes import get_default_capture_region, list_modes
from app.core.paths import CONFIG_FILE


def build_default_config() -> dict[str, object]:
    display_setup = build_default_display_setup()
    resolution_preset = get_capture_resolution_preset(display_setup)
    return {
        "version": 3,
        "last_selected_mode": "random_grass",
        "encounter_increment": 1,
        "debug": {
            "save_debug_frames": False,
            "verbose_debug": False,
        },
        "display_setup": display_setup,
        "modes": {
            mode.key: {
                "capture_region": get_default_capture_region(mode.key, resolution_preset=resolution_preset),
            }
            for mode in list_modes(include_unimplemented=True)
        },
    }


class ConfigService:
    def __init__(self, config_path: Path = CONFIG_FILE) -> None:
        self.config_path = config_path
        self._config: dict[str, object] | None = None

    def load(self) -> dict[str, object]:
        if self._config is not None:
            return copy.deepcopy(self._config)

        config = build_default_config()
        if self.config_path.exists():
            try:
                loaded = json.loads(self.config_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    config = self._merge_dicts(config, loaded)
            except (json.JSONDecodeError, OSError):
                pass

        config["version"] = 3
        config["display_setup"] = normalize_display_setup(config.get("display_setup"))

        self._config = config
        self.save(config)
        return copy.deepcopy(config)

    def save(self, config: dict[str, object] | None = None) -> dict[str, object]:
        current = copy.deepcopy(config or self.load())
        self.config_path.write_text(json.dumps(current, indent=2), encoding="utf-8")
        self._config = current
        return copy.deepcopy(current)

    def get_mode_region(self, mode_key: str) -> dict[str, int]:
        config = self.load()
        resolution_preset = self.get_capture_resolution_preset()
        modes = config.get("modes", {})
        if isinstance(modes, dict):
            mode_entry = modes.get(mode_key, {})
            if isinstance(mode_entry, dict):
                capture_region = mode_entry.get("capture_region", {})
                if isinstance(capture_region, dict):
                    return {
                        "left": int(capture_region.get("left", 0)),
                        "top": int(capture_region.get("top", 0)),
                        "width": int(capture_region.get("width", 0)),
                        "height": int(capture_region.get("height", 0)),
                    }
        return get_default_capture_region(mode_key, resolution_preset=resolution_preset)

    def set_mode_region(self, mode_key: str, region: dict[str, int]) -> dict[str, object]:
        config = self.load()
        modes = config.setdefault("modes", {})
        if not isinstance(modes, dict):
            modes = {}
            config["modes"] = modes
        modes[mode_key] = {"capture_region": dict(region)}
        return self.save(config)

    def restore_default_region(self, mode_key: str) -> dict[str, object]:
        return self.set_mode_region(
            mode_key,
            get_default_capture_region(mode_key, resolution_preset=self.get_capture_resolution_preset()),
        )

    def get_display_setup(self) -> dict[str, object]:
        config = self.load()
        return normalize_display_setup(config.get("display_setup"))

    def set_display_setup(self, display_setup: dict[str, object]) -> dict[str, object]:
        config = self.load()
        config["display_setup"] = normalize_display_setup(display_setup)
        return self.save(config)

    def get_resolution_preset(self) -> str:
        display_setup = self.get_display_setup()
        return str(display_setup["resolution_preset"])

    def get_capture_resolution_preset(self) -> str:
        return get_capture_resolution_preset(self.get_display_setup())

    def save_capture_settings(
        self,
        *,
        display_setup: dict[str, object],
        regions: dict[str, dict[str, int]],
    ) -> dict[str, object]:
        config = self.load()
        config["display_setup"] = normalize_display_setup(display_setup)

        modes = config.setdefault("modes", {})
        if not isinstance(modes, dict):
            modes = {}
            config["modes"] = modes

        for mode_key, region in regions.items():
            modes[mode_key] = {"capture_region": dict(region)}

        return self.save(config)

    def get_last_selected_mode(self) -> str:
        config = self.load()
        return str(config.get("last_selected_mode", "random_grass"))

    def set_last_selected_mode(self, mode_key: str) -> dict[str, object]:
        config = self.load()
        config["last_selected_mode"] = mode_key
        return self.save(config)

    def get_encounter_increment(self) -> int:
        config = self.load()
        return max(1, int(config.get("encounter_increment", 1)))

    def set_encounter_increment(self, value: int) -> dict[str, object]:
        config = self.load()
        config["encounter_increment"] = max(1, int(value))
        return self.save(config)

    def get_debug_preferences(self) -> dict[str, bool]:
        config = self.load()
        debug = config.get("debug", {})
        if not isinstance(debug, dict):
            debug = {}
        return {
            "save_debug_frames": bool(debug.get("save_debug_frames", False)),
            "verbose_debug": bool(debug.get("verbose_debug", False)),
        }

    def set_debug_preferences(
        self,
        *,
        save_debug_frames: bool,
        verbose_debug: bool,
    ) -> dict[str, object]:
        config = self.load()
        config["debug"] = {
            "save_debug_frames": bool(save_debug_frames),
            "verbose_debug": bool(verbose_debug),
        }
        return self.save(config)

    def read_text(self) -> str:
        if not self.config_path.exists():
            self.save(build_default_config())
        return self.config_path.read_text(encoding="utf-8")

    def _merge_dicts(self, base: dict[str, object], incoming: dict[str, object]) -> dict[str, object]:
        merged = copy.deepcopy(base)
        for key, value in incoming.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = self._merge_dicts(merged[key], value)  # type: ignore[arg-type]
            else:
                merged[key] = value
        return merged
