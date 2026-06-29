from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING, Any

from .support import (
    DEPENDENCY_ADVANCEMENT_STATUSES,
    DEPENDENCY_RESOLVED_STATUSES,
    _json_dumps,
    _normalise_list,
    utc_now,
)

if TYPE_CHECKING:
    from .contracts import StoreMixinContract as _StoreMixinContract
else:

    class _StoreMixinContract:
        pass


class DependencyStoreMixin(_StoreMixinContract):
    @staticmethod
    def _payload_has_link_updates(payload: dict[str, Any]) -> bool:
        return any(
            field in payload
            for field in (
                "parent_external_id",
                "parent_external_ids",
                "child_external_ids",
            )
        )

    def _sync_card_links(
        self,
        conn: sqlite3.Connection,
        card_id: int,
        payload: dict[str, Any],
        *,
        creating: bool = False,
    ) -> None:
        if not creating and not self._payload_has_link_updates(payload):
            return
        card = self._one(
            conn, "SELECT id, board_slug, external_id FROM cards WHERE id = ?", (card_id,)
        )
        if not card:
            raise KeyError(f"card {card_id} not found")
        board_slug = card["board_slug"]
        touched_ids = {card_id}

        if creating or "parent_external_id" in payload or "parent_external_ids" in payload:
            conn.execute("DELETE FROM card_links WHERE child_card_id = ?", (card_id,))
            for parent_id in self._link_card_ids(
                conn,
                board_slug,
                self._parent_link_values(payload),
                current_card_id=card_id,
                direction="parent",
            ):
                self._insert_card_link(conn, board_slug, parent_id, card_id)
                touched_ids.add(parent_id)

        if creating or "child_external_ids" in payload:
            conn.execute("DELETE FROM card_links WHERE parent_card_id = ?", (card_id,))
            for child_id in self._link_card_ids(
                conn,
                board_slug,
                _normalise_list(payload.get("child_external_ids")),
                current_card_id=card_id,
                direction="child",
            ):
                self._insert_card_link(conn, board_slug, card_id, child_id)
                touched_ids.add(child_id)

        for touched_id in touched_ids:
            self._refresh_card_dependency_columns(conn, touched_id)

    @staticmethod
    def _parent_link_values(payload: dict[str, Any]) -> list[Any]:
        values: list[Any] = []
        if "parent_external_ids" in payload:
            values.extend(_normalise_list(payload.get("parent_external_ids")))
        elif "parent_external_id" in payload:
            values.extend(_normalise_list(payload.get("parent_external_id")))
        return values

    def _link_card_ids(
        self,
        conn: sqlite3.Connection,
        board_slug: str,
        values: list[Any],
        *,
        current_card_id: int,
        direction: str,
    ) -> list[int]:
        card_ids: list[int] = []
        seen: set[int] = set()
        for value in values:
            external_id = self._clean_text(value)
            if not external_id:
                continue
            row = self._one(
                conn,
                "SELECT id FROM cards WHERE board_slug = ? AND external_id = ?",
                (board_slug, external_id),
            )
            if not row:
                raise KeyError(
                    f"{direction} dependency card {external_id} not found on board {board_slug}"
                )
            dependency_id = int(row["id"])
            if dependency_id == current_card_id:
                raise ValueError("a card cannot depend on itself")
            if dependency_id in seen:
                continue
            seen.add(dependency_id)
            card_ids.append(dependency_id)
        return card_ids

    def _insert_card_link(
        self,
        conn: sqlite3.Connection,
        board_slug: str,
        parent_card_id: int,
        child_card_id: int,
    ) -> None:
        if self._card_link_creates_cycle(conn, parent_card_id, child_card_id):
            raise ValueError("card dependency would create a cycle")
        conn.execute(
            """
            INSERT OR IGNORE INTO card_links (
                board_slug, parent_card_id, child_card_id, created_at
            )
            VALUES (?, ?, ?, ?)
            """,
            (board_slug, parent_card_id, child_card_id, utc_now()),
        )

    def _card_link_creates_cycle(
        self,
        conn: sqlite3.Connection,
        parent_card_id: int,
        child_card_id: int,
    ) -> bool:
        if parent_card_id == child_card_id:
            return True
        row = self._one(
            conn,
            """
            WITH RECURSIVE descendants(id) AS (
                SELECT child_card_id
                FROM card_links
                WHERE parent_card_id = ?
                UNION
                SELECT links.child_card_id
                FROM card_links links
                JOIN descendants ON links.parent_card_id = descendants.id
            )
            SELECT 1 FROM descendants WHERE id = ? LIMIT 1
            """,
            (child_card_id, parent_card_id),
        )
        return bool(row)

    def _refresh_card_dependency_columns(
        self,
        conn: sqlite3.Connection,
        card_id: int,
    ) -> None:
        parents = [
            row["external_id"]
            for row in conn.execute(
                """
                SELECT parent.external_id
                FROM card_links links
                JOIN cards parent ON parent.id = links.parent_card_id
                WHERE links.child_card_id = ?
                ORDER BY parent.external_id
                """,
                (card_id,),
            )
        ]
        children = [
            row["external_id"]
            for row in conn.execute(
                """
                SELECT child.external_id
                FROM card_links links
                JOIN cards child ON child.id = links.child_card_id
                WHERE links.parent_card_id = ?
                ORDER BY child.external_id
                """,
                (card_id,),
            )
        ]
        conn.execute(
            """
            UPDATE cards
            SET parent_external_id = ?, child_external_ids = ?
            WHERE id = ?
            """,
            (parents[0] if parents else None, _json_dumps(children), card_id),
        )

    def _assert_dependencies_allow_status(
        self,
        conn: sqlite3.Connection,
        card_id: int,
        status: str,
    ) -> None:
        if status not in DEPENDENCY_ADVANCEMENT_STATUSES:
            return
        unresolved = self._unresolved_child_dependencies(conn, card_id)
        if not unresolved:
            return
        details = ", ".join(f"{item['external_id']} ({item['status']})" for item in unresolved)
        raise ValueError(
            f"card cannot advance to {status} until child dependencies are done: {details}"
        )

    def _unresolved_child_dependencies(
        self, conn: sqlite3.Connection, card_id: int
    ) -> list[dict[str, Any]]:
        return [
            {
                "id": int(row["id"]),
                "external_id": row["external_id"],
                "title": row["title"],
                "status": row["status"],
            }
            for row in conn.execute(
                """
                SELECT child.id, child.external_id, child.title, child.status
                FROM card_links links
                JOIN cards child ON child.id = links.child_card_id
                WHERE links.parent_card_id = ?
                  AND child.status NOT IN ({})
                ORDER BY child.external_id
                """.format(", ".join("?" for _ in DEPENDENCY_RESOLVED_STATUSES)),
                (card_id, *sorted(DEPENDENCY_RESOLVED_STATUSES)),
            )
        ]

    def _attach_dependency_links(
        self,
        conn: sqlite3.Connection,
        cards: list[dict[str, Any]],
    ) -> None:
        if not cards:
            return
        by_id = {int(card["id"]): card for card in cards}
        for card in cards:
            card["parent_dependencies"] = []
            card["child_dependencies"] = []

        placeholders = ", ".join("?" for _ in by_id)
        params = tuple(by_id)
        for row in conn.execute(
            f"""
            SELECT
                links.parent_card_id,
                links.child_card_id,
                parent.id AS parent_id,
                parent.external_id AS parent_external_id,
                parent.title AS parent_title,
                parent.status AS parent_status,
                child.id AS child_id,
                child.external_id AS child_external_id,
                child.title AS child_title,
                child.status AS child_status
            FROM card_links links
            JOIN cards parent ON parent.id = links.parent_card_id
            JOIN cards child ON child.id = links.child_card_id
            WHERE links.parent_card_id IN ({placeholders})
               OR links.child_card_id IN ({placeholders})
            """,
            (*params, *params),
        ):
            parent_id = int(row["parent_card_id"])
            child_id = int(row["child_card_id"])
            if child_id in by_id:
                by_id[child_id]["parent_dependencies"].append(
                    {
                        "id": int(row["parent_id"]),
                        "external_id": row["parent_external_id"],
                        "title": row["parent_title"],
                        "status": row["parent_status"],
                    }
                )
            if parent_id in by_id:
                by_id[parent_id]["child_dependencies"].append(
                    {
                        "id": int(row["child_id"]),
                        "external_id": row["child_external_id"],
                        "title": row["child_title"],
                        "status": row["child_status"],
                    }
                )

        for card in cards:
            parents = sorted(
                card["parent_dependencies"],
                key=lambda item: str(item.get("external_id") or ""),
            )
            children = sorted(
                card["child_dependencies"],
                key=lambda item: str(item.get("external_id") or ""),
            )
            card["parent_dependencies"] = parents
            card["child_dependencies"] = children
            card["parent_external_ids"] = [item["external_id"] for item in parents]
            card["parent_external_id"] = (
                card["parent_external_ids"][0] if card["parent_external_ids"] else None
            )
            card["child_external_ids"] = [item["external_id"] for item in children]
            unresolved = [
                item for item in children if item.get("status") not in DEPENDENCY_RESOLVED_STATUSES
            ]
            card["blocked_by_child_external_ids"] = [item["external_id"] for item in unresolved]
            card["dependency_blocked"] = bool(unresolved)
            if unresolved:
                details = ", ".join(
                    f"{item['external_id']} ({item['status']})" for item in unresolved
                )
                card["dependency_warnings"] = [
                    f"Waiting on child dependencies before advancing: {details}"
                ]
            else:
                card["dependency_warnings"] = []

    def _attach_card_comments(
        self,
        conn: sqlite3.Connection,
        cards: list[dict[str, Any]],
    ) -> None:
        if not cards:
            return
        by_id = {int(card["id"]): card for card in cards}
        for card in cards:
            card["comments"] = []
            card["comment_count"] = 0

        placeholders = ", ".join("?" for _ in by_id)
        for row in conn.execute(
            f"""
            SELECT *
            FROM card_comments
            WHERE card_id IN ({placeholders})
            ORDER BY id
            """,
            tuple(by_id),
        ):
            comment = self._card_comment_from_row(row)
            card = by_id.get(int(comment["card_id"]))
            if not card:
                continue
            card["comments"].append(comment)
            card["comment_count"] = len(card["comments"])

    def _backfill_card_links(self, conn: sqlite3.Connection) -> None:
        for row in conn.execute(
            "SELECT id, board_slug, parent_external_id, child_external_ids FROM cards"
        ):
            card_id = int(row["id"])
            board_slug = row["board_slug"]
            for parent_external_id in _normalise_list(row["parent_external_id"]):
                parent_id = self._dependency_id_for_backfill(conn, board_slug, parent_external_id)
                if parent_id and parent_id != card_id:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO card_links (
                            board_slug, parent_card_id, child_card_id, created_at
                        )
                        VALUES (?, ?, ?, ?)
                        """,
                        (board_slug, parent_id, card_id, utc_now()),
                    )
            for child_external_id in _normalise_list(row["child_external_ids"]):
                child_id = self._dependency_id_for_backfill(conn, board_slug, child_external_id)
                if child_id and child_id != card_id:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO card_links (
                            board_slug, parent_card_id, child_card_id, created_at
                        )
                        VALUES (?, ?, ?, ?)
                        """,
                        (board_slug, card_id, child_id, utc_now()),
                    )

    def _dependency_id_for_backfill(
        self,
        conn: sqlite3.Connection,
        board_slug: str,
        external_id: Any,
    ) -> int | None:
        cleaned = self._clean_text(external_id)
        if not cleaned:
            return None
        row = self._one(
            conn,
            "SELECT id FROM cards WHERE board_slug = ? AND external_id = ?",
            (board_slug, cleaned),
        )
        return int(row["id"]) if row else None

    def _resolve_card_id(
        self,
        conn: sqlite3.Connection,
        payload: dict[str, Any],
        *,
        board_slug: str,
        required: bool = False,
    ) -> int | None:
        if payload.get("current_card_id"):
            return self._card_id_on_board(
                conn, int(payload["current_card_id"]), board_slug=board_slug
            )
        if payload.get("card_id"):
            return self._card_id_on_board(conn, int(payload["card_id"]), board_slug=board_slug)
        external_id = self._clean_text(
            payload.get("current_card_external_id") or payload.get("card_external_id")
        )
        if external_id:
            row = self._one(
                conn,
                "SELECT id FROM cards WHERE board_slug = ? AND external_id = ?",
                (board_slug, external_id),
            )
            if row:
                return int(row["id"])
            raise KeyError(f"card {external_id} not found on board {board_slug}")
        if required:
            raise ValueError("card reference is incomplete")
        return None
