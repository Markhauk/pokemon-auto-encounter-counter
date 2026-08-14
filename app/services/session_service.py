from __future__ import annotations

from datetime import datetime, timezone

from app.core.event_logger import EventLogger, SessionMigrationResult
from app.core.models import HuntContext, SessionContext
from app.core.state_manager import StateManager

from .config_service import ConfigService


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class SessionService:
    """Coordinates the Game -> Hunt -> Session progress hierarchy."""

    def __init__(
        self,
        *,
        config_service: ConfigService,
        state_manager: StateManager,
        event_logger: EventLogger,
    ) -> None:
        self.config_service = config_service
        self.state_manager = state_manager
        self.event_logger = event_logger

    def initialize(self) -> tuple[SessionContext, SessionMigrationResult]:
        game_id, game_name = self._active_game()
        legacy_session_id = self._build_session_id(game_id, 1)
        migration = self.event_logger.migrate_legacy_session(
            game_id=game_id,
            game_name=game_name,
            session_id=legacy_session_id,
            session_number=1,
        )
        if migration.migrated_count:
            self.state_manager.backup_for_migration("session_identity_v1")

        hunt = self.state_manager.ensure_hunt_for_game(game_id=game_id, game_name=game_name)
        self.event_logger.migrate_legacy_hunt(
            hunt_id=hunt.hunt_id,
            hunt_name=hunt.hunt_name,
            hunt_started_at=hunt.hunt_started_at,
        )

        current = self.current_context()
        if current is None:
            first_live_session = max(
                hunt.session_number + 1,
                migration.max_session_number + 1 if migration.event_count else 1,
            )
            current = self._create_context(
                game_id=game_id,
                game_name=game_name,
                session_number=first_live_session,
                hunt=hunt,
            )
            self.state_manager.write_session_context(current)
        elif current.game_id != game_id or current.hunt_id != hunt.hunt_id:
            current = self.start_new_session(game_id=game_id, game_name=game_name)

        self.state_manager.write_obs_counter(current.hunt_encounter_count)
        return current, migration

    def current_context(self) -> SessionContext | None:
        state = self.state_manager.read_state_dict()
        session_id = str(state.get("session_id", "")).strip()
        if not session_id:
            return None
        return SessionContext(
            game_id=str(state.get("game_id", "")),
            game_name=str(state.get("game_name", "")),
            session_id=session_id,
            session_number=max(1, int(state.get("session_number", 1))),
            session_started_at=str(state.get("session_started_at", "")),
            session_start_counter=int(state.get("session_start_counter", 0)),
            session_encounter_count=max(0, int(state.get("session_encounter_count", 0))),
            hunt_id=str(state.get("hunt_id", "")),
            hunt_name=str(state.get("hunt_name", "")),
            hunt_status=str(state.get("hunt_status", "active")),
            hunt_started_at=str(state.get("hunt_started_at", "")),
            hunt_completed_at=str(state.get("hunt_completed_at", "")),
            hunt_encounter_count=max(0, int(state.get("hunt_encounter_count", 0))),
            hunt_catch_counter=max(0, int(state.get("hunt_catch_counter", 0))),
            hunt_last_catch_at_encounter=max(
                0, int(state.get("hunt_last_catch_at_encounter", 0))
            ),
            hunt_encounters_since_last_catch=max(
                0, int(state.get("hunt_encounters_since_last_catch", 0))
            ),
            session_start_hunt_counter=max(
                0, int(state.get("session_start_hunt_counter", 0))
            ),
        )

    def ensure_for_active_game(self) -> SessionContext:
        game_id, game_name = self._active_game()
        hunt = self.state_manager.ensure_hunt_for_game(game_id=game_id, game_name=game_name)
        current = self.current_context()
        if current is not None and current.game_id == game_id and current.hunt_id == hunt.hunt_id:
            return current
        return self.start_new_session(game_id=game_id, game_name=game_name)

    def list_hunts(self, *, game_id: str | None = None) -> list[HuntContext]:
        resolved_game_id = game_id or self._active_game()[0]
        return self.state_manager.list_hunts(game_id=resolved_game_id)

    def active_hunt(self) -> HuntContext:
        game_id, game_name = self._active_game()
        return self.state_manager.ensure_hunt_for_game(game_id=game_id, game_name=game_name)

    def start_new_hunt(self, *, name: str, complete_current: bool) -> SessionContext:
        game_id, game_name = self._active_game()
        hunt = self.state_manager.create_hunt(
            game_id=game_id,
            game_name=game_name,
            name=name,
            complete_current=complete_current,
        )
        context = self._create_context(
            game_id=game_id,
            game_name=game_name,
            session_number=1,
            hunt=hunt,
        )
        self.state_manager.write_session_context(context)
        return context

    def select_hunt(self, hunt_id: str) -> SessionContext:
        game_id, game_name = self._active_game()
        current = self.current_context()
        if current is not None and current.game_id == game_id and current.hunt_id == hunt_id:
            return current
        hunt = self.state_manager.select_hunt(hunt_id=hunt_id, game_id=game_id)
        context = self._create_context(
            game_id=game_id,
            game_name=game_name,
            session_number=hunt.session_number + 1,
            hunt=hunt,
        )
        self.state_manager.write_session_context(context)
        return context

    def start_new_session(
        self,
        *,
        game_id: str | None = None,
        game_name: str | None = None,
    ) -> SessionContext:
        active_game_id, active_game_name = self._active_game()
        resolved_game_id = game_id or active_game_id
        resolved_game_name = game_name or active_game_name
        hunt = self.state_manager.ensure_hunt_for_game(
            game_id=resolved_game_id,
            game_name=resolved_game_name,
        )
        next_number = hunt.session_number + 1
        context = self._create_context(
            game_id=resolved_game_id,
            game_name=resolved_game_name,
            session_number=next_number,
            hunt=hunt,
        )
        self.state_manager.write_session_context(context)
        return context

    def _active_game(self) -> tuple[str, str]:
        game_id = self.config_service.get_active_game_id()
        game = self.config_service.get_game(game_id)
        return game_id, game.name if game is not None else game_id

    def _create_context(
        self,
        *,
        game_id: str,
        game_name: str,
        session_number: int,
        hunt: HuntContext,
    ) -> SessionContext:
        counter = self.state_manager.read_counter()
        return SessionContext(
            game_id=game_id,
            game_name=game_name,
            session_id=self._build_session_id(hunt.hunt_id, session_number),
            session_number=session_number,
            session_started_at=_now_iso(),
            session_start_counter=counter,
            session_encounter_count=0,
            hunt_id=hunt.hunt_id,
            hunt_name=hunt.hunt_name,
            hunt_status="active",
            hunt_started_at=hunt.hunt_started_at,
            hunt_completed_at="",
            hunt_encounter_count=hunt.hunt_encounter_count,
            hunt_catch_counter=hunt.hunt_catch_counter,
            hunt_last_catch_at_encounter=hunt.hunt_last_catch_at_encounter,
            hunt_encounters_since_last_catch=hunt.hunt_encounters_since_last_catch,
            session_start_hunt_counter=hunt.hunt_encounter_count,
        )

    @staticmethod
    def _build_session_id(parent_id: str, session_number: int) -> str:
        return f"{parent_id}-session-{max(1, int(session_number)):04d}"
