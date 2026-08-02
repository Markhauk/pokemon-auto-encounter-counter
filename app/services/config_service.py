from __future__ import annotations

import copy
import json
from pathlib import Path

from app.core.capture import get_physical_monitors
from app.core.constants import POST_DETECTION_COOLDOWN_SECONDS
from app.core.display import (
    build_default_display_setup,
    normalize_display_setup,
    resolve_capture_monitor,
)
from app.core.filters import (
    DEFAULT_GAME_ID,
    FilterDefinition,
    GameDefinition,
    build_builtin_filters,
    build_builtin_games,
    get_filter_game_id,
    normalize_filter_definitions,
    normalize_game_definitions,
    normalize_game_id,
    slugify_filter_name,
    slugify_game_name,
)
from app.core.file_io import atomic_write_text
from app.core.interface import DEFAULT_FRAME_TYPE, normalize_frame_type
from app.core.modes import get_default_capture_region, list_modes
from app.core.paths import CONFIG_FILE


CONFIG_VERSION = 8


def _read_physical_monitors() -> list[dict[str, int]]:
    try:
        return get_physical_monitors()
    except Exception:
        return []


def _resolve_capture_monitor_or_none(
    display_setup: dict[str, object],
    *,
    physical_monitors: list[dict[str, int]] | None = None,
) -> dict[str, int] | None:
    physical_monitors = physical_monitors or _read_physical_monitors()
    if not physical_monitors:
        return None
    try:
        return resolve_capture_monitor(display_setup=display_setup, physical_monitors=physical_monitors)
    except ValueError:
        return dict(physical_monitors[0])


def build_default_config() -> dict[str, object]:
    physical_monitors = _read_physical_monitors()
    display_setup = build_default_display_setup(physical_monitors=physical_monitors)
    capture_monitor = _resolve_capture_monitor_or_none(
        display_setup,
        physical_monitors=physical_monitors,
    )
    return {
        "version": CONFIG_VERSION,
        "last_selected_mode": "filters",
        "active_game_id": DEFAULT_GAME_ID,
        "encounter_increment": 1,
        "debug": {
            "save_debug_frames": False,
            "verbose_debug": False,
        },
        "interface": {
            "frame_type": DEFAULT_FRAME_TYPE,
        },
        "display_setup": display_setup,
        "games": [
            game_definition.as_dict()
            for game_definition in build_builtin_games()
        ],
        "filters": [
            filter_definition.as_dict()
            for filter_definition in build_builtin_filters(capture_monitor=capture_monitor)
        ],
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
                original_text = self.config_path.read_text(encoding="utf-8")
                loaded = json.loads(original_text)
                if isinstance(loaded, dict):
                    if loaded.get("version") != CONFIG_VERSION:
                        self._backup_for_migration(
                            original_text,
                            source_version=loaded.get("version"),
                        )
                    config = self._merge_dicts(config, loaded)
            except (json.JSONDecodeError, OSError):
                pass

        physical_monitors = self.get_physical_monitors()

        config["version"] = CONFIG_VERSION
        interface = config.get("interface", {})
        if not isinstance(interface, dict):
            interface = {}
        config["interface"] = {
            "frame_type": normalize_frame_type(interface.get("frame_type")),
        }
        config["display_setup"] = normalize_display_setup(
            config.get("display_setup"),
            physical_monitors=physical_monitors,
        )
        capture_monitor = self.get_capture_monitor(
            display_setup=config["display_setup"],  # type: ignore[arg-type]
            physical_monitors=physical_monitors,
        )
        config["games"] = [
            game_definition.as_dict()
            for game_definition in normalize_game_definitions(config.get("games"))
        ]
        legacy_mode_regions = self._extract_legacy_mode_regions(config.get("modes"))
        normalized_filters = normalize_filter_definitions(
            config.get("filters"),
            capture_monitor=capture_monitor,
            legacy_mode_regions=legacy_mode_regions,
        )
        existing_games = normalize_game_definitions(config.get("games"))
        existing_game_ids = {game.id for game in existing_games}
        missing_game_ids = sorted({get_filter_game_id(filter_definition) for filter_definition in normalized_filters} - existing_game_ids)
        for missing_game_id in missing_game_ids:
            existing_games.append(
                GameDefinition(
                    id=missing_game_id,
                    name=missing_game_id,
                    built_in=False,
                    description="Recovered from filter metadata.",
                )
            )

        config["games"] = [game_definition.as_dict() for game_definition in existing_games]
        valid_game_ids = {game.id for game in existing_games}
        active_game_id = normalize_game_id(config.get("active_game_id", DEFAULT_GAME_ID))
        if active_game_id not in valid_game_ids:
            active_game_id = existing_games[0].id if existing_games else DEFAULT_GAME_ID
        config["active_game_id"] = active_game_id
        config["filters"] = [filter_definition.as_dict() for filter_definition in normalized_filters]

        self._config = config
        self.save(config)
        return copy.deepcopy(config)

    def save(self, config: dict[str, object] | None = None) -> dict[str, object]:
        current = copy.deepcopy(config or self.load())
        current.pop("modes", None)
        atomic_write_text(self.config_path, json.dumps(current, indent=2))
        self._config = current
        return copy.deepcopy(current)

    def get_mode_region(self, mode_key: str) -> dict[str, int]:
        legacy_mapping = {
            "random_grass": "fled",
            "safari_zone": "wild",
            "egg_mode": "huh",
        }
        filter_id = legacy_mapping.get(mode_key)
        if filter_id:
            filter_definition = self.get_filter(filter_id)
            if filter_definition is not None:
                return dict(filter_definition.capture_region)
        return get_default_capture_region(mode_key, monitor=self.get_capture_monitor())

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
            get_default_capture_region(mode_key, monitor=self.get_capture_monitor()),
        )

    def get_display_setup(self) -> dict[str, object]:
        config = self.load()
        return normalize_display_setup(
            config.get("display_setup"),
            physical_monitors=self.get_physical_monitors(),
        )

    def get_physical_monitors(self) -> list[dict[str, int]]:
        return _read_physical_monitors()

    def get_capture_monitor(
        self,
        *,
        display_setup: dict[str, object] | None = None,
        physical_monitors: list[dict[str, int]] | None = None,
    ) -> dict[str, int] | None:
        active_physical_monitors = physical_monitors or self.get_physical_monitors()
        active_display_setup = normalize_display_setup(
            display_setup if display_setup is not None else self.get_display_setup(),
            physical_monitors=active_physical_monitors,
        )
        return _resolve_capture_monitor_or_none(
            active_display_setup,
            physical_monitors=active_physical_monitors,
        )

    def get_games(self) -> list[GameDefinition]:
        config = self.load()
        return normalize_game_definitions(config.get("games"))

    def get_game(self, game_id: str) -> GameDefinition | None:
        normalized_game_id = slugify_game_name(game_id)
        for game_definition in self.get_games():
            if game_definition.id == normalized_game_id:
                return game_definition
        return None

    def get_active_game_id(self) -> str:
        config = self.load()
        configured_game_id = slugify_game_name(str(config.get("active_game_id", DEFAULT_GAME_ID)))
        if self.get_game(configured_game_id) is not None:
            return configured_game_id
        return DEFAULT_GAME_ID

    def set_active_game_id(self, game_id: str) -> dict[str, object]:
        config = self.load()
        normalized_game_id = normalize_game_id(game_id)
        config["active_game_id"] = normalized_game_id if self.get_game(normalized_game_id) is not None else DEFAULT_GAME_ID
        return self.save(config)

    def set_display_setup(self, display_setup: dict[str, object]) -> dict[str, object]:
        config = self.load()
        config["display_setup"] = normalize_display_setup(
            display_setup,
            physical_monitors=self.get_physical_monitors(),
        )
        return self.save(config)

    def save_capture_settings(
        self,
        *,
        display_setup: dict[str, object],
        filters: list[FilterDefinition] | None = None,
        regions: dict[str, dict[str, int]] | None = None,
    ) -> dict[str, object]:
        config = self.load()
        config["display_setup"] = normalize_display_setup(
            display_setup,
            physical_monitors=self.get_physical_monitors(),
        )

        active_filters = filters or self.get_filters()
        region_overrides = regions or {}
        rewritten_filters: list[dict[str, object]] = []
        for filter_definition in active_filters:
            capture_region = region_overrides.get(filter_definition.id, filter_definition.capture_region)
            rewritten_filters.append(
                FilterDefinition(
                    id=filter_definition.id,
                    name=filter_definition.name,
                    enabled=filter_definition.enabled,
                    event_type=filter_definition.event_type,
                    template_path=filter_definition.template_path,
                    capture_region=dict(capture_region),
                    threshold=filter_definition.threshold,
                    cooldown_seconds=filter_definition.cooldown_seconds,
                    built_in=filter_definition.built_in,
                    description=filter_definition.description,
                    metadata=dict(filter_definition.metadata),
                ).as_dict()
            )

        config["filters"] = rewritten_filters

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

    def get_interface_frame_type(self) -> int:
        config = self.load()
        interface = config.get("interface", {})
        if not isinstance(interface, dict):
            return DEFAULT_FRAME_TYPE
        return normalize_frame_type(interface.get("frame_type"))

    def set_interface_frame_type(self, frame_type: object) -> dict[str, object]:
        config = self.load()
        config["interface"] = {
            "frame_type": normalize_frame_type(frame_type),
        }
        return self.save(config)

    def read_text(self) -> str:
        if not self.config_path.exists():
            self.save(build_default_config())
        return self.config_path.read_text(encoding="utf-8")

    def get_filters(self, *, game_id: str | None = None) -> list[FilterDefinition]:
        config = self.load()
        legacy_mode_regions = self._extract_legacy_mode_regions(config.get("modes"))
        filters = normalize_filter_definitions(
            config.get("filters"),
            capture_monitor=self.get_capture_monitor(),
            legacy_mode_regions=legacy_mode_regions,
        )
        if game_id is None:
            return filters

        normalized_game_id = slugify_game_name(game_id)
        return [
            filter_definition
            for filter_definition in filters
            if get_filter_game_id(filter_definition) == normalized_game_id
        ]

    def get_filter(self, filter_id: str) -> FilterDefinition | None:
        for filter_definition in self.get_filters():
            if filter_definition.id == filter_id:
                return filter_definition
        return None

    def save_filters(self, filters: list[FilterDefinition]) -> dict[str, object]:
        config = self.load()
        config["filters"] = [filter_definition.as_dict() for filter_definition in filters]
        return self.save(config)

    def save_games(self, games: list[GameDefinition]) -> dict[str, object]:
        config = self.load()
        config["games"] = [game_definition.as_dict() for game_definition in games]
        return self.save(config)

    def generate_filter_id(self, preferred_name: str) -> str:
        base = slugify_filter_name(preferred_name)
        existing_ids = {filter_definition.id for filter_definition in self.get_filters()}
        if base not in existing_ids:
            return base

        suffix = 2
        while f"{base}_{suffix}" in existing_ids:
            suffix += 1
        return f"{base}_{suffix}"

    def generate_game_id(self, preferred_name: str) -> str:
        base = slugify_game_name(preferred_name)
        existing_ids = {game_definition.id for game_definition in self.get_games()}
        if base not in existing_ids:
            return base

        suffix = 2
        while f"{base}_{suffix}" in existing_ids:
            suffix += 1
        return f"{base}_{suffix}"

    def create_game(self, *, name: str | None = None) -> GameDefinition:
        games = self.get_games()
        next_name = name or f"New Game {len(games) + 1}"
        game_definition = GameDefinition(
            id=self.generate_game_id(next_name),
            name=next_name,
            built_in=False,
            description="Custom game filter group.",
        )
        games.append(game_definition)

        config = self.load()
        config["games"] = [game.as_dict() for game in games]
        config["active_game_id"] = game_definition.id
        self.save(config)
        return game_definition

    def delete_game(self, game_id: str) -> dict[str, object]:
        normalized_game_id = slugify_game_name(game_id)
        games = self.get_games()
        target_game = next((game for game in games if game.id == normalized_game_id), None)
        if target_game is None:
            return self.load()
        if target_game.built_in:
            raise ValueError("Built-in games cannot be deleted.")

        rewritten_games = [game for game in games if game.id != normalized_game_id]
        rewritten_filters = [
            filter_definition
            for filter_definition in self.get_filters()
            if get_filter_game_id(filter_definition) != normalized_game_id
        ]

        config = self.load()
        config["games"] = [game.as_dict() for game in rewritten_games]
        config["filters"] = [filter_definition.as_dict() for filter_definition in rewritten_filters]

        active_game_id = str(config.get("active_game_id", DEFAULT_GAME_ID))
        if active_game_id == normalized_game_id:
            next_game = rewritten_games[0] if rewritten_games else build_builtin_games()[0]
            config["active_game_id"] = next_game.id

        return self.save(config)

    def create_filter(self, *, name: str | None = None, game_id: str | None = None) -> FilterDefinition:
        filters = self.get_filters()
        next_name = name or f"New Filter {len(filters) + 1}"
        filter_id = self.generate_filter_id(next_name)
        target_game_id = normalize_game_id(game_id or self.get_active_game_id())
        if self.get_game(target_game_id) is None:
            target_game_id = DEFAULT_GAME_ID
        filter_definition = FilterDefinition(
            id=filter_id,
            name=next_name,
            enabled=True,
            event_type="info",
            template_path=f"{filter_id}.png",
            capture_region=get_default_capture_region("random_grass", monitor=self.get_capture_monitor()),
            threshold=0.85,
            cooldown_seconds=POST_DETECTION_COOLDOWN_SECONDS,
            built_in=False,
            description="Custom filter.",
            metadata={"game_id": target_game_id},
        )
        filters.append(filter_definition)
        self.save_filters(filters)
        return filter_definition

    def delete_filter(self, filter_id: str) -> dict[str, object]:
        filters = [filter_definition for filter_definition in self.get_filters() if filter_definition.id != filter_id]
        return self.save_filters(filters)

    def replace_filter(self, updated_filter: FilterDefinition) -> dict[str, object]:
        filters = self.get_filters()
        rewritten_filters = [
            updated_filter if filter_definition.id == updated_filter.id else filter_definition
            for filter_definition in filters
        ]
        return self.save_filters(rewritten_filters)

    def _extract_legacy_mode_regions(self, raw_modes: object) -> dict[str, dict[str, int]]:
        if not isinstance(raw_modes, dict):
            return {}

        extracted: dict[str, dict[str, int]] = {}
        for mode in list_modes(include_unimplemented=True):
            mode_entry = raw_modes.get(mode.key)
            if not isinstance(mode_entry, dict):
                continue
            capture_region = mode_entry.get("capture_region")
            if not isinstance(capture_region, dict):
                continue
            extracted[mode.key] = {
                "left": int(capture_region.get("left", 0)),
                "top": int(capture_region.get("top", 0)),
                "width": int(capture_region.get("width", 1)),
                "height": int(capture_region.get("height", 1)),
            }
        return extracted

    def _merge_dicts(self, base: dict[str, object], incoming: dict[str, object]) -> dict[str, object]:
        merged = copy.deepcopy(base)
        for key, value in incoming.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = self._merge_dicts(merged[key], value)  # type: ignore[arg-type]
            else:
                merged[key] = value
        return merged

    def _backup_for_migration(self, original_text: str, *, source_version: object) -> Path:
        try:
            source_label = f"v{int(source_version)}"
        except (TypeError, ValueError):
            source_label = "legacy"
        backup_dir = (
            self.config_path.parent
            / "output"
            / "migration_backups"
            / f"config_{source_label}_to_v{CONFIG_VERSION}"
        )
        backup_file = backup_dir / self.config_path.name
        if not backup_file.exists():
            atomic_write_text(backup_file, original_text)
        return backup_file
