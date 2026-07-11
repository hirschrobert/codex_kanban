from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from ..git_worktrees import git_worktree_context
from ..store.core import KanbanStore
from ..store.support import slugify
from .api import _request_json

MAIN_BRANCH_NAMES = {"main", "master"}


def _current_git_branch(repo: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "branch", "--show-current"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return ""
    return result.stdout.strip()


def _git_output(repo: Path, args: list[str]) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip()


def _git_root(path: Path) -> Path | None:
    if not path.exists():
        return None
    output = _git_output(path, ["rev-parse", "--show-toplevel"])
    return Path(output).resolve() if output else None


def _git_branch_exists(repo: Path, branch: str) -> bool:
    return _git_output(repo, ["rev-parse", "--verify", f"refs/heads/{branch}"]) is not None


def _git_remote_branch_exists(repo: Path, branch: str) -> bool:
    return (
        _git_output(
            repo,
            ["rev-parse", "--verify", f"refs/remotes/origin/{branch}"],
        )
        is not None
    )


def _git_has_uncommitted_changes(repo: Path) -> bool:
    return bool(_git_output(repo, ["status", "--porcelain"]))


def _run_git(repo: Path, args: list[str]) -> None:
    try:
        subprocess.run(
            ["git", "-C", str(repo), *args],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ValueError(f"git {' '.join(args)} failed in {repo}") from exc


def _git_is_ancestor(repo: Path, ancestor: str, descendant: str) -> bool:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "merge-base", "--is-ancestor", ancestor, descendant],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        return False
    return result.returncode == 0


def _registered_worktree_paths(repo: Path) -> set[Path]:
    output = _git_output(repo, ["worktree", "list", "--porcelain"])
    if output is None:
        raise ValueError(f"cannot list git worktrees from {repo}")
    return {
        Path(line.removeprefix("worktree ")).expanduser().resolve()
        for line in output.splitlines()
        if line.startswith("worktree ")
    }


def cleanup_merged_card_worktree(
    card: dict[str, Any],
    *,
    merged_branch: str = "main",
) -> dict[str, Any]:
    card_label = str(card.get("external_id") or card.get("id") or "card")
    if card.get("status") != "done":
        raise ValueError(f"{card_label} must be done before its worktree can be removed")
    target_repo_value = str(card.get("target_repo") or "").strip()
    worktree_value = str(card.get("worktree_path") or "").strip()
    feature_branch = str(card.get("feature_branch") or "").strip()
    if not target_repo_value or not worktree_value or not feature_branch:
        raise ValueError(
            f"{card_label} requires target_repo, feature_branch, and worktree_path for cleanup"
        )

    target_repo = Path(target_repo_value).expanduser().resolve()
    worktree = Path(worktree_value).expanduser().resolve()
    target_context = git_worktree_context(target_repo)
    if not target_context:
        raise ValueError(f"target_repo is not a git worktree: {target_repo}")
    primary_repo = Path(target_context["primary_root"])
    if worktree == primary_repo:
        raise ValueError("refusing to remove the primary repository worktree")

    registered_worktrees = _registered_worktree_paths(primary_repo)
    if worktree not in registered_worktrees:
        if not worktree.exists():
            return {
                "card_id": card.get("id"),
                "external_id": card.get("external_id"),
                "worktree_path": str(worktree),
                "feature_branch": feature_branch,
                "merged_branch": merged_branch,
                "removed": False,
                "already_removed": True,
            }
        raise ValueError(f"path is not a registered worktree of {primary_repo}: {worktree}")

    worktree_context = git_worktree_context(worktree)
    if not worktree_context or worktree_context["common_dir"] != target_context["common_dir"]:
        raise ValueError(f"worktree does not belong to target_repo: {worktree}")
    if _git_has_uncommitted_changes(worktree):
        raise ValueError(f"refusing to remove dirty worktree: {worktree}")
    feature_ref = f"refs/heads/{feature_branch}"
    merged_ref = f"refs/heads/{merged_branch}"
    if not _git_branch_exists(primary_repo, feature_branch):
        raise ValueError(f"feature branch does not exist: {feature_branch}")
    if not _git_branch_exists(primary_repo, merged_branch):
        raise ValueError(f"merged branch does not exist: {merged_branch}")
    if not _git_is_ancestor(primary_repo, feature_ref, merged_ref):
        raise ValueError(f"feature branch {feature_branch} is not merged into {merged_branch}")

    _run_git(primary_repo, ["worktree", "remove", str(worktree)])
    return {
        "card_id": card.get("id"),
        "external_id": card.get("external_id"),
        "worktree_path": str(worktree),
        "feature_branch": feature_branch,
        "merged_branch": merged_branch,
        "removed": True,
        "already_removed": False,
    }


def _project_path_values(project: dict[str, Any] | None) -> list[str]:
    if not project:
        return []
    values: list[str] = []
    if project.get("root_path"):
        values.append(str(project["root_path"]))
    for item in project.get("paths") or []:
        if isinstance(item, dict) and item.get("path"):
            values.append(str(item["path"]))
        elif item:
            values.append(str(item))
    return values


def _unique_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    result: list[Path] = []
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result


def _project_git_roots(project: dict[str, Any] | None, target_repo: Path) -> list[Path]:
    candidates = [target_repo]
    candidates.extend(Path(value).expanduser() for value in _project_path_values(project))
    roots = [root for candidate in candidates if (root := _git_root(candidate.resolve()))]
    return _unique_paths(roots)


def _projects_by_board(projects: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for project in projects:
        if project.get("removed_at"):
            continue
        board_slug = project.get("board_slug")
        if board_slug:
            result[slugify(str(board_slug))] = project
    return result


def _load_projects_by_board(
    *,
    server_url: str,
    store: KanbanStore | None,
) -> dict[str, dict[str, Any]]:
    if server_url:
        result = _request_json(server_url, "/api/projects") or {}
        return _projects_by_board(result.get("projects") or [])
    if store:
        return _projects_by_board(store.list_projects(include_removed=False))
    return {}


def _project_for_card(
    card: dict[str, Any],
    projects_by_board: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    board_slug = card.get("board_slug")
    return projects_by_board.get(slugify(str(board_slug))) if board_slug else None


def _target_branch_for_due_card(card: dict[str, Any]) -> str:
    branch = str(card.get("target_branch") or "").strip()
    if not branch:
        raise ValueError(
            f"due workflow card {card.get('external_id') or card.get('id')} has no target_branch"
        )
    if branch.lower() in MAIN_BRANCH_NAMES:
        raise ValueError(
            f"due workflow card {card.get('external_id') or card.get('id')} targets {branch}; "
            "workflow automation must use a release branch, not main or master"
        )
    return branch


def _target_repo_for_due_card(
    card: dict[str, Any],
    project: dict[str, Any] | None,
) -> Path:
    explicit = str(card.get("target_repo") or "").strip()
    if explicit:
        path = Path(explicit).expanduser().resolve()
        if not path.is_dir() or not _git_root(path):
            raise ValueError(
                f"due workflow card {card.get('external_id') or card.get('id')} "
                f"has an invalid target_repo: {explicit}"
            )
        return path

    for value in _project_path_values(project):
        path = Path(value).expanduser().resolve()
        if path.is_dir() and _git_root(path):
            return path
    raise ValueError(
        f"due workflow card {card.get('external_id') or card.get('id')} has no target_repo "
        "and its registered project has no git repo fallback"
    )


def _ensure_release_branch(repo: Path, branch: str) -> dict[str, str]:
    current = _current_git_branch(repo)
    if current == branch:
        return {"repo": str(repo), "branch": branch, "action": "already-current"}
    if _git_has_uncommitted_changes(repo):
        raise ValueError(
            f"refusing to switch {repo} to {branch}; the worktree has uncommitted changes"
        )
    if _git_branch_exists(repo, branch):
        _run_git(repo, ["checkout", branch])
        return {"repo": str(repo), "branch": branch, "action": "checked-out"}
    if _git_remote_branch_exists(repo, branch):
        _run_git(repo, ["checkout", "-b", branch, "--track", f"origin/{branch}"])
        return {"repo": str(repo), "branch": branch, "action": "tracked-remote"}
    _run_git(repo, ["checkout", "-b", branch])
    return {"repo": str(repo), "branch": branch, "action": "created"}


def _due_card_context(
    card: dict[str, Any],
    project: dict[str, Any] | None,
    *,
    prepare_branches: bool,
) -> dict[str, Any]:
    target_branch = _target_branch_for_due_card(card)
    target_repo = _target_repo_for_due_card(card, project)
    project_repos = _project_git_roots(project, target_repo)
    if not project_repos:
        raise ValueError(
            f"due workflow card {card.get('external_id') or card.get('id')} "
            "has no registered git repository scope"
        )
    branch_actions = (
        [_ensure_release_branch(repo, target_branch) for repo in project_repos]
        if prepare_branches
        else [
            {"repo": str(repo), "branch": target_branch, "action": "not-prepared"}
            for repo in project_repos
        ]
    )
    return {
        "target_repo": str(target_repo),
        "target_branch": target_branch,
        "project_repos": [str(repo) for repo in project_repos],
        "branch_actions": branch_actions,
    }
