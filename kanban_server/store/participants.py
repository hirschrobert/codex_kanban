from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .support import (
    _json_dumps,
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
                    self._clean_text(payload.get("message")) or "",
                    _json_dumps(_normalise_metadata(payload.get("metadata"))),
                    now,
                ),
            )
            if cursor.lastrowid is None:
                raise RuntimeError("event insert did not return an id")
            row = self._one(conn, "SELECT * FROM events WHERE id = ?", (int(cursor.lastrowid),))
            return self._event_from_row(row)
