from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..git_worktrees import git_worktree_context
from .support import (
    DEFAULT_AI_AGENT_MANAGER_DISPLAY_NAME,
    DEFAULT_AI_AGENT_MANAGER_ROLE,
    DEFAULT_AI_AGENT_MANAGER_SUFFIX,
    DEFAULT_CODEX_SUBAGENTS_DISPLAY_NAME,
    DEFAULT_CODEX_SUBAGENTS_ROLE,
    DEFAULT_CODEX_SUBAGENTS_SUFFIX,
    GENERIC_AGENT_PROFILES,
    MAX_ACTIVE_IMPLEMENTERS_PER_PROJECT,
    _json_dumps,
    _json_loads,
    _normalise_list,
    agent_profile_id,
    discover_default_agent_profiles,
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
            agent_profiles = self._project_agent_profiles(
                root_path,
                paths,
                payload.get("agent_profiles"),
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

    def refresh_project_agents(self, board_slug: str) -> dict[str, Any] | None:
        board_slug = slugify(board_slug)
        with self._lock, self._connect() as conn:
            project = self._active_project_for_board(conn, board_slug)
            if not project:
                return None
            return self._refresh_project_agents(conn, project)

    def default_board_slug(self) -> str:
        with self._lock, self._connect() as conn:
            return self._default_board_slug(conn)

    def list_projects(self, include_removed: bool = False) -> list[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            projects = self._list_projects(conn, include_removed=include_removed)
            return projects if include_removed else self._visible_projects(projects)

    def _visible_projects(self, projects: list[dict[str, Any]]) -> list[dict[str, Any]]:
        candidate_paths = {
            str(Path(candidate["path"]).expanduser().resolve()): str(project.get("slug"))
            for project in projects
            if not project.get("removed_at")
            for candidate in self._project_path_candidates(project)
        }
        visible: list[dict[str, Any]] = []
        for project in projects:
            root_path = str(project.get("root_path") or "").strip()
            context = git_worktree_context(root_path) if root_path else None
            primary_owner = candidate_paths.get(str(context["primary_root"])) if context else None
            if context and context["is_linked_worktree"]:
                if primary_owner and primary_owner != project.get("slug"):
                    continue
            visible.append(project)
        return visible

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

    def resolve_project_for_paths(self, paths: list[str | Path]) -> dict[str, Any]:
        query_paths: list[Path] = []
        seen_query_paths: set[str] = set()
        for path in paths:
            if not str(path).strip():
                continue
            query_path = Path(path).expanduser().resolve()
            if str(query_path) in seen_query_paths:
                continue
            seen_query_paths.add(str(query_path))
            query_paths.append(query_path)
        with self._lock, self._connect() as conn:
            projects = self._visible_projects(self._list_projects(conn, include_removed=False))

        matches: list[dict[str, Any]] = []
        winning_project_slugs: set[str] = set()
        ambiguous = False
        ambiguity_reason = ""
        for query_path in query_paths:
            query_matches: list[dict[str, Any]] = []
            context = git_worktree_context(query_path)
            identity_paths = [query_path]
            if context and context["is_linked_worktree"]:
                identity_paths.insert(0, context["primary_root"])
            for project in projects:
                for candidate in self._project_path_candidates(project):
                    candidate_path = Path(candidate["path"]).expanduser().resolve()
                    for identity_rank, identity_path in enumerate(identity_paths):
                        try:
                            identity_path.relative_to(candidate_path)
                        except ValueError:
                            continue
                        query_matches.append(
                            {
                                "project": project,
                                "project_slug": project.get("slug"),
                                "board_slug": project.get("board_slug"),
                                "display_name": project.get("display_name"),
                                "query_path": str(query_path),
                                "identity_path": str(identity_path),
                                "matched_path": str(candidate_path),
                                "label": candidate["label"],
                                "identity_rank": identity_rank,
                                "score": len(candidate_path.parts),
                            }
                        )
            matches.extend(query_matches)
            if not query_matches:
                continue
            best_rank = min(int(match["identity_rank"]) for match in query_matches)
            ranked_matches = [
                match for match in query_matches if int(match["identity_rank"]) == best_rank
            ]
            best_score = max(int(match["score"]) for match in ranked_matches)
            winners = [match for match in ranked_matches if int(match["score"]) == best_score]
            winner_slugs = {str(match["project_slug"]) for match in winners}
            if len(winner_slugs) > 1:
                ambiguous = True
                ambiguity_reason = (
                    "More than one registered project path matched the workspace equally."
                )
                winning_project_slugs.update(winner_slugs)
                continue
            winning_project_slugs.add(next(iter(winner_slugs)))

        if len(winning_project_slugs) > 1:
            ambiguous = True
            ambiguity_reason = (
                ambiguity_reason or "Workspace paths resolved to more than one registered project."
            )

        project = None
        if len(winning_project_slugs) == 1 and not ambiguous:
            slug = next(iter(winning_project_slugs))
            project = next((item for item in projects if item.get("slug") == slug), None)

        public_matches = [
            {key: value for key, value in match.items() if key != "project"} for match in matches
        ]
        return {
            "project": project,
            "matches": public_matches,
            "ambiguous": ambiguous,
            "ambiguity_reason": ambiguity_reason,
        }

    def project_for_path(self, path: str | Path) -> dict[str, Any] | None:
        return self.resolve_project_for_paths([path])["project"]

    @staticmethod
    def _project_path_candidates(project: dict[str, Any]) -> list[dict[str, str]]:
        candidates: list[dict[str, str]] = []
        seen_paths: set[str] = set()

        def add_candidate(label: str, path: str) -> None:
            if not path:
                return
            path_key = str(Path(path).expanduser().resolve())
            if path_key in seen_paths:
                return
            seen_paths.add(path_key)
            candidates.append({"label": label, "path": path})

        for item in project.get("paths", []):
            if isinstance(item, dict):
                path = str(item.get("path") or "").strip()
                label = str(item.get("label") or project.get("display_name") or path)
            else:
                path = str(item or "").strip()
                label = str(project.get("display_name") or path)
            add_candidate(label, path)
        add_candidate(
            str(project.get("display_name") or project.get("slug") or "root"),
            str(project.get("root_path") or "").strip(),
        )
        return candidates

    def _seed_project_agents(
        self, conn: sqlite3.Connection, board_slug: str, agent_profiles: list[Any]
    ) -> None:
        now = utc_now()
        participant_ids: set[str] = set()
        manager_id = slugify(f"{board_slug}-{DEFAULT_AI_AGENT_MANAGER_SUFFIX}")
        participant_ids.add(manager_id)
        self._seed_project_agent_manager(conn, board_slug, manager_id, now)
        native_subagents_id = slugify(f"{board_slug}-{DEFAULT_CODEX_SUBAGENTS_SUFFIX}")
        participant_ids.add(native_subagents_id)
        self._seed_project_native_subagents(conn, board_slug, native_subagents_id, now)
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

    @staticmethod
    def _seed_project_agent_manager(
        conn: sqlite3.Connection,
        board_slug: str,
        manager_id: str,
        now: str,
    ) -> None:
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
                manager_id,
                DEFAULT_AI_AGENT_MANAGER_DISPLAY_NAME,
                DEFAULT_AI_AGENT_MANAGER_ROLE,
                board_slug,
                now,
                now,
                now,
            ),
        )

    @staticmethod
    def _seed_project_native_subagents(
        conn: sqlite3.Connection,
        board_slug: str,
        participant_id: str,
        now: str,
    ) -> None:
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
                DEFAULT_CODEX_SUBAGENTS_DISPLAY_NAME,
                DEFAULT_CODEX_SUBAGENTS_ROLE,
                board_slug,
                now,
                now,
                now,
            ),
        )

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

    def _refresh_project_agents(
        self,
        conn: sqlite3.Connection,
        project: dict[str, Any],
    ) -> dict[str, Any]:
        board_slug = str(project["board_slug"])
        agent_profiles = self._project_agent_profiles(
            project.get("root_path"),
            project.get("paths", []),
            project.get("agent_profiles", []),
        )
        now = utc_now()
        conn.execute(
            """
            UPDATE projects
            SET agent_profiles = ?, updated_at = ?
            WHERE slug = ?
            """,
            (_json_dumps(agent_profiles), now, project["slug"]),
        )
        self._seed_project_agents(conn, board_slug, agent_profiles)
        row = self._one(conn, "SELECT * FROM projects WHERE slug = ?", (project["slug"],))
        refreshed = self._project_from_row(row)
        if not refreshed:
            raise KeyError(f"project {project['slug']} not found")
        return {
            "project": refreshed,
            "agent_profiles": agent_profiles,
            "participant_ids": [
                slugify(f"{board_slug}-{DEFAULT_AI_AGENT_MANAGER_SUFFIX}"),
                slugify(f"{board_slug}-{DEFAULT_CODEX_SUBAGENTS_SUFFIX}"),
                *(
                    slugify(f"{board_slug}-{profile}")
                    for profile in agent_profiles
                    if agent_profile_id(profile)
                ),
            ],
        }

    @staticmethod
    def _project_agent_profiles(
        root_path: str | Path | None,
        paths: list[Any] | None,
        *groups: Any,
    ) -> list[str]:
        return merge_agent_profiles(
            list(GENERIC_AGENT_PROFILES),
            discover_default_agent_profiles(),
            *groups,
            discover_project_agent_profiles(root_path, paths),
        )
