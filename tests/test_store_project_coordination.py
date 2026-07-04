from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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

    def test_overview_limits_done_cards_by_default(self) -> None:
        store = self.make_store()
        self.register_demo_project(store)
        active = store.create_card(
            {
                "board_slug": "demo",
                "title": "Active card",
                "description": "Active cards remain visible.",
                "status": "in_progress",
            }
        )
        done_cards = [
            store.create_card(
                {
                    "board_slug": "demo",
                    "title": f"Done card {index}",
                    "description": f"Completed work {index}.",
                    "status": "done",
                }
            )
            for index in range(7)
        ]

        overview = store.overview("demo")
        overview_ids = [card["id"] for card in overview["cards"]]

        self.assertIn(active["id"], overview_ids)
        self.assertEqual(overview["done_limit"], 5)
        self.assertEqual(overview["done_card_count"], 7)
        self.assertEqual(overview["done_cards_hidden_count"], 2)
        self.assertTrue(overview["done_cards_hidden"])
        self.assertEqual(
            [card["id"] for card in overview["cards"] if card["status"] == "done"],
            [card["id"] for card in reversed(done_cards[-5:])],
        )

        without_done = store.overview("demo", done_limit=0)
        self.assertEqual(
            [card["id"] for card in without_done["cards"]],
            [active["id"]],
        )
        self.assertEqual(without_done["done_cards_hidden_count"], 7)

        all_done = store.overview("demo", done_limit=-1)
        self.assertEqual(
            [card["id"] for card in all_done["cards"] if card["status"] == "done"],
            [card["id"] for card in reversed(done_cards)],
        )
        self.assertEqual(all_done["done_cards_hidden_count"], 0)

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

    def test_overview_refreshes_stale_project_agent_participants(self) -> None:
        store = self.make_store()
        root = Path(self.tmp.name) / "demo"
        (root / "src").mkdir(parents=True)
        project = store.register_project(
            {
                "slug": "demo",
                "display_name": "Demo",
                "board_slug": "demo",
                "card_prefix": "DM",
                "root_path": str(root),
            }
        )
        agent_dir = root / ".codex" / "agents"
        agent_dir.mkdir(parents=True)
        (agent_dir / "qa-reviewer.toml").write_text(
            'name = "qa_reviewer"\n',
            encoding="utf-8",
        )
        with store._connect() as conn:
            conn.execute(
                "UPDATE projects SET agent_profiles = ? WHERE slug = ?",
                (json.dumps(["project_implementer"]), project["slug"]),
            )
            conn.execute(
                "DELETE FROM participants WHERE id != ?",
                ("demo-project-implementer",),
            )

        overview = store.overview(cwd=str(root / "src"))
        agent_ids = {participant["id"] for participant in store.snapshot("demo")["participants"]}

        self.assertTrue(overview["agent_profiles_refreshed"])
        self.assertIn("domain_model_steward", overview["agent_profiles"])
        self.assertIn("qa_reviewer", overview["agent_profiles"])
        self.assertIn("demo-ai-agent-manager", overview["agent_participant_ids"])
        self.assertIn("demo-ai-agent-manager", agent_ids)
        self.assertIn("demo-domain-model-steward", agent_ids)
        self.assertIn("demo-qa-reviewer", agent_ids)

    def test_overview_refresh_discovers_current_default_agent_files(self) -> None:
        store = self.make_store()
        codex_home = Path(self.tmp.name) / "codex-home"
        agent_dir = codex_home / "agents"
        agent_dir.mkdir(parents=True)
        (agent_dir / "default-helper.toml").write_text(
            'name = "default_helper"\n',
            encoding="utf-8",
        )
        root = Path(self.tmp.name) / "demo"
        (root / "src").mkdir(parents=True)
        store.register_project(
            {
                "slug": "demo",
                "display_name": "Demo",
                "board_slug": "demo",
                "card_prefix": "DM",
                "root_path": str(root),
            }
        )
        with store._connect() as conn:
            conn.execute(
                "DELETE FROM participants WHERE id = ?",
                ("demo-default-helper",),
            )

        with mock.patch.dict("os.environ", {"CODEX_HOME": str(codex_home)}):
            overview = store.overview(cwd=str(root / "src"))

        agent_ids = {participant["id"] for participant in store.snapshot("demo")["participants"]}
        self.assertIn("default_helper", overview["agent_profiles"])
        self.assertIn("demo-default-helper", agent_ids)

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

        self.assertIn(
            "same target repo and branch without distinct feature branches: release/1.2",
            first_reasons,
        )
        self.assertIn("same declared files: app/workflow.py", first_reasons)
        self.assertEqual(second_conflict["external_id"], first["external_id"])

    def test_snapshot_conflicts_same_release_branch_without_feature_branches(self) -> None:
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
                "description": "Uses a worktree but no feature branch.",
                "status": "in_progress",
                "target_repo": "/tmp/demo",
                "target_branch": "release/1.2",
                "worktree_path": "/workspace/worktrees/demo-a",
                "files_changed": ["app/first.py"],
            }
        )
        store.create_card(
            {
                "board_slug": project["board_slug"],
                "title": "Second implementation",
                "description": "Uses another worktree but no feature branch.",
                "status": "in_progress",
                "target_repo": "/tmp/demo",
                "target_branch": "release/1.2",
                "worktree_path": "/workspace/worktrees/demo-b",
                "files_changed": ["app/second.py"],
            }
        )

        cards = {card["id"]: card for card in store.snapshot("demo")["cards"]}
        first_reasons = cards[first["id"]]["conflicts"][0]["reasons"]

        self.assertIn(
            "same target repo and branch without distinct feature branches: release/1.2",
            first_reasons,
        )

    def test_snapshot_allows_same_release_branch_with_distinct_feature_branches(self) -> None:
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
        store.create_card(
            {
                "board_slug": project["board_slug"],
                "title": "First implementation",
                "description": "Touches one area.",
                "status": "in_progress",
                "target_repo": "/tmp/demo",
                "target_branch": "release/1.2",
                "feature_branch": "feature/DM-0001-first",
                "worktree_path": "/workspace/worktrees/demo-a",
                "files_changed": ["app/first.py"],
            }
        )
        store.create_card(
            {
                "board_slug": project["board_slug"],
                "title": "Second implementation",
                "description": "Touches another area.",
                "status": "in_progress",
                "target_repo": "/tmp/demo",
                "target_branch": "release/1.2",
                "feature_branch": "feature/DM-0002-second",
                "worktree_path": "/workspace/worktrees/demo-b",
                "files_changed": ["app/second.py"],
            }
        )

        cards = store.snapshot("demo")["cards"]

        self.assertTrue(all(not card["conflicts"] for card in cards))

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

    def test_snapshot_and_event_pages_default_to_latest_ten(self) -> None:
        store = self.make_store()
        self.register_demo_project(store)
        for index in range(25):
            store.create_event(
                {
                    "board_slug": "demo",
                    "event_type": f"test.{index:02d}",
                    "message": str(index),
                }
            )

        snapshot = store.snapshot("demo")
        second_page = store.list_events(
            "demo",
            limit=10,
            before_id=snapshot["events_next_before_id"],
        )
        third_page = store.list_events(
            "demo",
            limit=10,
            before_id=second_page["next_before_id"],
        )

        self.assertEqual(
            [event["event_type"] for event in snapshot["events"]],
            [f"test.{index:02d}" for index in range(15, 25)],
        )
        self.assertTrue(snapshot["events_has_more"])
        self.assertEqual(snapshot["events_next_before_id"], snapshot["events"][0]["id"])
        self.assertEqual(
            [event["event_type"] for event in second_page["events"]],
            [f"test.{index:02d}" for index in range(5, 15)],
        )
        self.assertTrue(second_page["has_more"])
        self.assertEqual(
            [event["event_type"] for event in third_page["events"]],
            [f"test.{index:02d}" for index in range(5)],
        )
        self.assertFalse(third_page["has_more"])
        self.assertIsNone(third_page["next_before_id"])

    def test_events_include_related_cards_even_when_archived(self) -> None:
        store = self.make_store()
        self.register_demo_project(store)
        template = store.create_card(
            {
                "board_slug": "demo",
                "title": "Recurring source",
                "description": "Hidden source card.",
            }
        )
        generated = store.create_card(
            {
                "board_slug": "demo",
                "title": "Generated work",
                "description": "Visible generated card.",
            }
        )
        store.update_card(template["id"], {"archived": True})

        event = store.create_event(
            {
                "board_slug": "demo",
                "event_type": "workflow.manual",
                "card_id": generated["id"],
                "message": generated["title"],
                "metadata": {
                    "source_card_id": template["id"],
                    "source_external_id": template["external_id"],
                },
            }
        )
        snapshot = store.snapshot("demo")
        snapshot_event = snapshot["events"][-1]

        self.assertEqual([card["id"] for card in snapshot["cards"]], [generated["id"]])
        self.assertEqual(
            [card["external_id"] for card in event["related_cards"]],
            [generated["external_id"], template["external_id"]],
        )
        self.assertEqual(
            [card["external_id"] for card in snapshot_event["related_cards"]],
            [generated["external_id"], template["external_id"]],
        )
        self.assertFalse(snapshot_event["related_cards"][0]["archived"])
        self.assertTrue(snapshot_event["related_cards"][1]["archived"])
        self.assertEqual(snapshot_event["related_cards"][1]["title"], "Recurring source")

    def test_event_pages_include_related_archived_cards(self) -> None:
        store = self.make_store()
        self.register_demo_project(store)
        archived = store.create_card(
            {
                "board_slug": "demo",
                "title": "Archived source",
                "description": "Hidden but still related.",
            }
        )
        visible = store.create_card(
            {
                "board_slug": "demo",
                "title": "Visible target",
                "description": "Visible related card.",
            }
        )
        store.update_card(archived["id"], {"archived": True})
        for index in range(12):
            store.create_event(
                {
                    "board_slug": "demo",
                    "event_type": f"noise.{index:02d}",
                    "message": "newer event",
                }
            )
        related_event = store.create_event(
            {
                "board_slug": "demo",
                "event_type": "workflow.manual",
                "card_id": visible["id"],
                "message": visible["title"],
                "metadata": {
                    "source_card_id": archived["id"],
                    "source_external_id": archived["external_id"],
                },
            }
        )
        for index in range(12, 24):
            store.create_event(
                {
                    "board_slug": "demo",
                    "event_type": f"noise.{index:02d}",
                    "message": "newer event",
                }
            )

        snapshot = store.snapshot("demo")
        page = store.list_events(
            "demo",
            limit=10,
            before_id=snapshot["events_next_before_id"],
        )
        page_event = next(event for event in page["events"] if event["id"] == related_event["id"])

        self.assertEqual(
            [card["external_id"] for card in page_event["related_cards"]],
            [visible["external_id"], archived["external_id"]],
        )
        self.assertFalse(page_event["related_cards"][0]["archived"])
        self.assertTrue(page_event["related_cards"][1]["archived"])

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
