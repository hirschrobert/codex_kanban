from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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

    def test_main_turn_uses_stable_manager_role_and_raw_runtime_id(self) -> None:
        participant_id, raw_agent_id = hook._participant_id_for_hook(
            {"session_id": "session-123"},
            "UserPromptSubmit",
            "codex-agent",
            "demo",
        )

        self.assertEqual(participant_id, "demo-ai-agent-manager")
        self.assertEqual(raw_agent_id, "session-123")

    def test_unknown_subagent_uses_native_people_role(self) -> None:
        participant_id, raw_agent_id = hook._participant_id_for_hook(
            {"agent_id": "agent-unknown"},
            "SubagentStart",
            "unregistered_agent",
            "demo",
        )

        self.assertEqual(participant_id, "demo-codex-subagents")
        self.assertEqual(raw_agent_id, "agent-unknown")

    def test_subagent_context_tells_agents_to_comment_on_parent_card(self) -> None:
        message = hook._context_message(
            {
                "instruction_paths": ["/workspace/demo/AGENTS.md"],
                "agent_profiles": ["project_reviewer"],
            },
            "demo",
        )

        self.assertIn("parent coordination card", message)
        self.assertIn("findings, decisions, blockers, and next steps", message)
        self.assertIn("does not require delegation", message)
        self.assertIn("optional offers", message)

    def test_event_metadata_records_the_model_for_each_turn(self) -> None:
        metadata = hook._event_metadata(
            {
                "model": "gpt-5.6",
                "session_id": "session-123",
                "turn_id": "turn-456",
            },
            hook_name="UserPromptSubmit",
            cwd="/workspace/demo",
            project_slug="demo",
            raw_agent_id="session-123",
            agent_type="codex-agent",
        )

        self.assertEqual(metadata["model"], "gpt-5.6")
        self.assertEqual(metadata["session_id"], "session-123")
        self.assertEqual(metadata["turn_id"], "turn-456")
        self.assertEqual(metadata["status"], "running")

    def test_event_metadata_omits_unreported_runtime_fields(self) -> None:
        metadata = hook._event_metadata(
            {},
            hook_name="SubagentStart",
            cwd="/workspace/demo",
            project_slug="demo",
            raw_agent_id="agent-123",
            agent_type="project_reviewer",
        )

        self.assertNotIn("model", metadata)
        self.assertNotIn("session_id", metadata)
        self.assertNotIn("turn_id", metadata)

    def test_hook_installer_adds_prompt_start_and_preserves_unrelated_hooks(self) -> None:
        existing = {
            "hooks": {
                "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "other-tool"}]}],
                "Stop": [
                    {
                        "hooks": [
                            {
                                "type": "command",
                                "command": "OLD=1 python3 -m kanban_server.hook",
                            }
                        ]
                    }
                ],
            }
        }

        merged = hook._merged_user_hooks(
            existing,
            repo=Path("/workspace/codex-kanban"),
            server_url="http://127.0.0.1:8766",
        )

        for event_name in hook.KANBAN_HOOK_EVENTS:
            groups = merged["hooks"][event_name]
            kanban_groups = [group for group in groups if hook._is_kanban_hook_group(group)]
            self.assertEqual(len(kanban_groups), 1, event_name)
            command = kanban_groups[0]["hooks"][0]["command"]
            if event_name != "Stop":
                self.assertIn(f"CODEX_HOOK_EVENT={event_name}", command)
        self.assertEqual(
            merged["hooks"]["UserPromptSubmit"][0], existing["hooks"]["UserPromptSubmit"][0]
        )
        self.assertEqual(merged["hooks"]["Stop"][0], existing["hooks"]["Stop"][0])

    def test_user_prompt_and_stop_drive_main_runtime_lifecycle(self) -> None:
        store = self.make_store()
        root = self.make_repo(
            "## Codex Kanban\n\n- You must use the `codex-kanban` skill to coordinate work.\n"
        )
        store.register_project(
            {
                "slug": "new-project",
                "display_name": "New Project",
                "board_slug": "new-project",
                "card_prefix": "NEW",
                "root_path": str(root),
            }
        )
        environment = {
            "CODEX_KANBAN_DB": str(store.db_path),
            "CODEX_KANBAN_URL": "",
        }
        prompt_payload = {
            "hook_event_name": "UserPromptSubmit",
            "cwd": str(root),
            "model": "gpt-5.6-terra",
            "session_id": "session-123",
            "turn_id": "turn-1",
        }
        with (
            patch.dict(os.environ, environment, clear=False),
            patch.object(sys, "stdin", io.StringIO(json.dumps(prompt_payload))),
        ):
            self.assertEqual(hook.main([]), 0)

        manager = next(
            participant
            for participant in KanbanStore(store.db_path).snapshot("new-project")["participants"]
            if participant["id"] == "new-project-ai-agent-manager"
        )
        self.assertEqual(manager["status"], "running")
        self.assertEqual(manager["instances"][0]["model"], "gpt-5.6-terra")

        stop_payload = dict(prompt_payload, hook_event_name="Stop", turn_id="turn-1")
        with (
            patch.dict(os.environ, environment, clear=False),
            patch.object(sys, "stdin", io.StringIO(json.dumps(stop_payload))),
        ):
            self.assertEqual(hook.main([]), 0)

        manager = next(
            participant
            for participant in KanbanStore(store.db_path).snapshot("new-project")["participants"]
            if participant["id"] == "new-project-ai-agent-manager"
        )
        self.assertEqual(manager["status"], "idle")
        self.assertEqual(manager["instances"], [])

    def test_native_subagent_hooks_drive_people_lifecycle_without_relabeling(self) -> None:
        store = self.make_store()
        root = self.make_repo(
            "## Codex Kanban\n\n- You must use the `codex-kanban` skill to coordinate work.\n"
        )
        store.register_project(
            {
                "slug": "new-project",
                "display_name": "New Project",
                "board_slug": "new-project",
                "card_prefix": "NEW",
                "root_path": str(root),
            }
        )
        store.upsert_participant(
            {
                "id": "new-project-project-reviewer",
                "kind": "agent",
                "display_name": "project_reviewer",
                "status": "reviewing",
                "board_slug": "new-project",
            }
        )
        environment = {
            "CODEX_KANBAN_DB": str(store.db_path),
            "CODEX_KANBAN_URL": "",
        }
        start_payload = {
            "hook_event_name": "SubagentStart",
            "cwd": str(root),
            "agent_type": "default",
            "agent_id": "agent-123",
            "model": "gpt-5.6-terra",
        }
        with (
            patch.dict(os.environ, environment, clear=False),
            patch.object(sys, "stdin", io.StringIO(json.dumps(start_payload))),
            patch("sys.stdout", new_callable=io.StringIO),
        ):
            self.assertEqual(hook.main([]), 0)

        native_role = next(
            participant
            for participant in KanbanStore(store.db_path).snapshot("new-project")["participants"]
            if participant["id"] == "new-project-codex-subagents"
        )
        self.assertEqual(native_role["status"], "running")
        self.assertEqual(native_role["instances"][0]["id"], "agent-123")
        self.assertEqual(native_role["instances"][0]["agent_type"], "default")
        start_event = KanbanStore(store.db_path).snapshot("new-project")["events"][-1]
        self.assertEqual(start_event["metadata"]["agent_type"], "default")
        self.assertEqual(start_event["metadata"]["binding_source"], "native_subagent")

        stop_payload = dict(start_payload, hook_event_name="SubagentStop")
        with (
            patch.dict(os.environ, environment, clear=False),
            patch.object(sys, "stdin", io.StringIO(json.dumps(stop_payload))),
        ):
            self.assertEqual(hook.main([]), 0)

        native_role = next(
            participant
            for participant in KanbanStore(store.db_path).snapshot("new-project")["participants"]
            if participant["id"] == "new-project-codex-subagents"
        )
        self.assertEqual(native_role["status"], "idle")
        self.assertEqual(native_role["instances"], [])
        stop_event = KanbanStore(store.db_path).snapshot("new-project")["events"][-1]
        self.assertEqual(stop_event["metadata"]["binding_source"], "native_subagent")


if __name__ == "__main__":
    unittest.main()
