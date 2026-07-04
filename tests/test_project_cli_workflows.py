from __future__ import annotations

import contextlib
import io
import json
import subprocess
import unittest

from kanban_server import project
from kanban_server.store import KanbanStore
from tests.project_cli_support import ProjectCliCase


class ProjectCliWorkflowTest(ProjectCliCase):
    def test_workflow_start_creates_idempotent_maintenance_card(self) -> None:
        db_path = self.make_db_path()
        first_output = io.StringIO()
        second_output = io.StringIO()

        args = [
            "workflow-start",
            "--db",
            str(db_path),
            "--board",
            "demo",
            "--workflow-key",
            "docs-refresh",
            "--scheduled-for",
            "2026-06-28",
            "--title",
            "Refresh stale docs",
            "--description",
            "Check documentation drift from recent changes.",
            "--target-repo",
            "/tmp/demo",
            "--target-branch",
            "release/current",
            "--assignee",
            "demo-project-implementer",
            "--actor-id",
            "demo-project-reviewer",
        ]
        with contextlib.redirect_stdout(io.StringIO()):
            project.main(
                [
                    "register",
                    "--db",
                    str(db_path),
                    "--root",
                    "/tmp/demo",
                    "--slug",
                    "demo",
                    "--display-name",
                    "Demo",
                    "--card-prefix",
                    "DM",
                ]
            )
            project.main(
                [
                    "participant-upsert",
                    "--db",
                    str(db_path),
                    "--board",
                    "demo",
                    "--id",
                    "demo-project-implementer",
                    "--display-name",
                    "project_implementer",
                    "--kind",
                    "agent",
                    "--status",
                    "idle",
                ]
            )
            project.main(
                [
                    "participant-upsert",
                    "--db",
                    str(db_path),
                    "--board",
                    "demo",
                    "--id",
                    "demo-project-reviewer",
                    "--display-name",
                    "project_reviewer",
                    "--kind",
                    "agent",
                    "--status",
                    "idle",
                ]
            )

        with contextlib.redirect_stdout(first_output):
            first_exit = project.main(args)
        with contextlib.redirect_stdout(second_output):
            second_exit = project.main(args)

        first = json.loads(first_output.getvalue())
        second = json.loads(second_output.getvalue())

        self.assertEqual(first_exit, 0)
        self.assertEqual(second_exit, 0)
        self.assertTrue(first["created"])
        self.assertFalse(second["created"])
        self.assertEqual(first["card"]["id"], second["card"]["id"])
        self.assertEqual(first["card"]["target_branch"], "release/current")
        self.assertEqual(first["card"]["owner_id"], "demo-project-reviewer")
        self.assertEqual(first["card"]["created_by_id"], "demo-project-reviewer")

    def test_workflow_start_requires_target_branch(self) -> None:
        db_path = self.make_db_path()

        with self.assertRaises(SystemExit) as raised:
            project.main(
                [
                    "workflow-start",
                    "--db",
                    str(db_path),
                    "--board",
                    "demo",
                    "--workflow-key",
                    "docs-refresh",
                ]
            )

        self.assertIn("requires --target-branch", str(raised.exception))

    def test_due_run_dry_run_lists_codex_exec_command(self) -> None:
        db_path = self.make_db_path()
        repo = self.make_git_repo("demo")
        output = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()):
            project.main(
                [
                    "register",
                    "--db",
                    str(db_path),
                    "--root",
                    "/tmp/demo",
                    "--slug",
                    "demo",
                    "--display-name",
                    "Demo",
                    "--card-prefix",
                    "DM",
                ]
            )
            project.main(
                [
                    "workflow-start",
                    "--db",
                    str(db_path),
                    "--board",
                    "demo",
                    "--workflow-key",
                    "docs-refresh",
                    "--scheduled-for",
                    "2026-06-28",
                    "--title",
                    "Refresh stale docs",
                    "--description",
                    "Check documentation drift from recent changes.",
                    "--target-repo",
                    str(repo),
                    "--target-branch",
                    "release/current",
                ]
            )

        with contextlib.redirect_stdout(output):
            exit_code = project.main(
                [
                    "due-run",
                    "--db",
                    str(db_path),
                    "--board",
                    "demo",
                ]
            )

        result = json.loads(output.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertTrue(result["dry_run"])
        self.assertEqual(len(result["cards"]), 1)
        self.assertEqual(result["cards"][0]["command"][:4], ["codex", "exec", "--cd", str(repo)])
        self.assertEqual(result["cards"][0]["workflow_key"], "docs-refresh")

    def test_due_run_dry_run_does_not_schedule_repeating_templates(self) -> None:
        db_path = self.make_db_path()
        repo = self.make_git_repo("demo")
        output = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()):
            project.main(
                [
                    "register",
                    "--db",
                    str(db_path),
                    "--root",
                    str(repo),
                    "--slug",
                    "demo",
                    "--display-name",
                    "Demo",
                    "--card-prefix",
                    "DM",
                ]
            )
            template = json.loads(
                self.capture_project_main(
                    [
                        "card-create",
                        "--db",
                        str(db_path),
                        "--board",
                        "demo",
                        "--title",
                        "Refresh docs",
                        "--description",
                        "Scheduled recurring maintenance.",
                        "--target-repo",
                        str(repo),
                        "--target-branch",
                        "release/current",
                    ]
                )
            )
            KanbanStore(db_path).update_card(
                template["id"],
                {
                    "repeat_cadence": "daily",
                    "repeat_next_run_at": "2000-01-01T00:00:00Z",
                },
            )

        with contextlib.redirect_stdout(output):
            exit_code = project.main(
                [
                    "due-run",
                    "--db",
                    str(db_path),
                    "--board",
                    "demo",
                ]
            )

        result = json.loads(output.getvalue())
        snapshot = KanbanStore(db_path).snapshot("demo")

        self.assertEqual(exit_code, 0)
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["scheduled_results"], [])
        self.assertEqual(result["cards"], [])
        self.assertEqual(
            [card["external_id"] for card in snapshot["cards"]], [template["external_id"]]
        )

    def test_due_run_can_filter_specific_ready_workflow_cards(self) -> None:
        db_path = self.make_db_path()
        repo = self.make_git_repo("demo")
        output = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()):
            project.main(
                [
                    "register",
                    "--db",
                    str(db_path),
                    "--root",
                    str(repo),
                    "--slug",
                    "demo",
                    "--display-name",
                    "Demo",
                    "--card-prefix",
                    "DM",
                ]
            )
            project.main(
                [
                    "workflow-start",
                    "--db",
                    str(db_path),
                    "--board",
                    "demo",
                    "--workflow-key",
                    "docs-refresh",
                    "--scheduled-for",
                    "2026-06-28",
                    "--target-repo",
                    str(repo),
                    "--target-branch",
                    "release/current",
                ]
            )
            second = json.loads(
                self.capture_project_main(
                    [
                        "workflow-start",
                        "--db",
                        str(db_path),
                        "--board",
                        "demo",
                        "--workflow-key",
                        "metadata-refresh",
                        "--scheduled-for",
                        "2026-06-28",
                        "--target-repo",
                        str(repo),
                        "--target-branch",
                        "release/current",
                    ]
                )
            )

        with contextlib.redirect_stdout(output):
            exit_code = project.main(
                [
                    "due-run",
                    "--db",
                    str(db_path),
                    "--board",
                    "demo",
                    "--card",
                    second["card"]["external_id"],
                ]
            )

        result = json.loads(output.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertEqual([card["workflow_key"] for card in result["cards"]], ["metadata-refresh"])

    def test_due_run_execute_marks_successful_card_done(self) -> None:
        db_path = self.make_db_path()
        repo = self.make_git_repo("demo")
        codex_stub = self.make_codex_stub(0)
        with contextlib.redirect_stdout(io.StringIO()):
            project.main(
                [
                    "register",
                    "--db",
                    str(db_path),
                    "--root",
                    str(repo),
                    "--slug",
                    "demo",
                    "--display-name",
                    "Demo",
                    "--card-prefix",
                    "DM",
                ]
            )
            workflow = json.loads(
                self.capture_project_main(
                    [
                        "workflow-start",
                        "--db",
                        str(db_path),
                        "--board",
                        "demo",
                        "--workflow-key",
                        "docs-refresh",
                        "--scheduled-for",
                        "2026-06-28",
                        "--target-repo",
                        str(repo),
                        "--target-branch",
                        "release/current",
                    ]
                )
            )
            exit_code = project.main(
                [
                    "due-run",
                    "--db",
                    str(db_path),
                    "--board",
                    "demo",
                    "--execute",
                    "--codex-bin",
                    str(codex_stub),
                ]
            )

        store = KanbanStore(db_path)
        updated = store.get_card(workflow["card"]["id"])
        assert updated is not None
        current_branch = subprocess.run(
            ["git", "-C", str(repo), "branch", "--show-current"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

        self.assertEqual(exit_code, 0)
        self.assertEqual(updated["status"], "done")
        self.assertEqual(current_branch, "release/current")

    def test_due_run_execute_blocks_main_branch_target(self) -> None:
        db_path = self.make_db_path()
        repo = self.make_git_repo("demo")
        codex_stub = self.make_codex_stub(0)
        with contextlib.redirect_stdout(io.StringIO()):
            project.main(
                [
                    "register",
                    "--db",
                    str(db_path),
                    "--root",
                    str(repo),
                    "--slug",
                    "demo",
                    "--display-name",
                    "Demo",
                    "--card-prefix",
                    "DM",
                ]
            )
            workflow = json.loads(
                self.capture_project_main(
                    [
                        "workflow-start",
                        "--db",
                        str(db_path),
                        "--board",
                        "demo",
                        "--workflow-key",
                        "unsafe-refresh",
                        "--scheduled-for",
                        "2026-06-28",
                        "--target-repo",
                        str(repo),
                        "--target-branch",
                        "main",
                    ]
                )
            )
            project.main(
                [
                    "due-run",
                    "--db",
                    str(db_path),
                    "--board",
                    "demo",
                    "--execute",
                    "--codex-bin",
                    str(codex_stub),
                ]
            )

        updated = KanbanStore(db_path).get_card(workflow["card"]["id"])
        assert updated is not None

        self.assertEqual(updated["status"], "blocked")
        self.assertIn("must use a release branch", updated["blocker_reason"])


if __name__ == "__main__":
    unittest.main()
