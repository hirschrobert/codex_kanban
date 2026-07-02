from __future__ import annotations

import sqlite3
import threading
from contextlib import AbstractContextManager
from datetime import datetime
from pathlib import Path
from typing import Any


class StoreMixinContract:
    """Type-only contract for the composed store mixins.

    Runtime mixins inherit an empty stand-in instead; this contract exists so
    Pyright can see the helpers supplied by sibling mixins and KanbanStore.
    """

    db_path: Path
    preferred_board_slug: str | None
    _lock: threading.RLock

    def _active_project_for_board(
        self,
        conn: sqlite3.Connection,
        board_slug: str,
    ) -> dict[str, Any] | None: ...

    def _assert_dependencies_allow_status(
        self,
        conn: sqlite3.Connection,
        card_id: int,
        status: str,
    ) -> None: ...

    def _attach_card_comments(
        self,
        conn: sqlite3.Connection,
        cards: list[dict[str, Any]],
    ) -> None: ...

    def _attach_affected_project_paths(
        self,
        cards: list[dict[str, Any]],
        active_project: dict[str, Any] | None,
    ) -> None: ...

    def _attach_dependency_links(
        self,
        conn: sqlite3.Connection,
        cards: list[dict[str, Any]],
    ) -> None: ...

    def _backfill_card_links(self, conn: sqlite3.Connection) -> None: ...

    def _board_is_removed_project(self, conn: sqlite3.Connection, board_slug: str) -> bool: ...

    @staticmethod
    def _bool_payload(value: Any) -> bool: ...

    def _card_comment_from_row(self, row: sqlite3.Row | None) -> dict[str, Any]: ...

    def _card_from_row(self, row: sqlite3.Row | None) -> dict[str, Any]: ...

    def _card_id_on_board(
        self,
        conn: sqlite3.Connection,
        card_id: int,
        *,
        board_slug: str,
    ) -> int: ...

    def _card_prefix(self, conn: sqlite3.Connection, board_slug: str) -> str: ...

    def _cards_with_coordination(
        self,
        cards: list[dict[str, Any]],
        participants: list[dict[str, Any]],
    ) -> list[dict[str, Any]]: ...

    @staticmethod
    def _clean_text(value: Any) -> str | None: ...

    def _connect(self) -> AbstractContextManager[sqlite3.Connection]: ...

    def _default_board_slug(self, conn: sqlite3.Connection) -> str: ...

    def _enforce_agent_limits(
        self,
        conn: sqlite3.Connection,
        *,
        participant_id: str,
        display_name: str,
        kind: str,
        status: str,
        board_slug: str,
    ) -> None: ...

    @staticmethod
    def _ensure_column(
        conn: sqlite3.Connection,
        table: str,
        column: str,
        definition: str,
    ) -> None: ...

    def _event_from_row(self, row: sqlite3.Row | None) -> dict[str, Any]: ...

    def _first_repeat_run_at(
        self,
        cadence: Any,
        repeat_time: Any,
        timezone_name: Any,
        *,
        now: datetime | None = None,
    ) -> str | None: ...

    @staticmethod
    def _format_utc(value: datetime) -> str: ...

    def _list_projects(
        self,
        conn: sqlite3.Connection,
        *,
        include_removed: bool,
    ) -> list[dict[str, Any]]: ...

    @staticmethod
    def _one(
        conn: sqlite3.Connection,
        query: str,
        params: tuple[Any, ...] = (),
    ) -> sqlite3.Row | None: ...

    def _open_connection(self) -> sqlite3.Connection: ...

    def _participant_board_slug(
        self,
        conn: sqlite3.Connection,
        payload: dict[str, Any],
        existing: sqlite3.Row | None,
    ) -> str: ...

    def _participant_from_row(
        self,
        row: sqlite3.Row | dict[str, Any] | None,
        *,
        now: datetime,
    ) -> dict[str, Any]: ...

    @staticmethod
    def _payload_has_link_updates(payload: dict[str, Any]) -> bool: ...

    @staticmethod
    def _payload_references_card(payload: dict[str, Any]) -> bool: ...

    def _project_from_row(self, row: sqlite3.Row | None) -> dict[str, Any] | None: ...

    @staticmethod
    def _project_int_setting(
        payload: dict[str, Any],
        key: str,
        existing: Any,
        default: int,
    ) -> int: ...

    def _repeat_settings_from_payload(
        self,
        payload: dict[str, Any],
        *,
        target_branch: str | None,
    ) -> tuple[str, str, str]: ...

    def _resolve_card_id(
        self,
        conn: sqlite3.Connection,
        payload: dict[str, Any],
        *,
        board_slug: str,
        required: bool = False,
    ) -> int | None: ...

    def _sync_card_links(
        self,
        conn: sqlite3.Connection,
        card_id: int,
        payload: dict[str, Any],
        *,
        creating: bool = False,
    ) -> None: ...

    def _validate_assignee(
        self,
        conn: sqlite3.Connection,
        assignee_id: str | None,
        *,
        board_slug: str,
    ) -> str | None: ...

    def _validate_owner(
        self,
        conn: sqlite3.Connection,
        owner_id: str | None,
        *,
        board_slug: str,
        current_owner_id: str | None = None,
    ) -> str | None: ...

    @staticmethod
    def _validate_participant(kind: str, status: str) -> None: ...

    def _validate_participant_scope(
        self,
        conn: sqlite3.Connection,
        participant_id: str,
        board_slug: str,
        *,
        kind: str | None = None,
        existing: sqlite3.Row | None = None,
        action: str,
    ) -> None: ...

    @staticmethod
    def _validate_priority(priority: str) -> None: ...

    @staticmethod
    def _validate_repeat_cadence(value: Any) -> str: ...

    def _validate_repeat_project_gate(
        self,
        conn: sqlite3.Connection,
        board_slug: str,
        cadence: Any,
    ) -> None: ...

    @staticmethod
    def _validate_repeat_target_branch(cadence: Any, target_branch: Any) -> None: ...

    @staticmethod
    def _validate_repeat_time(value: Any) -> str: ...

    @staticmethod
    def _validate_repeat_timezone(value: Any) -> str: ...

    @staticmethod
    def _validate_status(status: str) -> None: ...

    def add_card_comment(self, card_id: int, payload: dict[str, Any]) -> dict[str, Any]: ...

    def create_card(self, payload: dict[str, Any]) -> dict[str, Any]: ...

    def create_event(self, payload: dict[str, Any]) -> dict[str, Any]: ...

    def ensure_board(
        self,
        slug: str,
        title: str | None = None,
        *,
        conn: sqlite3.Connection | None = None,
    ) -> None: ...

    def get_card(self, card_id: int) -> dict[str, Any] | None: ...

    def project_for_path(self, path: str | Path) -> dict[str, Any] | None: ...

    def resolve_project_for_paths(self, paths: list[str | Path]) -> dict[str, Any]: ...
