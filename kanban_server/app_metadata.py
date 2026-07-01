from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from . import __version__

REPO_ROOT = Path(__file__).resolve().parents[1]


def app_metadata(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    source_hash = _git_output(repo_root, "rev-parse", "--short", "HEAD") or "unknown"
    return {
        "name": "codex-kanban",
        "version": __version__,
        "hash": source_hash,
        "dirty": bool(_git_output(repo_root, "status", "--short")),
    }


def _git_output(repo_root: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()
