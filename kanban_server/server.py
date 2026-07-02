from __future__ import annotations

import argparse
import errno
import ipaddress
import json
import mimetypes
import os
import queue
import socket
import sys
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs, unquote, urlparse

from .app_metadata import app_metadata as current_app_metadata
from .project.registration import auto_register_payload_for_cwd
from .store.core import KanbanStore
from .store.support import DEFAULT_DB_PATH

STATIC_DIR = Path(__file__).resolve().parent / "static"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8766
IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address


def _is_address_in_use_error(exc: OSError) -> bool:
    return exc.errno == errno.EADDRINUSE


def _host_addresses(host: str) -> set[IPAddress]:
    try:
        results = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return set()
    addresses: set[IPAddress] = set()
    for result in results:
        try:
            addresses.add(ipaddress.ip_address(result[4][0]))
        except ValueError:
            continue
    return addresses


def _proc_net_tcp_address(hex_address: str, *, ipv6: bool) -> IPAddress | None:
    try:
        raw_address = bytes.fromhex(hex_address)
    except ValueError:
        return None
    try:
        if ipv6:
            if len(raw_address) != 16:
                return None
            network_order = b"".join(
                raw_address[index : index + 4][::-1] for index in range(0, 16, 4)
            )
            return ipaddress.IPv6Address(network_order)
        if len(raw_address) != 4:
            return None
        return ipaddress.IPv4Address(raw_address[::-1])
    except ValueError:
        return None


def _ipv6_wildcard_can_block_ipv4() -> bool:
    try:
        return Path("/proc/sys/net/ipv6/bindv6only").read_text(encoding="utf-8").strip() == "0"
    except OSError:
        return False


def _listener_address_matches(
    listener_address: IPAddress,
    requested: set[IPAddress],
    *,
    ipv6_wildcard_blocks_ipv4: bool,
) -> bool:
    if not requested:
        return False
    if listener_address.is_unspecified:
        if any(address.version == listener_address.version for address in requested):
            return True
        return (
            ipv6_wildcard_blocks_ipv4
            and listener_address.version == 6
            and any(address.version == 4 for address in requested)
        )
    if any(
        address.is_unspecified and address.version == listener_address.version
        for address in requested
    ):
        return True
    return listener_address in requested


def _listener_socket_inodes(host: str, port: int) -> set[str]:
    requested_addresses = _host_addresses(host)
    ipv6_wildcard_blocks_ipv4 = _ipv6_wildcard_can_block_ipv4()
    inodes: set[str] = set()
    for proc_net_path, ipv6 in (
        (Path("/proc/net/tcp"), False),
        (Path("/proc/net/tcp6"), True),
    ):
        try:
            lines = proc_net_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines[1:]:
            fields = line.split()
            if len(fields) < 10 or fields[3] != "0A":
                continue
            try:
                hex_address, hex_port = fields[1].rsplit(":", 1)
                local_port = int(hex_port, 16)
            except ValueError:
                continue
            local_address = _proc_net_tcp_address(hex_address, ipv6=ipv6)
            if (
                local_port == port
                and local_address
                and _listener_address_matches(
                    local_address,
                    requested_addresses,
                    ipv6_wildcard_blocks_ipv4=ipv6_wildcard_blocks_ipv4,
                )
            ):
                inodes.add(fields[9])
    return inodes


def _pids_for_socket_inodes(inodes: set[str]) -> set[int]:
    if not inodes:
        return set()
    try:
        pid_dirs = sorted(
            (path for path in Path("/proc").iterdir() if path.name.isdecimal()),
            key=lambda path: int(path.name),
        )
    except OSError:
        return set()

    pids: set[int] = set()
    for pid_dir in pid_dirs:
        try:
            fd_paths = list((pid_dir / "fd").iterdir())
        except OSError:
            continue
        for fd_path in fd_paths:
            try:
                target = os.readlink(fd_path)
            except OSError:
                continue
            if (
                target.startswith("socket:[")
                and target.removeprefix("socket:[").removesuffix("]") in inodes
            ):
                pids.add(int(pid_dir.name))
                break
    return pids


def _find_listener_pid(host: str, port: int) -> int | None:
    pids = _pids_for_socket_inodes(_listener_socket_inodes(host, port))
    return next(iter(pids)) if len(pids) == 1 else None


def _address_in_use_message(host: str, port: int, pid: int | None) -> str:
    stop_hint = (
        f"Stop the process using that port with `kill {pid}`, or start this one on another port"
        if pid is not None
        else "Stop the existing dashboard process, or start this one on another port"
    )
    return (
        f"Codex Kanban could not start because {host}:{port} is already in use.\n"
        f"{stop_hint} with `python3 -m kanban_server --port <free-port>`."
    )


class EventBroker:
    def __init__(self) -> None:
        self._clients: dict[queue.Queue[dict[str, Any]], dict[str, Any]] = {}
        self._lock = threading.Lock()

    def subscribe(
        self,
        board_slug: str,
        *,
        include_archived: bool = False,
        archived_only: bool = False,
    ) -> queue.Queue[dict[str, Any]]:
        client: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=8)
        with self._lock:
            self._clients[client] = {
                "board_slug": board_slug,
                "include_archived": include_archived,
                "archived_only": archived_only,
            }
        return client

    def unsubscribe(self, client: queue.Queue[dict[str, Any]]) -> None:
        with self._lock:
            self._clients.pop(client, None)

    def publish(self, board_slug: str, event: str, data: dict[str, Any]) -> None:
        message = {"event": event, "data": data}
        with self._lock:
            clients = [
                client
                for client, settings in self._clients.items()
                if settings["board_slug"] == board_slug
            ]
        for client in clients:
            self._put(client, message)

    def publish_snapshots(
        self,
        board_slug: str,
        store: KanbanStore,
        app_metadata: dict[str, Any] | None = None,
    ) -> None:
        with self._lock:
            clients = [
                (client, dict(settings))
                for client, settings in self._clients.items()
                if settings["board_slug"] == board_slug
            ]
        snapshots: dict[tuple[bool, bool], dict[str, Any]] = {}
        for client, settings in clients:
            snapshot_key = (
                bool(settings.get("include_archived")),
                bool(settings.get("archived_only")),
            )
            if snapshot_key not in snapshots:
                snapshots[snapshot_key] = store.snapshot(
                    board_slug,
                    include_archived=snapshot_key[0],
                    archived_only=snapshot_key[1],
                )
                snapshots[snapshot_key]["app"] = dict(app_metadata or {})
            self._put(
                client,
                {
                    "event": "snapshot",
                    "data": snapshots[snapshot_key],
                },
            )

    def _put(self, client: queue.Queue[dict[str, Any]], message: dict[str, Any]) -> None:
        try:
            client.put_nowait(message)
        except queue.Full:
            try:
                client.get_nowait()
                client.put_nowait(message)
            except queue.Full:
                pass
            except queue.Empty:
                pass

    def board_slugs(self) -> set[str]:
        with self._lock:
            return {settings["board_slug"] for settings in self._clients.values()}


class KanbanHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        handler_class: type[BaseHTTPRequestHandler],
        *,
        store: KanbanStore,
        static_dir: Path,
        default_board_slug: str | None = None,
        app_metadata: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(server_address, handler_class)
        self.store = store
        self.static_dir = static_dir
        self.default_board_slug = default_board_slug
        self.app_metadata = current_app_metadata() if app_metadata is None else app_metadata
        self.broker = EventBroker()
        self.scheduler_stop = threading.Event()


class KanbanHandler(BaseHTTPRequestHandler):
    server_version = "CodexKanban/0.1"

    @property
    def kanban_server(self) -> KanbanHTTPServer:
        return cast(KanbanHTTPServer, self.server)

    def log_message(self, format: str, *args: Any) -> None:
        sys.stderr.write(f"{self.address_string()} - {format % args}\n")

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self._cors_headers()
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/snapshot":
                query = parse_qs(parsed.query)
                board = query.get("board", [None])[0]
                include_archived = query.get("include_archived", ["0"])[0] in {
                    "1",
                    "true",
                    "yes",
                    "on",
                }
                archived_only = query.get("archived_only", ["0"])[0] in {
                    "1",
                    "true",
                    "yes",
                    "on",
                }
                self._send_json(
                    self._snapshot(
                        board or self.kanban_server.default_board_slug,
                        include_archived=include_archived,
                        archived_only=archived_only,
                    )
                )
                return
            if parsed.path == "/api/projects":
                snapshot = self.kanban_server.store.snapshot(self.kanban_server.default_board_slug)
                self._send_json(
                    {
                        "projects": snapshot["projects"],
                        "all_projects": snapshot["all_projects"],
                        "boards": snapshot["boards"],
                    }
                )
                return
            if parsed.path == "/api/overview":
                query = parse_qs(parsed.query)
                board = query.get("board", [None])[0]
                cwd = query.get("cwd", [None])[0]
                repo = query.get("repo", [None])[0]
                include_archived = self._truthy_query(query, "include_archived")
                archived_only = self._truthy_query(query, "archived_only")
                limit = self._int_query(query, "limit")
                result = self.kanban_server.store.overview(
                    board,
                    cwd=cwd,
                    repo=repo,
                    include_archived=include_archived,
                    archived_only=archived_only,
                    limit=limit,
                )
                if (
                    self._truthy_query(query, "register_if_missing")
                    and not board
                    and not result.get("matched_project")
                    and not (result.get("project_resolution") or {}).get("ambiguous")
                ):
                    registration_target = repo or cwd
                    payload = (
                        auto_register_payload_for_cwd(registration_target)
                        if registration_target
                        else None
                    )
                    if payload:
                        registered_project = self.kanban_server.store.register_project(payload)
                        self._broadcast_project_change(registered_project["board_slug"])
                        result = self.kanban_server.store.overview(
                            board,
                            cwd=cwd,
                            repo=repo,
                            include_archived=include_archived,
                            archived_only=archived_only,
                            limit=limit,
                        )
                        result["registered_project"] = registered_project
                self._send_json(result)
                return
            if parsed.path == "/api/workflows/due-cards":
                query = parse_qs(parsed.query)
                board = query.get("board", [None])[0]
                raw_limit = query.get("limit", ["0"])[0]
                try:
                    limit = int(raw_limit)
                except ValueError:
                    limit = 0
                self._send_json(
                    {
                        "cards": self.kanban_server.store.due_workflow_cards(
                            board,
                            limit=limit if limit > 0 else None,
                        )
                    }
                )
                return
            if parsed.path == "/api/events/stream":
                query = parse_qs(parsed.query)
                board = (
                    query.get("board", [None])[0]
                    or self.kanban_server.default_board_slug
                    or self.kanban_server.store.default_board_slug()
                )
                include_archived = query.get("include_archived", ["0"])[0] in {
                    "1",
                    "true",
                    "yes",
                    "on",
                }
                archived_only = query.get("archived_only", ["0"])[0] in {
                    "1",
                    "true",
                    "yes",
                    "on",
                }
                self._stream_events(
                    board,
                    include_archived=include_archived,
                    archived_only=archived_only,
                )
                return
            self._serve_static(parsed.path)
        except Exception as exc:
            self._send_error(exc)

    @staticmethod
    def _truthy_query(query: dict[str, list[str]], key: str) -> bool:
        return query.get(key, ["0"])[0] in {"1", "true", "yes", "on"}

    @staticmethod
    def _int_query(query: dict[str, list[str]], key: str) -> int:
        try:
            return int(query.get(key, ["0"])[0])
        except ValueError:
            return 0

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            payload = self._read_json()
            if parsed.path == "/api/projects":
                project = self.kanban_server.store.register_project(payload)
                self._broadcast_project_change(project["board_slug"])
                self._send_json(project, HTTPStatus.CREATED)
                return

            parts = parsed.path.strip("/").split("/")
            if len(parts) == 4 and parts[:2] == ["api", "projects"]:
                project_slug = unquote(parts[2])
                action = parts[3]
                if action == "remove":
                    project = self.kanban_server.store.remove_project(project_slug)
                    self._broadcast_project_change(project["board_slug"])
                    self._send_json(project)
                    return
                if action == "prune":
                    result = self.kanban_server.store.prune_project(project_slug)
                    self._broadcast_project_change(result["board_slug"])
                    self._send_json(result)
                    return

            if parsed.path == "/api/cards":
                payload.setdefault("owner_id", payload.get("actor_id"))
                card = self.kanban_server.store.create_card(payload)
                self.kanban_server.store.create_event(
                    {
                        "board_slug": card["board_slug"],
                        "event_type": "card.created",
                        "card_id": card["id"],
                        "participant_id": payload.get("actor_id"),
                        "message": card["title"],
                        "metadata": {"status": card["status"]},
                    }
                )
                self._broadcast(card["board_slug"])
                self._send_json(card, HTTPStatus.CREATED)
                return

            if len(parts) == 4 and parts[:2] == ["api", "cards"]:
                card_id = int(parts[2])
                action = parts[3]
                if action == "run-now":
                    result = self.kanban_server.store.run_repeating_card_now(card_id, payload)
                    card = result["card"]
                    self._broadcast(card["board_slug"])
                    self._send_json(
                        result,
                        HTTPStatus.CREATED if result.get("created") else HTTPStatus.OK,
                    )
                    return
                if action == "comments":
                    comment = self.kanban_server.store.add_card_comment(card_id, payload)
                    self.kanban_server.store.create_event(
                        {
                            "board_slug": comment["board_slug"],
                            "event_type": "card.commented",
                            "card_id": comment["card_id"],
                            "participant_id": comment.get("participant_id"),
                            "message": comment["body"][:120],
                            "metadata": {"comment_id": comment["id"]},
                        }
                    )
                    self._broadcast(comment["board_slug"])
                    self._send_json(comment, HTTPStatus.CREATED)
                    return

            if parsed.path == "/api/workflows/start":
                result = self.kanban_server.store.start_workflow(payload)
                card = result["card"]
                if result.get("created"):
                    self.kanban_server.store.create_event(
                        {
                            "board_slug": card["board_slug"],
                            "event_type": "workflow.started",
                            "card_id": card["id"],
                            "participant_id": payload.get("actor_id"),
                            "message": card["title"],
                            "metadata": {
                                "workflow_key": payload.get("workflow_key") or "",
                                "scheduled_for": payload.get("scheduled_for") or "",
                            },
                        }
                    )
                self._broadcast(card["board_slug"])
                self._send_json(
                    result, HTTPStatus.CREATED if result.get("created") else HTTPStatus.OK
                )
                return

            if parsed.path == "/api/workflows/due":
                board = payload.get("board_slug") or payload.get("board")
                results = self.kanban_server.store.run_due_repeating_cards(board_slug=board)
                board_slugs = {
                    result["card"]["board_slug"] for result in results if result.get("card")
                }
                for board_slug in board_slugs:
                    self._broadcast(board_slug)
                self._send_json({"results": results})
                return

            if parsed.path == "/api/participants":
                participant = self.kanban_server.store.upsert_participant(payload)
                self.kanban_server.store.create_event(
                    {
                        "board_slug": participant.get("current_board_slug")
                        or self.kanban_server.store.default_board_slug(),
                        "event_type": "participant.updated",
                        "participant_id": participant["id"],
                        "message": participant["display_name"],
                        "metadata": {
                            "kind": participant["kind"],
                            "status": participant["status"],
                        },
                    }
                )
                self._broadcast(
                    participant.get("current_board_slug")
                    or self.kanban_server.store.default_board_slug()
                )
                self._send_json(participant, HTTPStatus.CREATED)
                return

            if parsed.path.startswith("/api/participants/") and parsed.path.endswith("/heartbeat"):
                participant_id = parsed.path.split("/")[3]
                participant = self.kanban_server.store.heartbeat(participant_id, payload)
                if not payload.get("quiet"):
                    self.kanban_server.store.create_event(
                        {
                            "board_slug": participant.get("current_board_slug")
                            or self.kanban_server.store.default_board_slug(),
                            "event_type": "participant.heartbeat",
                            "participant_id": participant["id"],
                            "message": participant["status"],
                            "metadata": {"scope": participant.get("current_scope") or ""},
                        }
                    )
                self._broadcast(
                    participant.get("current_board_slug")
                    or self.kanban_server.store.default_board_slug()
                )
                self._send_json(participant)
                return

            if parsed.path == "/api/events":
                if payload.get("participant"):
                    participant = dict(payload["participant"])
                    participant.setdefault(
                        "board_slug",
                        payload.get("board_slug") or self.kanban_server.store.default_board_slug(),
                    )
                    saved_participant = self.kanban_server.store.upsert_participant(participant)
                    payload.setdefault("participant_id", saved_participant["id"])
                event = self.kanban_server.store.create_event(payload)
                self._broadcast(event["board_slug"])
                self._send_json(event, HTTPStatus.CREATED)
                return

            self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        except Exception as exc:
            self._send_error(exc)

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        try:
            parts = parsed.path.strip("/").split("/")
            if len(parts) == 3 and parts[:2] == ["api", "cards"]:
                card_id = int(parts[2])
                result = self.kanban_server.store.delete_card(card_id)
                card = result["card"]
                self.kanban_server.store.create_event(
                    {
                        "board_slug": card["board_slug"],
                        "event_type": "card.deleted",
                        "message": (
                            f"{card.get('external_id') or card_id} {card.get('title') or ''}"
                        ),
                        "metadata": {
                            "deleted_card_id": card_id,
                            "deleted_external_id": card.get("external_id"),
                        },
                    }
                )
                self._broadcast(card["board_slug"])
                self._send_json(result)
                return
            self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        except Exception as exc:
            self._send_error(exc)

    def do_PATCH(self) -> None:
        parsed = urlparse(self.path)
        try:
            parts = parsed.path.strip("/").split("/")
            if len(parts) == 4 and parts[:2] == ["api", "projects"]:
                project_slug = unquote(parts[2])
                action = parts[3]
                if action == "settings":
                    project = self.kanban_server.store.update_project_settings(
                        project_slug,
                        self._read_json(),
                    )
                    self._broadcast_project_change(project["board_slug"])
                    self._send_json(project)
                    return
            if len(parts) == 3 and parts[:2] == ["api", "cards"]:
                card_id = int(parts[2])
                before = self.kanban_server.store.get_card(card_id)
                card = self.kanban_server.store.update_card(card_id, self._read_json())
                event_type = "card.updated"
                message = card["title"]
                metadata: dict[str, Any] = {}
                if before and before.get("status") != card.get("status"):
                    event_type = "card.moved"
                    message = f"{before.get('status')} -> {card.get('status')}"
                    metadata["from_status"] = before.get("status")
                    metadata["to_status"] = card.get("status")
                self.kanban_server.store.create_event(
                    {
                        "board_slug": card["board_slug"],
                        "event_type": event_type,
                        "card_id": card["id"],
                        "message": message,
                        "metadata": metadata,
                    }
                )
                self._broadcast(card["board_slug"])
                self._send_json(card)
                return
            self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        except Exception as exc:
            self._send_error(exc)

    def _broadcast(self, board_slug: str) -> None:
        self.kanban_server.broker.publish_snapshots(
            board_slug,
            self.kanban_server.store,
            self.kanban_server.app_metadata,
        )

    def _broadcast_project_change(self, board_slug: str | None = None) -> None:
        board_slugs = self.kanban_server.broker.board_slugs()
        if board_slug:
            board_slugs.add(board_slug)
        for active_board_slug in board_slugs:
            self._broadcast(active_board_slug)

    def _stream_events(
        self,
        board_slug: str,
        *,
        include_archived: bool = False,
        archived_only: bool = False,
    ) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self._cors_headers()
        self.end_headers()
        client = self.kanban_server.broker.subscribe(
            board_slug,
            include_archived=include_archived,
            archived_only=archived_only,
        )
        try:
            self._write_sse(
                "snapshot",
                self._snapshot(
                    board_slug,
                    include_archived=include_archived,
                    archived_only=archived_only,
                ),
            )
            while True:
                try:
                    message = client.get(timeout=25)
                    self._write_sse(message["event"], message["data"])
                except queue.Empty:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            return
        finally:
            self.kanban_server.broker.unsubscribe(client)

    def _write_sse(self, event: str, data: dict[str, Any]) -> None:
        payload = json.dumps(data, ensure_ascii=True)
        self.wfile.write(f"event: {event}\ndata: {payload}\n\n".encode())
        self.wfile.flush()

    def _snapshot(
        self,
        board_slug: str | None,
        *,
        include_archived: bool = False,
        archived_only: bool = False,
    ) -> dict[str, Any]:
        snapshot = self.kanban_server.store.snapshot(
            board_slug,
            include_archived=include_archived,
            archived_only=archived_only,
        )
        snapshot["app"] = dict(self.kanban_server.app_metadata)
        return snapshot

    def _serve_static(self, request_path: str) -> None:
        if request_path in {"", "/"}:
            relative = "index.html"
        elif request_path.startswith("/static/"):
            relative = request_path.removeprefix("/static/")
        else:
            relative = request_path.lstrip("/")

        static_root = self.kanban_server.static_dir.resolve()
        target = (static_root / relative).resolve()
        if not target.is_relative_to(static_root) or not target.is_file():
            self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            return

        content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        data = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self._cors_headers()
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or "0")
        if length == 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw) if raw.strip() else {}

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload, ensure_ascii=True, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self._cors_headers()
        self.end_headers()
        self.wfile.write(data)

    def _send_error(self, exc: Exception) -> None:
        if isinstance(exc, ValueError):
            status = HTTPStatus.BAD_REQUEST
        elif isinstance(exc, KeyError):
            status = HTTPStatus.NOT_FOUND
        elif isinstance(exc, json.JSONDecodeError):
            status = HTTPStatus.BAD_REQUEST
            exc = ValueError("invalid JSON")
        else:
            status = HTTPStatus.INTERNAL_SERVER_ERROR
        self._send_json({"error": str(exc)}, status)

    def _cors_headers(self) -> None:
        origin = self.headers.get("Origin")
        if origin:
            host = urlparse(origin).hostname
            if host in {"127.0.0.1", "localhost", "::1"}:
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")


def _run_scheduler(server: KanbanHTTPServer) -> None:
    while not server.scheduler_stop.is_set():
        try:
            results = server.store.run_due_repeating_cards()
            board_slugs = {result["card"]["board_slug"] for result in results if result.get("card")}
            for board_slug in board_slugs:
                server.broker.publish_snapshots(
                    board_slug,
                    server.store,
                    server.app_metadata,
                )
        except Exception as exc:
            sys.stderr.write(f"Codex Kanban scheduler error: {exc}\n")
        server.scheduler_stop.wait(60)


def _preferred_board_slug(store: KanbanStore) -> str | None:
    explicit = os.environ.get("CODEX_KANBAN_BOARD", "").strip()
    if explicit:
        return explicit
    project = store.project_for_path(Path.cwd())
    return project["board_slug"] if project else None


def run_server(host: str, port: int, db_path: Path) -> None:
    store = KanbanStore(db_path)
    default_board_slug = _preferred_board_slug(store)
    store.preferred_board_slug = default_board_slug
    server = KanbanHTTPServer(
        (host, port),
        KanbanHandler,
        store=store,
        static_dir=STATIC_DIR,
        default_board_slug=default_board_slug,
    )
    scheduler = threading.Thread(target=_run_scheduler, args=(server,), daemon=True)
    scheduler.start()
    print(f"Codex Kanban running at http://{host}:{port}", flush=True)
    print(f"SQLite database: {store.db_path}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.scheduler_stop.set()
        scheduler.join(timeout=2)
        server.server_close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Codex Kanban dashboard.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    args = parser.parse_args(argv)
    try:
        run_server(args.host, args.port, args.db)
    except OSError as exc:
        if not _is_address_in_use_error(exc):
            raise
        print(
            _address_in_use_message(args.host, args.port, _find_listener_pid(args.host, args.port)),
            file=sys.stderr,
        )
        return 1
    return 0
