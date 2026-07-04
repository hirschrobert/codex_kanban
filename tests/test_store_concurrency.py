from __future__ import annotations

import asyncio
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from kanban_server.store import KanbanStore


class KanbanStoreConcurrencyTest(unittest.TestCase):
    def make_store(self) -> KanbanStore:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        return KanbanStore(Path(self.tmp.name) / "kanban.sqlite3")

    def register_demo_project(self, store: KanbanStore) -> None:
        store.register_project(
            {
                "slug": "demo",
                "display_name": "Demo",
                "board_slug": "demo",
                "card_prefix": "DM",
                "root_path": "/tmp/demo",
            }
        )

    def test_sqlite_connections_use_concurrency_pragmas(self) -> None:
        store = self.make_store()

        with store._connect() as conn:
            journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            busy_timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
            synchronous = conn.execute("PRAGMA synchronous").fetchone()[0]

        self.assertEqual(str(journal_mode).lower(), "wal")
        self.assertGreaterEqual(int(busy_timeout), 30_000)
        self.assertEqual(int(synchronous), 1)

    def test_async_store_methods_run_concurrent_sqlite_work(self) -> None:
        store = self.make_store()
        self.register_demo_project(store)

        async def write_events() -> dict[str, Any]:
            await asyncio.gather(
                *(
                    store.create_event_async(
                        {
                            "board_slug": "demo",
                            "event_type": f"async.{index:02d}",
                            "message": f"event {index}",
                        }
                    )
                    for index in range(20)
                )
            )
            return await store.list_events_async("demo", limit=50)

        page = asyncio.run(write_events())
        event_types = {event["event_type"] for event in page["events"]}

        self.assertTrue({f"async.{index:02d}" for index in range(20)} <= event_types)

    def test_separate_store_instances_support_concurrent_cli_writers(self) -> None:
        store = self.make_store()
        self.register_demo_project(store)
        db_path = store.db_path

        def create_card(index: int) -> str:
            local_store = KanbanStore(db_path)
            card = local_store.create_card(
                {
                    "board_slug": "demo",
                    "title": f"Concurrent card {index}",
                    "description": "Created from a separate store instance.",
                }
            )
            return str(card["external_id"])

        with ThreadPoolExecutor(max_workers=8) as executor:
            external_ids = list(executor.map(create_card, range(24)))

        snapshot = store.snapshot("demo")

        self.assertEqual(len(external_ids), 24)
        self.assertEqual(len(set(external_ids)), 24)
        self.assertEqual(
            len([card for card in snapshot["cards"] if card["title"].startswith("Concurrent")]),
            24,
        )


if __name__ == "__main__":
    unittest.main()
