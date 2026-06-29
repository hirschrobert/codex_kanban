from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from kanban_server import hook
from kanban_server.store import KanbanStore


class HookAutoRegistrationTest(unittest.TestCase):
    def make_store(self) -> KanbanStore:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        return KanbanStore(Path(self.tmp.name) / "kanban.sqlite3")

    def make_repo(self, instruction: str) -> Path:
        root = Path(self.tmp.name) / "new-project"
        root.mkdir()
        (root / ".git").mkdir()
        (root / "AGENTS.md").write_text(instruction, encoding="utf-8")
        (root / "src").mkdir()
        return root

    def test_auto_registers_repo_that_requires_codex_kanban(self) -> None:
        store = self.make_store()
        root = self.make_repo(
            "## Codex Kanban\n\n" "- You must use the `codex-kanban` skill to coordinate work.\n"
        )

        project = hook._auto_register_project(store, root / "src", "")
        matched = store.project_for_path(root / "src")

        self.assertIsNotNone(project)
        assert project is not None
        assert matched is not None
        self.assertEqual(project["slug"], "new-project")
        self.assertEqual(project["board_slug"], "new-project")
        self.assertEqual(project["card_prefix"], "NEW")
        self.assertEqual(matched["slug"], "new-project")
        self.assertIn("domain_model_steward", project["agent_profiles"])
        self.assertIn("api_contract_steward", project["agent_profiles"])

    def test_auto_register_discovers_project_local_agent_profiles(self) -> None:
        store = self.make_store()
        root = self.make_repo(
            "## Codex Kanban\n\n" "- You must use the `codex-kanban` skill to coordinate work.\n"
        )
        agent_dir = root / ".codex" / "agents"
        agent_dir.mkdir(parents=True)
        (agent_dir / "domain-accountant.toml").write_text(
            'name = "domain_accountant"\n',
            encoding="utf-8",
        )

        project = hook._auto_register_project(store, root / "src", "")
        assert project is not None
        snapshot = store.snapshot(project["board_slug"])
        agent_ids = {participant["id"] for participant in snapshot["participants"]}

        self.assertIn("domain_accountant", project["agent_profiles"])
        self.assertIn("new-project-domain-accountant", agent_ids)

    def test_does_not_auto_register_without_project_instruction(self) -> None:
        store = self.make_store()
        root = self.make_repo("# Project\n\nNo Kanban instruction here.\n")

        project = hook._auto_register_project(store, root / "src", "")

        self.assertIsNone(project)
        self.assertEqual(store.list_projects(include_removed=True), [])

    def test_generic_subagent_uses_board_scoped_participant_id(self) -> None:
        participant_id, raw_agent_id = hook._participant_id_for_hook(
            {"agent_id": "subagent-123"},
            "SubagentStart",
            "project_implementer",
            "demo",
        )

        self.assertEqual(participant_id, "demo-project-implementer")
        self.assertEqual(raw_agent_id, "subagent-123")

    def test_project_local_subagent_uses_board_scoped_participant_id(self) -> None:
        participant_id, raw_agent_id = hook._participant_id_for_hook(
            {"agent_id": "subagent-456"},
            "SubagentStart",
            "domain_accountant",
            "demo",
            ["domain_accountant"],
        )

        self.assertEqual(participant_id, "demo-domain-accountant")
        self.assertEqual(raw_agent_id, "subagent-456")


if __name__ == "__main__":
    unittest.main()
