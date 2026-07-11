from __future__ import annotations

from pathlib import Path
from typing import Any


def _directory(path: str | Path) -> Path:
    candidate = Path(path).expanduser().resolve()
    return candidate.parent if candidate.is_file() else candidate


def git_worktree_root(path: str | Path) -> Path | None:
    candidate = _directory(path)
    for directory in (candidate, *candidate.parents):
        if (directory / ".git").exists():
            return directory
    return None


def _git_dir(worktree_root: Path) -> Path | None:
    marker = worktree_root / ".git"
    if marker.is_dir():
        return marker.resolve()
    if not marker.is_file():
        return None
    try:
        prefix, value = marker.read_text(encoding="utf-8").strip().split(":", 1)
    except (OSError, ValueError):
        return None
    if prefix.strip().lower() != "gitdir" or not value.strip():
        return None
    git_dir = Path(value.strip()).expanduser()
    if not git_dir.is_absolute():
        git_dir = worktree_root / git_dir
    return git_dir.resolve()


def git_worktree_context(path: str | Path) -> dict[str, Any] | None:
    worktree_root = git_worktree_root(path)
    if not worktree_root:
        return None
    git_dir = _git_dir(worktree_root)
    if not git_dir:
        return None

    common_dir = git_dir
    common_marker = git_dir / "commondir"
    if common_marker.is_file():
        try:
            common_value = common_marker.read_text(encoding="utf-8").strip()
        except OSError:
            common_value = ""
        if common_value:
            common_dir = (git_dir / common_value).resolve()

    primary_root = common_dir.parent if common_dir.name == ".git" else worktree_root
    primary_marker = primary_root / ".git"
    if not primary_marker.exists():
        primary_root = worktree_root
    return {
        "worktree_root": worktree_root,
        "primary_root": primary_root.resolve(),
        "git_dir": git_dir,
        "common_dir": common_dir,
        "is_linked_worktree": worktree_root.resolve() != primary_root.resolve(),
    }


def primary_worktree_root(path: str | Path) -> Path | None:
    context = git_worktree_context(path)
    return context["primary_root"] if context else None
