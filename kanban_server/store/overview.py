from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from .support import DEFAULT_OVERVIEW_DONE_LIMIT, slugify

if TYPE_CHECKING:
    from .contracts import StoreMixinContract as _StoreMixinContract
else:

    class _StoreMixinContract:
        pass


class OverviewStoreMixin(_StoreMixinContract):
    def overview(
        self,
        board_slug: str | None = None,
        *,
        cwd: str | None = None,
        repo: str | None = None,
        include_archived: bool = False,
        archived_only: bool = False,
        limit: int = 0,
        done_limit: int = DEFAULT_OVERVIEW_DONE_LIMIT,
    ) -> dict[str, Any]:
        resolution = self.resolve_project_for_paths([path for path in (cwd, repo) if path])
        matched_project = resolution["project"]
        resolution_payload = {key: value for key, value in resolution.items() if key != "project"}
        with self._lock, self._connect() as conn:
            requested_board_slug = slugify(board_slug) if board_slug else None
            effective_board_slug = (
                requested_board_slug
                or (matched_project["board_slug"] if matched_project else None)
                or self._default_board_slug(conn)
            )
            if requested_board_slug and not self._one(
                conn, "SELECT 1 FROM boards WHERE slug = ?", (requested_board_slug,)
            ):
                effective_board_slug = self._default_board_slug(conn)
            if self._board_is_removed_project(conn, effective_board_slug):
                effective_board_slug = self._default_board_slug(conn)
            self.ensure_board(effective_board_slug, conn=conn)

            board = self._one(
                conn,
                "SELECT * FROM boards WHERE slug = ?",
                (effective_board_slug,),
            )
            active_project = self._active_project_for_board(conn, effective_board_slug)
            agent_refresh = None
            if active_project:
                agent_refresh = self._refresh_project_agents(conn, active_project)
                active_project = agent_refresh["project"]
            projects = self._overview_projects(conn)
            cards, done_card_count, done_cards_hidden_count = self._overview_cards(
                conn,
                effective_board_slug,
                active_project=active_project,
                include_archived=include_archived,
                archived_only=archived_only,
                limit=limit,
                done_limit=done_limit,
            )
            archived_count = self._archived_card_count(conn, effective_board_slug)
            return {
                "board": dict(board) if board else None,
                "matched_project": matched_project,
                "project_resolution": resolution_payload,
                "active_project": active_project,
                "projects": projects,
                "agent_profiles_refreshed": bool(agent_refresh),
                "agent_profiles": (
                    agent_refresh["agent_profiles"]
                    if agent_refresh
                    else active_project.get("agent_profiles", []) if active_project else []
                ),
                "agent_participant_ids": (
                    agent_refresh["participant_ids"] if agent_refresh else []
                ),
                "cards": cards,
                "card_count": len(cards),
                "done_limit": done_limit,
                "done_card_count": done_card_count,
                "done_cards_hidden_count": done_cards_hidden_count,
                "done_cards_hidden": done_cards_hidden_count > 0,
                "archived_card_count": archived_count,
                "archived_cards_hidden": bool(
                    archived_count and not include_archived and not archived_only
                ),
                "archived_notice": self._archived_notice(
                    archived_count,
                    include_archived=include_archived,
                    archived_only=archived_only,
                ),
                "registration_hint": self._registration_hint(
                    cwd,
                    repo,
                    matched_project,
                    resolution_payload,
                    requested_board_slug,
                ),
                "include_archived": include_archived,
                "archived_only": archived_only,
            }

    def _overview_projects(self, conn: sqlite3.Connection) -> list[dict[str, Any]]:
        projects: list[dict[str, Any]] = []
        for project in self._list_projects(conn, include_removed=False):
            projects.append(
                {
                    "slug": project.get("slug"),
                    "display_name": project.get("display_name"),
                    "board_slug": project.get("board_slug"),
                    "root_path": project.get("root_path"),
                    "paths": project.get("paths", []),
                    "card_count": project.get("card_count", 0),
                }
            )
        return projects

    def _overview_cards(
        self,
        conn: sqlite3.Connection,
        board_slug: str,
        *,
        active_project: dict[str, Any] | None,
        include_archived: bool,
        archived_only: bool,
        limit: int,
        done_limit: int,
    ) -> tuple[list[dict[str, Any]], int, int]:
        archived_filter = self._archived_filter(
            include_archived=include_archived,
            archived_only=archived_only,
        )
        query = f"""
            SELECT * FROM cards
            WHERE board_slug = ?
              {archived_filter}
            ORDER BY
                archived_at IS NOT NULL,
                CASE status
                    WHEN 'in_progress' THEN 1
                    WHEN 'review' THEN 2
                    WHEN 'blocked' THEN 3
                    WHEN 'ready' THEN 4
                    WHEN 'backlog' THEN 5
                    WHEN 'done' THEN 6
                    ELSE 7
                END,
                COALESCE(NULLIF(updated_at, ''), created_at) DESC,
                id DESC
        """
        params: list[Any] = [board_slug]
        if limit > 0:
            query += " LIMIT ?"
            params.append(limit)
        cards = [self._card_from_row(row) for row in conn.execute(query, params)]
        cards, done_card_count, done_cards_hidden_count = self._limit_done_cards(
            cards,
            done_limit,
        )
        participants = self._overview_participants(conn, board_slug)
        self._attach_dependency_links(conn, cards)
        self._attach_comment_counts(conn, cards)
        self._attach_affected_project_paths(cards, active_project)
        cards = self._cards_with_coordination(cards, participants)
        return (
            [self._overview_card(card) for card in cards],
            done_card_count,
            done_cards_hidden_count,
        )

    @staticmethod
    def _limit_done_cards(
        cards: list[dict[str, Any]],
        done_limit: int,
    ) -> tuple[list[dict[str, Any]], int, int]:
        done_card_count = sum(1 for card in cards if card.get("status") == "done")
        if done_limit < 0:
            return cards, done_card_count, 0

        limited: list[dict[str, Any]] = []
        shown_done = 0
        hidden_done = 0
        for card in cards:
            if card.get("status") != "done":
                limited.append(card)
                continue
            if shown_done < done_limit:
                limited.append(card)
                shown_done += 1
            else:
                hidden_done += 1
        return limited, done_card_count, hidden_done

    def _overview_participants(
        self,
        conn: sqlite3.Connection,
        board_slug: str,
    ) -> list[dict[str, Any]]:
        now = datetime.now(UTC)
        return [
            self._participant_from_row(row, now=now)
            for row in conn.execute(
                """
                SELECT * FROM participants
                WHERE current_board_slug = ? OR current_board_slug IS NULL
                """,
                (board_slug,),
            )
        ]

    def _attach_comment_counts(
        self,
        conn: sqlite3.Connection,
        cards: list[dict[str, Any]],
    ) -> None:
        if not cards:
            return
        by_id = {int(card["id"]): card for card in cards}
        placeholders = ", ".join("?" for _ in by_id)
        for row in conn.execute(
            f"""
            SELECT card_id, COUNT(*) AS count
            FROM card_comments
            WHERE card_id IN ({placeholders})
            GROUP BY card_id
            """,
            tuple(by_id),
        ):
            card = by_id.get(int(row["card_id"]))
            if card:
                card["comment_count"] = int(row["count"])

    @staticmethod
    def _archived_filter(*, include_archived: bool, archived_only: bool) -> str:
        if archived_only:
            return "AND archived_at IS NOT NULL"
        if include_archived:
            return ""
        return "AND archived_at IS NULL"

    def _archived_card_count(self, conn: sqlite3.Connection, board_slug: str) -> int:
        row = self._one(
            conn,
            "SELECT COUNT(*) AS count FROM cards WHERE board_slug = ? AND archived_at IS NOT NULL",
            (board_slug,),
        )
        return int(row["count"] if row else 0)

    @staticmethod
    def _archived_notice(
        archived_count: int,
        *,
        include_archived: bool,
        archived_only: bool,
    ) -> str:
        if not archived_count:
            return ""
        if archived_only:
            return f"Showing only {archived_count} archived card(s)."
        if include_archived:
            return f"Included {archived_count} archived card(s)."
        return (
            f"{archived_count} archived card(s) are hidden by default; search archived cards "
            "when older context may matter."
        )

    @staticmethod
    def _registration_hint(
        cwd: str | None,
        repo: str | None,
        matched_project: dict[str, Any] | None,
        resolution: dict[str, Any],
        requested_board_slug: str | None,
    ) -> str:
        if resolution.get("ambiguous"):
            reason = str(resolution.get("ambiguity_reason") or "Ambiguous project path match.")
            if requested_board_slug:
                return f"{reason} Using explicit board '{requested_board_slug}'."
            return (
                f"{reason} Pass an explicit board or fix registered project paths before "
                "using Kanban for implementation work."
            )
        if not (cwd or repo) or matched_project:
            return ""
        return (
            "No registered project path matched this cwd or repo. Register the repo or "
            "ecosystem before using Kanban for implementation work."
        )

    @staticmethod
    def _overview_card(card: dict[str, Any]) -> dict[str, Any]:
        keys = (
            "id",
            "external_id",
            "title",
            "description",
            "status",
            "priority",
            "owner_id",
            "assignee_id",
            "target_repo",
            "target_branch",
            "feature_branch",
            "worktree_path",
            "blocker_reason",
            "affected_paths",
            "affected_project_paths",
            "deployment_dispositions",
            "comment_count",
            "conflicts",
            "coordination_warnings",
            "dependency_warnings",
            "blocked_by_child_external_ids",
            "dependency_blocked",
            "parent_external_ids",
            "child_external_ids",
            "checks",
            "files_changed",
            "updated_at",
            "archived",
        )
        return {key: card.get(key) for key in keys}
