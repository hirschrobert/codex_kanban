from __future__ import annotations

import subprocess
import sys
import unittest

from kanban_server import project
from kanban_server.project import main as project_main
from kanban_server.store import DEFAULT_DB_PATH, GENERIC_AGENT_PROFILES, KanbanStore


class PublicEntrypointTest(unittest.TestCase):
    def test_project_package_exposes_main(self) -> None:
        self.assertIs(project_main, project.main)
        self.assertEqual(DEFAULT_DB_PATH.name, "kanban.sqlite3")
        self.assertIn("project_implementer", GENERIC_AGENT_PROFILES)
        self.assertTrue(callable(KanbanStore))

    def test_project_package_module_help_runs(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "kanban_server.project", "--help"],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        self.assertIn("Register projects with Codex Kanban", result.stdout)


if __name__ == "__main__":
    unittest.main()
