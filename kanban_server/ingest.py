from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .store.core import KanbanStore
from .store.support import DEFAULT_DB_PATH, _normalise_metadata


def _read_stdin_json() -> dict[str, Any]:
    if sys.stdin.isatty():
        return {}
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {"stdin": raw}
    return parsed if isinstance(parsed, dict) else {"stdin": parsed}


def _post_json(server_url: str, path: str, payload: dict[str, Any]) -> bool:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        server_url.rstrip("/") + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            return 200 <= response.status < 300
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8").strip()
        try:
            parsed = json.loads(detail)
        except json.JSONDecodeError:
            parsed = {}
        message = parsed.get("error") or detail or exc.reason
        raise SystemExit(f"POST {path} failed: {message}") from exc
    except (OSError, urllib.error.URLError):
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Record a Codex Kanban event from hooks or wrapper scripts."
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument(
        "--server-url",
        default=os.environ.get("CODEX_KANBAN_URL", ""),
    )
    parser.add_argument(
        "--board",
        default=os.environ.get("CODEX_KANBAN_BOARD", ""),
    )
    parser.add_argument("--cwd", default=os.environ.get("CODEX_KANBAN_CWD", os.getcwd()))
    parser.add_argument("--event-type", default="event")
    parser.add_argument("--message", default="")
    parser.add_argument("--participant-id")
    parser.add_argument("--participant-kind", default="agent")
    parser.add_argument("--display-name")
    parser.add_argument("--role", default="")
    parser.add_argument("--status", default="running")
    parser.add_argument("--current-card-id", type=int)
    parser.add_argument("--current-card-external-id")
    parser.add_argument("--current-scope", default="")
    parser.add_argument("--card-id", type=int)
    parser.add_argument("--card-external-id")
    parser.add_argument("--metadata", default="")
    args = parser.parse_args(argv)

    stdin_payload = _read_stdin_json()
    metadata = _normalise_metadata(args.metadata)
    if stdin_payload:
        metadata["stdin"] = stdin_payload

    participant = None
    store = None
    board = args.board
    if not board:
        store = KanbanStore(args.db)
        project = store.project_for_path(args.cwd)
        board = project["board_slug"] if project else store.default_board_slug()

    if args.participant_id or args.display_name:
        participant = {
            "id": args.participant_id or args.display_name,
            "kind": args.participant_kind,
            "display_name": args.display_name or args.participant_id,
            "role": args.role,
            "status": args.status,
            "board_slug": board,
            "current_card_id": args.current_card_id,
            "current_card_external_id": args.current_card_external_id,
            "current_scope": args.current_scope,
        }

    event = {
        "board_slug": board,
        "event_type": args.event_type,
        "message": args.message,
        "participant_id": args.participant_id,
        "card_id": args.card_id,
        "card_external_id": args.card_external_id or args.current_card_external_id,
        "metadata": metadata,
    }

    if args.server_url:
        if participant:
            _post_json(args.server_url, "/api/participants", participant)
        if _post_json(args.server_url, "/api/events", event):
            return 0

    store = store or KanbanStore(args.db)
    try:
        if participant:
            store.upsert_participant(participant)
        store.create_event(event)
    except (ValueError, KeyError) as exc:
        raise SystemExit(str(exc)) from None
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
