from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from ..store.support import (
    GENERIC_AGENT_PROFILES,
    discover_project_agent_profiles,
    merge_agent_profiles,
    slugify,
)
from .git_ops import _current_git_branch

DEFAULT_AI_AGENT_MANAGER_DISPLAY_NAME = "AI Agent Manager"
DEFAULT_AI_AGENT_MANAGER_ROLE = "Main AI agent coordinating Kanban cards through the CLI."
DEFAULT_AI_AGENT_MANAGER_SUFFIX = "ai-agent-manager"


def _default_instruction_paths(root: Path) -> list[str]:
    return [str(path) for path in [root / "AGENTS.md"] if path.exists()]


def _path_entry(value: str) -> dict[str, str]:
    if "=" in value:
        label, path = value.split("=", 1)
        return {"label": label.strip(), "path": path.strip()}
    path = value.strip()
    return {"label": Path(path).name or path, "path": path}


def _agent_profiles(
    args: argparse.Namespace,
    *,
    root: Path | None = None,
    paths: list[dict[str, str]] | None = None,
) -> list[str]:
    return merge_agent_profiles(
        args.agent_profile or list(GENERIC_AGENT_PROFILES),
        discover_project_agent_profiles(root, paths or []) if root else [],
    )


def _registration_payload(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).expanduser().resolve()
    display_name = args.display_name or root.name
    slug = slugify(args.slug or display_name)
    paths = [_path_entry(item) for item in getattr(args, "path", [])]
    if not paths:
        paths = [{"label": display_name, "path": str(root)}]
    instruction_paths = getattr(args, "instruction", []) or _default_instruction_paths(root)
    return {
        "slug": slug,
        "display_name": display_name,
        "board_slug": slugify(args.board or slug),
        "card_prefix": (args.card_prefix or slug.split("-")[0]).upper(),
        "description": args.description or "",
        "root_path": str(root),
        "paths": paths,
        "instruction_paths": instruction_paths,
        "agent_profiles": _agent_profiles(args, root=root, paths=paths),
    }


def _description_with_context(
    description: str,
    *,
    why: str | None = None,
    risks: list[str] | None = None,
    acceptance: list[str] | None = None,
) -> str:
    base_description = description.strip()
    sections = [base_description]
    if why and why.strip() and not _has_context_section(base_description, "Why this card exists:"):
        sections.append(f"Why this card exists:\n{why.strip()}")
    if risks and not _has_context_section(base_description, "If this is not fixed:"):
        lines = [_bullet_line(item) for item in risks if item.strip()]
        if lines:
            sections.append("If this is not fixed:\n" + "\n".join(lines))
    if acceptance and not _has_context_section(base_description, "Acceptance criteria:"):
        lines = [_bullet_line(item) for item in acceptance if item.strip()]
        if lines:
            sections.append("Acceptance criteria:\n" + "\n".join(lines))
    return "\n\n".join(sections)


def _has_context_section(description: str, heading: str) -> bool:
    return bool(re.search(rf"(?im)^\s*{re.escape(heading)}\s*$", description))


def _bullet_line(value: str) -> str:
    text = value.strip()
    return text if text.startswith(("- ", "* ")) else f"- {text}"


def _default_ai_agent_manager_id(board_slug: str) -> str:
    return f"{slugify(board_slug)}-{DEFAULT_AI_AGENT_MANAGER_SUFFIX}"


def _default_ai_agent_manager_payload_for_args(
    args: argparse.Namespace,
) -> dict[str, str] | None:
    if args.actor_id or not args.board:
        return None
    board_slug = slugify(args.board)
    return {
        "id": _default_ai_agent_manager_id(board_slug),
        "display_name": DEFAULT_AI_AGENT_MANAGER_DISPLAY_NAME,
        "kind": "agent",
        "status": "idle",
        "role": DEFAULT_AI_AGENT_MANAGER_ROLE,
        "board_slug": board_slug,
    }


def _card_payload(args: argparse.Namespace) -> dict[str, Any]:
    actor_id = args.actor_id
    if not actor_id and args.board:
        actor_id = _default_ai_agent_manager_id(args.board)
    intake_source = args.intake_source
    if not intake_source and args.board and not args.actor_id:
        intake_source = "main_agent"
    payload = {
        "board_slug": args.board,
        "title": args.title,
        "description": _description_with_context(
            args.description,
            why=args.why,
            risks=args.risk,
            acceptance=args.acceptance,
        ),
        "status": args.status,
        "priority": args.priority,
        "assignee_id": args.assignee,
        "owner_id": args.owner or actor_id,
        "actor_id": actor_id,
        "intake_kind": args.intake_kind,
        "intake_source": intake_source,
        "reported_by": args.reported_by,
        "impact": args.impact,
        "evidence": args.evidence,
        "affected_paths": args.affected_path or [],
        "deployment_dispositions": args.deployment_disposition or [],
        "target_repo": args.target_repo,
        "target_branch": args.target_branch,
        "starting_target_sha": args.start_sha,
        "handoff_target_sha": args.handoff_sha,
        "feature_branch": args.feature_branch,
        "worktree_path": args.worktree_path,
        "blocker_reason": args.blocker,
        "parent_external_id": args.parent,
        "child_external_ids": args.child or [],
        "files_changed": args.file_changed or [],
        "checks": args.check or [],
        "assumptions": args.assumption or [],
        "follow_up_cards": args.follow_up or [],
    }
    return {key: value for key, value in payload.items() if value not in (None, [], "")}


def _card_update_payload(args: argparse.Namespace) -> dict[str, Any]:
    blocker_reason = args.blocker
    if getattr(args, "clear_blocker", False):
        if blocker_reason not in (None, ""):
            raise ValueError("--clear-blocker cannot be combined with a non-empty --blocker")
        blocker_reason = ""
    payload = {
        "status": args.status,
        "owner_id": args.owner,
        "assignee_id": args.assignee,
        "target_repo": args.target_repo,
        "target_branch": args.target_branch,
        "starting_target_sha": args.start_sha,
        "handoff_target_sha": args.handoff_sha,
        "feature_branch": args.feature_branch,
        "worktree_path": args.worktree_path,
        "blocker_reason": blocker_reason,
        "parent_external_id": args.parent,
        "child_external_ids": args.child or None,
        "deployment_dispositions": args.deployment_disposition or None,
        "checks": args.check or None,
        "files_changed": args.file_changed or None,
        "assumptions": args.assumption or None,
        "follow_up_cards": args.follow_up or None,
    }
    update = {key: value for key, value in payload.items() if value not in (None, [], "")}
    if getattr(args, "clear_blocker", False) or args.blocker is not None:
        update["blocker_reason"] = blocker_reason or ""
    return update


def _participant_payload(args: argparse.Namespace) -> dict[str, Any]:
    payload = {
        "id": args.id,
        "display_name": args.display_name,
        "kind": args.kind,
        "status": args.status,
        "role": args.role,
        "board_slug": args.board,
        "current_card_id": args.current_card_id,
        "current_card_external_id": args.current_card_external_id,
        "current_scope": args.current_scope,
    }
    return {key: value for key, value in payload.items() if value not in (None, "")}


def _workflow_payload(args: argparse.Namespace) -> dict[str, Any]:
    target_repo = Path(args.target_repo).expanduser().resolve() if args.target_repo else None
    target_branch = args.target_branch or ""
    if not target_branch and args.target_branch_from_git:
        branch_repo = target_repo or Path.cwd()
        target_branch = _current_git_branch(branch_repo)
    if not target_branch:
        raise SystemExit(
            "workflow-start requires --target-branch, or --target-branch-from-git "
            "when the current git branch is the intended release branch."
        )

    scheduled_for = args.scheduled_for or ""
    description = _description_with_context(
        args.description
        or f"Run recurring workflow `{args.workflow_key}` for {scheduled_for or 'today'}.",
        why=args.why,
        risks=args.risk,
        acceptance=args.acceptance,
    )
    payload = {
        "board_slug": args.board,
        "workflow_key": args.workflow_key,
        "scheduled_for": scheduled_for,
        "title": args.title or f"Run {args.workflow_key} workflow",
        "description": description,
        "status": args.status,
        "priority": args.priority,
        "assignee_id": args.assignee,
        "actor_id": args.actor_id,
        "target_repo": str(target_repo) if target_repo else args.target_repo,
        "target_branch": target_branch,
        "checks": args.check or [],
    }
    return {key: value for key, value in payload.items() if value not in (None, [], "")}
