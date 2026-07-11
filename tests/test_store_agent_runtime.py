from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from kanban_server.store import KanbanStore
from kanban_server.store.support import STALE_AFTER_SECONDS


class AgentRuntimeSnapshotTest(unittest.TestCase):
    def make_store(self) -> KanbanStore:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        store = KanbanStore(Path(self.tmp.name) / "kanban.sqlite3")
        store.register_project(
            {
                "slug": "demo",
                "display_name": "Demo",
                "board_slug": "demo",
                "card_prefix": "DM",
                "root_path": self.tmp.name,
            }
        )
        return store

    @staticmethod
    def runtime_event(
        store: KanbanStore,
        *,
        raw_id: str,
        event_type: str = "subagent.started",
        status: str = "running",
        model: str = "gpt-5.6",
    ) -> dict[str, Any]:
        return store.create_event(
            {
                "board_slug": "demo",
                "event_type": event_type,
                "participant_id": "demo-project-reviewer",
                "metadata": {
                    "raw_agent_id": raw_id,
                    "agent_type": "project_reviewer",
                    "status": status,
                    "model": model,
                    "session_id": "session-1",
                    "turn_id": f"turn-{raw_id}",
                    "cwd": "/workspace/demo",
                },
            }
        )

    @staticmethod
    def role(snapshot: dict[str, Any]) -> dict[str, Any]:
        participants = snapshot["participants"]
        assert isinstance(participants, list)
        return next(item for item in participants if item["id"] == "demo-project-reviewer")

    def test_groups_parallel_live_instances_under_one_role(self) -> None:
        store = self.make_store()
        self.runtime_event(store, raw_id="agent-1", model="gpt-5.6")
        self.runtime_event(
            store,
            raw_id="agent-2",
            status="waiting_approval",
            model="gpt-5.6-terra",
        )
        store.upsert_participant(
            {
                "id": "old-raw-agent-row",
                "kind": "agent",
                "display_name": "Old runtime",
                "status": "idle",
                "board_slug": "demo",
            }
        )

        snapshot = store.snapshot("demo")
        role = self.role(snapshot)
        participant_ids = {item["id"] for item in snapshot["participants"]}

        self.assertEqual(role["instance_count"], 2)
        self.assertEqual(role["instance_status_counts"], {"running": 1, "waiting_approval": 1})
        self.assertEqual(
            {item["model"] for item in role["instances"]},
            {"gpt-5.6", "gpt-5.6-terra"},
        )
        self.assertEqual(
            {item["agent_type"] for item in role["instances"]},
            {"project_reviewer"},
        )
        self.assertNotIn("old-raw-agent-row", participant_ids)

    def test_native_subagent_role_preserves_each_reported_type(self) -> None:
        store = self.make_store()
        for raw_id, agent_type in (
            ("agent-default", "default"),
            ("agent-worker", "worker"),
            ("agent-custom", "ad_hoc_researcher"),
        ):
            store.create_event(
                {
                    "board_slug": "demo",
                    "event_type": "subagent.started",
                    "participant_id": "demo-codex-subagents",
                    "metadata": {
                        "raw_agent_id": raw_id,
                        "agent_type": agent_type,
                        "status": "running",
                    },
                }
            )

        native_role = next(
            item
            for item in store.snapshot("demo")["participants"]
            if item["id"] == "demo-codex-subagents"
        )

        self.assertEqual(native_role["display_name"], "Codex subagents")
        self.assertEqual(
            {instance["agent_type"] for instance in native_role["instances"]},
            {"default", "worker", "ad_hoc_researcher"},
        )

    def test_finished_and_stale_instances_disappear_but_role_remains(self) -> None:
        store = self.make_store()
        started = self.runtime_event(store, raw_id="finished-agent")
        self.runtime_event(
            store,
            raw_id="finished-agent",
            event_type="subagent.stopped",
            status="done",
        )
        stale = self.runtime_event(store, raw_id="stale-agent")
        stale_time = (
            (datetime.now(UTC) - timedelta(seconds=STALE_AFTER_SECONDS + 10))
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        )
        with store._connect() as conn:
            conn.execute(
                "UPDATE events SET created_at = ? WHERE id IN (?, ?)",
                (stale_time, started["id"], stale["id"]),
            )

        role = self.role(store.snapshot("demo"))

        self.assertEqual(role["instances"], [])
        self.assertEqual(role["instance_count"], 0)
        self.assertEqual(role["status"], "idle")
        self.assertFalse(role["is_stale"])

    def test_latest_turn_preserves_per_turn_model_for_the_instance(self) -> None:
        store = self.make_store()
        self.runtime_event(store, raw_id="agent-1", model="gpt-5.6")
        event = self.runtime_event(store, raw_id="agent-1", model="gpt-5.6-terra")
        with store._connect() as conn:
            row = conn.execute(
                "SELECT metadata FROM events WHERE id = ?", (event["id"],)
            ).fetchone()

        role = self.role(store.snapshot("demo"))

        self.assertEqual(json.loads(row["metadata"])["model"], "gpt-5.6-terra")
        self.assertEqual(role["instances"][0]["model"], "gpt-5.6-terra")

    def test_prompt_before_card_intake_late_binds_unique_active_card(self) -> None:
        store = self.make_store()
        store.create_event(
            {
                "board_slug": "demo",
                "event_type": "hook.userpromptsubmit",
                "participant_id": "demo-ai-agent-manager",
                "metadata": {
                    "raw_agent_id": "session-1",
                    "status": "running",
                    "model": "gpt-5.6",
                },
            }
        )
        card = store.create_card(
            {
                "board_slug": "demo",
                "title": "Live work",
                "description": "Created after the user prompt hook.",
                "status": "in_progress",
                "assignee_id": "demo-ai-agent-manager",
                "target_branch": "release/1.0.0",
            }
        )

        manager = next(
            item
            for item in store.snapshot("demo")["participants"]
            if item["id"] == "demo-ai-agent-manager"
        )

        self.assertEqual(manager["active_models"], ["gpt-5.6"])
        self.assertEqual(manager["active_cards"][0]["external_id"], card["external_id"])
        self.assertEqual(manager["instances"][0]["current_card_external_id"], card["external_id"])
        self.assertEqual(manager["focused_card"]["external_id"], card["external_id"])
        self.assertEqual(manager["instances"][0]["card_source"], "explicit_participant_focus")

    def test_explicit_focus_beats_ambiguous_active_assignments(self) -> None:
        store = self.make_store()
        store.create_event(
            {
                "board_slug": "demo",
                "event_type": "hook.userpromptsubmit",
                "participant_id": "demo-ai-agent-manager",
                "metadata": {"raw_agent_id": "session-1", "status": "running"},
            }
        )
        first = store.create_card(
            {
                "board_slug": "demo",
                "title": "First",
                "description": "Older active assignment.",
                "status": "in_progress",
                "assignee_id": "demo-ai-agent-manager",
                "target_branch": "release/1.0.0",
            }
        )
        second = store.create_card(
            {
                "board_slug": "demo",
                "title": "Second",
                "description": "Current focused assignment.",
                "status": "in_progress",
                "assignee_id": "demo-ai-agent-manager",
                "target_branch": "release/1.0.0",
            }
        )

        manager = next(
            item
            for item in store.snapshot("demo")["participants"]
            if item["id"] == "demo-ai-agent-manager"
        )

        self.assertEqual(
            {card["external_id"] for card in manager["active_cards"]},
            {first["external_id"], second["external_id"]},
        )
        self.assertEqual(manager["focused_card"]["external_id"], second["external_id"])
        self.assertEqual(manager["instances"][0]["current_card_external_id"], second["external_id"])
        self.assertEqual(manager["instances"][0]["card_source"], "explicit_participant_focus")

    def test_hook_style_upsert_without_card_preserves_explicit_focus(self) -> None:
        store = self.make_store()
        card = store.create_card(
            {
                "board_slug": "demo",
                "title": "Focused",
                "description": "Current assignment.",
                "status": "in_progress",
                "assignee_id": "demo-ai-agent-manager",
                "target_branch": "release/1.0.0",
            }
        )

        store.upsert_participant(
            {
                "id": "demo-ai-agent-manager",
                "kind": "agent",
                "display_name": "AI Agent Manager",
                "status": "idle",
                "board_slug": "demo",
                "current_scope": "/workspace/demo",
            }
        )

        manager = next(
            item
            for item in store.snapshot("demo")["participants"]
            if item["id"] == "demo-ai-agent-manager"
        )
        self.assertEqual(manager["current_card_id"], card["id"])
        self.assertEqual(manager["focused_card"]["external_id"], card["external_id"])

    def test_leaving_active_status_clears_matching_focus(self) -> None:
        store = self.make_store()
        card = store.create_card(
            {
                "board_slug": "demo",
                "title": "Focused",
                "description": "Current assignment.",
                "status": "in_progress",
                "assignee_id": "demo-project-reviewer",
                "target_branch": "release/1.0.0",
            }
        )

        store.update_card(card["id"], {"status": "done"})

        reviewer = self.role(store.snapshot("demo"))
        self.assertIsNone(reviewer["current_card_id"])
        self.assertIsNone(reviewer["focused_card"])

    def test_multiple_active_cards_or_instances_are_not_guessed(self) -> None:
        store = self.make_store()
        for raw_id in ("session-1", "session-2"):
            store.create_event(
                {
                    "board_slug": "demo",
                    "event_type": "hook.userpromptsubmit",
                    "participant_id": "demo-ai-agent-manager",
                    "metadata": {"raw_agent_id": raw_id, "status": "running"},
                }
            )
        for title in ("First", "Second"):
            store.create_card(
                {
                    "board_slug": "demo",
                    "title": title,
                    "description": "Ambiguous live work.",
                    "status": "in_progress",
                    "assignee_id": "demo-ai-agent-manager",
                    "target_branch": "release/1.0.0",
                }
            )

        manager = next(
            item
            for item in store.snapshot("demo")["participants"]
            if item["id"] == "demo-ai-agent-manager"
        )

        self.assertEqual(len(manager["active_cards"]), 2)
        self.assertIsNotNone(manager["focused_card"])
        self.assertTrue(
            all(not instance["current_card_external_id"] for instance in manager["instances"])
        )


if __name__ == "__main__":
    unittest.main()
