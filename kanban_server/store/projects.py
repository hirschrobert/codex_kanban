from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .support import (
    GENERIC_AGENT_PROFILES,
    MAX_ACTIVE_IMPLEMENTERS_PER_PROJECT,
    _json_dumps,
    _json_loads,
    _normalise_list,
    agent_profile_id,
    discover_project_agent_profiles,
    merge_agent_profiles,
    slugify,
    utc_now,
)

if TYPE_CHECKING:
    from .contracts import StoreMixinContract as _StoreMixinContract
else:

    class _StoreMixinContract:
        pass


class ProjectStoreMixin(_StoreMixinContract):
    def register_project(
        self,
        payload: dict[str, Any],
        *,
        conn: sqlite3.Connection | None = None,
    ) -> dict[str, Any]:
        display_name = str(payload.get("display_name") or payload.get("title") or "").strip()
        slug = slugify(str(payload.get("slug") or display_name))
        if not display_name:
            raise ValueError("project display_name is required")

        board_slug = slugify(str(payload.get("board_slug") or slug))
        card_prefix = str(payload.get("card_prefix") or slug.split("-")[0]).strip().upper()
        owns_conn = conn is None
        active = conn or self._open_connection()
        try:
            existing = self._one(active, "SELECT * FROM projects WHERE slug = ?", (slug,))
            if existing and existing["board_slug"] != board_slug:
                self._migrate_project_board_slug(
                    active,
                    old_board_slug=existing["board_slug"],
                    new_board_slug=board_slug,
                    title=display_name,
                )
            self.ensure_board(board_slug, display_name, conn=active)
            now = utc_now()
            root_path = self._clean_text(payload.get("root_path")) or ""
            paths = _normalise_list(payload.get("paths"))
            instruction_paths = _normalise_list(payload.get("instruction_paths"))
            agent_profiles = merge_agent_profiles(
                payload.get("agent_profiles") or list(GENERIC_AGENT_PROFILES),
                discover_project_agent_profiles(root_path, paths),
            )
            values = {
                "slug": slug,
                "display_name": display_name,
                "board_slug": board_slug,
                "card_prefix": card_prefix[:12],
                "description": self._clean_text(payload.get("description")) or "",
                "root_path": root_path,
                "paths": _json_dumps(paths),
                "instruction_paths": _json_dumps(instruction_paths),
                "agent_profiles": _json_dumps(agent_profiles),
                "max_active_implementers": self._project_int_setting(
                    payload,
                    "max_active_implementers",
                    existing["max_active_implementers"] if existing else None,
                    MAX_ACTIVE_IMPLEMENTERS_PER_PROJECT,
                ),
                "removed_at": None,
                "created_at": existing["created_at"] if existing else now,
                "updated_at": now,
            }
            active.execute(
                """
                INSERT INTO projects (
                    slug, display_name, board_slug, card_prefix, description,
                    root_path, paths, instruction_paths, agent_profiles,
                    max_active_implementers, removed_at, created_at, updated_at
                )
                VALUES (
                    :slug, :display_name, :board_slug, :card_prefix, :description,
                    :root_path, :paths, :instruction_paths, :agent_profiles,
                    :max_active_implementers, :removed_at, :created_at, :updated_at
                )
                ON CONFLICT(slug) DO UPDATE SET
                    display_name = excluded.display_name,
                    board_slug = excluded.board_slug,
                    card_prefix = excluded.card_prefix,
                    description = excluded.description,
                    root_path = excluded.root_path,
                    paths = excluded.paths,
                    instruction_paths = excluded.instruction_paths,
                    agent_profiles = excluded.agent_profiles,
                    max_active_implementers = excluded.max_active_implementers,
                    removed_at = NULL,
                    updated_at = excluded.updated_at
                """,
                values,
            )
            active.execute(
                """
                UPDATE boards
                SET title = ?, description = ?, updated_at = ?
                WHERE slug = ?
                """,
                (display_name, values["description"], now, board_slug),
            )
            self._seed_project_agents(active, board_slug, _json_loads(values["agent_profiles"], []))
            if existing and existing["board_slug"] != board_slug:
                self._drop_unused_board(active, existing["board_slug"])
            if owns_conn:
                active.commit()
            row = self._one(active, "SELECT * FROM projects WHERE slug = ?", (slug,))
            project = self._project_from_row(row)
            if not project:
                raise KeyError(f"project {slug} not found")
            return project
        finally:
            if owns_conn:
                active.close()

    def default_board_slug(self) -> str:
        with self._lock, self._connect() as conn:
            return self._default_board_slug(conn)

    def list_projects(self, include_removed: bool = False) -> list[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            return self._list_projects(conn, include_removed=include_removed)

    def _migrate_project_board_slug(
        self,
        conn: sqlite3.Connection,
        *,
        old_board_slug: str,
        new_board_slug: str,
        title: str,
    ) -> None:
        owner = self._one(
            conn,
            "SELECT slug FROM projects WHERE board_slug = ?",
            (new_board_slug,),
        )
        if owner:
            raise ValueError(f"board_slug '{new_board_slug}' is already used by {owner['slug']}")

        self.ensure_board(new_board_slug, title, conn=conn)
        for table in ("cards", "card_links", "card_comments", "workflow_runs", "events"):
            conn.execute(
                f"UPDATE {table} SET board_slug = ? WHERE board_slug = ?",
                (new_board_slug, old_board_slug),
            )
        conn.execute(
            """
            UPDATE participants
            SET current_board_slug = ?
            WHERE current_board_slug = ?
            """,
            (new_board_slug, old_board_slug),
        )
        self._rename_board_scoped_participants(conn, old_board_slug, new_board_slug)

    def _rename_board_scoped_participants(
        self,
        conn: sqlite3.Connection,
        old_board_slug: str,
        new_board_slug: str,
    ) -> None:
        rows = list(
            conn.execute(
                "SELECT * FROM participants WHERE id = ? OR id LIKE ?",
                (old_board_slug, f"{old_board_slug}-%"),
            )
        )
        for row in rows:
            old_id = row["id"]
            suffix = old_id.removeprefix(old_board_slug).removeprefix("-")
            new_id = new_board_slug if not suffix else f"{new_board_slug}-{suffix}"
            if old_id == new_id:
                continue
            existing = self._one(conn, "SELECT 1 FROM participants WHERE id = ?", (new_id,))
            if not existing:
                values = dict(row)
                values["id"] = new_id
                values["current_board_slug"] = new_board_slug
                columns = ", ".join(values)
                placeholders = ", ".join("?" for _ in values)
                conn.execute(
                    f"INSERT INTO participants ({columns}) VALUES ({placeholders})",
                    tuple(values.values()),
                )
            self._replace_participant_references(conn, old_id, new_id)
            conn.execute("DELETE FROM participants WHERE id = ?", (old_id,))

    @staticmethod
    def _replace_participant_references(
        conn: sqlite3.Connection,
        old_id: str,
        new_id: str,
    ) -> None:
        conn.execute("UPDATE cards SET assignee_id = ? WHERE assignee_id = ?", (new_id, old_id))
        conn.execute("UPDATE cards SET owner_id = ? WHERE owner_id = ?", (new_id, old_id))
        conn.execute(
            "UPDATE cards SET created_by_id = ? WHERE created_by_id = ?",
            (new_id, old_id),
        )
        conn.execute(
            "UPDATE events SET participant_id = ? WHERE participant_id = ?",
            (new_id, old_id),
        )
        conn.execute(
            "UPDATE card_comments SET participant_id = ? WHERE participant_id = ?",
            (new_id, old_id),
        )

    def _drop_unused_board(self, conn: sqlite3.Connection, board_slug: str) -> None:
        if self._one(conn, "SELECT 1 FROM projects WHERE board_slug = ?", (board_slug,)):
            return
        referencing_tables = ("cards", "card_links", "card_comments", "workflow_runs", "events")
        for table in referencing_tables:
            if self._one(conn, f"SELECT 1 FROM {table} WHERE board_slug = ?", (board_slug,)):
                return
        conn.execute("DELETE FROM boards WHERE slug = ?", (board_slug,))

    def update_project_settings(self, slug: str, payload: dict[str, Any]) -> dict[str, Any]:
        project_slug = slugify(slug)
        with self._lock, self._connect() as conn:
            row = self._one(conn, "SELECT * FROM projects WHERE slug = ?", (project_slug,))
            if not row:
                raise KeyError(f"project {project_slug} not found")
            if "max_active_implementers" not in payload:
                raise ValueError("max_active_implementers is required")

            max_active_implementers = self._project_int_setting(
                payload,
                "max_active_implementers",
                row["max_active_implementers"],
                MAX_ACTIVE_IMPLEMENTERS_PER_PROJECT,
            )
            now = utc_now()
            conn.execute(
                """
                UPDATE projects
                SET max_active_implementers = ?, updated_at = ?
                WHERE slug = ?
                """,
                (max_active_implementers, now, project_slug),
            )
            updated = self._one(conn, "SELECT * FROM projects WHERE slug = ?", (project_slug,))
            project = self._project_from_row(updated)
            if not project:
                raise KeyError(f"project {project_slug} not found")
            return project

    def remove_project(self, slug: str) -> dict[str, Any]:
        project_slug = slugify(slug)
        with self._lock, self._connect() as conn:
            row = self._one(conn, "SELECT * FROM projects WHERE slug = ?", (project_slug,))
            if not row:
                raise KeyError(f"project {project_slug} not found")
            now = utc_now()
            conn.execute(
                "UPDATE projects SET removed_at = ?, updated_at = ? WHERE slug = ?",
                (now, now, project_slug),
            )
            updated = self._one(conn, "SELECT * FROM projects WHERE slug = ?", (project_slug,))
            project = self._project_from_row(updated)
            if not project:
                raise KeyError(f"project {project_slug} not found")
            return project

    def prune_project(self, slug: str) -> dict[str, Any]:
        project_slug = slugify(slug)
        with self._lock, self._connect() as conn:
            row = self._one(conn, "SELECT * FROM projects WHERE slug = ?", (project_slug,))
            if not row:
                raise KeyError(f"project {project_slug} not found")
            project = self._project_from_row(row)
            if not project:
                raise KeyError(f"project {project_slug} not found")
            board_slug = project["board_slug"]
            conn.execute(
                """
                DELETE FROM participants
                WHERE current_board_slug = ? OR id LIKE ?
                """,
                (board_slug, f"{board_slug}-%"),
            )
            conn.execute("DELETE FROM boards WHERE slug = ?", (board_slug,))
            return {
                "pruned": True,
                "slug": project_slug,
                "board_slug": board_slug,
            }

    def project_for_path(self, path: str | Path) -> dict[str, Any] | None:
        query_path = Path(path).resolve()
        with self._lock, self._connect() as conn:
            projects = self._list_projects(conn, include_removed=False)
        best: tuple[int, dict[str, Any]] | None = None
        for project in projects:
            candidates = [project.get("root_path") or ""]
            candidates.extend(item.get("path", "") for item in project.get("paths", []))
            for candidate in candidates:
                if not candidate:
                    continue
                try:
                    candidate_path = Path(candidate).resolve()
                    query_path.relative_to(candidate_path)
                except ValueError:
                    continue
                score = len(candidate_path.parts)
                if best is None or score > best[0]:
                    best = (score, project)
        return best[1] if best else None

    def _seed_project_agents(
        self, conn: sqlite3.Connection, board_slug: str, agent_profiles: list[Any]
    ) -> None:
        now = utc_now()
        participant_ids: set[str] = set()
        for profile in agent_profiles:
            profile_name = agent_profile_id(profile)
            if not profile_name:
                continue
            participant_id = slugify(f"{board_slug}-{profile_name}")
            participant_ids.add(participant_id)
            role = GENERIC_AGENT_PROFILES.get(
                profile_name,
                f"Project-scoped agent profile: {profile_name}",
            )
            conn.execute(
                """
                INSERT INTO participants (
                    id, kind, display_name, role, status, current_board_slug,
                    current_scope, last_seen_at, created_at, updated_at
                )
                VALUES (?, 'agent', ?, ?, 'idle', ?, '', ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    display_name = excluded.display_name,
                    role = excluded.role,
                    current_board_slug = excluded.current_board_slug,
                    updated_at = excluded.updated_at
                """,
                (
                    participant_id,
                    profile_name,
                    role,
                    board_slug,
                    now,
                    now,
                    now,
                ),
            )
        self._prune_removed_project_agents(conn, board_slug, participant_ids)

    def _prune_removed_project_agents(
        self, conn: sqlite3.Connection, board_slug: str, participant_ids: set[str]
    ) -> None:
        params: list[Any] = [board_slug, f"{board_slug}-%"]
        extra_filter = ""
        if participant_ids:
            placeholders = ", ".join("?" for _ in participant_ids)
            extra_filter = f"AND id NOT IN ({placeholders})"
            params.extend(sorted(participant_ids))
        conn.execute(
            f"""
            DELETE FROM participants
            WHERE current_board_slug = ?
              AND id LIKE ?
              AND kind = 'agent'
              AND current_card_id IS NULL
              {extra_filter}
            """,
            params,
        )
