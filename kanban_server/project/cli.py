from __future__ import annotations

import argparse
import os
from pathlib import Path

from ..store.support import DEFAULT_DB_PATH, DEFAULT_OVERVIEW_DONE_LIMIT
from .commands import (
    card_comment,
    card_create,
    card_move,
    due_run,
    list_projects,
    overview,
    participant_upsert,
    print_prompt,
    register,
    reset,
    snapshot,
    workflow_start,
    worktree_cleanup,
)


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", required=True)
    parser.add_argument("--slug")
    parser.add_argument("--display-name")
    parser.add_argument("--card-prefix")
    parser.add_argument(
        "--agent-profile",
        action="append",
        help="Reusable agent profile to expose on the board. Repeat for multiple profiles.",
    )


def _add_connection_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument(
        "--server-url",
        default=os.environ.get("CODEX_KANBAN_URL", ""),
    )


def _add_card_handoff_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--owner")
    parser.add_argument("--assignee")
    parser.add_argument("--handoff-sha")
    parser.add_argument("--blocker")
    parser.add_argument(
        "--deployment-disposition",
        action="append",
        default=[],
        help=(
            "Deployment checklist entry, e.g. "
            "'Portal|/repo=deployed:verified live version'. Repeat for each app/repo."
        ),
    )
    parser.add_argument("--check", action="append", default=[])
    parser.add_argument("--file-changed", action="append", default=[])
    parser.add_argument("--assumption", action="append", default=[])
    parser.add_argument("--follow-up", action="append", default=[])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Register projects with Codex Kanban.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    register_parser = subparsers.add_parser("register")
    _add_common_arguments(register_parser)
    _add_connection_arguments(register_parser)
    register_parser.add_argument("--board")
    register_parser.add_argument("--description")
    register_parser.add_argument(
        "--path",
        action="append",
        default=[],
        help="Project path or label=/path. Repeat for multi-repo ecosystems.",
    )
    register_parser.add_argument(
        "--instruction",
        action="append",
        default=[],
        help="Instruction file path, usually AGENTS.md. Repeat for ecosystems.",
    )
    register_parser.set_defaults(func=register)

    list_parser = subparsers.add_parser("list", help="List registered projects.")
    _add_connection_arguments(list_parser)
    list_parser.add_argument("--all", action="store_true", help="Include soft-removed projects.")
    list_parser.set_defaults(func=list_projects)

    snapshot_parser = subparsers.add_parser("snapshot", help="Print a board snapshot.")
    _add_connection_arguments(snapshot_parser)
    snapshot_parser.add_argument("--board")
    snapshot_parser.add_argument(
        "--include-archived",
        action="store_true",
        help="Include archived cards in the snapshot.",
    )
    snapshot_parser.add_argument(
        "--archived-only",
        action="store_true",
        help="Show only archived cards in the snapshot.",
    )
    snapshot_parser.add_argument(
        "--done-limit",
        type=int,
        default=None,
        help=(
            "Maximum done cards to include in the snapshot. "
            "Omit for the recent two-day view, use 0 to hide recent done cards, "
            "or -1 to include all done cards explicitly."
        ),
    )
    snapshot_parser.set_defaults(func=snapshot)

    overview_parser = subparsers.add_parser(
        "overview",
        help="Print a lean project/card overview for agent startup.",
    )
    _add_connection_arguments(overview_parser)
    overview_parser.add_argument("--board")
    overview_parser.add_argument("--cwd", default=os.getcwd())
    overview_parser.add_argument("--repo")
    overview_parser.add_argument("--limit", type=int, default=0)
    overview_parser.add_argument(
        "--done-limit",
        type=int,
        default=DEFAULT_OVERVIEW_DONE_LIMIT,
        help=(
            "Maximum done cards to include in the startup overview. "
            "Use 0 to hide done cards or -1 to include all done cards."
        ),
    )
    overview_parser.add_argument(
        "--register-if-missing",
        action="store_true",
        help="Auto-register a single repo when AGENTS.md opts into codex-kanban.",
    )
    overview_parser.add_argument(
        "--include-archived",
        action="store_true",
        help="Include archived cards in the overview.",
    )
    overview_parser.add_argument(
        "--archived-only",
        action="store_true",
        help="Show only archived cards in the overview.",
    )
    overview_parser.set_defaults(func=overview)

    card_create_parser = subparsers.add_parser("card-create", help="Create a Kanban card.")
    _add_connection_arguments(card_create_parser)
    card_create_parser.add_argument("--board")
    card_create_parser.add_argument("--title", required=True)
    card_create_parser.add_argument("--description", required=True)
    card_create_parser.add_argument("--why")
    card_create_parser.add_argument("--risk", action="append", default=[])
    card_create_parser.add_argument("--acceptance", action="append", default=[])
    card_create_parser.add_argument("--status", default="backlog")
    card_create_parser.add_argument("--priority", default="normal")
    card_create_parser.add_argument("--actor-id")
    card_create_parser.add_argument("--intake-kind")
    card_create_parser.add_argument("--intake-source")
    card_create_parser.add_argument("--reported-by")
    card_create_parser.add_argument("--impact")
    card_create_parser.add_argument("--evidence")
    card_create_parser.add_argument("--affected-path", action="append", default=[])
    card_create_parser.add_argument("--target-repo")
    card_create_parser.add_argument("--target-branch")
    card_create_parser.add_argument("--feature-branch")
    card_create_parser.add_argument("--start-sha")
    card_create_parser.add_argument("--worktree-path")
    card_create_parser.add_argument("--parent")
    card_create_parser.add_argument("--child", action="append", default=[])
    _add_card_handoff_arguments(card_create_parser)
    card_create_parser.set_defaults(func=card_create)

    card_move_parser = subparsers.add_parser("card-move", help="Move or hand off a card.")
    _add_connection_arguments(card_move_parser)
    card_move_parser.add_argument("card_id", type=int)
    card_move_parser.add_argument("--status", required=True)
    card_move_parser.add_argument("--target-repo")
    card_move_parser.add_argument("--target-branch")
    card_move_parser.add_argument("--feature-branch")
    card_move_parser.add_argument("--start-sha")
    card_move_parser.add_argument("--worktree-path")
    card_move_parser.add_argument("--parent")
    card_move_parser.add_argument("--child", action="append", default=[])
    _add_card_handoff_arguments(card_move_parser)
    card_move_parser.add_argument(
        "--clear-blocker",
        action="store_true",
        help="Clear an existing blocker reason while moving or handing off a card.",
    )
    card_move_parser.set_defaults(func=card_move)

    card_comment_parser = subparsers.add_parser(
        "card-comment", help="Add a durable note/comment to a card."
    )
    _add_connection_arguments(card_comment_parser)
    card_comment_parser.add_argument("card_id", type=int)
    card_comment_parser.add_argument("--board")
    card_comment_parser.add_argument("--participant-id")
    card_comment_parser.add_argument("--actor-id")
    card_comment_parser.add_argument("--author-name")
    card_comment_parser.add_argument(
        "--author-kind",
        choices=("agent", "human", "system"),
    )
    comment_body = card_comment_parser.add_mutually_exclusive_group(required=True)
    comment_body.add_argument("--body")
    comment_body.add_argument("--comment", dest="body")
    card_comment_parser.set_defaults(func=card_comment)

    cleanup_parser = subparsers.add_parser(
        "worktree-cleanup",
        help="Remove a clean card worktree after its feature branch is merged.",
    )
    _add_connection_arguments(cleanup_parser)
    cleanup_parser.add_argument("card_id", type=int)
    cleanup_parser.add_argument("--merged-branch", default="main")
    cleanup_parser.set_defaults(func=worktree_cleanup)

    workflow_parser = subparsers.add_parser(
        "workflow-start",
        help="Create or reuse a scheduled workflow card for external cron.",
    )
    _add_connection_arguments(workflow_parser)
    workflow_parser.add_argument("--board")
    workflow_parser.add_argument("--workflow-key", required=True)
    workflow_parser.add_argument("--scheduled-for")
    workflow_parser.add_argument("--title")
    workflow_parser.add_argument("--description")
    workflow_parser.add_argument("--why")
    workflow_parser.add_argument("--risk", action="append", default=[])
    workflow_parser.add_argument("--acceptance", action="append", default=[])
    workflow_parser.add_argument("--status", default="ready")
    workflow_parser.add_argument("--priority", default="normal")
    workflow_parser.add_argument("--assignee")
    workflow_parser.add_argument("--actor-id")
    workflow_parser.add_argument("--target-repo")
    workflow_parser.add_argument("--target-branch")
    workflow_parser.add_argument(
        "--target-branch-from-git",
        action="store_true",
        help="Use the current branch of --target-repo, or cwd, as the target branch.",
    )
    workflow_parser.add_argument("--check", action="append", default=[])
    workflow_parser.set_defaults(func=workflow_start)

    due_run_parser = subparsers.add_parser(
        "due-run",
        help="Run due ready workflow cards with Codex CLI.",
    )
    _add_connection_arguments(due_run_parser)
    due_run_parser.add_argument("--board")
    due_run_parser.add_argument(
        "--card",
        action="append",
        default=[],
        help="Only run a specific ready workflow card by numeric id or external id. Repeatable.",
    )
    due_run_parser.add_argument("--limit", type=int, default=0)
    due_run_parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually invoke codex exec. Without this flag, print a dry-run plan.",
    )
    due_run_parser.add_argument("--codex-bin", default="codex")
    due_run_parser.add_argument(
        "--codex-arg",
        action="append",
        default=[],
        help="Extra argument passed to codex exec before the prompt. Repeat as needed.",
    )
    due_run_parser.add_argument(
        "--stop-on-failure",
        action="store_true",
        help="Stop after the first codex exec failure.",
    )
    due_run_parser.set_defaults(func=due_run)

    participant_parser = subparsers.add_parser(
        "participant-upsert", help="Create or update a participant."
    )
    _add_connection_arguments(participant_parser)
    participant_parser.add_argument("--id")
    participant_parser.add_argument("--display-name")
    participant_parser.add_argument(
        "--kind",
        default="agent",
        choices=("agent", "human", "system"),
    )
    participant_parser.add_argument("--status", default="idle")
    participant_parser.add_argument("--role", default="")
    participant_parser.add_argument("--board")
    participant_parser.add_argument("--current-card-id", type=int)
    participant_parser.add_argument("--current-card-external-id")
    participant_parser.add_argument("--current-scope", default="")
    participant_parser.set_defaults(func=participant_upsert)

    reset_parser = subparsers.add_parser("reset")
    reset_parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    reset_parser.add_argument("--yes", action="store_true")
    reset_parser.set_defaults(func=reset)

    prompt_parser = subparsers.add_parser("prompt")
    _add_common_arguments(prompt_parser)
    prompt_parser.add_argument("--board")
    prompt_parser.add_argument("--description")
    prompt_parser.set_defaults(func=print_prompt)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (ValueError, KeyError) as exc:
        raise SystemExit(str(exc)) from None


if __name__ == "__main__":
    raise SystemExit(main())
