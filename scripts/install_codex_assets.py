#!/usr/bin/env python3
"""Install the repository's managed Codex assets without replacing user config."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
SOURCE_SKILL = ROOT / ".codex" / "skills" / "codex-kanban"
SOURCE_AGENTS = ROOT / ".codex" / "agents"
SOURCE_CONFIG = ROOT / ".codex" / "config.toml"
MARKDOWN_LINK = re.compile(r"\[[^]]*\]\(([^)]+)\)")


def default_codex_home() -> Path:
    configured = os.environ.get("CODEX_HOME", "").strip()
    return Path(configured).expanduser() if configured else Path.home() / ".codex"


def local_markdown_targets(document: Path) -> list[Path]:
    targets: list[Path] = []
    for raw_target in MARKDOWN_LINK.findall(document.read_text(encoding="utf-8")):
        target = raw_target.strip().split(maxsplit=1)[0].strip("<>")
        parsed = urlsplit(target)
        if parsed.scheme or parsed.netloc or not parsed.path:
            continue
        path = Path(unquote(parsed.path))
        if path.is_absolute():
            continue
        targets.append((document.parent / path).resolve())
    return targets


def validate_skill(skill_root: Path) -> None:
    missing: list[str] = []
    resolved_root = skill_root.resolve()
    for document in sorted(skill_root.rglob("*.md")):
        for target in local_markdown_targets(document):
            if not target.is_relative_to(resolved_root):
                missing.append(
                    f"{document.relative_to(skill_root)} -> {target} (outside skill bundle)"
                )
            elif not target.exists():
                missing.append(f"{document.relative_to(skill_root)} -> {target}")
    if missing:
        details = "\n".join(f"- {item}" for item in missing)
        raise RuntimeError(f"Skill contains missing local Markdown targets:\n{details}")


def timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")


def install_skill(source: Path, destination: Path, backup_root: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".codex-kanban-install-", dir=destination.parent))
    staged_skill = stage / "codex-kanban"
    previous = backup_root / "skills" / "codex-kanban"
    try:
        shutil.copytree(source, staged_skill)
        validate_skill(staged_skill)
        if destination.exists():
            previous.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(destination, previous)
        shutil.move(staged_skill, destination)
    except Exception:
        if not destination.exists() and previous.exists():
            shutil.move(previous, destination)
        raise
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def install_agents(source: Path, destination: Path, backup_root: Path) -> list[str]:
    destination.mkdir(parents=True, exist_ok=True)
    installed: list[str] = []
    for source_file in sorted(source.glob("*.toml")):
        target = destination / source_file.name
        if target.exists():
            backup = backup_root / "agents" / target.name
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, backup)
        with tempfile.NamedTemporaryFile(dir=destination, delete=False) as temporary:
            temporary_path = Path(temporary.name)
        try:
            shutil.copy2(source_file, temporary_path)
            temporary_path.replace(target)
        finally:
            temporary_path.unlink(missing_ok=True)
        installed.append(target.name)
    return installed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Install Codex Kanban skill and managed custom-agent profiles."
    )
    parser.add_argument(
        "--codex-home",
        type=Path,
        default=default_codex_home(),
        help="Codex home directory (default: CODEX_HOME or ~/.codex).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate source assets and print destinations without writing files.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    codex_home = args.codex_home.expanduser().resolve()
    skill_destination = codex_home / "skills" / "codex-kanban"
    agents_destination = codex_home / "agents"

    validate_skill(SOURCE_SKILL)
    if args.dry_run:
        print(f"Validated skill source: {SOURCE_SKILL}")
        print(f"Would replace managed skill: {skill_destination}")
        print(f"Would update managed agent profiles in: {agents_destination}")
        print(f"Would leave user configuration unchanged: {codex_home / 'config.toml'}")
        return 0

    backup_root = codex_home / "backups" / f"codex-kanban-{timestamp()}"
    install_skill(SOURCE_SKILL, skill_destination, backup_root)
    installed_agents = install_agents(SOURCE_AGENTS, agents_destination, backup_root)
    validate_skill(skill_destination)

    print(f"Installed skill: {skill_destination}")
    print(f"Installed managed agent profiles: {', '.join(installed_agents)}")
    if backup_root.exists():
        print(f"Backed up replaced assets: {backup_root}")
    print(f"User configuration was not changed; review defaults in: {SOURCE_CONFIG}")
    print("Start a new Codex session, then run the Kanban startup overview.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
