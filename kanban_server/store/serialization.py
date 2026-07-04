from __future__ import annotations

import os
import sqlite3
from collections import defaultdict
from datetime import UTC, datetime
from itertools import combinations
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .support import (
    ACTIVE_CARD_STATUSES,
    ACTIVE_CONFLICT_STATUSES,
    ACTIVE_PARTICIPANT_STATUSES,
    DEFAULT_REPEAT_TIME,
    DEFAULT_REPEAT_TIMEZONE,
    JSON_LIST_FIELDS,
    LANE_STATUSES,
    LOCAL_COMMENT_AUTHOR_NAME,
    MAX_ACTIVE_AGENTS_GLOBAL,
    MAX_ACTIVE_AGENTS_PER_PROJECT,
    MAX_ACTIVE_IMPLEMENTERS_PER_PROJECT,
    PARTICIPANT_KINDS,
    PARTICIPANT_STATUSES,
    PRIORITIES,
    PROJECT_JSON_FIELDS,
    STALE_AFTER_SECONDS,
    _json_loads,
    _normalise_comment_author_name,
    _normalise_deployment_dispositions,
    _normalise_text_newlines,
    _utc_datetime,
    slugify,
)

if TYPE_CHECKING:
    from .contracts import StoreMixinContract as _StoreMixinContract
else:

    class _StoreMixinContract:
        pass


class SerializationCoordinationMixin(_StoreMixinContract):
    @staticmethod
    def _format_utc(value: datetime) -> str:
        return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")

    def _card_from_row(self, row: sqlite3.Row | None) -> dict[str, Any]:
        if row is None:
            return {}
        card = dict(row)
        for field in JSON_LIST_FIELDS:
            card[field] = _json_loads(card.get(field), [])
        card["deployment_dispositions"] = _normalise_deployment_dispositions(
            card.get("deployment_dispositions")
        )
        card["child_external_ids"] = _json_loads(card.get("child_external_ids"), [])
        parent_external_id = self._clean_text(card.get("parent_external_id"))
        card["parent_external_id"] = parent_external_id
        card["parent_external_ids"] = [parent_external_id] if parent_external_id else []
        card["repeat_cadence"] = self._clean_text(card.get("repeat_cadence")) or "none"
        card["repeat_time"] = self._clean_text(card.get("repeat_time")) or DEFAULT_REPEAT_TIME
        card["repeat_timezone"] = (
            self._clean_text(card.get("repeat_timezone")) or DEFAULT_REPEAT_TIMEZONE
        )
        card["repeat_next_run_at"] = self._clean_text(card.get("repeat_next_run_at"))
        card["archived"] = bool(card.get("archived_at"))
        card.setdefault("comments", [])
        card.setdefault("comment_count", 0)
        card.setdefault("parent_dependencies", [])
        card.setdefault("child_dependencies", [])
        card.setdefault("blocked_by_child_external_ids", [])
        card.setdefault("dependency_blocked", False)
        card.setdefault("dependency_warnings", [])
        card.setdefault("conflicts", [])
        card.setdefault("coordination_warnings", [])
        card.setdefault("affected_project_paths", [])
        card.setdefault("created_by", None)
        card.setdefault("owner", None)
        card.setdefault("assignee", None)
        card.setdefault("assignee_is_active", False)
        card.setdefault("assignee_is_stale", False)
        return card

    def _attach_affected_project_paths(
        self,
        cards: list[dict[str, Any]],
        active_project: dict[str, Any] | None,
    ) -> None:
        project_paths = active_project.get("paths") if active_project else []
        if not isinstance(project_paths, list) or not project_paths:
            for card in cards:
                card["affected_project_paths"] = []
            return

        for card in cards:
            card["affected_project_paths"] = self._affected_project_path_entries(
                card,
                project_paths,
            )

    def _affected_project_path_entries(
        self,
        card: dict[str, Any],
        project_paths: list[Any],
    ) -> list[dict[str, Any]]:
        candidates = self._card_scope_paths(card)
        if not candidates:
            return []

        entries: list[dict[str, Any]] = []
        seen: set[str] = set()
        for raw_entry in project_paths:
            if isinstance(raw_entry, dict):
                label = self._clean_text(raw_entry.get("label"))
                raw_path = self._clean_text(raw_entry.get("path"))
            else:
                label = None
                raw_path = self._clean_text(raw_entry)
            path = self._normalised_path(raw_path)
            if not path or path in seen:
                continue
            matches = [
                candidate for candidate in candidates if self._paths_overlap(path, candidate)
            ]
            if not matches:
                continue
            seen.add(path)
            entries.append(
                {
                    "label": label or Path(path).name or path,
                    "path": path,
                    "source_paths": sorted(set(matches)),
                }
            )
        return entries

    def _card_scope_paths(self, card: dict[str, Any]) -> list[str]:
        raw_paths: list[Any] = [
            *card.get("affected_paths", []),
            card.get("target_repo"),
            card.get("worktree_path"),
        ]
        raw_paths.extend(
            item.get("path")
            for item in card.get("deployment_dispositions", [])
            if isinstance(item, dict)
        )
        target_repo = self._normalised_path(card.get("target_repo"))
        for item in card.get("files_changed", []):
            path = self._normalised_path(item)
            if not path:
                continue
            if os.path.isabs(path) or not target_repo:
                raw_paths.append(path)
            else:
                raw_paths.append(os.path.join(target_repo, path))

        paths: list[str] = []
        seen: set[str] = set()
        for raw_path in raw_paths:
            path = self._normalised_path(raw_path)
            if not path or path in seen:
                continue
            seen.add(path)
            paths.append(path)
        return paths

    @staticmethod
    def _paths_overlap(left: str, right: str) -> bool:
        left_path = os.path.normcase(os.path.normpath(left))
        right_path = os.path.normcase(os.path.normpath(right))
        if left_path == right_path:
            return True
        try:
            return os.path.commonpath([left_path, right_path]) in {left_path, right_path}
        except ValueError:
            return False

    def _participant_from_row(
        self, row: sqlite3.Row | dict[str, Any] | None, *, now: datetime
    ) -> dict[str, Any]:
        if row is None:
            return {}
        participant = dict(row)
        age = self._participant_age_seconds(participant, now)
        active_status = participant.get("status") in ACTIVE_PARTICIPANT_STATUSES
        is_stale = bool(active_status and (age is None or age > STALE_AFTER_SECONDS))
        participant["seconds_since_seen"] = age
        participant["is_active_status"] = active_status
        participant["is_stale"] = is_stale
        participant["is_active"] = bool(active_status and not is_stale)
        return participant

    def _participant_age_seconds(self, participant: dict[str, Any], now: datetime) -> int | None:
        seen_at = _utc_datetime(self._clean_text(participant.get("last_seen_at")))
        if not seen_at:
            return None
        return max(0, int((now - seen_at.astimezone(UTC)).total_seconds()))

    def _event_from_row(self, row: sqlite3.Row | None) -> dict[str, Any]:
        if row is None:
            return {}
        event = dict(row)
        event["metadata"] = _json_loads(event.get("metadata"), {})
        event["related_cards"] = []
        return event

    def _card_comment_from_row(self, row: sqlite3.Row | None) -> dict[str, Any]:
        if row is None:
            return {}
        comment = dict(row)
        author_name = self._clean_text(comment.get("author_name")) or (
            self._clean_text(comment.get("participant_id")) or "Unknown"
        )
        comment["author_name"] = _normalise_comment_author_name(author_name) or "Unknown"
        comment["author_kind"] = self._clean_text(comment.get("author_kind")) or "human"
        return comment

    def _project_from_row(self, row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        project = dict(row)
        for field in PROJECT_JSON_FIELDS:
            project[field] = _json_loads(project.get(field), [])
        return project

    def _default_board_slug(self, conn: sqlite3.Connection) -> str:
        preferred = self._clean_text(getattr(self, "preferred_board_slug", None))
        if preferred:
            row = self._one(
                conn,
                """
                SELECT projects.board_slug
                FROM projects
                JOIN boards ON boards.slug = projects.board_slug
                WHERE projects.board_slug = ?
                  AND projects.removed_at IS NULL
                LIMIT 1
                """,
                (slugify(preferred),),
            )
            if row:
                return row["board_slug"]
        row = self._one(
            conn,
            """
            SELECT board_slug FROM projects
            WHERE removed_at IS NULL
            ORDER BY display_name
            LIMIT 1
            """,
        )
        return row["board_slug"] if row else "default"

    def _card_prefix(self, conn: sqlite3.Connection, board_slug: str) -> str:
        row = self._one(
            conn,
            "SELECT card_prefix FROM projects WHERE board_slug = ?",
            (board_slug,),
        )
        if row and row["card_prefix"]:
            return row["card_prefix"]
        return slugify(board_slug).upper()

    def _cards_with_coordination(
        self, cards: list[dict[str, Any]], participants: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        enriched = [dict(card, conflicts=[], coordination_warnings=[]) for card in cards]
        by_id = {int(card["id"]): card for card in enriched}
        participants_by_id = {participant["id"]: participant for participant in participants}

        for card in enriched:
            card["coordination_warnings"] = [
                *self._coordination_warnings(card),
                *card.get("dependency_warnings", []),
            ]
            self._attach_card_owner(card, participants_by_id)
            self._attach_card_creator(card, participants_by_id)
            self._attach_assignee_liveness(card, participants_by_id)

        for left_id, right_id in self._conflict_candidate_pairs(enriched):
            left = by_id[left_id]
            right = by_id[right_id]
            reasons = self._conflict_reasons(left, right)
            if not reasons:
                continue
            by_id[left_id]["conflicts"].append(self._conflict_summary(right, reasons))
            by_id[right_id]["conflicts"].append(self._conflict_summary(left, reasons))

        return enriched

    def _conflict_candidate_pairs(self, cards: list[dict[str, Any]]) -> list[tuple[int, int]]:
        buckets: dict[tuple[str, str], list[int]] = defaultdict(list)
        for card in cards:
            card_id = int(card["id"])
            for key in self._conflict_keys(card):
                buckets[key].append(card_id)

        pairs: set[tuple[int, int]] = set()
        for card_ids in buckets.values():
            for left_id, right_id in combinations(sorted(set(card_ids)), 2):
                pairs.add((left_id, right_id))
        return sorted(pairs)

    def _conflict_keys(self, card: dict[str, Any]) -> set[tuple[str, str]]:
        if card.get("status") not in ACTIVE_CONFLICT_STATUSES:
            return set()
        keys: set[tuple[str, str]] = set()
        repo = self._normalised_path(card.get("target_repo"))
        if repo:
            keys.add(("repo", repo))
        feature = self._clean_text(card.get("feature_branch"))
        if feature:
            keys.add(("feature", feature))
        worktree = self._normalised_path(card.get("worktree_path"))
        if worktree:
            keys.add(("worktree", worktree))
        for item in card.get("files_changed", []):
            path = self._normalised_path(item)
            if path:
                keys.add(("file", path))
        return keys

    def _attach_card_owner(
        self, card: dict[str, Any], participants_by_id: dict[str, dict[str, Any]]
    ) -> None:
        owner_id = self._clean_text(card.get("owner_id"))
        if not owner_id:
            return
        participant = participants_by_id.get(owner_id)
        if participant:
            card["owner"] = {
                "id": participant.get("id"),
                "display_name": participant.get("display_name"),
                "kind": participant.get("kind"),
                "status": participant.get("status"),
            }
            return
        card["owner"] = {
            "id": owner_id,
            "display_name": owner_id,
            "kind": "unknown",
            "status": "",
        }

    def _attach_card_creator(
        self, card: dict[str, Any], participants_by_id: dict[str, dict[str, Any]]
    ) -> None:
        creator_id = self._clean_text(card.get("created_by_id"))
        creator_name = self._clean_text(card.get("created_by_name"))
        creator_kind = self._clean_text(card.get("created_by_kind")) or "human"
        participant = participants_by_id.get(creator_id or "")
        if participant:
            creator_name = self._clean_text(participant.get("display_name")) or creator_id
            creator_kind = self._clean_text(participant.get("kind")) or creator_kind
        if not creator_name:
            creator_name = creator_id or "Unknown"
        card["created_by"] = {
            "id": creator_id,
            "display_name": creator_name,
            "kind": creator_kind,
        }

    def _attach_assignee_liveness(
        self, card: dict[str, Any], participants_by_id: dict[str, dict[str, Any]]
    ) -> None:
        assignee_id = self._clean_text(card.get("assignee_id"))
        participant = participants_by_id.get(assignee_id or "")
        if not participant:
            return

        card["assignee"] = {
            "id": participant.get("id"),
            "display_name": participant.get("display_name"),
            "kind": participant.get("kind"),
            "status": participant.get("status"),
            "last_seen_at": participant.get("last_seen_at"),
            "seconds_since_seen": participant.get("seconds_since_seen"),
            "is_active": participant.get("is_active"),
            "is_stale": participant.get("is_stale"),
        }
        card["assignee_is_active"] = bool(participant.get("is_active"))
        card["assignee_is_stale"] = bool(participant.get("is_stale"))

        if card.get("status") not in ACTIVE_CARD_STATUSES:
            return
        if participant.get("kind") != "agent":
            return
        if participant.get("is_stale"):
            seconds = participant.get("seconds_since_seen")
            age = self._human_age(seconds) if isinstance(seconds, int) else "unknown time"
            card["coordination_warnings"].append(
                f"Assigned agent has not checked in for {age}; "
                "verify before assuming work is active."
            )
        elif not participant.get("is_active"):
            card["coordination_warnings"].append(
                f"Assigned agent status is {participant.get('status')}; "
                "card may need a fresh start or status update."
            )

    @staticmethod
    def _human_age(seconds: int) -> str:
        if seconds < 60:
            return f"{seconds}s"
        minutes = seconds // 60
        if minutes < 60:
            return f"{minutes}m"
        hours = minutes // 60
        if hours < 48:
            return f"{hours}h"
        return f"{hours // 24}d"

    def _coordination_warnings(self, card: dict[str, Any]) -> list[str]:
        if card.get("status") not in ACTIVE_CONFLICT_STATUSES:
            warnings: list[str] = []
        else:
            warnings = []

        if card.get("status") in ACTIVE_CONFLICT_STATUSES and not self._clean_text(
            card.get("target_branch")
        ):
            warnings.append(
                "Target branch is empty. Use the upcoming release branch, or main "
                "when no unreleased branch exists."
            )
        if (
            card.get("status") in ACTIVE_CONFLICT_STATUSES
            and self._clean_text(card.get("feature_branch"))
            and not self._clean_text(card.get("worktree_path"))
        ):
            warnings.append(
                "Feature branch has no worktree path. Record the worktree path "
                "before handing off isolated branch work."
            )
        if card.get("repeat_cadence") != "none" and not self._clean_text(card.get("target_branch")):
            warnings.append(
                "Repeating cards need a target branch so scheduled work stays "
                "on the current release branch."
            )
        return warnings

    def _conflict_reasons(self, left: dict[str, Any], right: dict[str, Any]) -> list[str]:
        if left.get("status") not in ACTIVE_CONFLICT_STATUSES:
            return []
        if right.get("status") not in ACTIVE_CONFLICT_STATUSES:
            return []

        reasons: list[str] = []
        left_repo = self._normalised_path(left.get("target_repo"))
        right_repo = self._normalised_path(right.get("target_repo"))
        left_branch = self._clean_text(left.get("target_branch"))
        right_branch = self._clean_text(right.get("target_branch"))
        left_feature = self._clean_text(left.get("feature_branch"))
        right_feature = self._clean_text(right.get("feature_branch"))
        left_worktree = self._normalised_path(left.get("worktree_path"))
        right_worktree = self._normalised_path(right.get("worktree_path"))
        if left_repo and left_repo == right_repo:
            if not left_branch or not right_branch:
                reasons.append("same target repo with a missing target branch")
            elif left_branch == right_branch and not (
                left_feature and right_feature and left_feature != right_feature
            ):
                reasons.append(
                    "same target repo and branch without distinct feature "
                    f"branches: {left_branch}"
                )

        if left_feature and left_feature == right_feature:
            reasons.append(f"same feature branch: {left_feature}")

        if left_worktree and left_worktree == right_worktree:
            reasons.append(f"same worktree path: {left_worktree}")

        left_files = {self._normalised_path(item) for item in left.get("files_changed", [])}
        right_files = {self._normalised_path(item) for item in right.get("files_changed", [])}
        shared_files = sorted(item for item in left_files & right_files if item)
        if shared_files:
            shown = ", ".join(shared_files[:4])
            suffix = "..." if len(shared_files) > 4 else ""
            reasons.append(f"same declared files: {shown}{suffix}")

        return reasons

    @staticmethod
    def _conflict_summary(card: dict[str, Any], reasons: list[str]) -> dict[str, Any]:
        return {
            "card_id": card.get("id"),
            "external_id": card.get("external_id"),
            "title": card.get("title"),
            "status": card.get("status"),
            "reasons": reasons,
        }

    def _normalised_path(self, value: Any) -> str | None:
        text = self._clean_text(value)
        if not text:
            return None
        try:
            return os.path.normpath(os.path.expanduser(text))
        except TypeError:
            return text

    @staticmethod
    def _one(
        conn: sqlite3.Connection, query: str, params: tuple[Any, ...] = ()
    ) -> sqlite3.Row | None:
        return conn.execute(query, params).fetchone()

    @staticmethod
    def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def _list_projects(
        self, conn: sqlite3.Connection, *, include_removed: bool
    ) -> list[dict[str, Any]]:
        where = "" if include_removed else "WHERE p.removed_at IS NULL"
        projects: list[dict[str, Any]] = []
        for row in conn.execute(f"""
                SELECT
                    p.*,
                    (SELECT COUNT(*) FROM cards WHERE board_slug = p.board_slug) AS card_count,
                    (
                        SELECT COUNT(*)
                        FROM participants
                        WHERE current_board_slug = p.board_slug
                           OR id LIKE p.board_slug || '-%'
                    ) AS participant_count
                FROM projects p
                {where}
                ORDER BY p.removed_at IS NOT NULL, p.display_name
                """):
            project = self._project_from_row(row)
            if project:
                projects.append(project)
        return projects

    def _board_is_removed_project(self, conn: sqlite3.Connection, board_slug: str) -> bool:
        row = self._one(
            conn,
            "SELECT removed_at FROM projects WHERE board_slug = ?",
            (board_slug,),
        )
        return bool(row and row["removed_at"])

    def _active_project_for_board(
        self,
        conn: sqlite3.Connection,
        board_slug: str,
    ) -> dict[str, Any] | None:
        return self._project_from_row(
            self._one(
                conn,
                "SELECT * FROM projects WHERE board_slug = ? AND removed_at IS NULL",
                (board_slug,),
            )
        )

    def _validate_repeat_project_gate(
        self,
        conn: sqlite3.Connection,
        board_slug: str,
        cadence: Any,
    ) -> None:
        if self._validate_repeat_cadence(cadence or "none") == "none":
            return
        if not self._active_project_for_board(conn, board_slug):
            raise ValueError("repeating cards require an active registered project board")

    @staticmethod
    def _project_int_setting(
        payload: dict[str, Any],
        key: str,
        existing: Any,
        default: int,
    ) -> int:
        value = payload.get(key)
        if value in (None, ""):
            value = existing if existing not in (None, "") else default
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            raise ValueError(f"{key} must be a whole number") from None
        if parsed < 0:
            raise ValueError(f"{key} must be 0 or greater")
        return parsed

    def _max_active_implementers_for_board(self, conn: sqlite3.Connection, board_slug: str) -> int:
        row = self._one(
            conn,
            """
            SELECT max_active_implementers
            FROM projects
            WHERE board_slug = ? AND removed_at IS NULL
            """,
            (board_slug,),
        )
        if not row:
            return MAX_ACTIVE_IMPLEMENTERS_PER_PROJECT
        return int(row["max_active_implementers"])

    @staticmethod
    def _clean_text(value: Any) -> str | None:
        if value is None:
            return None
        text = _normalise_text_newlines(str(value)).strip()
        return text or None

    def _participant_board_slug(
        self,
        conn: sqlite3.Connection,
        payload: dict[str, Any],
        existing: sqlite3.Row | None,
    ) -> str:
        explicit = self._clean_text(payload.get("board_slug"))
        if explicit:
            return slugify(explicit)
        if existing and existing["current_board_slug"]:
            return existing["current_board_slug"]
        return self._default_board_slug(conn)

    @staticmethod
    def _payload_references_card(payload: dict[str, Any]) -> bool:
        return any(
            payload.get(field) not in (None, "")
            for field in (
                "current_card_id",
                "card_id",
                "current_card_external_id",
                "card_external_id",
            )
        )

    def _card_id_on_board(self, conn: sqlite3.Connection, card_id: int, *, board_slug: str) -> int:
        row = self._one(conn, "SELECT id, board_slug FROM cards WHERE id = ?", (card_id,))
        if not row:
            raise KeyError(f"card {card_id} not found")
        if row["board_slug"] != board_slug:
            raise ValueError(
                f"card {card_id} belongs to board '{row['board_slug']}', "
                f"cannot be used on board '{board_slug}'"
            )
        return int(row["id"])

    def _participant_id_board_scope(
        self, conn: sqlite3.Connection, participant_id: str
    ) -> str | None:
        for row in conn.execute("SELECT slug FROM boards ORDER BY LENGTH(slug) DESC"):
            board_slug = row["slug"]
            if participant_id == board_slug or participant_id.startswith(f"{board_slug}-"):
                return board_slug
        return None

    def _validate_participant_scope(
        self,
        conn: sqlite3.Connection,
        participant_id: str,
        board_slug: str,
        *,
        kind: str | None = None,
        existing: sqlite3.Row | None = None,
        action: str,
    ) -> None:
        scoped_board = self._participant_id_board_scope(conn, participant_id)
        if scoped_board and scoped_board != board_slug:
            raise ValueError(
                f"participant '{participant_id}' is scoped to board '{scoped_board}', "
                f"cannot {action} on board '{board_slug}'"
            )

        row = existing or self._one(
            conn,
            "SELECT id, kind, current_board_slug FROM participants WHERE id = ?",
            (participant_id,),
        )
        if not row:
            return
        participant_kind = kind or row["kind"]
        current_board = row["current_board_slug"]
        if participant_kind == "system":
            return
        if current_board and current_board != board_slug:
            raise ValueError(
                f"participant '{participant_id}' belongs to board '{current_board}', "
                f"cannot {action} on board '{board_slug}'"
            )

    def _enforce_agent_limits(
        self,
        conn: sqlite3.Connection,
        *,
        participant_id: str,
        display_name: str,
        kind: str,
        status: str,
        board_slug: str,
    ) -> None:
        if kind != "agent" or status not in ACTIVE_PARTICIPANT_STATUSES:
            return

        now = datetime.now(UTC)
        active_agents = [
            self._participant_from_row(row, now=now)
            for row in conn.execute(
                """
                SELECT * FROM participants
                WHERE kind = 'agent'
                  AND status IN ('running', 'reviewing')
                  AND id != ?
                """,
                (participant_id,),
            )
        ]
        fresh_agents = [agent for agent in active_agents if agent.get("is_active")]
        same_board = [
            agent for agent in fresh_agents if agent.get("current_board_slug") == board_slug
        ]
        if MAX_ACTIVE_AGENTS_PER_PROJECT and len(same_board) >= MAX_ACTIVE_AGENTS_PER_PROJECT:
            raise ValueError(
                f"board '{board_slug}' already has {len(same_board)} active agents; "
                f"limit is {MAX_ACTIVE_AGENTS_PER_PROJECT}"
            )

        profile = slugify(display_name)
        max_active_implementers = self._max_active_implementers_for_board(conn, board_slug)
        if profile == "project-implementer" and max_active_implementers:
            implementers = [
                agent
                for agent in same_board
                if slugify(str(agent.get("display_name") or "")) == "project-implementer"
                or str(agent.get("id") or "").endswith("-project-implementer")
            ]
            if len(implementers) >= max_active_implementers:
                raise ValueError(
                    f"board '{board_slug}' already has {len(implementers)} active "
                    f"project_implementer agents; limit is "
                    f"{max_active_implementers}"
                )

        if MAX_ACTIVE_AGENTS_GLOBAL and len(fresh_agents) >= MAX_ACTIVE_AGENTS_GLOBAL:
            raise ValueError(
                f"global active agent limit is {MAX_ACTIVE_AGENTS_GLOBAL}; "
                "wait for an active agent to finish or become stale"
            )

    @staticmethod
    def _validate_status(status: str) -> None:
        if status not in LANE_STATUSES:
            raise ValueError(f"unsupported card status: {status}")

    @staticmethod
    def _validate_priority(priority: str) -> None:
        if priority not in PRIORITIES:
            raise ValueError(f"unsupported priority: {priority}")

    def _validate_assignee(
        self,
        conn: sqlite3.Connection,
        assignee_id: str | None,
        *,
        board_slug: str,
    ) -> str | None:
        if not assignee_id:
            return None
        row = self._one(conn, "SELECT * FROM participants WHERE id = ?", (assignee_id,))
        if row:
            self._validate_participant_scope(
                conn,
                assignee_id,
                board_slug,
                existing=row,
                action="assign card",
            )
            return assignee_id

        self._validate_participant_scope(
            conn,
            assignee_id,
            board_slug,
            action="assign card",
        )

        known = [
            item["id"]
            for item in conn.execute(
                """
                SELECT id FROM participants
                WHERE current_board_slug = ? OR id LIKE ?
                ORDER BY display_name
                LIMIT 8
                """,
                (board_slug, f"{board_slug}-%"),
            )
        ]
        known_text = f" Known participants: {', '.join(known)}." if known else ""
        raise ValueError(
            f"unknown assignee_id '{assignee_id}' for board '{board_slug}'. "
            "Assignees must be registered participants; choose an id from the "
            "board snapshot or create one first with the participant-upsert CLI."
            f"{known_text}"
        )

    def _validate_owner(
        self,
        conn: sqlite3.Connection,
        owner_id: str | None,
        *,
        board_slug: str,
        current_owner_id: str | None = None,
    ) -> str | None:
        if not owner_id:
            return None
        if owner_id == LOCAL_COMMENT_AUTHOR_NAME:
            return owner_id
        row = self._one(conn, "SELECT * FROM participants WHERE id = ?", (owner_id,))
        if current_owner_id and owner_id == current_owner_id and not row:
            return owner_id
        if row:
            self._validate_participant_scope(
                conn,
                owner_id,
                board_slug,
                existing=row,
                action="own card",
            )
            return owner_id

        self._validate_participant_scope(conn, owner_id, board_slug, action="own card")
        known = [
            item["id"]
            for item in conn.execute(
                """
                SELECT id FROM participants
                WHERE current_board_slug = ? OR id LIKE ?
                ORDER BY display_name
                LIMIT 8
                """,
                (board_slug, f"{board_slug}-%"),
            )
        ]
        known_text = f" Known participants: {', '.join(known)}." if known else ""
        raise ValueError(
            f"unknown owner_id '{owner_id}' for board '{board_slug}'. "
            f"Owners must be registered participants or '{LOCAL_COMMENT_AUTHOR_NAME}'; "
            "choose an id from the board snapshot or create one first with the "
            "participant-upsert CLI."
            f"{known_text}"
        )

    @staticmethod
    def _validate_participant(kind: str, status: str) -> None:
        if kind not in PARTICIPANT_KINDS:
            raise ValueError(f"unsupported participant kind: {kind}")
        if status not in PARTICIPANT_STATUSES:
            raise ValueError(f"unsupported participant status: {status}")
