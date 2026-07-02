from __future__ import annotations

import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from kanban_server import project
from kanban_server.store import KanbanStore


class ProjectCliOverviewTest(unittest.TestCase):
    def make_db_path(self) -> Path:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        return Path(self.tmp.name) / "kanban.sqlite3"

    def make_git_repo(self, name: str = "repo") -> Path:
        repo = Path(self.tmp.name) / name
        repo.mkdir()
        subprocess.run(
            ["git", "init", str(repo)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return repo

    @staticmethod
    def capture_project_main(args: list[str]) -> str:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            project.main(args)
        return output.getvalue()

    def test_overview_lists_active_cards_and_archive_hint(self) -> None:
        db_path = self.make_db_path()
        store = KanbanStore(db_path)
        project_record = store.register_project(
            {
                "slug": "demo",
                "display_name": "Demo",
                "board_slug": "demo",
                "card_prefix": "DM",
                "root_path": "/workspace/demo",
                "paths": [{"label": "Demo App", "path": "/workspace/demo/app"}],
            }
        )
        active = store.create_card(
            {
                "board_slug": project_record["board_slug"],
                "title": "Visible startup card",
                "description": "The overview includes descriptions.",
                "affected_paths": ["/workspace/demo/app/main.py"],
            }
        )
        archived = store.create_card(
            {
                "board_slug": project_record["board_slug"],
                "title": "Archived startup card",
                "description": "Hidden unless requested.",
                "archived": True,
            }
        )

        overview = json.loads(
            self.capture_project_main(
                [
                    "overview",
                    "--db",
                    str(db_path),
                    "--cwd",
                    "/workspace/demo/app",
                ]
            )
        )
        archived_snapshot = json.loads(
            self.capture_project_main(
                [
                    "snapshot",
                    "--db",
                    str(db_path),
                    "--board",
                    "demo",
                    "--archived-only",
                ]
            )
        )

        self.assertEqual(overview["matched_project"]["slug"], "demo")
        self.assertEqual([card["id"] for card in overview["cards"]], [active["id"]])
        self.assertEqual(overview["cards"][0]["description"], "The overview includes descriptions.")
        self.assertEqual(overview["cards"][0]["affected_project_paths"][0]["label"], "Demo App")
        self.assertIn("archived", overview["archived_notice"])
        self.assertEqual([card["id"] for card in archived_snapshot["cards"]], [archived["id"]])

    def test_overview_done_limit_flag_controls_completed_cards(self) -> None:
        db_path = self.make_db_path()
        store = KanbanStore(db_path)
        project_record = store.register_project(
            {
                "slug": "demo",
                "display_name": "Demo",
                "board_slug": "demo",
                "card_prefix": "DM",
                "root_path": "/workspace/demo",
            }
        )
        active = store.create_card(
            {
                "board_slug": project_record["board_slug"],
                "title": "Active startup card",
                "description": "Active card.",
                "status": "in_progress",
            }
        )
        done_cards = [
            store.create_card(
                {
                    "board_slug": project_record["board_slug"],
                    "title": f"Done card {index}",
                    "description": "Done card.",
                    "status": "done",
                }
            )
            for index in range(6)
        ]

        overview = json.loads(
            self.capture_project_main(
                [
                    "overview",
                    "--db",
                    str(db_path),
                    "--board",
                    "demo",
                ]
            )
        )
        all_done = json.loads(
            self.capture_project_main(
                [
                    "overview",
                    "--db",
                    str(db_path),
                    "--board",
                    "demo",
                    "--done-limit",
                    "-1",
                ]
            )
        )

        self.assertEqual(overview["done_card_count"], 6)
        self.assertEqual(overview["done_cards_hidden_count"], 1)
        self.assertIn(active["id"], [card["id"] for card in overview["cards"]])
        self.assertEqual(
            [card["id"] for card in overview["cards"] if card["status"] == "done"],
            [card["id"] for card in reversed(done_cards[-5:])],
        )
        self.assertEqual(
            [card["id"] for card in all_done["cards"] if card["status"] == "done"],
            [card["id"] for card in reversed(done_cards)],
        )

    def test_overview_can_auto_register_single_repo_with_kanban_instructions(self) -> None:
        db_path = self.make_db_path()
        repo = self.make_git_repo("demo")
        (repo / "AGENTS.md").write_text(
            "Use codex-kanban for implementation work.\n",
            encoding="utf-8",
        )
        src = repo / "src"
        src.mkdir()

        overview = json.loads(
            self.capture_project_main(
                [
                    "overview",
                    "--db",
                    str(db_path),
                    "--cwd",
                    str(src),
                    "--repo",
                    str(repo),
                    "--register-if-missing",
                ]
            )
        )

        self.assertEqual(overview["matched_project"]["slug"], "demo")
        self.assertEqual(overview["registered_project"]["root_path"], str(repo))
        self.assertEqual(overview["registration_hint"], "")


if __name__ == "__main__":
    unittest.main()
