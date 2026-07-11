from __future__ import annotations

import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from kanban_server import project
from kanban_server.project.git_ops import cleanup_merged_card_worktree
from kanban_server.store import KanbanStore


class WorktreeCleanupTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.primary = base / "demo"
        self.linked = base / "worktrees" / "demo-feature"
        self.primary.mkdir()
        self.run_git(self.primary, "init", "-b", "main")
        self.run_git(self.primary, "config", "user.name", "Test User")
        self.run_git(self.primary, "config", "user.email", "test@example.com")
        (self.primary / "initial.txt").write_text("initial\n", encoding="utf-8")
        self.run_git(self.primary, "add", "initial.txt")
        self.run_git(self.primary, "commit", "-m", "initial")
        self.linked.parent.mkdir()
        self.run_git(
            self.primary,
            "worktree",
            "add",
            "-b",
            "feature/demo",
            str(self.linked),
        )

    @staticmethod
    def run_git(repo: Path, *args: str) -> None:
        subprocess.run(
            ["git", "-C", str(repo), *args],
            check=True,
            capture_output=True,
            text=True,
        )

    def commit_feature_change(self) -> None:
        (self.linked / "feature.txt").write_text("feature\n", encoding="utf-8")
        self.run_git(self.linked, "add", "feature.txt")
        self.run_git(self.linked, "commit", "-m", "feature")

    def card_payload(self, *, status: str = "done") -> dict[str, object]:
        return {
            "id": 1,
            "external_id": "DM-0001",
            "status": status,
            "target_repo": str(self.primary),
            "feature_branch": "feature/demo",
            "worktree_path": str(self.linked),
        }

    def test_cleanup_removes_clean_worktree_after_main_merge(self) -> None:
        self.commit_feature_change()
        self.run_git(self.primary, "merge", "--no-ff", "feature/demo", "-m", "merge feature")

        result = cleanup_merged_card_worktree(self.card_payload())
        repeated = cleanup_merged_card_worktree(self.card_payload())

        self.assertTrue(result["removed"])
        self.assertFalse(self.linked.exists())
        self.assertTrue(repeated["already_removed"])

    def test_cleanup_refuses_unmerged_or_dirty_worktree(self) -> None:
        self.commit_feature_change()
        with self.assertRaisesRegex(ValueError, "not merged into main"):
            cleanup_merged_card_worktree(self.card_payload())

        self.run_git(self.primary, "merge", "--no-ff", "feature/demo", "-m", "merge feature")
        (self.linked / "dirty.txt").write_text("dirty\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "dirty worktree"):
            cleanup_merged_card_worktree(self.card_payload())

    def test_cleanup_cli_preserves_provenance_and_records_removal(self) -> None:
        self.commit_feature_change()
        self.run_git(self.primary, "merge", "--no-ff", "feature/demo", "-m", "merge feature")
        db_path = Path(self.tmp.name) / "cli.sqlite3"
        store = KanbanStore(db_path)
        store.register_project(
            {
                "slug": "demo",
                "display_name": "Demo",
                "board_slug": "demo",
                "card_prefix": "DM",
                "root_path": str(self.primary),
            }
        )
        card = store.create_card(
            {
                "board_slug": "demo",
                "title": "Merged worktree",
                "description": "The worktree should now be removed.",
                "status": "done",
                "target_repo": str(self.primary),
                "target_branch": "release/1.0",
                "feature_branch": "feature/demo",
                "worktree_path": str(self.linked),
            }
        )
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            exit_code = project.main(
                [
                    "worktree-cleanup",
                    "--db",
                    str(db_path),
                    str(card["id"]),
                ]
            )

        result = json.loads(output.getvalue())
        updated = KanbanStore(db_path).get_card(card["id"])
        assert updated is not None
        self.assertEqual(exit_code, 0)
        self.assertTrue(result["removed"])
        self.assertEqual(updated["worktree_path"], str(self.linked))
        self.assertEqual(updated["change_source"]["kind"], "worktree")
        self.assertEqual(updated["deployment_dispositions"][-1]["status"], "removed")


if __name__ == "__main__":
    unittest.main()
