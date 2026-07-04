from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from kanban_server.store import KanbanStore


class KanbanStoreProjectCase(unittest.TestCase):
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
