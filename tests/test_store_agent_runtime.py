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
        self.assertNotIn("old-raw-agent-row", participant_ids)

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


if __name__ == "__main__":
    unittest.main()
