from __future__ import annotations

import tempfile
import types
import unittest
from pathlib import Path
from typing import Any

from kanban_server.server import EventBroker
from kanban_server.store import KanbanStore


class SnapshotScalingTest(unittest.TestCase):
    def make_store(self) -> KanbanStore:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        return KanbanStore(Path(self.tmp.name) / "kanban.sqlite3")

    def test_project_board_slug_change_migrates_board_state(self) -> None:
        store = self.make_store()
        payload = {
            "slug": "codex-kanban",
            "display_name": "codex_kanban",
            "board_slug": "ai-work",
            "card_prefix": "AI",
            "root_path": str(Path(self.tmp.name) / "codex_kanban"),
            "agent_profiles": ["project_implementer", "project_reviewer"],
        }
        project = store.register_project(payload)
        child = store.create_card(
            {
                "board_slug": project["board_slug"],
                "external_id": "AI-0032",
                "title": "Prerequisite",
                "description": "Historical work item.",
            }
        )
        parent = store.create_card(
            {
                "board_slug": project["board_slug"],
                "external_id": "AI-0033",
                "title": "Optimize snapshot",
                "description": "Performance work item.",
                "assignee_id": "ai-work-project-implementer",
                "child_external_ids": [child["external_id"]],
            }
        )
        comment = store.add_card_comment(
            parent["id"],
            {
                "participant_id": "ai-work-project-reviewer",
                "body": "Preserve this review note.",
            },
        )
        store.create_event(
            {
                "board_slug": "ai-work",
                "event_type": "card.reviewed",
                "card_id": parent["id"],
                "card_external_id": parent["external_id"],
                "participant_id": "ai-work-project-reviewer",
            }
        )
        workflow = store.start_workflow(
            {
                "board_slug": "ai-work",
                "workflow_key": "docs-refresh",
                "scheduled_for": "2026-06-29",
                "target_branch": "release/0.1.1",
            }
        )

        payload["board_slug"] = "codex-kanban"
        migrated = store.register_project(payload)
        snapshot = store.snapshot("codex-kanban")
        stale_snapshot = store.snapshot("ai-work")
        cards = {card["external_id"]: card for card in snapshot["cards"]}
        participants = {participant["id"] for participant in snapshot["participants"]}

        self.assertEqual(migrated["board_slug"], "codex-kanban")
        self.assertEqual(stale_snapshot["board"]["slug"], "codex-kanban")
        self.assertNotIn("ai-work", {board["slug"] for board in snapshot["boards"]})
        self.assertEqual(cards["AI-0033"]["assignee_id"], "codex-kanban-project-implementer")
        self.assertEqual(cards["AI-0033"]["child_external_ids"], ["AI-0032"])
        self.assertEqual(cards["AI-0032"]["parent_external_ids"], ["AI-0033"])
        self.assertIn("codex-kanban-project-implementer", participants)
        self.assertNotIn("ai-work-project-implementer", participants)
        self.assertEqual(cards["AI-0033"]["comments"][0]["id"], comment["id"])
        self.assertEqual(
            cards["AI-0033"]["comments"][0]["participant_id"],
            "codex-kanban-project-reviewer",
        )
        self.assertTrue(
            any(
                event["board_slug"] == "codex-kanban"
                and event["participant_id"] == "codex-kanban-project-reviewer"
                for event in snapshot["events"]
            )
        )
        self.assertEqual(
            [card["id"] for card in store.due_workflow_cards("codex-kanban")],
            [workflow["card"]["id"]],
        )

    def test_snapshot_keeps_dependency_links_for_multiple_cards(self) -> None:
        store = self.make_store()
        first = store.create_card({"title": "First", "description": "First dependency."})
        second = store.create_card({"title": "Second", "description": "Second dependency."})
        parent = store.create_card(
            {
                "title": "Parent",
                "description": "Depends on both child cards.",
                "child_external_ids": [first["external_id"], second["external_id"]],
            }
        )

        cards = {card["external_id"]: card for card in store.snapshot()["cards"]}

        self.assertEqual(
            cards[parent["external_id"]]["child_external_ids"],
            [first["external_id"], second["external_id"]],
        )
        self.assertEqual(
            cards[first["external_id"]]["parent_external_ids"], [parent["external_id"]]
        )
        self.assertEqual(
            cards[second["external_id"]]["parent_external_ids"], [parent["external_id"]]
        )

    def test_snapshot_cards_sort_by_latest_card_timestamp(self) -> None:
        store = self.make_store()
        oldest = store.create_card({"title": "Oldest", "description": "Old created card."})
        updated = store.create_card({"title": "Updated", "description": "Recently updated card."})
        newest = store.create_card({"title": "Newest", "description": "Newest created card."})

        with store._connect() as conn:
            conn.execute(
                "UPDATE cards SET created_at = ?, updated_at = ? WHERE id = ?",
                ("2026-01-01T08:00:00Z", "", oldest["id"]),
            )
            conn.execute(
                "UPDATE cards SET created_at = ?, updated_at = ? WHERE id = ?",
                ("2026-01-01T08:00:00Z", "2026-01-03T09:00:00Z", updated["id"]),
            )
            conn.execute(
                "UPDATE cards SET created_at = ?, updated_at = ? WHERE id = ?",
                ("2026-01-04T08:00:00Z", "", newest["id"]),
            )

        self.assertEqual(
            [card["title"] for card in store.snapshot()["cards"]],
            ["Newest", "Updated", "Oldest"],
        )

    def test_snapshot_includes_owner_and_assignee_people(self) -> None:
        store = self.make_store()
        store.register_project(
            {
                "slug": "demo",
                "display_name": "Demo",
                "board_slug": "demo",
                "root_path": str(Path(self.tmp.name) / "demo"),
                "agent_profiles": ["project_implementer"],
            }
        )
        store.upsert_participant(
            {
                "id": "demo-user",
                "display_name": "Demo User",
                "kind": "human",
                "board_slug": "demo",
            }
        )
        card = store.create_card(
            {
                "board_slug": "demo",
                "title": "Owned work",
                "description": "Ownership should be visible.",
                "owner_id": "demo-user",
                "assignee_id": "demo-project-implementer",
            }
        )

        snapshot_card = {item["id"]: item for item in store.snapshot("demo")["cards"]}[card["id"]]

        self.assertEqual(snapshot_card["owner_id"], "demo-user")
        self.assertEqual(snapshot_card["owner"]["display_name"], "Demo User")
        self.assertEqual(snapshot_card["created_by_name"], "local developer")
        self.assertEqual(snapshot_card["created_by"]["display_name"], "local developer")
        self.assertEqual(snapshot_card["assignee_id"], "demo-project-implementer")
        self.assertEqual(
            snapshot_card["assignee"]["display_name"],
            "project_implementer",
        )

    def test_created_by_uses_actor_when_card_is_created(self) -> None:
        store = self.make_store()
        store.register_project(
            {
                "slug": "demo",
                "display_name": "Demo",
                "board_slug": "demo",
                "root_path": str(Path(self.tmp.name) / "demo"),
                "agent_profiles": ["project_implementer"],
            }
        )
        card = store.create_card(
            {
                "board_slug": "demo",
                "title": "Actor-created",
                "description": "Creator metadata should be preserved.",
                "actor_id": "demo-project-implementer",
            }
        )

        snapshot_card = {item["id"]: item for item in store.snapshot("demo")["cards"]}[card["id"]]

        self.assertEqual(snapshot_card["owner_id"], "demo-project-implementer")
        self.assertEqual(snapshot_card["created_by_id"], "demo-project-implementer")
        self.assertEqual(
            snapshot_card["created_by"]["display_name"],
            "project_implementer",
        )

    def test_unknown_explicit_owner_is_rejected(self) -> None:
        store = self.make_store()
        store.register_project(
            {
                "slug": "demo",
                "display_name": "Demo",
                "board_slug": "demo",
                "root_path": str(Path(self.tmp.name) / "demo"),
                "agent_profiles": ["project_implementer"],
            }
        )

        with self.assertRaisesRegex(ValueError, "unknown owner_id 'demo-typo'"):
            store.create_card(
                {
                    "board_slug": "demo",
                    "title": "Bad owner",
                    "description": "Owner typos should be rejected.",
                    "owner_id": "demo-typo",
                }
            )

    def test_update_preserves_existing_non_participant_owner(self) -> None:
        store = self.make_store()
        card = store.create_card(
            {
                "title": "Legacy owner",
                "description": "Legacy owner should survive ordinary edits.",
            }
        )
        with store._connect() as conn:
            conn.execute(
                "UPDATE cards SET owner_id = ? WHERE id = ?",
                ("legacy-owner", card["id"]),
            )

        updated = store.update_card(
            card["id"],
            {
                "description": "Edited without changing the legacy owner.",
                "owner_id": "legacy-owner",
            },
        )

        self.assertEqual(updated["owner_id"], "legacy-owner")

    def test_update_preserves_existing_cross_board_prefixed_legacy_owner(self) -> None:
        store = self.make_store()
        store.register_project(
            {
                "slug": "alpha",
                "display_name": "Alpha",
                "board_slug": "alpha",
                "root_path": str(Path(self.tmp.name) / "alpha"),
            }
        )
        beta = store.register_project(
            {
                "slug": "beta",
                "display_name": "Beta",
                "board_slug": "beta",
                "root_path": str(Path(self.tmp.name) / "beta"),
            }
        )
        card = store.create_card(
            {
                "board_slug": beta["board_slug"],
                "title": "Prefixed legacy owner",
                "description": "Legacy owner should survive even with another board prefix.",
            }
        )
        with store._connect() as conn:
            conn.execute(
                "UPDATE cards SET owner_id = ? WHERE id = ?",
                ("alpha-legacy-owner", card["id"]),
            )

        updated = store.update_card(
            card["id"],
            {
                "description": "Edited without changing the prefixed legacy owner.",
                "owner_id": "alpha-legacy-owner",
            },
        )

        self.assertEqual(updated["owner_id"], "alpha-legacy-owner")

    def test_conflict_scan_skips_inactive_unrelated_cards(self) -> None:
        store = self.make_store()
        original_conflict_reasons = store._conflict_reasons
        calls: list[tuple[int, int]] = []

        def counted_conflict_reasons(
            self: KanbanStore,
            left: dict[str, Any],
            right: dict[str, Any],
        ) -> list[str]:
            del self
            calls.append((int(left["id"]), int(right["id"])))
            return original_conflict_reasons(left, right)

        store._conflict_reasons = types.MethodType(counted_conflict_reasons, store)
        first = store.create_card(
            {
                "title": "First active",
                "description": "Active implementation.",
                "status": "in_progress",
                "target_repo": "/tmp/demo",
                "target_branch": "release/0.1.1",
            }
        )
        second = store.create_card(
            {
                "title": "Second active",
                "description": "Active implementation.",
                "status": "blocked",
                "target_repo": "/tmp/demo",
                "target_branch": "release/0.1.1",
            }
        )
        store.create_card(
            {
                "title": "Unrelated active",
                "description": "Different repo.",
                "status": "in_progress",
                "target_repo": "/tmp/other",
                "target_branch": "release/0.1.1",
            }
        )
        for index in range(10):
            store.create_card(
                {
                    "title": f"Done {index}",
                    "description": "Inactive card with matching repo.",
                    "status": "done",
                    "target_repo": "/tmp/demo",
                    "target_branch": "release/0.1.1",
                }
            )

        cards = {card["id"]: card for card in store.snapshot()["cards"]}

        self.assertEqual(calls, [(first["id"], second["id"])])
        self.assertEqual(cards[first["id"]]["conflicts"][0]["card_id"], second["id"])
        self.assertEqual(cards[second["id"]]["conflicts"][0]["card_id"], first["id"])


class EventBrokerScalingTest(unittest.TestCase):
    def test_publish_snapshots_reuses_snapshot_per_subscription_options(self) -> None:
        broker = EventBroker()
        default_a = broker.subscribe("demo")
        default_b = broker.subscribe("demo")
        archived = broker.subscribe("demo", archived_only=True)
        other = broker.subscribe("other")
        store = CountingSnapshotStore()

        broker.publish_snapshots("demo", store)  # type: ignore[arg-type]

        self.assertEqual(
            store.calls,
            [
                ("demo", False, False),
                ("demo", False, True),
            ],
        )
        self.assertIs(default_a.get_nowait()["data"], default_b.get_nowait()["data"])
        self.assertEqual(archived.get_nowait()["data"]["archived_only"], True)
        self.assertTrue(other.empty())


class CountingSnapshotStore:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bool, bool]] = []

    def snapshot(
        self,
        board_slug: str,
        *,
        include_archived: bool = False,
        archived_only: bool = False,
    ) -> dict[str, Any]:
        self.calls.append((board_slug, include_archived, archived_only))
        return {
            "board": {"slug": board_slug},
            "include_archived": include_archived,
            "archived_only": archived_only,
        }


if __name__ == "__main__":
    unittest.main()
