from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest import mock

from kanban_server.store import GENERIC_AGENT_PROFILES
from tests.store_project_support import KanbanStoreProjectCase


class KanbanStoreProjectCoordinationTest(KanbanStoreProjectCase):
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


if __name__ == "__main__":
    unittest.main()
