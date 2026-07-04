from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from .support import (
    EVENT_RETENTION_HOURS,
    PARTICIPANT_KINDS,
    _json_dumps,
    _normalise_comment_author_name,
    _normalise_metadata,
    slugify,
    utc_now,
)

if TYPE_CHECKING:
    from .contracts import StoreMixinContract as _StoreMixinContract
else:

    class _StoreMixinContract:
        pass


class ParticipantEventStoreMixin(_StoreMixinContract):
    def upsert_participant(self, payload: dict[str, Any]) -> dict[str, Any]:
        display_name = str(payload.get("display_name") or payload.get("id") or "").strip()
        participant_id = slugify(str(payload.get("id") or display_name))
        if not participant_id:
            raise ValueError("participant id or display_name is required")

        kind = str(payload.get("kind") or "human")
        status = str(payload.get("status") or "idle")
        self._validate_participant(kind, status)

        with self._lock, self._connect() as conn:
            existing = self._one(conn, "SELECT * FROM participants WHERE id = ?", (participant_id,))
            board_slug = self._participant_board_slug(conn, payload, existing)
            self.ensure_board(board_slug, conn=conn)
            self._validate_participant_scope(
                conn,
                participant_id,
                board_slug,
                kind=kind,
                existing=existing,
                action="update participant",
            )
            self._enforce_agent_limits(
                conn,
                participant_id=participant_id,
                display_name=display_name or participant_id,
                kind=kind,
                status=status,
                board_slug=board_slug,
            )
            now = utc_now()
            values = {
                "id": participant_id,
                "kind": kind,
                "display_name": display_name or participant_id,
                "role": self._clean_text(payload.get("role"))
                or (existing["role"] if existing else ""),
                "status": status,
                "current_card_id": self._resolve_card_id(
                    conn,
                    payload,
                    board_slug=board_slug,
                    required=self._payload_references_card(payload),
                ),
                "current_board_slug": board_slug,
                "current_scope": self._clean_text(payload.get("current_scope"))
                or (existing["current_scope"] if existing else ""),
                "last_seen_at": now,
                "created_at": existing["created_at"] if existing else now,
                "updated_at": now,
            }
            conn.execute(
                """
                INSERT INTO participants (
                    id, kind, display_name, role, status, current_card_id,
                    current_board_slug, current_scope, last_seen_at, created_at, updated_at
                )
                VALUES (
                    :id, :kind, :display_name, :role, :status, :current_card_id,
                    :current_board_slug, :current_scope, :last_seen_at, :created_at, :updated_at
                )
                ON CONFLICT(id) DO UPDATE SET
                    kind = excluded.kind,
                    display_name = excluded.display_name,
                    role = excluded.role,
                    status = excluded.status,
                    current_card_id = excluded.current_card_id,
                    current_board_slug = excluded.current_board_slug,
                    current_scope = excluded.current_scope,
                    last_seen_at = excluded.last_seen_at,
                    updated_at = excluded.updated_at
                """,
                values,
            )
            row = self._one(conn, "SELECT * FROM participants WHERE id = ?", (participant_id,))
            if not row:
                raise KeyError(f"participant {participant_id} not found")
            return dict(row)

    def heartbeat(self, participant_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        payload = dict(payload)
        payload["id"] = participant_id
        return self.upsert_participant(payload)

    def prune_events_before(self, cutoff: str) -> int:
        cutoff = str(cutoff or "").strip()
        if not cutoff:
            raise ValueError("event prune cutoff is required")
        with self._lock, self._connect() as conn:
            cursor = conn.execute("DELETE FROM events WHERE created_at < ?", (cutoff,))
            return int(cursor.rowcount or 0)

    def prune_events_older_than(
        self,
        hours: int = EVENT_RETENTION_HOURS,
        *,
        now: datetime | None = None,
    ) -> int:
        if hours < 0:
            raise ValueError("event retention hours must be non-negative")
        current = now or datetime.now(UTC)
        if current.tzinfo is None:
            current = current.replace(tzinfo=UTC)
        cutoff = (
            (current.astimezone(UTC) - timedelta(hours=hours))
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        )
        return self.prune_events_before(cutoff)

    def create_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        event_type = str(payload.get("event_type") or "event").strip()
        if not event_type:
            raise ValueError("event_type is required")

        with self._lock, self._connect() as conn:
            board_slug = (
                slugify(str(payload["board_slug"]))
                if payload.get("board_slug")
                else self._default_board_slug(conn)
            )
            self.ensure_board(board_slug, conn=conn)
            card_id = self._resolve_card_id(
                conn,
                payload,
                board_slug=board_slug,
                required=self._payload_references_card(payload),
            )
            card_external_id = self._clean_text(payload.get("card_external_id"))
            if card_id and not card_external_id:
                row = self._one(conn, "SELECT external_id FROM cards WHERE id = ?", (card_id,))
                card_external_id = row["external_id"] if row else None
            participant_id = self._clean_text(payload.get("participant_id"))
            if participant_id:
                self._validate_participant_scope(
                    conn,
                    participant_id,
                    board_slug,
                    action="create event",
                )
            now = utc_now()
            message = self._clean_text(payload.get("message")) or ""
            metadata = _normalise_metadata(payload.get("metadata"))
            if not metadata.get("comment_id"):
                comment_id = self._agent_feedback_comment_id(
                    conn,
                    event_type=event_type,
                    board_slug=board_slug,
                    card_id=card_id,
                    participant_id=participant_id,
                    message=message,
                    metadata=metadata,
                    created_at=now,
                )
                if comment_id is not None:
                    metadata["comment_id"] = comment_id
            cursor = conn.execute(
                """
                INSERT INTO events (
                    board_slug, event_type, card_id, card_external_id,
                    participant_id, message, metadata, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    board_slug,
                    event_type,
                    card_id,
                    card_external_id,
                    participant_id,
                    message,
                    _json_dumps(metadata),
                    now,
                ),
            )
            if cursor.lastrowid is None:
                raise RuntimeError("event insert did not return an id")
            row = self._one(conn, "SELECT * FROM events WHERE id = ?", (int(cursor.lastrowid),))
            return self._event_from_row(row)

    def _agent_feedback_comment_id(
        self,
        conn: Any,
        *,
        event_type: str,
        board_slug: str,
        card_id: int | None,
        participant_id: str | None,
        message: str,
        metadata: dict[str, Any],
        created_at: str,
    ) -> int | None:
        feedback_events = {
            "agent.finished",
            "agent.feedback",
            "agent.handoff",
            "subagent.stopped",
            "subagent.finished",
            "subagent.feedback",
            "subagent.handoff",
        }
        if event_type not in feedback_events:
            return None
        if not card_id or not message:
            return None

        source_event_key = self._feedback_source_event_key(
            event_type=event_type,
            card_id=card_id,
            participant_id=participant_id,
            message=message,
            metadata=metadata,
        )
        existing = self._feedback_comment_by_source_event(
            conn,
            board_slug=board_slug,
            card_id=card_id,
            source_event_key=source_event_key,
        )
        if existing is not None:
            return existing

        participant = None
        if participant_id:
            participant = self._one(
                conn,
                "SELECT id, display_name, kind FROM participants WHERE id = ?",
                (participant_id,),
            )
        author_name = _normalise_comment_author_name(
            self._clean_text(participant["display_name"] if participant else None)
            or participant_id
            or "agent"
        )
        author_kind = self._clean_text(participant["kind"] if participant else None) or "agent"
        if author_kind not in PARTICIPANT_KINDS:
            author_kind = "agent"
        try:
            cursor = conn.execute(
                """
                INSERT INTO card_comments (
                    board_slug, card_id, participant_id,
                    author_name, author_kind, body, source_event_key, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    board_slug,
                    card_id,
                    participant_id if participant else None,
                    author_name or "agent",
                    author_kind,
                    message,
                    source_event_key,
                    created_at,
                ),
            )
            lastrowid = cursor.lastrowid
        except sqlite3.IntegrityError:
            existing = self._feedback_comment_by_source_event(
                conn,
                board_slug=board_slug,
                card_id=card_id,
                source_event_key=source_event_key,
            )
            if existing is not None:
                return existing
            raise
        if lastrowid is None:
            raise RuntimeError("card comment insert did not return an id")
        conn.execute("UPDATE cards SET updated_at = ? WHERE id = ?", (created_at, card_id))
        return int(lastrowid)

    def _feedback_comment_by_source_event(
        self,
        conn: Any,
        *,
        board_slug: str,
        card_id: int,
        source_event_key: str,
    ) -> int | None:
        row = self._one(
            conn,
            """
            SELECT id FROM card_comments
            WHERE board_slug = ?
              AND card_id = ?
              AND source_event_key = ?
            """,
            (board_slug, card_id, source_event_key),
        )
        return int(row["id"]) if row else None

    def _feedback_source_event_key(
        self,
        *,
        event_type: str,
        card_id: int,
        participant_id: str | None,
        message: str,
        metadata: dict[str, Any],
    ) -> str:
        explicit = self._clean_text(
            metadata.get("feedback_key")
            or metadata.get("idempotency_key")
            or metadata.get("dedupe_key")
            or metadata.get("event_id")
        )
        if explicit:
            return f"explicit:{explicit}"

        hook = self._clean_text(metadata.get("hook"))
        raw_agent_id = self._clean_text(metadata.get("raw_agent_id"))
        cwd = self._clean_text(metadata.get("cwd"))
        project = self._clean_text(metadata.get("project"))
        if hook or raw_agent_id:
            return "|".join(
                [
                    "hook",
                    event_type,
                    str(card_id),
                    participant_id or "",
                    hook or "",
                    raw_agent_id or "",
                    project or "",
                    cwd or "",
                    message,
                ]
            )

        return "|".join(
            [
                "event",
                event_type,
                str(card_id),
                participant_id or "",
                message,
            ]
        )
