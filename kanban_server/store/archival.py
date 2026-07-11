from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from .support import DEFAULT_DONE_LOOKBACK_DAYS, slugify, utc_now

if TYPE_CHECKING:
    from .contracts import StoreMixinContract as _StoreMixinContract
else:

    class _StoreMixinContract:
        pass


class CardArchivalStoreMixin(_StoreMixinContract):
    def old_done_cards(
        self,
        board_slug: str,
        *,
        older_than_days: int = DEFAULT_DONE_LOOKBACK_DAYS,
    ) -> dict[str, Any]:
        days = self._validate_archive_age(older_than_days)
        cutoff = self._format_utc(datetime.now(UTC) - timedelta(days=days))
        with self._lock, self._connect() as conn:
            cards = [
                self._card_from_row(row)
                for row in conn.execute(
                    """
                    SELECT * FROM cards
                    WHERE board_slug = ? AND status = 'done' AND archived_at IS NULL
                      AND COALESCE(NULLIF(updated_at, ''), created_at) < ?
                    ORDER BY COALESCE(NULLIF(updated_at, ''), created_at), id
                    """,
                    (slugify(board_slug), cutoff),
                )
            ]
        return {"cards": cards, "count": len(cards), "cutoff": cutoff, "days": days}

    def archive_old_done_cards(
        self,
        board_slug: str,
        *,
        older_than_days: int = DEFAULT_DONE_LOOKBACK_DAYS,
        card_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        preview = self.old_done_cards(board_slug, older_than_days=older_than_days)
        eligible_ids = [int(card["id"]) for card in preview["cards"]]
        if card_ids is not None:
            requested_ids = {int(card_id) for card_id in card_ids}
            eligible_ids = [card_id for card_id in eligible_ids if card_id in requested_ids]
            preview["cards"] = [
                card for card in preview["cards"] if int(card["id"]) in requested_ids
            ]
            preview["count"] = len(eligible_ids)
        if not eligible_ids:
            return preview
        now = utc_now()
        placeholders = ", ".join("?" for _ in eligible_ids)
        with self._lock, self._connect() as conn:
            conn.execute(
                f"UPDATE cards SET archived_at = ?, updated_at = ? WHERE id IN ({placeholders})",
                (now, now, *eligible_ids),
            )
        return {**preview, "card_ids": eligible_ids, "archived_at": now}

    @staticmethod
    def _validate_archive_age(value: int) -> int:
        days = int(value)
        if days < 1 or days > 3650:
            raise ValueError("older_than_days must be between 1 and 3650")
        return days
