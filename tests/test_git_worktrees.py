from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from kanban_server.git_worktrees import git_worktree_context
from kanban_server.project.registration import auto_register_payload_for_cwd, repo_root
from kanban_server.store import KanbanStore


class GitWorktreeIdentityTest(unittest.TestCase):
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
        (self.primary / "AGENTS.md").write_text(
            "Use the `codex-kanban` skill for project work.\n",
            encoding="utf-8",
        )
        self.run_git(self.primary, "add", "AGENTS.md")
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

    def test_linked_worktree_resolves_primary_repository_identity(self) -> None:
        context = git_worktree_context(self.linked)

        assert context is not None
        self.assertTrue(context["is_linked_worktree"])
        self.assertEqual(context["worktree_root"], self.linked)
        self.assertEqual(context["primary_root"], self.primary)
        self.assertEqual(repo_root(self.linked), self.primary)

    def test_auto_registration_uses_primary_repository_from_worktree(self) -> None:
        payload = auto_register_payload_for_cwd(self.linked)

        assert payload is not None
        self.assertEqual(payload["slug"], "demo")
        self.assertEqual(payload["root_path"], str(self.primary))
        self.assertEqual(payload["paths"], [{"label": "demo", "path": str(self.primary)}])
        self.assertEqual(payload["instruction_paths"], [str(self.primary / "AGENTS.md")])

    def test_registered_primary_project_wins_over_stale_worktree_project(self) -> None:
        store = KanbanStore(Path(self.tmp.name) / "kanban.sqlite3")
        store.register_project(
            {
                "slug": "demo",
                "display_name": "Demo",
                "board_slug": "demo",
                "card_prefix": "DM",
                "root_path": str(self.primary),
            }
        )
        store.register_project(
            {
                "slug": "demo-feature",
                "display_name": "Demo feature worktree",
                "board_slug": "demo-feature",
                "card_prefix": "DMF",
                "root_path": str(self.linked),
            }
        )

        resolution = store.resolve_project_for_paths([self.linked])
        active_projects = store.list_projects()
        all_projects = store.list_projects(include_removed=True)

        self.assertFalse(resolution["ambiguous"])
        self.assertEqual(resolution["project"]["slug"], "demo")
        self.assertEqual([project["slug"] for project in active_projects], ["demo"])
        self.assertEqual({project["slug"] for project in all_projects}, {"demo", "demo-feature"})
        primary_matches = [
            match
            for match in resolution["matches"]
            if match["project_slug"] == "demo" and match["identity_rank"] == 0
        ]
        self.assertEqual(len(primary_matches), 1)
        self.assertEqual(primary_matches[0]["identity_path"], str(self.primary))


if __name__ == "__main__":
    unittest.main()
