from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from .support import (
    CARD_TEXT_FIELDS,
    DEFAULT_ACTIVITY_EVENT_LIMIT,
    DEFAULT_REPEAT_TIME,
    DEFAULT_REPEAT_TIMEZONE,
    JSON_LIST_FIELDS,
    LOCAL_COMMENT_AUTHOR_NAME,
    MAX_ACTIVE_AGENTS_GLOBAL,
    MAX_ACTIVE_AGENTS_PER_PROJECT,
    MAX_ACTIVE_IMPLEMENTERS_PER_PROJECT,
    PARTICIPANT_KINDS,
    STALE_AFTER_SECONDS,
    _json_dumps,
    _normalise_comment_author_name,
    _normalise_deployment_dispositions,
    _normalise_list,
    slugify,
    utc_now,
)

if TYPE_CHECKING:
    from .contracts import StoreMixinContract as _StoreMixinContract
else:

    class _StoreMixinContract:
        pass


class CardStoreMixin(_StoreMixinContract):
    def snapshot(
        self,
        board_slug: str | None = None,
        event_limit: int = DEFAULT_ACTIVITY_EVENT_LIMIT,
        *,
        include_archived: bool = False,
        archived_only: bool = False,
    ) -> dict[str, Any]:
        with self._lock, self._connect() as conn:
            now = datetime.now(UTC)
            server_time = self._format_utc(now)
            requested_board_slug = slugify(board_slug) if board_slug else None
            board_slug = requested_board_slug or self._default_board_slug(conn)
            if requested_board_slug and not self._one(
                conn, "SELECT 1 FROM boards WHERE slug = ?", (requested_board_slug,)
            ):
                board_slug = self._default_board_slug(conn)
            if self._board_is_removed_project(conn, board_slug):
                board_slug = self._default_board_slug(conn)
            self.ensure_board(board_slug, conn=conn)
            board = self._one(conn, "SELECT * FROM boards WHERE slug = ?", (board_slug,))
            boards = [dict(row) for row in conn.execute("SELECT * FROM boards ORDER BY slug")]
            projects = self._visible_projects(self._list_projects(conn, include_removed=False))
            all_projects = self._list_projects(conn, include_removed=True)
            active_project = self._project_from_row(
                self._one(
                    conn,
                    "SELECT * FROM projects WHERE board_slug = ? AND removed_at IS NULL",
                    (board_slug,),
                )
            )
            lanes = [
                dict(row)
                for row in conn.execute(
                    "SELECT * FROM lanes WHERE board_slug = ? ORDER BY position", (board_slug,)
                )
            ]
            participant_rows = list(
                conn.execute(
                    """
                    SELECT * FROM participants
                    WHERE current_board_slug = ? OR current_board_slug IS NULL
                    ORDER BY
                        CASE status
                            WHEN 'running' THEN 1
                            WHEN 'reviewing' THEN 2
                            WHEN 'waiting_approval' THEN 3
                            WHEN 'blocked' THEN 4
                            WHEN 'waiting' THEN 5
                            WHEN 'idle' THEN 6
                            WHEN 'done' THEN 7
                            ELSE 8
                        END,
                        last_seen_at DESC,
                        display_name
                    """,
                    (board_slug,),
                )
            )
            participants = self._participants_with_runtime(
                conn,
                participant_rows,
                board_slug=board_slug,
                active_project=active_project,
                now=now,
            )
            if archived_only:
                archived_filter = "AND archived_at IS NOT NULL"
            elif include_archived:
                archived_filter = ""
            else:
                archived_filter = "AND archived_at IS NULL"
            cards = [
                self._card_from_row(row)
                for row in conn.execute(
                    f"""
                    SELECT * FROM cards
                    WHERE board_slug = ?
                      {archived_filter}
                    ORDER BY
                        archived_at IS NOT NULL,
                        COALESCE(NULLIF(updated_at, ''), created_at) DESC,
                        id DESC
                    """,
                    (board_slug,),
                )
            ]
            self._attach_dependency_links(conn, cards)
            self._attach_card_comments(conn, cards)
            self._attach_affected_project_paths(cards, active_project)
            cards = self._cards_with_coordination(cards, participants)
            event_page = self._event_page(conn, board_slug, limit=event_limit)
            return {
                "server_time": server_time,
                "board": dict(board) if board else None,
                "boards": boards,
                "projects": projects,
                "all_projects": all_projects,
                "active_project": active_project,
                "agent_limits": {
                    "stale_after_seconds": STALE_AFTER_SECONDS,
                    "max_active_agents_per_project": MAX_ACTIVE_AGENTS_PER_PROJECT,
                    "default_max_active_implementers_per_project": (
                        MAX_ACTIVE_IMPLEMENTERS_PER_PROJECT
                    ),
                    "max_active_implementers_per_project": (
                        active_project["max_active_implementers"]
                        if active_project
                        else MAX_ACTIVE_IMPLEMENTERS_PER_PROJECT
                    ),
                    "max_active_agents_global": MAX_ACTIVE_AGENTS_GLOBAL,
                },
                "lanes": lanes,
                "cards": cards,
                "participants": participants,
                "events": event_page["events"],
                "events_has_more": event_page["has_more"],
                "events_next_before_id": event_page["next_before_id"],
            }

    def get_card(self, card_id: int) -> dict[str, Any] | None:
        with self._lock, self._connect() as conn:
            row = self._one(conn, "SELECT * FROM cards WHERE id = ?", (card_id,))
            if not row:
                return None
            card = self._card_from_row(row)
            self._attach_dependency_links(conn, [card])
            self._attach_card_comments(conn, [card])
            active_project = self._project_from_row(
                self._one(
                    conn,
                    "SELECT * FROM projects WHERE board_slug = ? AND removed_at IS NULL",
                    (card["board_slug"],),
                )
            )
            self._attach_affected_project_paths([card], active_project)
            return card

    def create_card(self, payload: dict[str, Any]) -> dict[str, Any]:
        title = str(payload.get("title") or "").strip()
        if not title:
            raise ValueError("title is required")
        description = self._clean_text(payload.get("description")) or ""
        if not description:
            raise ValueError("description is required")

        status = str(payload.get("status") or "backlog")
        priority = str(payload.get("priority") or "normal")
        self._validate_status(status)
        self._validate_priority(priority)
        repeat_cadence, repeat_time, repeat_timezone = self._repeat_settings_from_payload(
            payload,
            target_branch=self._clean_text(payload.get("target_branch")),
        )

        with self._lock, self._connect() as conn:
            board_slug = (
                slugify(str(payload["board_slug"]))
                if payload.get("board_slug")
                else self._default_board_slug(conn)
            )
            self.ensure_board(board_slug, conn=conn)
            self._validate_repeat_project_gate(conn, board_slug, repeat_cadence)
            assignee_id = self._validate_assignee(
                conn,
                self._clean_text(payload.get("assignee_id")),
                board_slug=board_slug,
            )
            created_by_id, created_by_name, created_by_kind = self._card_creator_from_payload(
                conn,
                payload,
                board_slug,
            )
            owner_id = self._owner_id_from_payload(
                conn,
                payload,
                board_slug,
                default_owner_id=created_by_id or LOCAL_COMMENT_AUTHOR_NAME,
            )
            now_dt = datetime.now(UTC)
            now = self._format_utc(now_dt)
            values = {
                "board_slug": board_slug,
                "external_id": self._clean_text(payload.get("external_id")),
                "title": title,
                "description": description,
                "status": status,
                "assignee_id": assignee_id,
                "owner_id": owner_id,
                "created_by_id": created_by_id,
                "created_by_name": created_by_name,
                "created_by_kind": created_by_kind,
                "intake_kind": self._clean_text(payload.get("intake_kind")) or "",
                "intake_source": self._clean_text(payload.get("intake_source")) or "",
                "reported_by": self._clean_text(payload.get("reported_by")) or "",
                "impact": self._clean_text(payload.get("impact")) or "",
                "evidence": self._clean_text(payload.get("evidence")) or "",
                "priority": priority,
                "target_repo": self._clean_text(payload.get("target_repo")),
                "target_branch": self._clean_text(payload.get("target_branch")),
                "starting_target_sha": self._clean_text(payload.get("starting_target_sha")),
                "handoff_target_sha": self._clean_text(payload.get("handoff_target_sha")),
                "feature_branch": self._clean_text(payload.get("feature_branch")),
                "worktree_path": self._clean_text(payload.get("worktree_path")),
                "blocker_reason": self._clean_text(payload.get("blocker_reason")),
                "parent_external_id": None,
                "child_external_ids": "[]",
                "affected_paths": _json_dumps(_normalise_list(payload.get("affected_paths"))),
                "deployment_dispositions": _json_dumps(
                    _normalise_deployment_dispositions(payload.get("deployment_dispositions"))
                ),
                "files_changed": _json_dumps(_normalise_list(payload.get("files_changed"))),
                "checks": _json_dumps(_normalise_list(payload.get("checks"))),
                "assumptions": _json_dumps(_normalise_list(payload.get("assumptions"))),
                "follow_up_cards": _json_dumps(_normalise_list(payload.get("follow_up_cards"))),
                "repeat_cadence": repeat_cadence,
                "repeat_time": repeat_time,
                "repeat_timezone": repeat_timezone,
                "repeat_last_period": self._clean_text(payload.get("repeat_last_period")),
                "repeat_last_created_card_id": None,
                "repeat_next_run_at": self._first_repeat_run_at(
                    repeat_cadence,
                    repeat_time,
                    repeat_timezone,
                    now=now_dt,
                ),
                "archived_at": now if self._bool_payload(payload.get("archived")) else None,
                "created_at": now,
                "updated_at": now,
            }
            columns = ", ".join(values)
            placeholders = ", ".join("?" for _ in values)
            cursor = conn.execute(
                f"INSERT INTO cards ({columns}) VALUES ({placeholders})", tuple(values.values())
            )
            if cursor.lastrowid is None:
                raise RuntimeError("card insert did not return an id")
            card_id = int(cursor.lastrowid)
            if not values["external_id"]:
                external_id = f"{self._card_prefix(conn, board_slug)}-{card_id:04d}"
                conn.execute(
                    "UPDATE cards SET external_id = ?, updated_at = ? WHERE id = ?",
                    (external_id, utc_now(), card_id),
                )
            self._sync_card_links(conn, card_id, payload, creating=True)
            self._assert_dependencies_allow_status(conn, card_id, status)
            row = self._one(conn, "SELECT * FROM cards WHERE id = ?", (card_id,))
            card = self._card_from_row(row)
            self._attach_dependency_links(conn, [card])
            return card

    def update_card(self, card_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        if not payload:
            raise ValueError("no fields supplied")

        with self._lock, self._connect() as conn:
            current = self._one(conn, "SELECT * FROM cards WHERE id = ?", (card_id,))
            if not current:
                raise KeyError(f"card {card_id} not found")

            updates: dict[str, Any] = {}
            for field in CARD_TEXT_FIELDS:
                if field not in payload:
                    continue
                if field == "title" and not str(payload[field]).strip():
                    raise ValueError("title cannot be empty")
                if field == "description" and not str(payload[field]).strip():
                    raise ValueError("description cannot be empty")
                if field == "status":
                    self._validate_status(str(payload[field]))
                if field == "priority":
                    self._validate_priority(str(payload[field]))
                value = self._clean_text(payload[field])
                if field == "assignee_id":
                    value = self._validate_assignee(
                        conn,
                        value,
                        board_slug=current["board_slug"],
                    )
                if field == "owner_id":
                    value = self._validate_owner(
                        conn,
                        value,
                        board_slug=current["board_slug"],
                        current_owner_id=current["owner_id"],
                    )
                if field in {
                    "intake_kind",
                    "intake_source",
                    "reported_by",
                    "impact",
                    "evidence",
                }:
                    value = value or ""
                if field == "repeat_cadence":
                    value = self._validate_repeat_cadence(value or "none")
                if field == "repeat_time":
                    value = self._validate_repeat_time(value or DEFAULT_REPEAT_TIME)
                if field == "repeat_timezone":
                    value = self._validate_repeat_timezone(value or DEFAULT_REPEAT_TIMEZONE)
                updates[field] = value

            for field in JSON_LIST_FIELDS:
                if field in payload:
                    if field == "deployment_dispositions":
                        updates[field] = _json_dumps(
                            _normalise_deployment_dispositions(payload[field])
                        )
                    else:
                        updates[field] = _json_dumps(_normalise_list(payload[field]))

            if "archived" in payload:
                updates["archived_at"] = (
                    utc_now() if self._bool_payload(payload["archived"]) else None
                )

            has_link_updates = self._payload_has_link_updates(payload)
            if updates:
                prospective = dict(current)
                prospective.update(updates)
                self._validate_repeat_target_branch(
                    prospective.get("repeat_cadence"),
                    prospective.get("target_branch"),
                )
                self._validate_repeat_project_gate(
                    conn,
                    current["board_slug"],
                    prospective.get("repeat_cadence"),
                )
                if {
                    "repeat_cadence",
                    "repeat_time",
                    "repeat_timezone",
                    "target_branch",
                } & set(updates):
                    updates["repeat_next_run_at"] = self._first_repeat_run_at(
                        prospective.get("repeat_cadence"),
                        prospective.get("repeat_time") or DEFAULT_REPEAT_TIME,
                        prospective.get("repeat_timezone") or DEFAULT_REPEAT_TIMEZONE,
                    )
                    if str(prospective.get("repeat_cadence") or "none") == "none":
                        updates["repeat_last_period"] = None
                        updates["repeat_last_created_card_id"] = None

            if not updates and not has_link_updates:
                raise ValueError("no supported fields supplied")

            if updates:
                updates["updated_at"] = utc_now()
                assignments = ", ".join(f"{field} = ?" for field in updates)
                conn.execute(
                    f"UPDATE cards SET {assignments} WHERE id = ?",
                    (*updates.values(), card_id),
                )
            if has_link_updates:
                self._sync_card_links(conn, card_id, payload)
                conn.execute("UPDATE cards SET updated_at = ? WHERE id = ?", (utc_now(), card_id))
            updated = self._one(conn, "SELECT * FROM cards WHERE id = ?", (card_id,))
            if not updated:
                raise KeyError(f"card {card_id} not found")
            status_changed = "status" in updates and updates["status"] != current["status"]
            if status_changed:
                self._assert_dependencies_allow_status(conn, card_id, updated["status"])
            card = self._card_from_row(updated)
            self._attach_dependency_links(conn, [card])
            return card

    def _card_creator_from_payload(
        self,
        conn: sqlite3.Connection,
        payload: dict[str, Any],
        board_slug: str,
    ) -> tuple[str | None, str, str]:
        creator_id = self._clean_text(
            payload.get("created_by_id") or payload.get("actor_id") or payload.get("participant_id")
        )
        creator_name = self._clean_text(
            payload.get("created_by_name") or payload.get("author_name")
        )
        creator_kind = self._clean_text(payload.get("created_by_kind")) or "human"
        if creator_id:
            self._validate_participant_scope(conn, creator_id, board_slug, action="create card")
            participant = self._one(
                conn,
                "SELECT display_name, kind FROM participants WHERE id = ?",
                (creator_id,),
            )
            if participant:
                creator_name = self._clean_text(participant["display_name"]) or creator_id
                creator_kind = self._clean_text(participant["kind"]) or "human"
            else:
                creator_name = creator_name or creator_id
        else:
            creator_name = creator_name or LOCAL_COMMENT_AUTHOR_NAME
        if creator_kind not in PARTICIPANT_KINDS:
            raise ValueError(f"unsupported card creator kind: {creator_kind}")
        creator_name = _normalise_comment_author_name(creator_name) or LOCAL_COMMENT_AUTHOR_NAME
        return creator_id, creator_name, creator_kind

    def _owner_id_from_payload(
        self,
        conn: sqlite3.Connection,
        payload: dict[str, Any],
        board_slug: str,
        *,
        default_owner_id: str,
    ) -> str:
        owner_id = self._clean_text(payload.get("owner_id")) or default_owner_id
        return self._validate_owner(conn, owner_id, board_slug=board_slug) or owner_id

    def add_card_comment(self, card_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        body = (
            self._clean_text(payload.get("body"))
            or self._clean_text(payload.get("comment"))
            or self._clean_text(payload.get("message"))
        )
        if not body:
            raise ValueError("comment body is required")

        with self._lock, self._connect() as conn:
            card = self._one(conn, "SELECT id, board_slug FROM cards WHERE id = ?", (card_id,))
            if not card:
                raise KeyError(f"card {card_id} not found")
            board_slug = card["board_slug"]
            requested_board = self._clean_text(payload.get("board_slug"))
            if requested_board and slugify(requested_board) != board_slug:
                raise ValueError(
                    f"card {card_id} belongs to board '{board_slug}', "
                    f"cannot comment on board '{slugify(requested_board)}'"
                )

            participant_id = self._clean_text(
                payload.get("participant_id") or payload.get("actor_id")
            )
            author_name = self._clean_text(
                payload.get("author_name") or payload.get("writer_name") or payload.get("writer")
            )
            author_kind = self._clean_text(payload.get("author_kind") or payload.get("writer_kind"))
            if participant_id:
                self._validate_participant_scope(
                    conn,
                    participant_id,
                    board_slug,
                    action="comment on card",
                )
                participant = self._one(
                    conn,
                    "SELECT id, display_name, kind FROM participants WHERE id = ?",
                    (participant_id,),
                )
                if not participant:
                    raise ValueError(f"unknown participant_id '{participant_id}'")
                author_name = self._clean_text(participant["display_name"]) or participant_id
                author_kind = self._clean_text(participant["kind"]) or "human"
            else:
                author_name = author_name or LOCAL_COMMENT_AUTHOR_NAME
                author_kind = author_kind or "human"
            author_name = _normalise_comment_author_name(author_name) or LOCAL_COMMENT_AUTHOR_NAME
            if author_kind not in PARTICIPANT_KINDS:
                raise ValueError(f"unsupported note author kind: {author_kind}")

            now = utc_now()
            cursor = conn.execute(
                """
                INSERT INTO card_comments (
                    board_slug, card_id, participant_id,
                    author_name, author_kind, body, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (board_slug, card_id, participant_id, author_name, author_kind, body, now),
            )
            if cursor.lastrowid is None:
                raise RuntimeError("card comment insert did not return an id")
            conn.execute("UPDATE cards SET updated_at = ? WHERE id = ?", (now, card_id))
            row = self._one(
                conn,
                "SELECT * FROM card_comments WHERE id = ?",
                (int(cursor.lastrowid),),
            )
            return self._card_comment_from_row(row)

    def delete_card(self, card_id: int) -> dict[str, Any]:
        with self._lock, self._connect() as conn:
            row = self._one(conn, "SELECT * FROM cards WHERE id = ?", (card_id,))
            if not row:
                raise KeyError(f"card {card_id} not found")
            if not row["archived_at"]:
                raise ValueError("only archived cards can be deleted")
            card = self._card_from_row(row)
            conn.execute("DELETE FROM cards WHERE id = ?", (card_id,))
            return {"deleted": True, "card": card}
