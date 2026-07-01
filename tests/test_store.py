from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from kanban_server.store import KanbanStore


class KanbanStoreTest(unittest.TestCase):
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

    def test_migration_starts_with_generic_default_board(self) -> None:
        store = self.make_store()
        snapshot = store.snapshot()

        self.assertEqual(snapshot["board"]["slug"], "default")
        self.assertEqual([lane["status"] for lane in snapshot["lanes"]][0], "backlog")
        self.assertEqual(snapshot["projects"], [])

    def test_create_and_move_card(self) -> None:
        store = self.make_store()
        card = store.create_card(
            {
                "title": "Implement dashboard",
                "description": "Build the first realtime board surface.",
                "priority": "high",
            }
        )

        self.assertEqual(card["status"], "backlog")
        self.assertEqual(card["external_id"], "DEFAULT-0001")

        moved = store.update_card(card["id"], {"status": "in_progress"})

        self.assertEqual(moved["status"], "in_progress")

    def test_intake_metadata_round_trips(self) -> None:
        store = self.make_store()

        card = store.create_card(
            {
                "title": "PDF preview fails",
                "description": "Opening an uploaded PDF shows a blank panel.",
                "intake_kind": "error_report",
                "intake_source": "main_agent",
                "reported_by": "Front desk",
                "impact": "Blocks invoice review.",
                "evidence": "Observed in the desktop client.",
                "affected_paths": ["/workspace/app", "/workspace/db_worker"],
            }
        )
        updated = store.update_card(
            card["id"],
            {
                "intake_kind": "feature_request",
                "intake_source": "dashboard",
                "reported_by": "Operations",
                "impact": "Reduces manual sorting.",
                "evidence": "Requested during triage.",
                "affected_paths": "/workspace/portal\n/workspace/extension",
            },
        )
        cleared = store.update_card(
            card["id"],
            {
                "intake_kind": "",
                "intake_source": "",
                "reported_by": "",
                "impact": "",
                "evidence": "",
                "affected_paths": "",
            },
        )

        self.assertEqual(card["intake_kind"], "error_report")
        self.assertEqual(card["intake_source"], "main_agent")
        self.assertEqual(card["reported_by"], "Front desk")
        self.assertEqual(card["impact"], "Blocks invoice review.")
        self.assertEqual(card["evidence"], "Observed in the desktop client.")
        self.assertEqual(card["affected_paths"], ["/workspace/app", "/workspace/db_worker"])
        self.assertEqual(updated["intake_kind"], "feature_request")
        self.assertEqual(updated["intake_source"], "dashboard")
        self.assertEqual(updated["reported_by"], "Operations")
        self.assertEqual(updated["impact"], "Reduces manual sorting.")
        self.assertEqual(updated["evidence"], "Requested during triage.")
        self.assertEqual(updated["affected_paths"], ["/workspace/portal", "/workspace/extension"])
        self.assertEqual(cleared["intake_kind"], "")
        self.assertEqual(cleared["intake_source"], "")
        self.assertEqual(cleared["reported_by"], "")
        self.assertEqual(cleared["impact"], "")
        self.assertEqual(cleared["evidence"], "")
        self.assertEqual(cleared["affected_paths"], [])

    def test_snapshot_unknown_board_falls_back_without_creating_board(self) -> None:
        store = self.make_store()
        self.register_demo_project(store)

        snapshot = store.snapshot("stale-local-storage")

        self.assertEqual(snapshot["board"]["slug"], "demo")
        self.assertNotIn("stale-local-storage", {board["slug"] for board in snapshot["boards"]})

    def test_create_card_requires_description(self) -> None:
        store = self.make_store()

        with self.assertRaisesRegex(ValueError, "description is required"):
            store.create_card({"title": "Missing description"})

    def test_repeating_card_defaults_to_german_time_and_requires_branch(self) -> None:
        store = self.make_store()

        with self.assertRaisesRegex(ValueError, "target_branch is required"):
            store.create_card(
                {
                    "title": "Refresh docs",
                    "description": "Recurring documentation cleanup.",
                    "repeat_cadence": "daily",
                }
            )

        self.register_demo_project(store)
        card = store.create_card(
            {
                "board_slug": "demo",
                "title": "Refresh docs",
                "description": "Recurring documentation cleanup.",
                "target_branch": "release/current",
                "repeat_cadence": "daily",
            }
        )

        self.assertEqual(card["repeat_cadence"], "daily")
        self.assertEqual(card["repeat_time"], "01:00")
        self.assertEqual(card["repeat_timezone"], "Europe/Berlin")
        self.assertIsNotNone(card["repeat_next_run_at"])

    def test_repeating_card_requires_active_project_board(self) -> None:
        store = self.make_store()

        with self.assertRaisesRegex(ValueError, "active registered project board"):
            store.create_card(
                {
                    "board_slug": "default",
                    "title": "Refresh docs",
                    "description": "Recurring documentation cleanup.",
                    "target_branch": "release/current",
                    "repeat_cadence": "daily",
                }
            )

    def test_due_repeating_card_creates_one_workflow_card_per_period(self) -> None:
        store = self.make_store()
        self.register_demo_project(store)
        template = store.create_card(
            {
                "board_slug": "demo",
                "title": "Refresh docs",
                "description": "Check docs for drift.",
                "target_repo": "/tmp/demo",
                "target_branch": "release/current",
                "repeat_cadence": "daily",
                "repeat_time": "01:00",
                "checks": ["python3 -m unittest discover -s tests"],
            }
        )
        with store._connect() as conn:
            conn.execute(
                "UPDATE cards SET repeat_next_run_at = ? WHERE id = ?",
                ("2026-06-27T23:00:00Z", template["id"]),
            )

        before = store.run_due_repeating_cards(datetime(2026, 6, 27, 22, 59, tzinfo=UTC))
        first = store.run_due_repeating_cards(datetime(2026, 6, 27, 23, 0, 30, tzinfo=UTC))
        second = store.run_due_repeating_cards(datetime(2026, 6, 27, 23, 5, tzinfo=UTC))
        snapshot = store.snapshot("demo")
        generated = [
            card
            for card in snapshot["cards"]
            if card["id"] != template["id"] and card["title"] == "Refresh docs"
        ]

        self.assertEqual(before, [])
        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 0)
        self.assertEqual(generated[0]["target_branch"], "release/current")
        self.assertEqual(generated[0]["repeat_cadence"], "none")
        self.assertEqual(generated[0]["checks"], ["python3 -m unittest discover -s tests"])
        template_snapshot = store.get_card(template["id"])
        assert template_snapshot is not None
        self.assertEqual(template_snapshot["repeat_last_period"], "2026-06-28")
        self.assertEqual(
            template_snapshot["repeat_next_run_at"],
            "2026-06-28T23:00:00Z",
        )

    def test_workflow_start_uses_actor_as_owner_and_creator(self) -> None:
        store = self.make_store()
        self.register_demo_project(store)

        result = store.start_workflow(
            {
                "board_slug": "demo",
                "workflow_key": "docs-refresh",
                "scheduled_for": "2026-06-28",
                "target_branch": "release/current",
                "actor_id": "demo-project-reviewer",
            }
        )

        self.assertEqual(result["card"]["owner_id"], "demo-project-reviewer")
        self.assertEqual(result["card"]["created_by_id"], "demo-project-reviewer")
        self.assertEqual(result["card"]["created_by_name"], "project_reviewer")

    def test_due_repeating_card_inherits_template_owner_and_creator(self) -> None:
        store = self.make_store()
        self.register_demo_project(store)
        template = store.create_card(
            {
                "board_slug": "demo",
                "title": "Refresh docs",
                "description": "Check docs for drift.",
                "target_repo": "/tmp/demo",
                "target_branch": "release/current",
                "repeat_cadence": "daily",
                "repeat_time": "01:00",
                "owner_id": "demo-project-reviewer",
                "actor_id": "demo-project-implementer",
            }
        )
        with store._connect() as conn:
            conn.execute(
                "UPDATE cards SET repeat_next_run_at = ? WHERE id = ?",
                ("2026-06-27T23:00:00Z", template["id"]),
            )

        result = store.run_due_repeating_cards(datetime(2026, 6, 27, 23, 0, 30, tzinfo=UTC))[0]

        self.assertEqual(result["card"]["owner_id"], "demo-project-reviewer")
        self.assertEqual(result["card"]["created_by_id"], "demo-project-implementer")

    def test_due_repeating_card_comments_when_previous_workflow_is_unfinished(self) -> None:
        store = self.make_store()
        self.register_demo_project(store)
        template = store.create_card(
            {
                "board_slug": "demo",
                "title": "Refresh docs",
                "description": "Check docs for drift.",
                "target_repo": "/tmp/demo",
                "target_branch": "release/current",
                "repeat_cadence": "daily",
                "repeat_time": "01:00",
                "owner_id": "demo-project-implementer",
            }
        )
        with store._connect() as conn:
            conn.execute(
                "UPDATE cards SET repeat_next_run_at = ? WHERE id = ?",
                ("2026-06-27T23:00:00Z", template["id"]),
            )

        first = store.run_due_repeating_cards(datetime(2026, 6, 27, 23, 0, 30, tzinfo=UTC))
        second = store.run_due_repeating_cards(datetime(2026, 6, 28, 23, 0, 30, tzinfo=UTC))
        generated = [
            card
            for card in store.snapshot("demo")["cards"]
            if card["id"] != template["id"] and card["title"] == "Refresh docs"
        ]
        existing = store.get_card(first[0]["card"]["id"])
        assert existing is not None
        template_snapshot = store.get_card(template["id"])
        assert template_snapshot is not None
        events = store.snapshot("demo")["events"]

        self.assertEqual(len(first), 1)
        self.assertTrue(first[0]["created"])
        self.assertEqual(len(second), 1)
        self.assertTrue(second[0]["reused"])
        self.assertEqual(len(generated), 1)
        self.assertEqual(existing["comment_count"], 1)
        self.assertIn("No duplicate ready card", existing["comments"][0]["body"])
        self.assertEqual(existing["comments"][0]["author_kind"], "system")
        self.assertEqual(template_snapshot["repeat_last_period"], "2026-06-29")
        self.assertTrue(any(event["event_type"] == "workflow.deferred" for event in events))

    def test_due_repeating_cards_can_be_limited_to_one_board(self) -> None:
        store = self.make_store()
        self.register_demo_project(store)
        store.register_project(
            {
                "slug": "other",
                "display_name": "Other",
                "board_slug": "other",
                "card_prefix": "OT",
                "root_path": "/tmp/other",
            }
        )
        demo_template = store.create_card(
            {
                "board_slug": "demo",
                "title": "Refresh demo docs",
                "description": "Check demo docs for drift.",
                "target_repo": "/tmp/demo",
                "target_branch": "release/current",
                "repeat_cadence": "daily",
                "repeat_time": "01:00",
                "owner_id": "demo-project-implementer",
            }
        )
        other_template = store.create_card(
            {
                "board_slug": "other",
                "title": "Refresh other docs",
                "description": "Check other docs for drift.",
                "target_repo": "/tmp/other",
                "target_branch": "release/current",
                "repeat_cadence": "daily",
                "repeat_time": "01:00",
            }
        )
        with store._connect() as conn:
            conn.execute(
                "UPDATE cards SET repeat_next_run_at = ? WHERE id IN (?, ?)",
                ("2026-06-27T23:00:00Z", demo_template["id"], other_template["id"]),
            )

        results = store.run_due_repeating_cards(
            datetime(2026, 6, 27, 23, 0, 30, tzinfo=UTC),
            board_slug="demo",
        )

        self.assertEqual([result["card"]["board_slug"] for result in results], ["demo"])
        self.assertEqual(len(store.due_workflow_cards("demo")), 1)
        self.assertEqual(store.due_workflow_cards("other"), [])

    def test_due_workflow_cards_lists_ready_workflow_cards_only(self) -> None:
        store = self.make_store()
        self.register_demo_project(store)
        workflow = store.start_workflow(
            {
                "board_slug": "demo",
                "workflow_key": "docs-refresh",
                "scheduled_for": "2026-06-28",
                "title": "Refresh docs",
                "description": "Check docs for drift.",
                "target_branch": "release/current",
            }
        )
        store.create_card(
            {
                "board_slug": "demo",
                "title": "Ordinary ready card",
                "description": "This is not a workflow run.",
                "status": "ready",
            }
        )

        due_cards = store.due_workflow_cards("demo")

        self.assertEqual([card["id"] for card in due_cards], [workflow["card"]["id"]])
        self.assertEqual(due_cards[0]["workflow_key"], "docs-refresh")
        self.assertEqual(due_cards[0]["workflow_scheduled_for"], "2026-06-28")

    def test_late_repeating_card_still_creates_ready_workflow_card(self) -> None:
        store = self.make_store()
        self.register_demo_project(store)
        template = store.create_card(
            {
                "board_slug": "demo",
                "title": "Refresh docs",
                "description": "Check docs for drift.",
                "target_repo": "/tmp/demo",
                "target_branch": "release/current",
                "repeat_cadence": "daily",
                "repeat_time": "01:00",
            }
        )
        with store._connect() as conn:
            conn.execute(
                "UPDATE cards SET repeat_next_run_at = ? WHERE id = ?",
                ("2026-06-27T23:00:00Z", template["id"]),
            )

        results = store.run_due_repeating_cards(datetime(2026, 6, 27, 23, 2, tzinfo=UTC))
        snapshot = store.snapshot("demo")
        generated = [
            card
            for card in snapshot["cards"]
            if card["id"] != template["id"] and card["title"] == "Refresh docs"
        ]
        updated = store.get_card(template["id"])
        assert updated is not None

        self.assertEqual(len(results), 1)
        self.assertEqual(len(generated), 1)
        self.assertEqual(generated[0]["status"], "ready")
        self.assertEqual(updated["repeat_last_period"], "2026-06-28")
        self.assertEqual(updated["repeat_next_run_at"], "2026-06-28T23:00:00Z")

    def test_run_repeating_card_now_creates_manual_workflow_card(self) -> None:
        store = self.make_store()
        self.register_demo_project(store)
        template = store.create_card(
            {
                "board_slug": "demo",
                "title": "Refresh docs",
                "description": "Check docs for drift.",
                "target_repo": "/tmp/demo",
                "target_branch": "release/current",
                "repeat_cadence": "daily",
                "repeat_time": "01:00",
                "owner_id": "demo-project-implementer",
            }
        )

        result = store.run_repeating_card_now(
            template["id"],
            {"actor_id": "demo-project-reviewer"},
        )
        updated = store.get_card(template["id"])
        assert updated is not None
        events = store.snapshot("demo")["events"]

        self.assertTrue(result["created"])
        self.assertEqual(result["card"]["title"], "Refresh docs")
        self.assertEqual(result["card"]["target_branch"], "release/current")
        self.assertEqual(result["card"]["repeat_cadence"], "none")
        self.assertEqual(result["card"]["owner_id"], "demo-project-implementer")
        self.assertEqual(result["card"]["created_by_id"], "demo-project-reviewer")
        self.assertIsNone(updated["repeat_last_period"])
        self.assertTrue(any(event["event_type"] == "workflow.manual" for event in events))

    def test_workflow_start_requires_active_project_board(self) -> None:
        store = self.make_store()

        with self.assertRaisesRegex(ValueError, "active registered project board"):
            store.start_workflow(
                {
                    "board_slug": "default",
                    "workflow_key": "docs-refresh",
                    "scheduled_for": "2026-06-28",
                    "target_branch": "release/current",
                }
            )

    def test_card_comments_are_attached_to_card_snapshots(self) -> None:
        store = self.make_store()
        store.upsert_participant(
            {
                "id": "default-human",
                "display_name": "Default Human",
                "kind": "human",
                "status": "idle",
                "board_slug": "default",
            }
        )
        card = store.create_card(
            {
                "title": "Needs notes",
                "description": "Capture context from humans and agents.",
            }
        )

        comment = store.add_card_comment(
            card["id"],
            {
                "participant_id": "default-human",
                "body": "Remember the release notes.",
            },
        )
        updated = store.get_card(card["id"])
        assert updated is not None

        self.assertEqual(comment["board_slug"], "default")
        self.assertEqual(comment["author_name"], "Default Human")
        self.assertEqual(comment["author_kind"], "human")
        self.assertIsNotNone(comment["created_at"])
        self.assertEqual(updated["comment_count"], 1)
        self.assertEqual(updated["comments"][0]["body"], "Remember the release notes.")
        self.assertEqual(updated["comments"][0]["author_name"], "Default Human")

    def test_local_comment_author_uses_developer_label(self) -> None:
        store = self.make_store()
        card = store.create_card(
            {
                "title": "Needs local note",
                "description": "Capture local context.",
            }
        )

        comment = store.add_card_comment(card["id"], {"body": "Local context."})
        legacy = store.add_card_comment(
            card["id"],
            {
                "author_name": "Local human",
                "author_kind": "human",
                "body": "Legacy local context.",
            },
        )
        updated = store.get_card(card["id"])
        assert updated is not None

        self.assertEqual(comment["author_name"], "local developer")
        self.assertEqual(comment["author_kind"], "human")
        self.assertEqual(legacy["author_name"], "local developer")
        self.assertEqual(updated["comments"][0]["author_name"], "local developer")
        self.assertEqual(updated["comments"][1]["author_name"], "local developer")

    def test_archive_hides_card_and_delete_requires_archive(self) -> None:
        store = self.make_store()
        active = store.create_card(
            {
                "title": "Keep visible",
                "description": "This card should stay in the normal board view.",
            }
        )
        card = store.create_card(
            {
                "title": "Archive me",
                "description": "This card should leave the default board view.",
            }
        )

        with self.assertRaisesRegex(ValueError, "only archived cards"):
            store.delete_card(card["id"])

        archived = store.update_card(card["id"], {"archived": True})
        default_snapshot = store.snapshot()
        archived_only_snapshot = store.snapshot(archived_only=True)
        archived_snapshot = store.snapshot(include_archived=True)
        result = store.delete_card(card["id"])

        self.assertTrue(archived["archived"])
        self.assertFalse(any(item["id"] == card["id"] for item in default_snapshot["cards"]))
        self.assertTrue(any(item["id"] == active["id"] for item in default_snapshot["cards"]))
        self.assertTrue(any(item["id"] == card["id"] for item in archived_only_snapshot["cards"]))
        self.assertFalse(
            any(item["id"] == active["id"] for item in archived_only_snapshot["cards"])
        )
        self.assertTrue(any(item["id"] == card["id"] for item in archived_snapshot["cards"]))
        self.assertTrue(any(item["id"] == active["id"] for item in archived_snapshot["cards"]))
        self.assertTrue(result["deleted"])
        self.assertIsNone(store.get_card(card["id"]))

    def test_multiline_text_normalizes_literal_newline_markers(self) -> None:
        store = self.make_store()
        card = store.create_card(
            {
                "title": "Normalize text",
                "description": "Summary\\n\\nWhy this card exists:\\nReadable sections.",
            }
        )
        updated = store.update_card(
            card["id"],
            {
                "description": "Updated\\n\\nAcceptance criteria:\\n- Looks readable.",
                "blocker_reason": "Waiting on input\\nfrom a human.",
            },
        )

        self.assertEqual(
            card["description"],
            "Summary\n\nWhy this card exists:\nReadable sections.",
        )
        self.assertEqual(
            updated["description"],
            "Updated\n\nAcceptance criteria:\n- Looks readable.",
        )
        self.assertEqual(updated["blocker_reason"], "Waiting on input\nfrom a human.")

    def test_unknown_assignee_gets_actionable_error(self) -> None:
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

        with self.assertRaisesRegex(
            ValueError,
            "unknown assignee_id 'missing-agent'.*participant-upsert",
        ):
            store.create_card(
                {
                    "board_slug": project["board_slug"],
                    "title": "Assign me",
                    "description": "This should explain the bad assignee.",
                    "assignee_id": "missing-agent",
                }
            )

        card = store.create_card(
            {
                "board_slug": project["board_slug"],
                "title": "Unassigned first",
                "description": "This card is used to test update validation.",
            }
        )
        with self.assertRaisesRegex(
            ValueError,
            "Known participants: demo-project-implementer",
        ):
            store.update_card(card["id"], {"assignee_id": "missing-agent"})

    def test_agent_assignee_must_belong_to_card_board(self) -> None:
        store = self.make_store()
        alpha = store.register_project(
            {
                "slug": "alpha",
                "display_name": "Alpha",
                "board_slug": "alpha",
                "card_prefix": "AL",
                "root_path": "/tmp/alpha",
                "agent_profiles": ["project_implementer"],
            }
        )
        beta = store.register_project(
            {
                "slug": "beta",
                "display_name": "Beta",
                "board_slug": "beta",
                "card_prefix": "BE",
                "root_path": "/tmp/beta",
                "agent_profiles": ["project_implementer"],
            }
        )

        with self.assertRaisesRegex(
            ValueError,
            "alpha-project-implementer.*scoped to board 'alpha'.*board 'beta'",
        ):
            store.create_card(
                {
                    "board_slug": beta["board_slug"],
                    "title": "Cross assign",
                    "description": "This must not use another board's agent.",
                    "assignee_id": f"{alpha['board_slug']}-project-implementer",
                }
            )

    def test_participant_card_link_must_be_on_same_board_and_exist(self) -> None:
        store = self.make_store()
        alpha = store.register_project(
            {
                "slug": "alpha",
                "display_name": "Alpha",
                "board_slug": "alpha",
                "card_prefix": "AL",
                "root_path": "/tmp/alpha",
                "agent_profiles": ["project_implementer"],
            }
        )
        beta = store.register_project(
            {
                "slug": "beta",
                "display_name": "Beta",
                "board_slug": "beta",
                "card_prefix": "BE",
                "root_path": "/tmp/beta",
                "agent_profiles": ["project_implementer"],
            }
        )
        alpha_card = store.create_card(
            {
                "board_slug": alpha["board_slug"],
                "title": "Alpha card",
                "description": "This card belongs only to alpha.",
            }
        )

        with self.assertRaisesRegex(ValueError, "card .* belongs to board 'alpha'"):
            store.upsert_participant(
                {
                    "id": "beta-project-implementer",
                    "display_name": "project_implementer",
                    "kind": "agent",
                    "status": "idle",
                    "board_slug": beta["board_slug"],
                    "current_card_id": alpha_card["id"],
                }
            )

        with self.assertRaisesRegex(KeyError, "AL-9999.*not found on board beta"):
            store.upsert_participant(
                {
                    "id": "beta-project-implementer",
                    "display_name": "project_implementer",
                    "kind": "agent",
                    "status": "idle",
                    "board_slug": beta["board_slug"],
                    "current_card_external_id": "AL-9999",
                }
            )

    def test_events_reject_cross_board_card_and_participant(self) -> None:
        store = self.make_store()
        alpha = store.register_project(
            {
                "slug": "alpha",
                "display_name": "Alpha",
                "board_slug": "alpha",
                "card_prefix": "AL",
                "root_path": "/tmp/alpha",
                "agent_profiles": ["project_implementer"],
            }
        )
        beta = store.register_project(
            {
                "slug": "beta",
                "display_name": "Beta",
                "board_slug": "beta",
                "card_prefix": "BE",
                "root_path": "/tmp/beta",
                "agent_profiles": ["project_implementer"],
            }
        )
        alpha_card = store.create_card(
            {
                "board_slug": alpha["board_slug"],
                "title": "Alpha event card",
                "description": "Events cannot move this to beta.",
            }
        )

        with self.assertRaisesRegex(ValueError, "card .* belongs to board 'alpha'"):
            store.create_event(
                {
                    "board_slug": beta["board_slug"],
                    "event_type": "agent.started",
                    "card_id": alpha_card["id"],
                }
            )

        with self.assertRaisesRegex(
            ValueError,
            "alpha-project-implementer.*scoped to board 'alpha'.*board 'beta'",
        ):
            store.create_event(
                {
                    "board_slug": beta["board_slug"],
                    "event_type": "agent.started",
                    "participant_id": "alpha-project-implementer",
                }
            )

    def test_snapshot_marks_stale_active_agent_and_card(self) -> None:
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
                "title": "Long running implementation",
                "description": "This card should expose stale agent state.",
                "status": "in_progress",
                "assignee_id": "demo-project-implementer",
                "target_branch": "main",
            }
        )
        store.upsert_participant(
            {
                "id": "demo-project-implementer",
                "display_name": "project_implementer",
                "kind": "agent",
                "status": "running",
                "board_slug": project["board_slug"],
                "current_card_external_id": card["external_id"],
            }
        )
        with store._connect() as conn:
            conn.execute("""
                UPDATE participants
                SET last_seen_at = '2000-01-01T00:00:00Z',
                    updated_at = '2000-01-01T00:00:00Z'
                WHERE id = 'demo-project-implementer'
                """)

        snapshot = store.snapshot("demo")
        participant = next(
            item for item in snapshot["participants"] if item["id"] == "demo-project-implementer"
        )
        stale_card = next(item for item in snapshot["cards"] if item["id"] == card["id"])

        self.assertTrue(participant["is_stale"])
        self.assertFalse(participant["is_active"])
        self.assertTrue(stale_card["assignee_is_stale"])
        self.assertIn("not checked in", stale_card["coordination_warnings"][0])

    def test_active_implementer_limit_uses_project_setting(self) -> None:
        store = self.make_store()
        for slug in ("alpha", "beta"):
            store.register_project(
                {
                    "slug": slug,
                    "display_name": slug.title(),
                    "board_slug": slug,
                    "card_prefix": slug[:2].upper(),
                    "root_path": f"/tmp/{slug}",
                    "agent_profiles": ["project_implementer"],
                }
            )
        alpha_settings = store.update_project_settings(
            "alpha",
            {"max_active_implementers": 2},
        )
        beta_settings = store.update_project_settings(
            "beta",
            {"max_active_implementers": 1},
        )

        self.assertEqual(alpha_settings["max_active_implementers"], 2)
        self.assertEqual(beta_settings["max_active_implementers"], 1)

        store.upsert_participant(
            {
                "id": "alpha-project-implementer",
                "display_name": "project_implementer",
                "kind": "agent",
                "status": "running",
                "board_slug": "alpha",
            }
        )
        second_alpha = store.upsert_participant(
            {
                "id": "alpha-project-implementer-extra",
                "display_name": "project_implementer",
                "kind": "agent",
                "status": "running",
                "board_slug": "alpha",
            }
        )
        beta = store.upsert_participant(
            {
                "id": "beta-project-implementer",
                "display_name": "project_implementer",
                "kind": "agent",
                "status": "running",
                "board_slug": "beta",
            }
        )

        alpha_snapshot = store.snapshot("alpha")
        active_alpha_project = alpha_snapshot["active_project"]

        self.assertEqual(second_alpha["status"], "running")
        self.assertEqual(beta["status"], "running")
        self.assertEqual(active_alpha_project["max_active_implementers"], 2)
        self.assertEqual(
            alpha_snapshot["agent_limits"]["max_active_implementers_per_project"],
            2,
        )
        with self.assertRaisesRegex(ValueError, "active project_implementer agents"):
            store.upsert_participant(
                {
                    "id": "alpha-project-implementer-third",
                    "display_name": "project_implementer",
                    "kind": "agent",
                    "status": "running",
                    "board_slug": "alpha",
                }
            )
        with self.assertRaisesRegex(ValueError, "active project_implementer agents"):
            store.upsert_participant(
                {
                    "id": "beta-project-implementer-extra",
                    "display_name": "project_implementer",
                    "kind": "agent",
                    "status": "running",
                    "board_slug": "beta",
                }
            )

    def test_project_settings_validate_integer_limits(self) -> None:
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

        with self.assertRaisesRegex(ValueError, "max_active_implementers must be 0 or greater"):
            store.update_project_settings("demo", {"max_active_implementers": -1})
        with self.assertRaisesRegex(ValueError, "max_active_implementers must be a whole number"):
            store.update_project_settings("demo", {"max_active_implementers": "two"})

        updated = store.update_project_settings("demo", {"max_active_implementers": 0})

        self.assertEqual(updated["max_active_implementers"], 0)


if __name__ == "__main__":
    unittest.main()
