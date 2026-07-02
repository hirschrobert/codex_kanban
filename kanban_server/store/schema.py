from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING

from .support import (
    DEFAULT_REPEAT_TIME,
    DEFAULT_REPEAT_TIMEZONE,
    LANES,
    LOCAL_COMMENT_AUTHOR_NAME,
    MAX_ACTIVE_IMPLEMENTERS_PER_PROJECT,
    utc_now,
)

if TYPE_CHECKING:
    from .contracts import StoreMixinContract as _StoreMixinContract
else:

    class _StoreMixinContract:
        pass


class SchemaStoreMixin(_StoreMixinContract):
    def _open_connection(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = self._open_connection()
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def migrate(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS boards (
                    slug TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS lanes (
                    board_slug TEXT NOT NULL,
                    status TEXT NOT NULL,
                    title TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    PRIMARY KEY (board_slug, status),
                    FOREIGN KEY (board_slug) REFERENCES boards(slug) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS projects (
                    slug TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    board_slug TEXT NOT NULL UNIQUE,
                    card_prefix TEXT NOT NULL DEFAULT '',
                    description TEXT NOT NULL DEFAULT '',
                    root_path TEXT NOT NULL DEFAULT '',
                    paths TEXT NOT NULL DEFAULT '[]',
                    instruction_paths TEXT NOT NULL DEFAULT '[]',
                    agent_profiles TEXT NOT NULL DEFAULT '[]',
                    max_active_implementers INTEGER NOT NULL DEFAULT 1,
                    removed_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (board_slug) REFERENCES boards(slug) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS participants (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'idle',
                    current_card_id INTEGER,
                    current_board_slug TEXT,
                    current_scope TEXT NOT NULL DEFAULT '',
                    last_seen_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (current_card_id) REFERENCES cards(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS cards (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    board_slug TEXT NOT NULL,
                    external_id TEXT,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    assignee_id TEXT,
                    owner_id TEXT,
                    created_by_id TEXT,
                    created_by_name TEXT NOT NULL DEFAULT 'local developer',
                    created_by_kind TEXT NOT NULL DEFAULT 'human',
                    intake_kind TEXT NOT NULL DEFAULT '',
                    intake_source TEXT NOT NULL DEFAULT '',
                    reported_by TEXT NOT NULL DEFAULT '',
                    impact TEXT NOT NULL DEFAULT '',
                    evidence TEXT NOT NULL DEFAULT '',
                    priority TEXT NOT NULL DEFAULT 'normal',
                    target_repo TEXT,
                    target_branch TEXT,
                    starting_target_sha TEXT,
                    handoff_target_sha TEXT,
                    feature_branch TEXT,
                    worktree_path TEXT,
                    blocker_reason TEXT,
                    parent_external_id TEXT,
                    child_external_ids TEXT NOT NULL DEFAULT '[]',
                    affected_paths TEXT NOT NULL DEFAULT '[]',
                    deployment_dispositions TEXT NOT NULL DEFAULT '[]',
                    files_changed TEXT NOT NULL DEFAULT '[]',
                    checks TEXT NOT NULL DEFAULT '[]',
                    assumptions TEXT NOT NULL DEFAULT '[]',
                    follow_up_cards TEXT NOT NULL DEFAULT '[]',
                    repeat_cadence TEXT NOT NULL DEFAULT 'none',
                    repeat_time TEXT NOT NULL DEFAULT '01:00',
                    repeat_timezone TEXT NOT NULL DEFAULT 'Europe/Berlin',
                    repeat_last_period TEXT,
                    repeat_last_created_card_id INTEGER,
                    repeat_next_run_at TEXT,
                    archived_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE (board_slug, external_id),
                    FOREIGN KEY (board_slug) REFERENCES boards(slug) ON DELETE CASCADE,
                    FOREIGN KEY (assignee_id) REFERENCES participants(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS card_links (
                    board_slug TEXT NOT NULL,
                    parent_card_id INTEGER NOT NULL,
                    child_card_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (parent_card_id, child_card_id),
                    FOREIGN KEY (board_slug) REFERENCES boards(slug) ON DELETE CASCADE,
                    FOREIGN KEY (parent_card_id) REFERENCES cards(id) ON DELETE CASCADE,
                    FOREIGN KEY (child_card_id) REFERENCES cards(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS card_comments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    board_slug TEXT NOT NULL,
                    card_id INTEGER NOT NULL,
                    participant_id TEXT,
                    author_name TEXT NOT NULL DEFAULT 'Unknown',
                    author_kind TEXT NOT NULL DEFAULT 'human',
                    body TEXT NOT NULL,
                    source_event_key TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (board_slug) REFERENCES boards(slug) ON DELETE CASCADE,
                    FOREIGN KEY (card_id) REFERENCES cards(id) ON DELETE CASCADE,
                    FOREIGN KEY (participant_id) REFERENCES participants(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS workflow_runs (
                    board_slug TEXT NOT NULL,
                    workflow_key TEXT NOT NULL,
                    scheduled_for TEXT NOT NULL,
                    card_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (board_slug, workflow_key, scheduled_for),
                    FOREIGN KEY (board_slug) REFERENCES boards(slug) ON DELETE CASCADE,
                    FOREIGN KEY (card_id) REFERENCES cards(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    board_slug TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    card_id INTEGER,
                    card_external_id TEXT,
                    participant_id TEXT,
                    message TEXT NOT NULL DEFAULT '',
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (board_slug) REFERENCES boards(slug) ON DELETE CASCADE,
                    FOREIGN KEY (card_id) REFERENCES cards(id) ON DELETE SET NULL,
                    FOREIGN KEY (participant_id) REFERENCES participants(id) ON DELETE SET NULL
                );

                CREATE INDEX IF NOT EXISTS idx_cards_board_status
                    ON cards(board_slug, status, updated_at);
                CREATE INDEX IF NOT EXISTS idx_events_board_created
                    ON events(board_slug, created_at);
                CREATE INDEX IF NOT EXISTS idx_participants_status
                    ON participants(status, last_seen_at);
                CREATE INDEX IF NOT EXISTS idx_card_links_board
                    ON card_links(board_slug, parent_card_id, child_card_id);
                CREATE INDEX IF NOT EXISTS idx_card_links_child
                    ON card_links(child_card_id);
                CREATE INDEX IF NOT EXISTS idx_card_comments_card
                    ON card_comments(card_id, id);
                CREATE INDEX IF NOT EXISTS idx_workflow_runs_card
                    ON workflow_runs(card_id);
                """)
            self._ensure_column(conn, "projects", "removed_at", "TEXT")
            self._ensure_column(
                conn,
                "projects",
                "max_active_implementers",
                f"INTEGER NOT NULL DEFAULT {MAX_ACTIVE_IMPLEMENTERS_PER_PROJECT}",
            )
            self._ensure_column(conn, "cards", "owner_id", "TEXT")
            self._ensure_column(conn, "cards", "created_by_id", "TEXT")
            self._ensure_column(
                conn,
                "cards",
                "created_by_name",
                f"TEXT NOT NULL DEFAULT '{LOCAL_COMMENT_AUTHOR_NAME}'",
            )
            self._ensure_column(
                conn,
                "cards",
                "created_by_kind",
                "TEXT NOT NULL DEFAULT 'human'",
            )
            self._ensure_column(
                conn,
                "cards",
                "intake_kind",
                "TEXT NOT NULL DEFAULT ''",
            )
            self._ensure_column(
                conn,
                "cards",
                "intake_source",
                "TEXT NOT NULL DEFAULT ''",
            )
            self._ensure_column(
                conn,
                "cards",
                "reported_by",
                "TEXT NOT NULL DEFAULT ''",
            )
            self._ensure_column(
                conn,
                "cards",
                "impact",
                "TEXT NOT NULL DEFAULT ''",
            )
            self._ensure_column(
                conn,
                "cards",
                "evidence",
                "TEXT NOT NULL DEFAULT ''",
            )
            self._ensure_column(
                conn,
                "cards",
                "affected_paths",
                "TEXT NOT NULL DEFAULT '[]'",
            )
            self._ensure_column(
                conn,
                "cards",
                "deployment_dispositions",
                "TEXT NOT NULL DEFAULT '[]'",
            )
            self._ensure_column(conn, "cards", "repeat_cadence", "TEXT NOT NULL DEFAULT 'none'")
            self._ensure_column(
                conn,
                "cards",
                "repeat_time",
                f"TEXT NOT NULL DEFAULT '{DEFAULT_REPEAT_TIME}'",
            )
            self._ensure_column(
                conn,
                "cards",
                "repeat_timezone",
                f"TEXT NOT NULL DEFAULT '{DEFAULT_REPEAT_TIMEZONE}'",
            )
            self._ensure_column(conn, "cards", "repeat_last_period", "TEXT")
            self._ensure_column(conn, "cards", "repeat_last_created_card_id", "INTEGER")
            self._ensure_column(conn, "cards", "repeat_next_run_at", "TEXT")
            self._ensure_column(conn, "cards", "archived_at", "TEXT")
            self._ensure_column(
                conn,
                "card_comments",
                "author_name",
                "TEXT NOT NULL DEFAULT 'Unknown'",
            )
            self._ensure_column(
                conn,
                "card_comments",
                "author_kind",
                "TEXT NOT NULL DEFAULT 'human'",
            )
            self._ensure_column(conn, "card_comments", "source_event_key", "TEXT")
            conn.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_card_comments_source_event
                    ON card_comments(board_slug, card_id, source_event_key)
                    WHERE source_event_key IS NOT NULL AND source_event_key != ''
                """)
            self._backfill_card_people(conn)
            self._backfill_card_links(conn)
            conn.commit()

    @staticmethod
    def _backfill_card_people(conn: sqlite3.Connection) -> None:
        conn.execute("""
            UPDATE cards
            SET created_by_id = (
                SELECT events.participant_id
                FROM events
                WHERE events.card_id = cards.id
                  AND events.event_type = 'card.created'
                  AND events.participant_id IS NOT NULL
                  AND events.participant_id != ''
                ORDER BY events.id
                LIMIT 1
            )
            WHERE (created_by_id IS NULL OR created_by_id = '')
              AND EXISTS (
                SELECT 1
                FROM events
                WHERE events.card_id = cards.id
                  AND events.event_type = 'card.created'
                  AND events.participant_id IS NOT NULL
                  AND events.participant_id != ''
              )
            """)
        conn.execute(
            """
            UPDATE cards
            SET created_by_name = COALESCE(
                    (
                        SELECT participants.display_name
                        FROM participants
                        WHERE participants.id = cards.created_by_id
                    ),
                    NULLIF(created_by_id, ''),
                    ?
                ),
                created_by_kind = COALESCE(
                    (
                        SELECT participants.kind
                        FROM participants
                        WHERE participants.id = cards.created_by_id
                    ),
                    NULLIF(created_by_kind, ''),
                    'human'
                )
            WHERE created_by_name IS NULL
               OR created_by_name = ''
               OR created_by_name = ?
            """,
            (LOCAL_COMMENT_AUTHOR_NAME, LOCAL_COMMENT_AUTHOR_NAME),
        )
        conn.execute(
            """
            UPDATE cards
            SET owner_id = COALESCE(
                NULLIF(assignee_id, ''),
                NULLIF(created_by_id, ''),
                ?
            )
            WHERE owner_id IS NULL OR owner_id = ''
            """,
            (LOCAL_COMMENT_AUTHOR_NAME,),
        )

    def reset(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript("""
                DELETE FROM events;
                DELETE FROM workflow_runs;
                DELETE FROM card_links;
                DELETE FROM card_comments;
                DELETE FROM cards;
                DELETE FROM participants;
                DELETE FROM projects;
                DELETE FROM lanes;
                DELETE FROM boards;
                DELETE FROM sqlite_sequence WHERE name IN ('cards', 'events', 'card_comments');
                """)
            conn.commit()

    def ensure_board(
        self,
        slug: str,
        title: str | None = None,
        *,
        conn: sqlite3.Connection | None = None,
    ) -> None:
        owns_conn = conn is None
        active = conn or self._open_connection()
        try:
            now = utc_now()
            active.execute(
                """
                INSERT INTO boards (slug, title, description, created_at, updated_at)
                VALUES (?, ?, '', ?, ?)
                ON CONFLICT(slug) DO NOTHING
                """,
                (slug, title or slug.replace("-", " ").title(), now, now),
            )
            for lane in LANES:
                active.execute(
                    """
                    INSERT INTO lanes (board_slug, status, title, position)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(board_slug, status)
                    DO UPDATE SET title = excluded.title, position = excluded.position
                    """,
                    (slug, lane["status"], lane["title"], lane["position"]),
                )
            if owns_conn:
                active.commit()
        finally:
            if owns_conn:
                active.close()
