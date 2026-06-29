from __future__ import annotations

import re
import sqlite3
from calendar import monthrange
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .support import (
    DEFAULT_REPEAT_TIME,
    DEFAULT_REPEAT_TIMEZONE,
    REPEAT_CADENCES,
    _normalise_list,
    _utc_datetime,
    slugify,
    utc_now,
)

if TYPE_CHECKING:
    from .contracts import StoreMixinContract as _StoreMixinContract
else:

    class _StoreMixinContract:
        pass


class WorkflowStoreMixin(_StoreMixinContract):
    def start_workflow(self, payload: dict[str, Any]) -> dict[str, Any]:
        workflow_key = slugify(str(payload.get("workflow_key") or payload.get("key") or ""))
        if not workflow_key:
            raise ValueError("workflow_key is required")
        scheduled_for = self._clean_text(payload.get("scheduled_for")) or utc_now()[:10]
        target_branch = self._clean_text(payload.get("target_branch"))
        if not target_branch:
            raise ValueError("target_branch is required for workflow-start")

        with self._lock, self._connect() as conn:
            board_slug = (
                slugify(str(payload["board_slug"]))
                if payload.get("board_slug")
                else self._default_board_slug(conn)
            )
            self.ensure_board(board_slug, conn=conn)
            project = self._active_project_for_board(conn, board_slug)
            if not project:
                raise ValueError("workflow-start requires an active registered project board")
            existing = self._workflow_run(conn, board_slug, workflow_key, scheduled_for)
            if existing:
                card = self.get_card(int(existing["card_id"]))
                if card:
                    return {
                        "created": False,
                        "workflow_run": dict(existing),
                        "card": card,
                    }

        title = self._clean_text(payload.get("title")) or f"Run workflow {workflow_key}"
        description = self._clean_text(payload.get("description")) or (
            f"Run recurring workflow `{workflow_key}` for {scheduled_for}."
        )
        card_payload = {
            "board_slug": board_slug,
            "title": title,
            "description": description,
            "status": self._clean_text(payload.get("status")) or "ready",
            "priority": self._clean_text(payload.get("priority")) or "normal",
            "owner_id": self._clean_text(payload.get("owner_id")),
            "actor_id": self._clean_text(payload.get("actor_id") or payload.get("participant_id")),
            "created_by_id": self._clean_text(payload.get("created_by_id")),
            "created_by_name": self._clean_text(payload.get("created_by_name")),
            "created_by_kind": self._clean_text(payload.get("created_by_kind")),
            "assignee_id": self._clean_text(payload.get("assignee_id")),
            "target_repo": self._clean_text(payload.get("target_repo"))
            or (project or {}).get("root_path"),
            "target_branch": target_branch,
            "repeat_cadence": "none",
            "checks": _normalise_list(payload.get("checks")),
        }
        card = self.create_card(card_payload)

        with self._lock, self._connect() as conn:
            now = utc_now()
            try:
                conn.execute(
                    """
                    INSERT INTO workflow_runs (
                        board_slug, workflow_key, scheduled_for,
                        card_id, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (board_slug, workflow_key, scheduled_for, card["id"], now, now),
                )
                run = self._workflow_run(conn, board_slug, workflow_key, scheduled_for)
                if not run:
                    raise RuntimeError("workflow run insert did not return a row")
                return {
                    "created": True,
                    "workflow_run": dict(run),
                    "card": card,
                }
            except sqlite3.IntegrityError:
                existing = self._workflow_run(conn, board_slug, workflow_key, scheduled_for)
                existing_card = self.get_card(int(existing["card_id"])) if existing else None
                return {
                    "created": False,
                    "workflow_run": dict(existing) if existing else {},
                    "card": existing_card or card,
                }

    def run_due_repeating_cards(
        self,
        now: datetime | None = None,
        board_slug: str | None = None,
    ) -> list[dict[str, Any]]:
        now = now or datetime.now(UTC)
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)

        requested_board = slugify(board_slug) if board_slug else None
        with self._lock, self._connect() as conn:
            params: list[Any] = []
            board_filter = ""
            if requested_board:
                board_filter = "AND cards.board_slug = ?"
                params.append(requested_board)
            templates = [
                self._card_from_row(row)
                for row in conn.execute(
                    f"""
                    SELECT cards.*
                    FROM cards
                    JOIN projects
                      ON projects.board_slug = cards.board_slug
                     AND projects.removed_at IS NULL
                    WHERE cards.archived_at IS NULL
                      AND cards.repeat_cadence IN ('daily', 'weekly', 'monthly')
                      {board_filter}
                    ORDER BY cards.board_slug, cards.id
                    """,
                    tuple(params),
                )
            ]

        results: list[dict[str, Any]] = []
        for template in templates:
            decision = self._repeat_due_decision(template, now)
            if not decision:
                continue
            next_run_at = decision.get("next_run_at")
            if not decision.get("period"):
                with self._lock, self._connect() as conn:
                    conn.execute(
                        """
                        UPDATE cards
                        SET repeat_next_run_at = ?,
                            updated_at = ?
                        WHERE id = ?
                        """,
                        (next_run_at, utc_now(), template["id"]),
                    )
                continue

            due = str(decision["period"])
            workflow_key = slugify(f"repeat-{template['external_id'] or template['id']}")
            existing_unfinished = self._unfinished_workflow_run(
                template["board_slug"],
                workflow_key,
            )
            if existing_unfinished:
                existing_card = self.get_card(int(existing_unfinished["card_id"]))
                if not existing_card:
                    continue
                scheduled_label = self._repeat_scheduled_label(
                    template, decision.get("scheduled_at")
                )
                comment = self.add_card_comment(
                    int(existing_unfinished["card_id"]),
                    {
                        "author_name": "Codex Kanban scheduler",
                        "author_kind": "system",
                        "body": (
                            "Recurring schedule "
                            f"{scheduled_label} "
                            f"(period {due}) was due, but this workflow card is still "
                            f"{existing_card.get('status') if existing_card else 'unfinished'}. "
                            "No duplicate ready card was created."
                        ),
                    },
                )
                with self._lock, self._connect() as conn:
                    conn.execute(
                        """
                        UPDATE cards
                        SET repeat_last_period = ?,
                            repeat_last_created_card_id = ?,
                            repeat_next_run_at = ?,
                            updated_at = ?
                        WHERE id = ?
                        """,
                        (
                            due,
                            existing_unfinished["card_id"],
                            next_run_at,
                            utc_now(),
                            template["id"],
                        ),
                    )
                self.create_event(
                    {
                        "board_slug": template["board_slug"],
                        "event_type": "workflow.deferred",
                        "card_id": int(existing_unfinished["card_id"]),
                        "message": (
                            existing_card.get("title") if existing_card else template["title"]
                        ),
                        "metadata": {
                            "source_card_id": template["id"],
                            "source_external_id": template.get("external_id"),
                            "repeat_cadence": template.get("repeat_cadence"),
                            "scheduled_for": due,
                            "comment_id": comment["id"],
                        },
                    }
                )
                results.append(
                    {
                        "created": False,
                        "reused": True,
                        "workflow_run": dict(existing_unfinished),
                        "card": existing_card,
                        "comment": comment,
                    }
                )
                continue
            result = self.start_workflow(
                {
                    "board_slug": template["board_slug"],
                    "workflow_key": workflow_key,
                    "scheduled_for": due,
                    "title": template["title"],
                    "description": (
                        f"Scheduled from recurring card "
                        f"{template.get('external_id') or template['id']}.\n\n"
                        f"{template['description']}"
                    ),
                    "status": "ready",
                    "priority": template["priority"],
                    "owner_id": template.get("owner_id"),
                    "created_by_id": template.get("created_by_id"),
                    "created_by_name": template.get("created_by_name"),
                    "created_by_kind": template.get("created_by_kind"),
                    "assignee_id": template.get("assignee_id"),
                    "target_repo": template.get("target_repo"),
                    "target_branch": template.get("target_branch"),
                    "checks": template.get("checks", []),
                }
            )
            with self._lock, self._connect() as conn:
                conn.execute(
                    """
                    UPDATE cards
                    SET repeat_last_period = ?,
                        repeat_last_created_card_id = ?,
                        repeat_next_run_at = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        due,
                        result["card"]["id"],
                        next_run_at,
                        utc_now(),
                        template["id"],
                    ),
                )
            if result.get("created"):
                self.create_event(
                    {
                        "board_slug": result["card"]["board_slug"],
                        "event_type": "workflow.scheduled",
                        "card_id": result["card"]["id"],
                        "message": result["card"]["title"],
                        "metadata": {
                            "source_card_id": template["id"],
                            "source_external_id": template.get("external_id"),
                            "repeat_cadence": template.get("repeat_cadence"),
                            "scheduled_for": due,
                        },
                    }
                )
            results.append(result)
        return results

    def run_repeating_card_now(
        self,
        card_id: int,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = payload or {}
        with self._lock, self._connect() as conn:
            row = self._one(conn, "SELECT * FROM cards WHERE id = ?", (card_id,))
            if not row:
                raise KeyError(f"card {card_id} not found")
            template = self._card_from_row(row)
            if template.get("archived"):
                raise ValueError("archived repeating cards cannot be run")
            cadence = self._validate_repeat_cadence(template.get("repeat_cadence") or "none")
            if cadence == "none":
                raise ValueError("run-now requires a repeating card")
            self._validate_repeat_target_branch(cadence, template.get("target_branch"))
            self._validate_repeat_project_gate(conn, template["board_slug"], cadence)

        manual_for = "manual-" + datetime.now(UTC).isoformat(timespec="microseconds").replace(
            "+00:00", "Z"
        )
        workflow_key = f"repeat-{template['external_id'] or template['id']}"
        actor_id = self._clean_text(payload.get("actor_id") or payload.get("participant_id"))
        result = self.start_workflow(
            {
                "board_slug": template["board_slug"],
                "workflow_key": workflow_key,
                "scheduled_for": manual_for,
                "title": template["title"],
                "description": (
                    f"Manually started from recurring card "
                    f"{template.get('external_id') or template['id']}.\n\n"
                    f"{template['description']}"
                ),
                "status": "ready",
                "priority": template["priority"],
                "owner_id": template.get("owner_id"),
                "actor_id": actor_id,
                "created_by_id": None if actor_id else template.get("created_by_id"),
                "created_by_name": None if actor_id else template.get("created_by_name"),
                "created_by_kind": None if actor_id else template.get("created_by_kind"),
                "assignee_id": template.get("assignee_id"),
                "target_repo": template.get("target_repo"),
                "target_branch": template.get("target_branch"),
                "checks": template.get("checks", []),
            }
        )
        if result.get("created"):
            self.create_event(
                {
                    "board_slug": result["card"]["board_slug"],
                    "event_type": "workflow.manual",
                    "card_id": result["card"]["id"],
                    "participant_id": actor_id,
                    "message": result["card"]["title"],
                    "metadata": {
                        "source_card_id": template["id"],
                        "source_external_id": template.get("external_id"),
                        "repeat_cadence": template.get("repeat_cadence"),
                        "scheduled_for": manual_for,
                    },
                }
            )
        return result

    def due_workflow_cards(
        self,
        board_slug: str | None = None,
        *,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            params: list[Any] = []
            board_filter = ""
            if board_slug:
                board_filter = "AND cards.board_slug = ?"
                params.append(slugify(board_slug))
            limit_clause = ""
            if limit is not None and limit > 0:
                limit_clause = "LIMIT ?"
                params.append(int(limit))
            cards = [
                self._card_from_row(row)
                for row in conn.execute(
                    f"""
                    SELECT
                        cards.*,
                        workflow_runs.workflow_key AS workflow_key,
                        workflow_runs.scheduled_for AS workflow_scheduled_for,
                        workflow_runs.created_at AS workflow_created_at
                    FROM workflow_runs
                    JOIN cards ON cards.id = workflow_runs.card_id
                    JOIN projects
                      ON projects.board_slug = cards.board_slug
                     AND projects.removed_at IS NULL
                    WHERE cards.status = 'ready'
                      AND cards.archived_at IS NULL
                      {board_filter}
                    ORDER BY workflow_runs.created_at, workflow_runs.scheduled_for, cards.id
                    {limit_clause}
                    """,
                    tuple(params),
                )
            ]
            self._attach_dependency_links(conn, cards)
            self._attach_card_comments(conn, cards)
            return cards

    def _workflow_run(
        self,
        conn: sqlite3.Connection,
        board_slug: str,
        workflow_key: str,
        scheduled_for: str,
    ) -> sqlite3.Row | None:
        return self._one(
            conn,
            """
            SELECT * FROM workflow_runs
            WHERE board_slug = ? AND workflow_key = ? AND scheduled_for = ?
            """,
            (board_slug, workflow_key, scheduled_for),
        )

    def _unfinished_workflow_run(
        self,
        board_slug: str,
        workflow_key: str,
    ) -> dict[str, Any] | None:
        with self._lock, self._connect() as conn:
            row = self._one(
                conn,
                """
                SELECT workflow_runs.*
                FROM workflow_runs
                JOIN cards ON cards.id = workflow_runs.card_id
                WHERE workflow_runs.board_slug = ?
                  AND workflow_runs.workflow_key = ?
                  AND cards.archived_at IS NULL
                  AND cards.status != 'done'
                ORDER BY workflow_runs.created_at, workflow_runs.scheduled_for
                LIMIT 1
                """,
                (board_slug, workflow_key),
            )
            return dict(row) if row else None

    def _repeat_settings_from_payload(
        self,
        payload: dict[str, Any],
        *,
        target_branch: str | None,
    ) -> tuple[str, str, str]:
        cadence = self._validate_repeat_cadence(
            self._clean_text(payload.get("repeat_cadence")) or "none"
        )
        repeat_time = self._validate_repeat_time(
            self._clean_text(payload.get("repeat_time")) or DEFAULT_REPEAT_TIME
        )
        timezone_name = self._validate_repeat_timezone(
            self._clean_text(payload.get("repeat_timezone")) or DEFAULT_REPEAT_TIMEZONE
        )
        self._validate_repeat_target_branch(cadence, target_branch)
        return cadence, repeat_time, timezone_name

    def _repeat_due_decision(
        self,
        card: dict[str, Any],
        now: datetime,
    ) -> dict[str, Any] | None:
        cadence = self._validate_repeat_cadence(card.get("repeat_cadence") or "none")
        if cadence == "none":
            return None
        self._validate_repeat_target_branch(cadence, card.get("target_branch"))
        repeat_time = self._validate_repeat_time(card.get("repeat_time") or DEFAULT_REPEAT_TIME)
        timezone_name = self._validate_repeat_timezone(
            card.get("repeat_timezone") or DEFAULT_REPEAT_TIMEZONE
        )

        scheduled_at = _utc_datetime(self._clean_text(card.get("repeat_next_run_at")))
        if not scheduled_at:
            return {
                "next_run_at": self._first_repeat_run_at(
                    cadence,
                    repeat_time,
                    timezone_name,
                    now=now,
                )
            }
        scheduled_at = scheduled_at.astimezone(UTC)
        now = now.astimezone(UTC)
        if now < scheduled_at:
            return None

        next_run_at = self._advance_repeat_run_at(
            cadence,
            repeat_time,
            timezone_name,
            scheduled_at=scheduled_at,
            now=now,
        )
        period = self._repeat_period_for(card, scheduled_at)
        if card.get("repeat_last_period") == period:
            return {"next_run_at": next_run_at}
        return {
            "period": period,
            "next_run_at": next_run_at,
            "scheduled_at": self._format_utc(scheduled_at),
        }

    def _repeat_scheduled_label(self, card: dict[str, Any], scheduled_at: Any) -> str:
        scheduled = _utc_datetime(self._clean_text(scheduled_at))
        if not scheduled:
            return "unknown time"
        timezone_name = self._validate_repeat_timezone(
            card.get("repeat_timezone") or DEFAULT_REPEAT_TIMEZONE
        )
        return scheduled.astimezone(ZoneInfo(timezone_name)).strftime("%Y-%m-%d %H:%M %Z")

    def _first_repeat_run_at(
        self,
        cadence: Any,
        repeat_time: Any,
        timezone_name: Any,
        *,
        now: datetime | None = None,
    ) -> str | None:
        cadence = self._validate_repeat_cadence(cadence or "none")
        if cadence == "none":
            return None
        repeat_time = self._validate_repeat_time(repeat_time or DEFAULT_REPEAT_TIME)
        timezone_name = self._validate_repeat_timezone(timezone_name or DEFAULT_REPEAT_TIMEZONE)
        now = now or datetime.now(UTC)
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        zone = ZoneInfo(timezone_name)
        local_now = now.astimezone(zone)
        hour, minute = (int(part) for part in repeat_time.split(":", 1))

        if cadence in {"daily", "weekly"}:
            candidate = local_now.replace(
                hour=hour,
                minute=minute,
                second=0,
                microsecond=0,
            )
            if candidate <= local_now:
                candidate += timedelta(days=1 if cadence == "daily" else 7)
            return self._format_utc(candidate)

        candidate = self._monthly_candidate(local_now, hour, minute, months_ahead=0)
        if candidate <= local_now:
            candidate = self._monthly_candidate(local_now, hour, minute, months_ahead=1)
        return self._format_utc(candidate)

    def _advance_repeat_run_at(
        self,
        cadence: Any,
        repeat_time: Any,
        timezone_name: Any,
        *,
        scheduled_at: datetime,
        now: datetime,
    ) -> str:
        cadence = self._validate_repeat_cadence(cadence)
        repeat_time = self._validate_repeat_time(repeat_time or DEFAULT_REPEAT_TIME)
        timezone_name = self._validate_repeat_timezone(timezone_name or DEFAULT_REPEAT_TIMEZONE)
        zone = ZoneInfo(timezone_name)
        hour, minute = (int(part) for part in repeat_time.split(":", 1))
        local_now = now.astimezone(zone)
        candidate = scheduled_at.astimezone(zone).replace(
            hour=hour,
            minute=minute,
            second=0,
            microsecond=0,
        )
        while candidate <= local_now:
            if cadence == "daily":
                candidate += timedelta(days=1)
            elif cadence == "weekly":
                candidate += timedelta(days=7)
            else:
                candidate = self._add_month(candidate)
        return self._format_utc(candidate)

    def _repeat_period_for(self, card: dict[str, Any], scheduled_at: datetime) -> str:
        cadence = self._validate_repeat_cadence(card.get("repeat_cadence") or "none")
        timezone_name = self._validate_repeat_timezone(
            card.get("repeat_timezone") or DEFAULT_REPEAT_TIMEZONE
        )
        local_scheduled = scheduled_at.astimezone(ZoneInfo(timezone_name))
        if cadence == "daily":
            return local_scheduled.strftime("%Y-%m-%d")
        if cadence == "weekly":
            iso_year, iso_week, _ = local_scheduled.isocalendar()
            return f"{iso_year}-W{iso_week:02d}"
        return local_scheduled.strftime("%Y-%m")

    @staticmethod
    def _monthly_candidate(
        local_now: datetime,
        hour: int,
        minute: int,
        *,
        months_ahead: int,
    ) -> datetime:
        month_index = local_now.month - 1 + months_ahead
        year = local_now.year + month_index // 12
        month = month_index % 12 + 1
        day = min(local_now.day, monthrange(year, month)[1])
        return local_now.replace(
            year=year,
            month=month,
            day=day,
            hour=hour,
            minute=minute,
            second=0,
            microsecond=0,
        )

    @staticmethod
    def _add_month(value: datetime) -> datetime:
        month_index = value.month
        year = value.year + month_index // 12
        month = month_index % 12 + 1
        day = min(value.day, monthrange(year, month)[1])
        return value.replace(year=year, month=month, day=day)

    @staticmethod
    def _validate_repeat_cadence(value: Any) -> str:
        cadence = str(value or "none").strip().lower()
        if cadence not in REPEAT_CADENCES:
            raise ValueError(f"unsupported repeat cadence: {cadence}")
        return cadence

    @staticmethod
    def _validate_repeat_time(value: Any) -> str:
        text = str(value or DEFAULT_REPEAT_TIME).strip()
        if not re.fullmatch(r"\d{2}:\d{2}", text):
            raise ValueError("repeat_time must use HH:MM")
        hour, minute = (int(part) for part in text.split(":", 1))
        if hour > 23 or minute > 59:
            raise ValueError("repeat_time must use HH:MM")
        return text

    @staticmethod
    def _validate_repeat_timezone(value: Any) -> str:
        timezone_name = str(value or DEFAULT_REPEAT_TIMEZONE).strip()
        try:
            ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            raise ValueError(f"unknown repeat timezone: {timezone_name}") from None
        return timezone_name

    @staticmethod
    def _validate_repeat_target_branch(cadence: Any, target_branch: Any) -> None:
        if str(cadence or "none") != "none" and not str(target_branch or "").strip():
            raise ValueError("target_branch is required for repeating cards")

    @staticmethod
    def _bool_payload(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        return str(value).strip().lower() in {"1", "true", "yes", "on"}
