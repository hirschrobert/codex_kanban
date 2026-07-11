from __future__ import annotations

import argparse
import json
import urllib.parse
from pathlib import Path
from typing import Any

from ..store.core import KanbanStore
from ..store.support import slugify
from .api import _patch_json, _post_json, _print_json, _request_json
from .due import due_run as due_run
from .payloads import (
    _agent_profiles,
    _card_comment_payload,
    _card_payload,
    _card_update_payload,
    _default_ai_agent_manager_payload_for_args,
    _participant_payload,
    _registration_payload,
    _workflow_payload,
)
from .registration import auto_register_payload_for_cwd

CODEX_KANBAN_REPO_ROOT = Path(__file__).resolve().parents[2]


def _limit_snapshot_done_cards(
    snapshot_payload: dict[str, Any],
    done_limit: int | None,
) -> dict[str, Any]:
    if done_limit is None:
        return snapshot_payload

    cards = list(snapshot_payload.get("cards") or [])
    done_card_count = sum(1 for card in cards if card.get("status") == "done")
    if done_limit < 0:
        limited_cards = cards
        hidden_done = 0
    else:
        limited_cards = []
        shown_done = 0
        hidden_done = 0
        for card in cards:
            if card.get("status") != "done":
                limited_cards.append(card)
                continue
            if shown_done < done_limit:
                limited_cards.append(card)
                shown_done += 1
            else:
                hidden_done += 1

    return {
        **snapshot_payload,
        "cards": limited_cards,
        "card_count": len(limited_cards),
        "done_limit": done_limit,
        "done_card_count": done_card_count,
        "done_cards_hidden_count": hidden_done,
        "done_cards_hidden": hidden_done > 0,
    }


def register(args: argparse.Namespace) -> int:
    payload = _registration_payload(args)
    if args.server_url:
        result = _post_json(args.server_url, "/api/projects", payload)
        if result is not None:
            _print_json(result)
            return 0

    store = KanbanStore(args.db)
    result = store.register_project(payload)
    _print_json(result)
    return 0


def list_projects(args: argparse.Namespace) -> int:
    if args.server_url:
        result = _request_json(args.server_url, "/api/projects")
        if result is not None:
            _print_json({"projects": result["all_projects" if args.all else "projects"]})
            return 0

    store = KanbanStore(args.db)
    _print_json({"projects": store.list_projects(include_removed=args.all)})
    return 0


def snapshot(args: argparse.Namespace) -> int:
    query = {
        key: value
        for key, value in {
            "board": args.board,
            "include_archived": "1" if args.include_archived else None,
            "archived_only": "1" if args.archived_only else None,
        }.items()
        if value
    }
    path = "/api/snapshot"
    if query:
        path += "?" + urllib.parse.urlencode(query)
    if args.server_url:
        result = _request_json(args.server_url, path)
        if result is not None:
            _print_json(_limit_snapshot_done_cards(result, args.done_limit))
            return 0

    store = KanbanStore(args.db)
    result = store.snapshot(
        args.board or None,
        include_archived=args.include_archived,
        archived_only=args.archived_only,
    )
    _print_json(_limit_snapshot_done_cards(result, args.done_limit))
    return 0


def overview(args: argparse.Namespace) -> int:
    query = {
        key: value
        for key, value in {
            "board": args.board,
            "cwd": str(Path(args.cwd).expanduser().resolve()) if args.cwd else None,
            "repo": str(Path(args.repo).expanduser().resolve()) if args.repo else None,
            "limit": str(args.limit) if args.limit else None,
            "done_limit": str(args.done_limit),
            "include_archived": "1" if args.include_archived else None,
            "archived_only": "1" if args.archived_only else None,
            "register_if_missing": "1" if args.register_if_missing else None,
        }.items()
        if value
    }
    path = "/api/overview"
    if query:
        path += "?" + urllib.parse.urlencode(query)
    if args.server_url:
        result = _request_json(args.server_url, path)
        if result is not None:
            _print_json(result)
            return 0

    store = KanbanStore(args.db)
    result = store.overview(
        args.board or None,
        cwd=query.get("cwd"),
        repo=query.get("repo"),
        include_archived=args.include_archived,
        archived_only=args.archived_only,
        limit=args.limit,
        done_limit=args.done_limit,
    )
    if (
        args.register_if_missing
        and not args.board
        and not result.get("matched_project")
        and not (result.get("project_resolution") or {}).get("ambiguous")
    ):
        registration_target = query.get("repo") or query.get("cwd")
        payload = (
            auto_register_payload_for_cwd(registration_target) if registration_target else None
        )
        if payload:
            result["registered_project"] = store.register_project(payload)
            result = {
                **store.overview(
                    args.board or None,
                    cwd=query.get("cwd"),
                    repo=query.get("repo"),
                    include_archived=args.include_archived,
                    archived_only=args.archived_only,
                    limit=args.limit,
                    done_limit=args.done_limit,
                ),
                "registered_project": result["registered_project"],
            }
    _print_json(result)
    return 0


def card_create(args: argparse.Namespace) -> int:
    payload = _card_payload(args)
    default_actor = _default_ai_agent_manager_payload_for_args(args)
    if args.server_url:
        if default_actor:
            _post_json(args.server_url, "/api/participants", default_actor)
        result = _post_json(args.server_url, "/api/cards", payload)
        if result is not None:
            _print_json(result)
            return 0

    store = KanbanStore(args.db)
    if default_actor:
        store.upsert_participant(default_actor)
    card = store.create_card(payload)
    store.create_event(
        {
            "board_slug": card["board_slug"],
            "event_type": "card.created",
            "card_id": card["id"],
            "participant_id": payload.get("actor_id"),
            "message": card["title"],
            "metadata": {"status": card["status"]},
        }
    )
    _print_json(card)
    return 0


def card_move(args: argparse.Namespace) -> int:
    payload = _card_update_payload(args)
    if args.server_url:
        result = _patch_json(args.server_url, f"/api/cards/{args.card_id}", payload)
        if result is not None:
            _print_json(result)
            return 0

    store = KanbanStore(args.db)
    before = store.get_card(args.card_id)
    card = store.update_card(args.card_id, payload)
    event_type = "card.updated"
    message = card["title"]
    metadata: dict[str, Any] = {}
    if before and before.get("status") != card.get("status"):
        event_type = "card.moved"
        message = f"{before.get('status')} -> {card.get('status')}"
        metadata = {"from_status": before.get("status"), "to_status": card.get("status")}
    store.create_event(
        {
            "board_slug": card["board_slug"],
            "event_type": event_type,
            "card_id": card["id"],
            "message": message,
            "metadata": metadata,
        }
    )
    _print_json(card)
    return 0


def card_comment(args: argparse.Namespace) -> int:
    payload = _card_comment_payload(args)
    default_actor = _default_ai_agent_manager_payload_for_args(args)
    if args.server_url:
        if default_actor:
            _post_json(args.server_url, "/api/participants", default_actor)
        result = _post_json(args.server_url, f"/api/cards/{args.card_id}/comments", payload)
        if result is not None:
            _print_json(result)
            return 0

    store = KanbanStore(args.db)
    if default_actor:
        store.upsert_participant(default_actor)
    comment = store.add_card_comment(args.card_id, payload)
    store.create_event(
        {
            "board_slug": comment["board_slug"],
            "event_type": "card.commented",
            "card_id": comment["card_id"],
            "participant_id": comment.get("participant_id"),
            "message": comment["body"][:120],
            "metadata": {"comment_id": comment["id"]},
        }
    )
    _print_json(comment)
    return 0


def participant_upsert(args: argparse.Namespace) -> int:
    payload = _participant_payload(args)
    if args.server_url:
        result = _post_json(args.server_url, "/api/participants", payload)
        if result is not None:
            _print_json(result)
            return 0

    store = KanbanStore(args.db)
    participant = store.upsert_participant(payload)
    store.create_event(
        {
            "board_slug": participant.get("current_board_slug") or store.default_board_slug(),
            "event_type": "participant.updated",
            "participant_id": participant["id"],
            "message": participant["display_name"],
            "metadata": {"kind": participant["kind"], "status": participant["status"]},
        }
    )
    _print_json(participant)
    return 0


def workflow_start(args: argparse.Namespace) -> int:
    payload = _workflow_payload(args)
    if args.server_url:
        result = _post_json(args.server_url, "/api/workflows/start", payload)
        if result is not None:
            _print_json(result)
            return 0

    store = KanbanStore(args.db)
    result = store.start_workflow(payload)
    if result.get("created"):
        card = result["card"]
        store.create_event(
            {
                "board_slug": card["board_slug"],
                "event_type": "workflow.started",
                "card_id": card["id"],
                "participant_id": args.actor_id,
                "message": card["title"],
                "metadata": {
                    "workflow_key": payload["workflow_key"],
                    "scheduled_for": payload.get("scheduled_for") or "",
                },
            }
        )
    _print_json(result)
    return 0


def reset(args: argparse.Namespace) -> int:
    if not args.yes:
        raise SystemExit("Refusing to reset the Kanban database without --yes.")
    store = KanbanStore(args.db)
    store.reset()
    _print_json({"reset": True, "db": str(store.db_path)})
    return 0


def print_prompt(args: argparse.Namespace) -> int:
    root = Path(args.root).expanduser().resolve()
    display_name = args.display_name or root.name
    slug = slugify(args.slug or display_name)
    card_prefix = (args.card_prefix or slug.split("-")[0]).upper()
    profiles = ", ".join(_agent_profiles(args, root=root))
    print(f"""Register this project with Codex Kanban before doing implementation work.

Run from a trusted shell:

KANBAN_REPO="${{CODEX_KANBAN_REPO:-{CODEX_KANBAN_REPO_ROOT}}}"
test -d "$KANBAN_REPO/kanban_server" || {{
  echo "Set CODEX_KANBAN_REPO to the codex_kanban checkout"
  exit 1
}}

PYTHONPATH="$KANBAN_REPO" python3 -m kanban_server.project register \\
  --server-url http://127.0.0.1:8766 \\
  --root {root} \\
  --slug {slug} \\
  --display-name {json.dumps(display_name)} \\
  --card-prefix {card_prefix}

After registration, use board `{slug}` as the shared orchestration surface.
Use the `codex-kanban` skill to respect human-added cards, work only on the
assigned card/scope, and keep delegation under the main Codex agent's control.
Board-scoped profiles are optional task-specific offers alongside Codex built-in
agents, other custom agents, and single-agent execution. Available project-local
and generic profiles: {profiles}. Using Kanban does not require delegation or a
justification for skipping it. When a registered profile is deliberately chosen,
select its exact custom-agent type so Codex loads the matching configuration;
native or otherwise unregistered agents remain visible under the board-scoped
Codex subagents People role with their reported runtime type.
When delegated work produces findings, decisions, blockers, or completion
results, add a concise card comment to the parent coordination card so the
topic context stays with the parent card, not only with a child card or chat.

For first overview, run:

PYTHONPATH="$KANBAN_REPO" python3 -m kanban_server.project overview \\
  --server-url http://127.0.0.1:8766 \\
  --cwd {root} \\
  --repo {root} \\
  --done-limit 5 \\
  --register-if-missing

This identifies the matching board from registered project paths, lists
all non-done non-archived cards plus the most recent done cards, and reports
whether additional done or archived cards exist for possible follow-up search.
It also refreshes board-scoped AI participants from current generic/default
profiles and discoverable project-local agents so UI people fields stay
current after agent defaults or project agents change.
Split multi-intent human requests before implementation: independent features,
fixes, affected apps/repos, user roles, UI flows, or deployment scopes should
be separate sibling cards or child cards under a coordination parent, not one
bundled implementation card.
Treat different user requests, implementation scopes, and agents as separate
contributors. Each feature/fix implementation card needs its own card-specific
branch with commits before handoff. Merge it to the release branch only after
human final review, then rebase or refresh remaining active feature/fix
branches from that release branch.
Concrete project rules stay in this repo's AGENTS.md; do not copy domain rules
into the global Kanban app.
""")
    return 0
