from __future__ import annotations

import argparse
import subprocess
import urllib.parse
from typing import Any

from ..store.core import KanbanStore
from .api import _patch_json, _post_json, _print_json, _request_json
from .git_ops import _due_card_context, _load_projects_by_board, _project_for_card


def _due_card_prompt(card: dict[str, Any], context: dict[str, Any] | None = None) -> str:
    context = context or {}
    comments = card.get("comments") or []
    note_lines = [
        f"- {item.get('author_name') or item.get('participant_id') or 'Unknown'} "
        f"({item.get('author_kind') or 'human'}, {item.get('created_at') or 'unknown time'}): "
        f"{item.get('body') or ''}"
        for item in comments
    ]
    checks = "\n".join(f"- {item}" for item in card.get("checks") or []) or "- none recorded"
    notes = "\n".join(note_lines) or "- none recorded"
    project_repos = (
        "\n".join(f"- {repo}" for repo in context.get("project_repos") or []) or "- none recorded"
    )
    target_repo = context.get("target_repo") or card.get("target_repo") or ""
    target_branch = context.get("target_branch") or card.get("target_branch") or ""
    feature_branch = card.get("feature_branch") or ""
    return f"""Execute this Codex Kanban ready workflow card.

Use the codex-kanban skill if it is available. Respect the current repo's
AGENTS.md and any project-specific approval gates. Do not commit, merge,
publish, deploy, migrate, or perform destructive work unless the project
instructions and human approval boundaries allow it.

Use the target release branch `{target_branch}` as the integration base. Never
work on `main` or `master` for this workflow. For feature/fix implementation
work, create or switch to the card-specific feature/fix branch recorded on the
card before editing files; if none is recorded, choose one based on the card ID
and record it on the card first. Commit implementation changes on that branch
before handoff. Work directly on the target release branch only for release
metadata or integration work allowed by the project instructions. If the branch
scope is unclear or unsafe, block the card and record why.

Board: {card.get('board_slug')}
Card: {card.get('external_id') or card.get('id')}
Title: {card.get('title')}
Status: {card.get('status')}
Workflow key: {card.get('workflow_key') or ''}
Scheduled for: {card.get('workflow_scheduled_for') or ''}
Target repo: {target_repo}
Target branch: {target_branch}
Feature branch: {feature_branch}

Registered project repos:
{project_repos}

Description:
{card.get('description') or ''}

Checks:
{checks}

Notes:
{notes}

Before changing files, update the Kanban card status visibly. When finished,
record files changed, checks run, failures, and remaining blockers on the card.
"""


def _due_card_summary(
    card: dict[str, Any],
    codex_bin: str,
    codex_args: list[str],
    context: dict[str, Any] | None,
) -> dict[str, Any]:
    if context and context.get("error"):
        target_repo = context.get("target_repo") or card.get("target_repo") or ""
        command: list[str] = []
    else:
        target_repo = (context or {}).get("target_repo") or card.get("target_repo") or ""
        command = [codex_bin, "exec", "--cd", target_repo, *codex_args, "<prompt>"]
    return {
        "id": card.get("id"),
        "external_id": card.get("external_id"),
        "board_slug": card.get("board_slug"),
        "title": card.get("title"),
        "workflow_key": card.get("workflow_key"),
        "scheduled_for": card.get("workflow_scheduled_for"),
        "target_repo": target_repo,
        "target_branch": (context or {}).get("target_branch") or card.get("target_branch"),
        "project_repos": (context or {}).get("project_repos") or [],
        "branch_actions": (context or {}).get("branch_actions") or [],
        "error": (context or {}).get("error"),
        "command": command,
    }


def _filter_due_cards(
    cards: list[dict[str, Any]],
    refs: list[str] | None,
) -> tuple[list[dict[str, Any]], list[str]]:
    requested = [ref.strip() for ref in refs or [] if ref.strip()]
    if not requested:
        return cards, []

    wanted = {ref.lower() for ref in requested}
    matched: set[str] = set()
    filtered: list[dict[str, Any]] = []
    for card in cards:
        labels = {
            str(card.get("id") or "").lower(),
            str(card.get("external_id") or "").lower(),
        }
        if labels & wanted:
            filtered.append(card)
            matched.update(labels & wanted)
    missing = [ref for ref in requested if ref.lower() not in matched]
    return filtered, missing


def _card_failure_payload(
    card: dict[str, Any],
    message: str,
    *,
    event_type: str = "workflow.runner.failed",
    returncode: int | None = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "workflow_key": card.get("workflow_key") or "",
        "scheduled_for": card.get("workflow_scheduled_for") or "",
    }
    if returncode is not None:
        metadata["returncode"] = returncode
    return {
        "board_slug": card["board_slug"],
        "event_type": event_type,
        "card_id": int(card["id"]),
        "message": message,
        "metadata": metadata,
    }


def _mark_due_card_blocked(
    *,
    card: dict[str, Any],
    reason: str,
    server_url: str,
    store: KanbanStore | None,
    returncode: int | None = None,
    record_event: bool = True,
) -> None:
    card_id = int(card["id"])
    if server_url:
        _patch_json(
            server_url,
            f"/api/cards/{card_id}",
            {
                "status": "blocked",
                "blocker_reason": reason,
            },
        )
        if record_event:
            _post_json(
                server_url,
                "/api/events",
                _card_failure_payload(card, reason, returncode=returncode),
            )
    elif store:
        store.update_card(card_id, {"status": "blocked", "blocker_reason": reason})
        if record_event:
            store.create_event(_card_failure_payload(card, reason, returncode=returncode))


def due_run(args: argparse.Namespace) -> int:
    codex_args = args.codex_arg or []
    if args.server_url:
        due_payload = {"board_slug": args.board} if args.board else {}
        scheduled = {"results": []}
        if args.execute:
            scheduled = _post_json(args.server_url, "/api/workflows/due", due_payload) or {
                "results": []
            }
        query: dict[str, Any] = {}
        if args.board:
            query["board"] = args.board
        if args.limit:
            query["limit"] = args.limit
        path = "/api/workflows/due-cards"
        if query:
            path += "?" + urllib.parse.urlencode(query)
        due = _request_json(args.server_url, path) or {"cards": []}
        cards = due.get("cards", [])
        store = None
    else:
        store = KanbanStore(args.db)
        scheduled = {"results": []}
        if args.execute:
            scheduled = {"results": store.run_due_repeating_cards(board_slug=args.board)}
        cards = store.due_workflow_cards(args.board, limit=args.limit or None)
    projects_by_board = _load_projects_by_board(server_url=args.server_url, store=store)
    cards, missing_card_refs = _filter_due_cards(cards, args.card)
    contexts: dict[int, dict[str, Any]] = {}
    for card in cards:
        project = _project_for_card(card, projects_by_board)
        try:
            contexts[int(card["id"])] = _due_card_context(
                card,
                project,
                prepare_branches=False,
            )
        except ValueError as exc:
            contexts[int(card["id"])] = {"error": str(exc)}

    summary = {
        "dry_run": not args.execute,
        "scheduled_results": scheduled.get("results", []),
        "cards": [
            _due_card_summary(card, args.codex_bin, codex_args, contexts.get(int(card["id"])))
            for card in cards
        ],
        "missing_card_refs": missing_card_refs,
        "executed": [],
    }
    if missing_card_refs:
        _print_json(summary)
        return 2
    if not args.execute:
        _print_json(summary)
        return 0

    for card in cards:
        card_id = int(card["id"])
        project = _project_for_card(card, projects_by_board)
        try:
            context = _due_card_context(card, project, prepare_branches=True)
        except ValueError as exc:
            reason = str(exc)
            _mark_due_card_blocked(
                card=card,
                reason=reason,
                server_url=args.server_url,
                store=store,
            )
            summary["executed"].append(
                {
                    "card_id": card_id,
                    "external_id": card.get("external_id"),
                    "returncode": None,
                    "error": reason,
                }
            )
            if args.stop_on_failure:
                _print_json(summary)
                return 1
            continue

        target_repo = context["target_repo"]
        prompt = _due_card_prompt(card, context)
        command = [args.codex_bin, "exec", "--cd", target_repo, *codex_args, prompt]
        if args.server_url:
            _patch_json(args.server_url, f"/api/cards/{card_id}", {"status": "in_progress"})
            _post_json(
                args.server_url,
                "/api/events",
                {
                    "board_slug": card["board_slug"],
                    "event_type": "workflow.runner.started",
                    "card_id": card_id,
                    "message": card.get("title") or "",
                    "metadata": {
                        "workflow_key": card.get("workflow_key") or "",
                        "scheduled_for": card.get("workflow_scheduled_for") or "",
                    },
                },
            )
        elif store:
            store.update_card(card_id, {"status": "in_progress"})
            store.create_event(
                {
                    "board_slug": card["board_slug"],
                    "event_type": "workflow.runner.started",
                    "card_id": card_id,
                    "message": card.get("title") or "",
                    "metadata": {
                        "workflow_key": card.get("workflow_key") or "",
                        "scheduled_for": card.get("workflow_scheduled_for") or "",
                    },
                }
            )

        completed = subprocess.run(command, cwd=target_repo)
        executed = {
            "card_id": card_id,
            "external_id": card.get("external_id"),
            "returncode": completed.returncode,
        }
        summary["executed"].append(executed)
        if completed.returncode == 0:
            if args.server_url:
                _patch_json(args.server_url, f"/api/cards/{card_id}", {"status": "done"})
            elif store:
                store.update_card(card_id, {"status": "done"})
            event_payload = {
                "board_slug": card["board_slug"],
                "event_type": "workflow.runner.finished",
                "card_id": card_id,
                "message": card.get("title") or "",
                "metadata": {"returncode": completed.returncode},
            }
        else:
            blocker_reason = (
                f"Codex CLI exited with code {completed.returncode} while executing "
                f"due workflow card {card.get('external_id') or card_id}."
            )
            _mark_due_card_blocked(
                card=card,
                reason=blocker_reason,
                server_url=args.server_url,
                store=store,
                returncode=completed.returncode,
                record_event=False,
            )
            event_payload = {
                "board_slug": card["board_slug"],
                "event_type": "workflow.runner.failed",
                "card_id": card_id,
                "message": blocker_reason,
                "metadata": {"returncode": completed.returncode},
            }

        if args.server_url:
            _post_json(args.server_url, "/api/events", event_payload)
        elif store:
            store.create_event(event_payload)

        if completed.returncode != 0 and args.stop_on_failure:
            _print_json(summary)
            return completed.returncode

    _print_json(summary)
    return 0
