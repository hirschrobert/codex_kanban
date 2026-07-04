from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .contracts import StoreMixinContract as _StoreMixinContract
else:

    class _StoreMixinContract:
        pass


class EventRelationStoreMixin(_StoreMixinContract):
    def _attach_event_related_cards(
        self,
        conn: sqlite3.Connection,
        events: list[dict[str, Any]],
        *,
        board_slug: str,
    ) -> None:
        if not events:
            return
        refs_by_event = [self._event_card_refs(event) for event in events]
        card_ids = sorted({card_id for refs in refs_by_event for card_id in refs["ids"]})
        external_ids = sorted(
            {external_id for refs in refs_by_event for external_id in refs["external_ids"]}
        )
        cards_by_id: dict[int, dict[str, Any]] = {}
        cards_by_external_id: dict[str, dict[str, Any]] = {}
        if card_ids:
            placeholders = ",".join("?" for _ in card_ids)
            for row in conn.execute(
                f"""
                SELECT id, external_id, title, status, archived_at
                FROM cards
                WHERE board_slug = ? AND id IN ({placeholders})
                """,
                (board_slug, *card_ids),
            ):
                card = self._event_related_card_from_row(row)
                cards_by_id[int(card["id"])] = card
                cards_by_external_id[card["external_id"]] = card
        if external_ids:
            placeholders = ",".join("?" for _ in external_ids)
            for row in conn.execute(
                f"""
                SELECT id, external_id, title, status, archived_at
                FROM cards
                WHERE board_slug = ? AND external_id IN ({placeholders})
                """,
                (board_slug, *external_ids),
            ):
                card = self._event_related_card_from_row(row)
                cards_by_id[int(card["id"])] = card
                cards_by_external_id[card["external_id"]] = card

        for event, refs in zip(events, refs_by_event, strict=True):
            related_cards: list[dict[str, Any]] = []
            seen: set[int] = set()
            for card_id in refs["ids"]:
                card = cards_by_id.get(card_id)
                if card and int(card["id"]) not in seen:
                    related_cards.append(card)
                    seen.add(int(card["id"]))
            for external_id in refs["external_ids"]:
                card = cards_by_external_id.get(external_id)
                if card and int(card["id"]) not in seen:
                    related_cards.append(card)
                    seen.add(int(card["id"]))
            event["related_cards"] = related_cards

    @staticmethod
    def _event_related_card_from_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": int(row["id"]),
            "external_id": row["external_id"],
            "title": row["title"],
            "status": row["status"],
            "archived": bool(row["archived_at"]),
        }

    def _event_card_refs(self, event: dict[str, Any]) -> dict[str, list[Any]]:
        ids: list[int] = []
        external_ids: list[str] = []
        self._collect_event_card_ids(event.get("card_id"), ids)
        self._collect_event_card_external_ids(event.get("card_external_id"), external_ids)
        metadata = event.get("metadata")
        if isinstance(metadata, dict):
            for key in (
                "card_id",
                "card_ids",
                "current_card_id",
                "current_card_ids",
                "source_card_id",
                "source_card_ids",
                "target_card_id",
                "target_card_ids",
                "parent_card_id",
                "parent_card_ids",
                "child_card_id",
                "child_card_ids",
                "related_card_id",
                "related_card_ids",
                "deleted_card_id",
                "repeat_last_created_card_id",
            ):
                self._collect_event_card_ids(metadata.get(key), ids)
            for key in (
                "card_external_id",
                "card_external_ids",
                "current_card_external_id",
                "current_card_external_ids",
                "source_card_external_id",
                "source_card_external_ids",
                "source_external_id",
                "source_external_ids",
                "target_card_external_id",
                "target_card_external_ids",
                "parent_external_id",
                "parent_external_ids",
                "child_external_id",
                "child_external_ids",
                "related_card_external_id",
                "related_card_external_ids",
            ):
                self._collect_event_card_external_ids(metadata.get(key), external_ids)
            self._collect_event_card_objects(metadata.get("related_cards"), ids, external_ids)
        return {
            "ids": self._unique_ints(ids),
            "external_ids": self._unique_texts(external_ids),
        }

    def _collect_event_card_objects(
        self,
        value: Any,
        ids: list[int],
        external_ids: list[str],
    ) -> None:
        if isinstance(value, dict):
            self._collect_event_card_ids(value.get("id") or value.get("card_id"), ids)
            self._collect_event_card_external_ids(
                value.get("external_id") or value.get("card_external_id"),
                external_ids,
            )
            return
        if isinstance(value, (list, tuple, set)):
            for item in value:
                self._collect_event_card_objects(item, ids, external_ids)

    def _collect_event_card_ids(self, value: Any, ids: list[int]) -> None:
        if isinstance(value, (list, tuple, set)):
            for item in value:
                self._collect_event_card_ids(item, ids)
            return
        if isinstance(value, dict):
            self._collect_event_card_objects(value, ids, [])
            return
        if value in (None, ""):
            return
        try:
            card_id = int(value)
        except (TypeError, ValueError):
            return
        if card_id > 0:
            ids.append(card_id)

    def _collect_event_card_external_ids(self, value: Any, external_ids: list[str]) -> None:
        if isinstance(value, (list, tuple, set)):
            for item in value:
                self._collect_event_card_external_ids(item, external_ids)
            return
        if isinstance(value, dict):
            self._collect_event_card_objects(value, [], external_ids)
            return
        external_id = self._clean_text(value)
        if external_id:
            external_ids.append(external_id)

    @staticmethod
    def _unique_ints(values: list[int]) -> list[int]:
        result: list[int] = []
        seen: set[int] = set()
        for value in values:
            if value not in seen:
                result.append(value)
                seen.add(value)
        return result

    @staticmethod
    def _unique_texts(values: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            if value not in seen:
                result.append(value)
                seen.add(value)
        return result
