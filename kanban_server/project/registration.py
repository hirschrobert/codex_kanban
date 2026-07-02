from __future__ import annotations

from pathlib import Path
from typing import Any

from ..store.support import GENERIC_AGENT_PROFILES, slugify


def repo_root(cwd: str | Path) -> Path:
    path = Path(cwd).expanduser().resolve()
    if path.is_file():
        path = path.parent
    for candidate in [path, *path.parents]:
        if (candidate / ".git").exists():
            return candidate
    return path


def instruction_paths(root: Path, cwd: str | Path) -> list[Path]:
    path = Path(cwd).expanduser().resolve()
    if path.is_file():
        path = path.parent
    try:
        relative = path.relative_to(root)
    except ValueError:
        relative = Path()

    paths: list[Path] = []
    current = root
    root_agents = current / "AGENTS.md"
    if root_agents.exists():
        paths.append(root_agents)
    for part in relative.parts:
        current = current / part
        agents_path = current / "AGENTS.md"
        if agents_path.exists():
            paths.append(agents_path)
    return paths


def uses_codex_kanban(paths: list[Path]) -> bool:
    for instruction_path in paths:
        try:
            if "codex-kanban" in instruction_path.read_text(encoding="utf-8").lower():
                return True
        except OSError:
            continue
    return False


def auto_register_payload(root: Path, paths: list[Path]) -> dict[str, Any]:
    display_name = root.name
    slug = slugify(display_name)
    return {
        "slug": slug,
        "display_name": display_name,
        "board_slug": slug,
        "card_prefix": slug.split("-")[0].upper()[:12],
        "description": "Auto-registered from project AGENTS.md.",
        "root_path": str(root),
        "paths": [{"label": display_name, "path": str(root)}],
        "instruction_paths": [str(path) for path in paths],
        "agent_profiles": list(GENERIC_AGENT_PROFILES),
    }


def auto_register_payload_for_cwd(cwd: str | Path) -> dict[str, Any] | None:
    root = repo_root(cwd)
    paths = instruction_paths(root, cwd)
    if not uses_codex_kanban(paths):
        return None
    return auto_register_payload(root, paths)
