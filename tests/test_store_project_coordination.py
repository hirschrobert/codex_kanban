from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from kanban_server.store import GENERIC_AGENT_PROFILES, KanbanStore


class KanbanStoreProjectCoordinationTest(unittest.TestCase):
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

    def test_register_project_uses_project_card_prefix_and_path_lookup(self) -> None:
        store = self.make_store()
        project = store.register_project(
            {
                "slug": "demo",
                "display_name": "Demo",
                "board_slug": "demo",
                "card_prefix": "DM",
                "root_path": "/tmp/demo",
                "paths": [{"label": "Demo app", "path": "/tmp/demo/app"}],
                "instruction_paths": ["/tmp/demo/AGENTS.md"],
                "agent_profiles": ["project_implementer"],
            }
        )
        card = store.create_card(
            {
                "board_slug": project["board_slug"],
                "title": "Human card",
                "description": "Human supplied work request.",
            }
        )
        matched = store.project_for_path("/tmp/demo/app/controllers")
        assert matched is not None
        snapshot = store.snapshot("demo")

        self.assertEqual(card["external_id"], "DM-0001")
        self.assertEqual(matched["slug"], "demo")
        self.assertTrue(
            any(
                participant["id"] == "demo-project-implementer"
                for participant in snapshot["participants"]
            )
        )

    def test_snapshot_derives_affected_project_paths_for_ecosystems(self) -> None:
        store = self.make_store()
        project = store.register_project(
            {
                "slug": "demo",
                "display_name": "Demo",
                "board_slug": "demo",
                "card_prefix": "DM",
                "root_path": "/workspace",
                "paths": [
                    {"label": "Portal", "path": "/workspace/portal"},
                    {"label": "Backend", "path": "/workspace/db_worker"},
                    {"label": "Thunderbird", "path": "/workspace/thunderbird"},
                ],
            }
        )
        store.create_card(
            {
                "board_slug": project["board_slug"],
                "title": "Deploy touched apps",
                "description": "Release everything changed by the request.",
                "affected_paths": ["/workspace/portal/src/App.jsx"],
                "target_repo": "/workspace/db_worker",
                "files_changed": ["worker.py"],
                "deployment_dispositions": ["/workspace/portal=deployed:verified live bundle"],
            }
        )

        card = store.snapshot("demo")["cards"][0]

        self.assertEqual(
            [entry["label"] for entry in card["affected_project_paths"]],
            ["Portal", "Backend"],
        )
        self.assertEqual(
            card["deployment_dispositions"],
            [
                {
                    "path": "/workspace/portal",
                    "status": "deployed",
                    "note": "verified live bundle",
                }
            ],
        )

    def test_overview_matches_workspace_and_hides_archived_cards(self) -> None:
        store = self.make_store()
        project = store.register_project(
            {
                "slug": "demo",
                "display_name": "Demo",
                "board_slug": "demo",
                "card_prefix": "DM",
                "root_path": "/workspace",
                "paths": [
                    {"label": "Portal", "path": "/workspace/portal"},
                    {"label": "Backend", "path": "/workspace/backend"},
                ],
            }
        )
        active = store.create_card(
            {
                "board_slug": project["board_slug"],
                "title": "Ship ecosystem change",
                "description": "Card descriptions are present in startup overview.",
                "status": "in_progress",
                "target_repo": "/workspace/backend",
                "target_branch": "release/1.0",
                "affected_paths": ["/workspace/portal/src/App.jsx"],
            }
        )
        store.add_card_comment(
            active["id"],
            {
                "body": "Delegated feedback should be visible as a count.",
                "author_name": "project_reviewer",
                "author_kind": "agent",
            },
        )
        archived = store.create_card(
            {
                "board_slug": project["board_slug"],
                "title": "Old context",
                "description": "Hidden by default.",
                "archived": True,
            }
        )

        overview = store.overview(cwd="/workspace/portal/src", repo="/workspace")
        cards_by_id = {card["id"]: card for card in overview["cards"]}

        self.assertEqual(overview["matched_project"]["slug"], "demo")
        self.assertEqual(overview["board"]["slug"], "demo")
        self.assertEqual(overview["archived_card_count"], 1)
        self.assertTrue(overview["archived_cards_hidden"])
        self.assertIn("archived", overview["archived_notice"])
        self.assertIn(active["id"], cards_by_id)
        self.assertNotIn(archived["id"], cards_by_id)
        self.assertEqual(
            cards_by_id[active["id"]]["description"],
            "Card descriptions are present in startup overview.",
        )
        self.assertEqual(cards_by_id[active["id"]]["comment_count"], 1)
        self.assertNotIn("comments", cards_by_id[active["id"]])
        self.assertEqual(
            [entry["label"] for entry in cards_by_id[active["id"]]["affected_project_paths"]],
            ["Portal", "Backend"],
        )

        archived_only = store.overview("demo", archived_only=True)

        self.assertEqual([card["id"] for card in archived_only["cards"]], [archived["id"]])
        self.assertFalse(archived_only["archived_cards_hidden"])

    def test_overview_reports_ambiguous_workspace_matches(self) -> None:
        store = self.make_store()
        store.register_project(
            {
                "slug": "alpha",
                "display_name": "Alpha",
                "board_slug": "alpha",
                "card_prefix": "A",
                "root_path": "/workspace/shared",
            }
        )
        store.register_project(
            {
                "slug": "beta",
                "display_name": "Beta",
                "board_slug": "beta",
                "card_prefix": "B",
                "root_path": "/workspace/shared",
            }
        )

        overview = store.overview(cwd="/workspace/shared/src")

        self.assertIsNone(overview["matched_project"])
        self.assertTrue(overview["project_resolution"]["ambiguous"])
        self.assertIn("explicit board", overview["registration_hint"])

    def test_overview_uses_explicit_board_when_workspace_match_is_ambiguous(self) -> None:
        store = self.make_store()
        store.register_project(
            {
                "slug": "alpha",
                "display_name": "Alpha",
                "board_slug": "alpha",
                "card_prefix": "A",
                "root_path": "/workspace/shared",
            }
        )
        store.register_project(
            {
                "slug": "beta",
                "display_name": "Beta",
                "board_slug": "beta",
                "card_prefix": "B",
                "root_path": "/workspace/shared",
            }
        )

        overview = store.overview("alpha", cwd="/workspace/shared/src")

        self.assertEqual(overview["board"]["slug"], "alpha")
        self.assertTrue(overview["project_resolution"]["ambiguous"])
        self.assertIn("Using explicit board 'alpha'", overview["registration_hint"])
        self.assertNotIn("Pass an explicit board", overview["registration_hint"])

    def test_overview_ignores_removed_project_matches(self) -> None:
        store = self.make_store()
        store.register_project(
            {
                "slug": "demo",
                "display_name": "Demo",
                "board_slug": "demo",
                "card_prefix": "DM",
                "root_path": "/tmp/demo",
            }
        )
        store.remove_project("demo")

        overview = store.overview(cwd="/tmp/demo/src")

        self.assertIsNone(overview["matched_project"])
        self.assertIn("No registered project path matched", overview["registration_hint"])

    def test_register_project_seeds_expanded_default_agent_profiles(self) -> None:
        store = self.make_store()
        project = store.register_project(
            {
                "slug": "demo",
                "display_name": "Demo",
                "board_slug": "demo",
                "card_prefix": "DM",
                "root_path": "/tmp/demo",
            }
        )

        agent_ids = {participant["id"] for participant in store.snapshot("demo")["participants"]}

        for profile in GENERIC_AGENT_PROFILES:
            self.assertIn(f"{project['board_slug']}-{profile.replace('_', '-')}", agent_ids)

    def test_register_project_discovers_project_local_agents(self) -> None:
        store = self.make_store()
        root = Path(self.tmp.name) / "demo"
        agent_dir = root / ".codex" / "agents"
        agent_dir.mkdir(parents=True)
        (agent_dir / "accounting-steward.toml").write_text(
            'name = "accounting_steward"\n'
            'description = "Project-local accounting rule reviewer."\n',
            encoding="utf-8",
        )

        project = store.register_project(
            {
                "slug": "demo",
                "display_name": "Demo",
                "board_slug": "demo",
                "card_prefix": "DM",
                "root_path": str(root),
            }
        )
        agent_ids = {participant["id"] for participant in store.snapshot("demo")["participants"]}

        self.assertIn("accounting_steward", project["agent_profiles"])
        self.assertIn("demo-accounting-steward", agent_ids)

    def test_register_project_prunes_removed_seeded_agents(self) -> None:
        store = self.make_store()
        payload = {
            "slug": "demo",
            "display_name": "Demo",
            "board_slug": "demo",
            "card_prefix": "DM",
            "root_path": "/tmp/demo",
            "agent_profiles": ["project_implementer", "project_specific_agent"],
        }
        store.register_project(payload)

        payload["agent_profiles"] = ["project_implementer"]
        store.register_project(payload)
        snapshot = store.snapshot("demo")
        agent_ids = {participant["id"] for participant in snapshot["participants"]}

        self.assertIn("demo-project-implementer", agent_ids)
        self.assertNotIn("demo-project-specific-agent", agent_ids)

    def test_snapshot_marks_active_card_conflicts(self) -> None:
        store = self.make_store()
        project = store.register_project(
            {
                "slug": "demo",
                "display_name": "Demo",
                "board_slug": "demo",
                "card_prefix": "DM",
                "root_path": "/tmp/demo",
            }
        )
        first = store.create_card(
            {
                "board_slug": project["board_slug"],
                "title": "First implementation",
                "description": "Touches the shared workflow.",
                "status": "in_progress",
                "target_repo": "/tmp/demo",
                "target_branch": "release/1.2",
                "worktree_path": "/workspace/worktrees/demo-a",
                "files_changed": ["app/workflow.py", "tests/test_workflow.py"],
            }
        )
        second = store.create_card(
            {
                "board_slug": project["board_slug"],
                "title": "Second implementation",
                "description": "Touches the same shared workflow.",
                "status": "in_progress",
                "target_repo": "/tmp/demo",
                "target_branch": "release/1.2",
                "worktree_path": "/workspace/worktrees/demo-b",
                "files_changed": ["app/workflow.py"],
            }
        )

        cards = {card["id"]: card for card in store.snapshot("demo")["cards"]}
        first_reasons = cards[first["id"]]["conflicts"][0]["reasons"]
        second_conflict = cards[second["id"]]["conflicts"][0]

        self.assertIn("same target repo and branch: release/1.2", first_reasons)
        self.assertIn("same declared files: app/workflow.py", first_reasons)
        self.assertEqual(second_conflict["external_id"], first["external_id"])

    def test_snapshot_warns_when_active_card_has_no_target_branch(self) -> None:
        store = self.make_store()
        store.create_card(
            {
                "title": "Unbranched implementation",
                "description": "This work needs an explicit integration branch.",
                "status": "in_progress",
                "target_repo": "/tmp/demo",
            }
        )

        card = store.snapshot()["cards"][0]

        self.assertIn("Target branch is empty", card["coordination_warnings"][0])

    def test_card_dependencies_are_reciprocal_and_block_advancement(self) -> None:
        store = self.make_store()
        project = store.register_project(
            {
                "slug": "demo",
                "display_name": "Demo",
                "board_slug": "demo",
                "card_prefix": "DM",
                "root_path": "/tmp/demo",
            }
        )
        child = store.create_card(
            {
                "board_slug": project["board_slug"],
                "title": "Contract first",
                "description": "Prerequisite contract work.",
            }
        )
        parent = store.create_card(
            {
                "board_slug": project["board_slug"],
                "title": "Implement after contract",
                "description": "Implementation depends on the child card.",
                "child_external_ids": [child["external_id"]],
            }
        )

        child_snapshot = store.get_card(child["id"])
        parent_snapshot = store.get_card(parent["id"])
        assert child_snapshot is not None
        assert parent_snapshot is not None

        self.assertEqual(parent_snapshot["child_external_ids"], [child["external_id"]])
        self.assertEqual(child_snapshot["parent_external_ids"], [parent["external_id"]])
        self.assertEqual(
            parent_snapshot["blocked_by_child_external_ids"],
            [child["external_id"]],
        )
        with self.assertRaisesRegex(ValueError, "child dependencies are done"):
            store.update_card(parent["id"], {"status": "in_progress"})

        store.update_card(child["id"], {"status": "done"})
        advanced = store.update_card(parent["id"], {"status": "in_progress"})

        self.assertEqual(advanced["status"], "in_progress")
        self.assertEqual(advanced["blocked_by_child_external_ids"], [])

    def test_archive_allowed_when_dependency_warning_exists(self) -> None:
        store = self.make_store()
        child = store.create_card(
            {
                "title": "Contract first",
                "description": "Prerequisite contract work.",
                "status": "done",
            }
        )
        parent = store.create_card(
            {
                "title": "Implement after contract",
                "description": "Implementation depends on the child card.",
                "child_external_ids": [child["external_id"]],
            }
        )
        active_parent = store.update_card(parent["id"], {"status": "in_progress"})
        store.update_card(child["id"], {"status": "ready"})

        warned_parent = store.get_card(active_parent["id"])
        assert warned_parent is not None
        self.assertEqual(
            warned_parent["blocked_by_child_external_ids"],
            [child["external_id"]],
        )

        archived = store.update_card(
            warned_parent["id"],
            {"archived": True, "status": warned_parent["status"]},
        )

        self.assertTrue(archived["archived"])
        self.assertEqual(archived["status"], "in_progress")

    def test_card_dependencies_reject_unknown_self_and_cycles(self) -> None:
        store = self.make_store()
        first = store.create_card(
            {
                "title": "First card",
                "description": "This card is used for dependency validation.",
                "external_id": "DM-0001",
            }
        )
        second = store.create_card(
            {
                "title": "Second card",
                "description": "This card depends on the first card.",
                "external_id": "DM-0002",
                "child_external_ids": ["DM-0001"],
            }
        )

        with self.assertRaisesRegex(KeyError, "dependency card DM-9999 not found"):
            store.update_card(first["id"], {"child_external_ids": ["DM-9999"]})
        with self.assertRaisesRegex(ValueError, "cannot depend on itself"):
            store.update_card(first["id"], {"child_external_ids": ["DM-0001"]})
        with self.assertRaisesRegex(ValueError, "create a cycle"):
            store.update_card(first["id"], {"child_external_ids": [second["external_id"]]})

    def test_update_card_replaces_dependency_links_without_orphans(self) -> None:
        store = self.make_store()
        first_child = store.create_card({"title": "First child", "description": "Old dependency."})
        second_child = store.create_card(
            {"title": "Second child", "description": "New dependency."}
        )
        parent = store.create_card(
            {
                "title": "Parent",
                "description": "Dependency replacement target.",
                "child_external_ids": [first_child["external_id"]],
            }
        )

        updated = store.update_card(
            parent["id"],
            {"child_external_ids": [second_child["external_id"]]},
        )
        old_child = store.get_card(first_child["id"])
        new_child = store.get_card(second_child["id"])
        assert old_child is not None
        assert new_child is not None

        self.assertEqual(updated["child_external_ids"], [second_child["external_id"]])
        self.assertEqual(old_child["parent_external_ids"], [])
        self.assertEqual(new_child["parent_external_ids"], [parent["external_id"]])

    def test_remove_project_hides_and_reregister_restores(self) -> None:
        store = self.make_store()
        payload = {
            "slug": "demo",
            "display_name": "Demo",
            "board_slug": "demo",
            "card_prefix": "DM",
            "root_path": "/tmp/demo",
            "agent_profiles": ["project_implementer"],
        }
        project = store.register_project(payload)
        card = store.create_card(
            {
                "board_slug": project["board_slug"],
                "title": "Keep me",
                "description": "This card survives a soft remove.",
            }
        )

        removed = store.remove_project("demo")
        active_projects = store.list_projects()
        all_projects = store.list_projects(include_removed=True)

        self.assertTrue(removed["removed_at"])
        self.assertEqual(active_projects, [])
        self.assertEqual(all_projects[0]["slug"], "demo")
        self.assertTrue(all_projects[0]["removed_at"])

        store.register_project(payload)
        snapshot = store.snapshot("demo")

        self.assertTrue(any(item["id"] == card["id"] for item in snapshot["cards"]))
        self.assertIsNone(snapshot["active_project"]["removed_at"])

    def test_prune_project_deletes_project_data(self) -> None:
        store = self.make_store()
        project = store.register_project(
            {
                "slug": "demo",
                "display_name": "Demo",
                "board_slug": "demo",
                "card_prefix": "DM",
                "root_path": "/tmp/demo",
                "agent_profiles": ["project_implementer"],
            }
        )
        card = store.create_card(
            {
                "board_slug": project["board_slug"],
                "title": "Delete me",
                "description": "This card is pruned.",
            }
        )
        store.upsert_participant(
            {
                "id": "demo-human",
                "display_name": "Demo Human",
                "board_slug": project["board_slug"],
            }
        )

        result = store.prune_project("demo")
        snapshot = store.snapshot()

        self.assertTrue(result["pruned"])
        self.assertEqual(store.list_projects(include_removed=True), [])
        self.assertIsNone(store.get_card(card["id"]))
        self.assertFalse(
            any(participant["id"] == "demo-human" for participant in snapshot["participants"])
        )

    def test_participant_heartbeat_and_event(self) -> None:
        store = self.make_store()
        participant = store.heartbeat(
            "demo-user",
            {
                "display_name": "Demo User",
                "kind": "human",
                "status": "running",
                "current_scope": "dashboard",
            },
        )
        event = store.create_event(
            {
                "event_type": "participant.heartbeat",
                "participant_id": participant["id"],
                "message": "running",
                "metadata": {"scope": "dashboard"},
            }
        )
        snapshot = store.snapshot()

        self.assertEqual(participant["status"], "running")
        self.assertEqual(event["metadata"]["scope"], "dashboard")
        self.assertTrue(any(item["participant_id"] == "demo-user" for item in snapshot["events"]))

    def test_delegated_agent_feedback_event_becomes_card_comment(self) -> None:
        store = self.make_store()
        self.register_demo_project(store)
        participant = store.upsert_participant(
            {
                "id": "demo-project-reviewer",
                "display_name": "project_reviewer",
                "kind": "agent",
                "status": "running",
                "board_slug": "demo",
            }
        )
        card = store.create_card(
            {
                "board_slug": "demo",
                "title": "Review handoff",
                "description": "Capture delegated feedback.",
            }
        )

        event_payload = {
            "board_slug": "demo",
            "event_type": "subagent.stopped",
            "card_id": card["id"],
            "participant_id": participant["id"],
            "message": "Review found one missing deployment disposition.",
        }
        event = store.create_event(event_payload)
        repeated_event = store.create_event(event_payload)
        distinct_event = store.create_event(
            {
                **event_payload,
                "message": "Review also wants browser-level coverage later.",
            }
        )
        updated = store.get_card(card["id"])
        assert updated is not None

        self.assertEqual(updated["comment_count"], 2)
        self.assertEqual(
            updated["comments"][0]["body"],
            "Review found one missing deployment disposition.",
        )
        self.assertEqual(updated["comments"][0]["participant_id"], "demo-project-reviewer")
        self.assertEqual(updated["comments"][0]["author_kind"], "agent")
        self.assertEqual(event["metadata"]["comment_id"], updated["comments"][0]["id"])
        self.assertEqual(repeated_event["metadata"]["comment_id"], updated["comments"][0]["id"])
        self.assertEqual(distinct_event["metadata"]["comment_id"], updated["comments"][1]["id"])
        self.assertEqual(
            updated["comments"][1]["body"],
            "Review also wants browser-level coverage later.",
        )

    def test_reset_clears_work_state_and_projects(self) -> None:
        store = self.make_store()
        project = store.register_project(
            {
                "slug": "demo",
                "display_name": "Demo",
                "board_slug": "demo",
                "card_prefix": "DM",
                "root_path": "/tmp/demo",
            }
        )
        card = store.create_card(
            {
                "board_slug": project["board_slug"],
                "title": "Reset me",
                "description": "Temporary work item.",
            }
        )
        store.create_event(
            {
                "board_slug": project["board_slug"],
                "event_type": "card.created",
                "card_id": card["id"],
            }
        )

        store.reset()
        snapshot = store.snapshot()

        self.assertEqual(snapshot["projects"], [])
        self.assertEqual(snapshot["cards"], [])
        self.assertEqual(snapshot["events"], [])


if __name__ == "__main__":
    unittest.main()
