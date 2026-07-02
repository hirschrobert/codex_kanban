from __future__ import annotations

import contextlib
import errno
import io
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from unittest import mock

from kanban_server import server
from kanban_server.store import KanbanStore


class QuietKanbanHandler(server.KanbanHandler):
    def log_message(self, format: str, *args: object) -> None:
        del format, args


class ServerDefaultsTest(unittest.TestCase):
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

    def start_server(
        self,
        store: KanbanStore,
        *,
        default_board_slug: str | None = None,
        app_metadata: dict[str, Any] | None = None,
    ) -> server.KanbanHTTPServer:
        httpd = server.KanbanHTTPServer(
            ("127.0.0.1", 0),
            QuietKanbanHandler,
            store=store,
            static_dir=server.STATIC_DIR,
            default_board_slug=default_board_slug,
            app_metadata=app_metadata,
        )
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        return httpd

    def request_json(
        self,
        httpd: server.KanbanHTTPServer,
        path: str,
        payload: dict[str, object],
        *,
        method: str = "POST",
    ) -> tuple[int, dict[str, Any]]:
        url = f"http://127.0.0.1:{httpd.server_address[1]}{path}"
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method=method,
        )
        with urllib.request.urlopen(request, timeout=3) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def test_default_port_avoids_common_oauth_callback_port(self) -> None:
        self.assertEqual(server.DEFAULT_PORT, 8766)
        self.assertNotEqual(server.DEFAULT_PORT, 8765)

    def test_main_prints_friendly_message_when_port_is_in_use(self) -> None:
        stderr = io.StringIO()
        error = OSError(errno.EADDRINUSE, "Address already in use")

        with mock.patch.object(server, "run_server", side_effect=error):
            with mock.patch.object(server, "_find_listener_pid", return_value=12345):
                with contextlib.redirect_stderr(stderr):
                    exit_code = server.main(["--host", "127.0.0.1", "--port", "8766"])

        message = stderr.getvalue()
        self.assertEqual(exit_code, 1)
        self.assertIn("Codex Kanban could not start", message)
        self.assertIn("127.0.0.1:8766", message)
        self.assertIn("kill 12345", message)
        self.assertIn("--port <free-port>", message)
        self.assertNotIn("Traceback", message)

    def test_main_reraises_unexpected_os_errors(self) -> None:
        stderr = io.StringIO()
        error = OSError(errno.EACCES, "Permission denied")

        with mock.patch.object(server, "run_server", side_effect=error):
            with contextlib.redirect_stderr(stderr):
                with self.assertRaises(OSError):
                    server.main(["--host", "127.0.0.1", "--port", "8766"])

        self.assertEqual(stderr.getvalue(), "")

    def test_listener_socket_inodes_match_requested_local_address(self) -> None:
        def listener_row(index: int, address: str, inode: str) -> str:
            return (
                f"{index}: {address}:223E 00000000:0000 0A 00000000:00000000 "
                f"00:00000000 00000000 100 0 {inode} 1"
            )

        proc_net_tcp = "\n".join(
            [
                "header",
                listener_row(0, "0100007F", "111"),
                listener_row(1, "0200007F", "222"),
                listener_row(2, "00000000", "333"),
            ]
        )

        def fake_read_text(path: Path, *, encoding: str = "utf-8") -> str:
            del encoding
            if str(path) == "/proc/net/tcp":
                return proc_net_tcp
            raise FileNotFoundError(path)

        with mock.patch.object(Path, "read_text", fake_read_text):
            self.assertEqual(server._listener_socket_inodes("127.0.0.1", 8766), {"111", "333"})
            self.assertEqual(server._listener_socket_inodes("127.0.0.2", 8766), {"222", "333"})

    def test_listener_socket_inodes_include_dual_stack_ipv6_wildcard(self) -> None:
        wildcard = "00000000000000000000000000000000"
        proc_net_tcp6 = "\n".join(
            [
                "header",
                (
                    f"0: {wildcard}:223E {wildcard}:0000 "
                    "0A 00000000:00000000 00:00000000 00000000 100 0 444 1"
                ),
            ]
        )

        def fake_read_text(path: Path, *, encoding: str = "utf-8") -> str:
            del encoding
            path_text = str(path)
            if path_text == "/proc/net/tcp":
                return "header"
            if path_text == "/proc/net/tcp6":
                return proc_net_tcp6
            if path_text == "/proc/sys/net/ipv6/bindv6only":
                return "0\n"
            raise FileNotFoundError(path)

        with mock.patch.object(Path, "read_text", fake_read_text):
            self.assertEqual(server._listener_socket_inodes("127.0.0.1", 8766), {"444"})

    def test_find_listener_pid_suppresses_ambiguous_matches(self) -> None:
        with mock.patch.object(server, "_listener_socket_inodes", return_value={"111", "222"}):
            with mock.patch.object(server, "_pids_for_socket_inodes", return_value={123, 456}):
                self.assertIsNone(server._find_listener_pid("127.0.0.1", 8766))

    def test_static_assets_are_not_cached(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = KanbanStore(Path(tmp) / "kanban.sqlite3")
            httpd = self.start_server(store)

            with urllib.request.urlopen(
                f"http://127.0.0.1:{httpd.server_address[1]}/static/app.js",
                timeout=3,
            ) as response:
                response.read()

            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers.get("Cache-Control"), "no-store")

    def test_cors_allows_only_loopback_origins(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = KanbanStore(Path(tmp) / "kanban.sqlite3")
            httpd = self.start_server(store)
            url = f"http://127.0.0.1:{httpd.server_address[1]}/api/snapshot"

            trusted = urllib.request.Request(url, headers={"Origin": "http://localhost:8766"})
            with urllib.request.urlopen(trusted, timeout=3) as response:
                response.read()
            self.assertEqual(
                response.headers.get("Access-Control-Allow-Origin"), "http://localhost:8766"
            )

            untrusted = urllib.request.Request(url, headers={"Origin": "https://example.test"})
            with urllib.request.urlopen(untrusted, timeout=3) as response:
                response.read()
            self.assertIsNone(response.headers.get("Access-Control-Allow-Origin"))

    def test_snapshot_defaults_to_server_preferred_board(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = KanbanStore(Path(tmp) / "kanban.sqlite3")
            store.register_project(
                {
                    "slug": "empty",
                    "display_name": "A Empty",
                    "board_slug": "empty",
                    "card_prefix": "EM",
                    "root_path": "/tmp/empty",
                }
            )
            store.register_project(
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
                    "board_slug": "demo",
                    "title": "Visible card",
                    "description": "The preferred board should be visible by default.",
                }
            )
            httpd = self.start_server(store, default_board_slug="demo")

            with urllib.request.urlopen(
                f"http://127.0.0.1:{httpd.server_address[1]}/api/snapshot",
                timeout=3,
            ) as response:
                body = json.loads(response.read().decode("utf-8"))

            self.assertEqual(body["board"]["slug"], "demo")
            self.assertEqual([card["title"] for card in body["cards"]], ["Visible card"])

    def test_snapshot_refreshes_stale_agent_participants_for_ui(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "demo"
            (root / "src").mkdir(parents=True)
            agent_dir = root / ".codex" / "agents"
            agent_dir.mkdir(parents=True)
            (agent_dir / "qa-reviewer.toml").write_text(
                'name = "qa_reviewer"\n',
                encoding="utf-8",
            )
            store = KanbanStore(Path(tmp) / "kanban.sqlite3")
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
                    "UPDATE projects SET agent_profiles = ? WHERE slug = ?",
                    (json.dumps(["project_implementer"]), "demo"),
                )
                conn.execute(
                    "DELETE FROM participants WHERE id != ?",
                    ("demo-project-implementer",),
                )
            httpd = self.start_server(store, default_board_slug="demo")

            with urllib.request.urlopen(
                f"http://127.0.0.1:{httpd.server_address[1]}/api/snapshot?board=demo",
                timeout=3,
            ) as response:
                body = json.loads(response.read().decode("utf-8"))

            participant_ids = {participant["id"] for participant in body["participants"]}
            self.assertIn("demo-ai-agent-manager", participant_ids)
            self.assertIn("demo-domain-model-steward", participant_ids)
            self.assertIn("demo-qa-reviewer", participant_ids)

    def test_snapshot_includes_app_version_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = KanbanStore(Path(tmp) / "kanban.sqlite3")
            app_metadata = {
                "name": "codex-kanban",
                "version": "9.8.7",
                "hash": "abc1234",
                "dirty": False,
            }
            httpd = self.start_server(store, app_metadata=app_metadata)

            with urllib.request.urlopen(
                f"http://127.0.0.1:{httpd.server_address[1]}/api/snapshot",
                timeout=3,
            ) as response:
                body = json.loads(response.read().decode("utf-8"))

            self.assertEqual(body["app"], app_metadata)

    def test_snapshot_unknown_board_uses_server_preferred_board(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = KanbanStore(
                Path(tmp) / "kanban.sqlite3",
                preferred_board_slug="codex-kanban",
            )
            store.register_project(
                {
                    "slug": "other",
                    "display_name": "Other",
                    "board_slug": "other",
                    "card_prefix": "OT",
                    "root_path": "/tmp/other",
                }
            )
            store.register_project(
                {
                    "slug": "codex-kanban",
                    "display_name": "codex_kanban",
                    "board_slug": "codex-kanban",
                    "card_prefix": "CK",
                    "root_path": "/tmp/codex_kanban",
                }
            )
            httpd = self.start_server(store, default_board_slug="codex-kanban")

            with urllib.request.urlopen(
                f"http://127.0.0.1:{httpd.server_address[1]}/api/snapshot?board=ai-work",
                timeout=3,
            ) as response:
                body = json.loads(response.read().decode("utf-8"))

            self.assertEqual(body["board"]["slug"], "codex-kanban")
            self.assertNotIn("ai-work", {board["slug"] for board in body["boards"]})

    def test_patch_project_settings_updates_implementer_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = KanbanStore(Path(tmp) / "kanban.sqlite3")
            store.register_project(
                {
                    "slug": "demo",
                    "display_name": "Demo",
                    "board_slug": "demo",
                    "card_prefix": "DM",
                    "root_path": "/tmp/demo",
                }
            )
            httpd = self.start_server(store)

            url = f"http://127.0.0.1:{httpd.server_address[1]}/api/projects/demo/settings"
            request = urllib.request.Request(
                url,
                data=json.dumps({"max_active_implementers": 2}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="PATCH",
            )

            with urllib.request.urlopen(request, timeout=3) as response:
                body = json.loads(response.read().decode("utf-8"))

            self.assertEqual(response.status, 200)
            self.assertEqual(body["max_active_implementers"], 2)
            self.assertEqual(
                store.snapshot("demo")["active_project"]["max_active_implementers"],
                2,
            )

    def test_patch_card_status_returns_400_when_dependency_unready(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = KanbanStore(Path(tmp) / "kanban.sqlite3")
            httpd = self.start_server(store)
            _, child = self.request_json(
                httpd,
                "/api/cards",
                {
                    "board_slug": "demo",
                    "title": "Child",
                    "description": "Prerequisite work.",
                },
            )
            _, parent = self.request_json(
                httpd,
                "/api/cards",
                {
                    "board_slug": "demo",
                    "title": "Parent",
                    "description": "Parent depends on child.",
                    "child_external_ids": [child["external_id"]],
                },
            )

            url = f"http://127.0.0.1:{httpd.server_address[1]}/api/cards/{parent['id']}"
            request = urllib.request.Request(
                url,
                data=json.dumps({"status": "in_progress"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="PATCH",
            )

            with self.assertRaises(urllib.error.HTTPError) as raised:
                urllib.request.urlopen(request, timeout=3)

            body = json.loads(raised.exception.read().decode("utf-8"))
            self.assertEqual(raised.exception.code, 400)
            self.assertIn("child dependencies are done", body["error"])

    def test_post_workflow_start_creates_card_and_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = KanbanStore(Path(tmp) / "kanban.sqlite3")
            self.register_demo_project(store)
            httpd = self.start_server(store)

            status, result = self.request_json(
                httpd,
                "/api/workflows/start",
                {
                    "board_slug": "demo",
                    "workflow_key": "docs-refresh",
                    "scheduled_for": "2026-06-28",
                    "title": "Refresh stale docs",
                    "description": "Check documentation drift from recent changes.",
                    "target_repo": "/tmp/demo",
                    "target_branch": "release/current",
                },
            )
            second_status, second = self.request_json(
                httpd,
                "/api/workflows/start",
                {
                    "board_slug": "demo",
                    "workflow_key": "docs-refresh",
                    "scheduled_for": "2026-06-28",
                    "title": "Refresh stale docs",
                    "description": "Check documentation drift from recent changes.",
                    "target_repo": "/tmp/demo",
                    "target_branch": "release/current",
                },
            )

            snapshot = store.snapshot("demo")

            self.assertEqual(status, 201)
            self.assertEqual(second_status, 200)
            self.assertTrue(result["created"])
            self.assertFalse(second["created"])
            self.assertEqual(result["card"]["id"], second["card"]["id"])
            self.assertTrue(
                any(event["event_type"] == "workflow.started" for event in snapshot["events"])
            )

    def test_post_card_run_now_creates_manual_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = KanbanStore(Path(tmp) / "kanban.sqlite3")
            self.register_demo_project(store)
            httpd = self.start_server(store)
            _, template = self.request_json(
                httpd,
                "/api/cards",
                {
                    "board_slug": "demo",
                    "title": "Refresh docs",
                    "description": "Check documentation drift.",
                    "target_repo": "/tmp/demo",
                    "target_branch": "release/current",
                    "repeat_cadence": "daily",
                },
            )

            status, result = self.request_json(
                httpd,
                f"/api/cards/{template['id']}/run-now",
                {},
            )
            snapshot = store.snapshot("demo")

            self.assertEqual(status, 201)
            self.assertTrue(result["created"])
            self.assertEqual(result["card"]["repeat_cadence"], "none")
            self.assertTrue(
                any(event["event_type"] == "workflow.manual" for event in snapshot["events"])
            )

    def test_post_due_workflows_respects_board_filter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = KanbanStore(Path(tmp) / "kanban.sqlite3")
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
            httpd = self.start_server(store)
            _, demo = self.request_json(
                httpd,
                "/api/cards",
                {
                    "board_slug": "demo",
                    "title": "Refresh demo docs",
                    "description": "Check demo docs.",
                    "target_repo": "/tmp/demo",
                    "target_branch": "release/current",
                    "repeat_cadence": "daily",
                },
            )
            _, other = self.request_json(
                httpd,
                "/api/cards",
                {
                    "board_slug": "other",
                    "title": "Refresh other docs",
                    "description": "Check other docs.",
                    "target_repo": "/tmp/other",
                    "target_branch": "release/current",
                    "repeat_cadence": "daily",
                },
            )
            with store._connect() as conn:
                conn.execute(
                    "UPDATE cards SET repeat_next_run_at = ? WHERE id IN (?, ?)",
                    ("2026-06-27T23:00:00Z", demo["id"], other["id"]),
                )

            status, result = self.request_json(
                httpd,
                "/api/workflows/due",
                {"board_slug": "demo"},
            )

            self.assertEqual(status, 200)
            self.assertEqual([item["card"]["board_slug"] for item in result["results"]], ["demo"])
            self.assertEqual(len(store.due_workflow_cards("demo")), 1)
            self.assertEqual(store.due_workflow_cards("other"), [])

    def test_post_card_comment_attaches_note(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = KanbanStore(Path(tmp) / "kanban.sqlite3")
            httpd = self.start_server(store)
            _, card = self.request_json(
                httpd,
                "/api/cards",
                {
                    "board_slug": "demo",
                    "title": "Needs notes",
                    "description": "Capture context.",
                },
            )

            status, comment = self.request_json(
                httpd,
                f"/api/cards/{card['id']}/comments",
                {"body": "Use the latest handoff note."},
            )
            updated = store.get_card(card["id"])
            assert updated is not None

            self.assertEqual(status, 201)
            self.assertEqual(comment["body"], "Use the latest handoff note.")
            self.assertEqual(comment["author_name"], "local developer")
            self.assertEqual(comment["author_kind"], "human")
            self.assertIsNotNone(comment["created_at"])
            self.assertEqual(updated["comment_count"], 1)
            self.assertEqual(updated["comments"][0]["body"], "Use the latest handoff note.")
            self.assertEqual(updated["comments"][0]["author_name"], "local developer")

    def test_post_and_patch_card_intake_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = KanbanStore(Path(tmp) / "kanban.sqlite3")
            httpd = self.start_server(store)

            status, card = self.request_json(
                httpd,
                "/api/cards",
                {
                    "board_slug": "demo",
                    "title": "Portal sorting request",
                    "description": "Show newest invoices first.",
                    "intake_kind": "feature_request",
                    "intake_source": "dashboard",
                    "reported_by": "Operations",
                    "impact": "Reduces manual searching.",
                    "evidence": "Requested during triage.",
                    "affected_paths": ["/workspace/portal"],
                    "deployment_dispositions": [{"path": "/workspace/portal", "status": "pending"}],
                },
            )
            patch_status, updated = self.request_json(
                httpd,
                f"/api/cards/{card['id']}",
                {
                    "intake_source": "main_agent",
                    "affected_paths": ["/workspace/portal", "/workspace/db_worker"],
                    "deployment_dispositions": ["/workspace/portal=deployed:verified live bundle"],
                },
                method="PATCH",
            )

            self.assertEqual(status, 201)
            self.assertEqual(card["intake_kind"], "feature_request")
            self.assertEqual(card["intake_source"], "dashboard")
            self.assertEqual(card["reported_by"], "Operations")
            self.assertEqual(card["impact"], "Reduces manual searching.")
            self.assertEqual(card["evidence"], "Requested during triage.")
            self.assertEqual(card["affected_paths"], ["/workspace/portal"])
            self.assertEqual(
                card["deployment_dispositions"],
                [{"path": "/workspace/portal", "status": "pending"}],
            )
            self.assertEqual(patch_status, 200)
            self.assertEqual(updated["intake_source"], "main_agent")
            self.assertEqual(
                updated["affected_paths"], ["/workspace/portal", "/workspace/db_worker"]
            )
            self.assertEqual(
                updated["deployment_dispositions"],
                [
                    {
                        "path": "/workspace/portal",
                        "status": "deployed",
                        "note": "verified live bundle",
                    }
                ],
            )

    def test_delete_card_requires_archived_card(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = KanbanStore(Path(tmp) / "kanban.sqlite3")
            httpd = self.start_server(store)
            _, card = self.request_json(
                httpd,
                "/api/cards",
                {
                    "board_slug": "demo",
                    "title": "Delete later",
                    "description": "Only archived cards can be deleted.",
                },
            )

            url = f"http://127.0.0.1:{httpd.server_address[1]}/api/cards/{card['id']}"
            delete_request = urllib.request.Request(url, method="DELETE")
            with self.assertRaises(urllib.error.HTTPError) as raised:
                urllib.request.urlopen(delete_request, timeout=3)
            self.assertEqual(raised.exception.code, 400)

            self.request_json(
                httpd,
                f"/api/cards/{card['id']}",
                {"archived": True},
                method="PATCH",
            )
            request = urllib.request.Request(url, method="DELETE")
            with urllib.request.urlopen(request, timeout=3) as response:
                body = json.loads(response.read().decode("utf-8"))

            self.assertEqual(response.status, 200)
            self.assertTrue(body["deleted"])
            self.assertIsNone(store.get_card(card["id"]))

    def test_snapshot_can_include_archived_cards(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = KanbanStore(Path(tmp) / "kanban.sqlite3")
            httpd = self.start_server(store)
            _, active = self.request_json(
                httpd,
                "/api/cards",
                {
                    "board_slug": "demo",
                    "title": "Active card",
                    "description": "Visible by default.",
                },
            )
            _, card = self.request_json(
                httpd,
                "/api/cards",
                {
                    "board_slug": "demo",
                    "title": "Archived card",
                    "description": "Hidden by default.",
                    "archived": True,
                },
            )

            with urllib.request.urlopen(
                f"http://127.0.0.1:{httpd.server_address[1]}/api/snapshot?board=demo",
                timeout=3,
            ) as response:
                hidden = json.loads(response.read().decode("utf-8"))
            with urllib.request.urlopen(
                f"http://127.0.0.1:{httpd.server_address[1]}/api/snapshot?board=demo&include_archived=1",
                timeout=3,
            ) as response:
                shown = json.loads(response.read().decode("utf-8"))
            with urllib.request.urlopen(
                f"http://127.0.0.1:{httpd.server_address[1]}/api/snapshot?board=demo&archived_only=1",
                timeout=3,
            ) as response:
                archived_only = json.loads(response.read().decode("utf-8"))

            self.assertFalse(any(item["id"] == card["id"] for item in hidden["cards"]))
            self.assertTrue(any(item["id"] == active["id"] for item in hidden["cards"]))
            self.assertTrue(any(item["id"] == card["id"] for item in shown["cards"]))
            self.assertTrue(any(item["id"] == active["id"] for item in shown["cards"]))
            self.assertTrue(any(item["id"] == card["id"] for item in archived_only["cards"]))
            self.assertFalse(any(item["id"] == active["id"] for item in archived_only["cards"]))

    def test_overview_resolves_workspace_and_reports_archived_hint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = KanbanStore(Path(tmp) / "kanban.sqlite3")
            project = store.register_project(
                {
                    "slug": "demo",
                    "display_name": "Demo",
                    "board_slug": "demo",
                    "card_prefix": "DM",
                    "root_path": "/workspace",
                    "paths": [{"label": "Portal", "path": "/workspace/portal"}],
                }
            )
            active = store.create_card(
                {
                    "board_slug": project["board_slug"],
                    "title": "Visible overview card",
                    "description": "Description travels in the lean overview.",
                    "affected_paths": ["/workspace/portal/src/App.jsx"],
                }
            )
            archived = store.create_card(
                {
                    "board_slug": project["board_slug"],
                    "title": "Archived card",
                    "description": "Hidden by default.",
                    "archived": True,
                }
            )
            httpd = self.start_server(store)

            with urllib.request.urlopen(
                (
                    f"http://127.0.0.1:{httpd.server_address[1]}"
                    "/api/overview?cwd=/workspace/portal/src"
                ),
                timeout=3,
            ) as response:
                overview = json.loads(response.read().decode("utf-8"))

            self.assertEqual(overview["matched_project"]["slug"], "demo")
            self.assertEqual(overview["board"]["slug"], "demo")
            self.assertEqual(overview["archived_card_count"], 1)
            self.assertTrue(overview["archived_cards_hidden"])
            self.assertEqual([card["id"] for card in overview["cards"]], [active["id"]])
            self.assertEqual(
                overview["cards"][0]["affected_project_paths"][0]["label"],
                "Portal",
            )

            with urllib.request.urlopen(
                (
                    f"http://127.0.0.1:{httpd.server_address[1]}"
                    "/api/overview?cwd=/workspace/portal/src&archived_only=1"
                ),
                timeout=3,
            ) as response:
                archived_only = json.loads(response.read().decode("utf-8"))

            self.assertEqual([card["id"] for card in archived_only["cards"]], [archived["id"]])

    def test_overview_done_limit_query_controls_completed_cards(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = KanbanStore(Path(tmp) / "kanban.sqlite3")
            project = store.register_project(
                {
                    "slug": "demo",
                    "display_name": "Demo",
                    "board_slug": "demo",
                    "card_prefix": "DM",
                    "root_path": "/workspace",
                }
            )
            active = store.create_card(
                {
                    "board_slug": project["board_slug"],
                    "title": "Active overview card",
                    "description": "Active card.",
                    "status": "in_progress",
                }
            )
            done_cards = [
                store.create_card(
                    {
                        "board_slug": project["board_slug"],
                        "title": f"Done card {index}",
                        "description": "Done card.",
                        "status": "done",
                    }
                )
                for index in range(4)
            ]
            httpd = self.start_server(store)

            with urllib.request.urlopen(
                (
                    f"http://127.0.0.1:{httpd.server_address[1]}"
                    "/api/overview?board=demo&done_limit=2"
                ),
                timeout=3,
            ) as response:
                overview = json.loads(response.read().decode("utf-8"))

            self.assertEqual(overview["done_card_count"], 4)
            self.assertEqual(overview["done_cards_hidden_count"], 2)
            self.assertIn(active["id"], [card["id"] for card in overview["cards"]])
            self.assertEqual(
                [card["id"] for card in overview["cards"] if card["status"] == "done"],
                [card["id"] for card in reversed(done_cards[-2:])],
            )


if __name__ == "__main__":
    unittest.main()
