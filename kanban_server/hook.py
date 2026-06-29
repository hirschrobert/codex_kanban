from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .ingest import _post_json
from .store.core import KanbanStore
from .store.support import DEFAULT_DB_PATH, GENERIC_AGENT_PROFILES, agent_profile_id, slugify


def _read_hook_payload() -> dict[str, Any]:
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw}
    return parsed if isinstance(parsed, dict) else {"payload": parsed}


def _first_text(*values: Any) -> str:
    for value in values:
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _hook_name(payload: dict[str, Any]) -> str:
    return _first_text(
        payload.get("hook_event_name"),
        payload.get("hookEventName"),
        payload.get("event"),
        payload.get("type"),
        os.environ.get("CODEX_HOOK_EVENT"),
        "hook",
    )


def _subagent_payload(payload: dict[str, Any]) -> dict[str, Any]:
    subagent = payload.get("subagent")
    return subagent if isinstance(subagent, dict) else {}


def _agent_type(payload: dict[str, Any]) -> str:
    subagent = _subagent_payload(payload)
    return _first_text(
        payload.get("agent_type"),
        payload.get("agentType"),
        subagent.get("type"),
        subagent.get("agent_type"),
        payload.get("matcher"),
        "codex-agent",
    )


def _agent_id(payload: dict[str, Any], agent_type: str) -> str:
    subagent = _subagent_payload(payload)
    return _first_text(
        payload.get("agent_id"),
        payload.get("agentId"),
        subagent.get("id"),
        payload.get("thread_id"),
        payload.get("threadId"),
        agent_type,
    )


def _explicit_board_slug(payload: dict[str, Any]) -> str:
    return _first_text(
        payload.get("board_slug"),
        payload.get("boardSlug"),
        payload.get("current_board_slug"),
        os.environ.get("CODEX_KANBAN_BOARD"),
    )


def _explicit_card_external_id(payload: dict[str, Any]) -> str:
    return _first_text(
        payload.get("current_card_external_id"),
        payload.get("currentCardExternalId"),
        payload.get("card_external_id"),
        payload.get("cardExternalId"),
        os.environ.get("CODEX_KANBAN_CARD"),
    )


def _project_for_board(store: KanbanStore, board_slug: str) -> dict[str, Any] | None:
    for project in store.list_projects():
        if project.get("board_slug") == board_slug:
            return project
    return None


def _participant_id_for_hook(
    payload: dict[str, Any],
    hook_name: str,
    agent_type: str,
    board_slug: str,
    agent_profiles: list[Any] | None = None,
) -> tuple[str, str]:
    raw_agent_id = _agent_id(payload, agent_type)
    known_profiles = {agent_profile_id(profile) for profile in GENERIC_AGENT_PROFILES}
    known_profiles.update(agent_profile_id(profile) for profile in (agent_profiles or []))
    if "subagent" in hook_name.lower() and agent_profile_id(agent_type) in known_profiles:
        return slugify(f"{board_slug}-{agent_type}"), raw_agent_id
    return raw_agent_id, raw_agent_id


def _status_for_hook(hook_name: str) -> str:
    lowered = hook_name.lower()
    if "stop" in lowered:
        return "done"
    if "permission" in lowered:
        return "waiting_approval"
    return "running"


def _event_type_for_hook(hook_name: str) -> str:
    lowered = hook_name.lower()
    if "subagent" in lowered and "start" in lowered:
        return "subagent.started"
    if "subagent" in lowered and "stop" in lowered:
        return "subagent.stopped"
    if lowered == "stop":
        return "turn.stopped"
    return f"hook.{lowered.replace('_', '-')}"


def _post_json_result(server_url: str, path: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        server_url.rstrip("/") + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            return json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError):
        return None


def _repo_root(cwd: str | Path) -> Path:
    path = Path(cwd).expanduser().resolve()
    if path.is_file():
        path = path.parent
    for candidate in [path, *path.parents]:
        if (candidate / ".git").exists():
            return candidate
    return path


def _instruction_paths(root: Path, cwd: str | Path) -> list[Path]:
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


def _uses_codex_kanban(instruction_paths: list[Path]) -> bool:
    for instruction_path in instruction_paths:
        try:
            if "codex-kanban" in instruction_path.read_text(encoding="utf-8").lower():
                return True
        except OSError:
            continue
    return False


def _auto_register_payload(root: Path, instruction_paths: list[Path]) -> dict[str, Any]:
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
        "instruction_paths": [str(path) for path in instruction_paths],
        "agent_profiles": list(GENERIC_AGENT_PROFILES),
    }


def _auto_register_project(
    store: KanbanStore, cwd: str | Path, server_url: str
) -> dict[str, Any] | None:
    root = _repo_root(cwd)
    instructions = _instruction_paths(root, cwd)
    if not _uses_codex_kanban(instructions):
        return None

    payload = _auto_register_payload(root, instructions)
    if server_url:
        project = _post_json_result(server_url, "/api/projects", payload)
        if project:
            return project
    return store.register_project(payload)


def _context_message(project: dict[str, Any], board_slug: str) -> str:
    instructions = ", ".join(project.get("instruction_paths", []))
    profiles = ", ".join(project.get("agent_profiles", []))
    return (
        f"This workspace is registered with Codex Kanban board '{board_slug}'. "
        "Use the `codex-kanban` skill for the shared orchestration workflow: "
        "respect human-added cards, work only on the assigned card/scope, update "
        "status, and produce auditable handoffs. "
        f"Use the registered agent profiles for this project when delegating: {profiles}. "
        "Project-specific agent extensions live in the project repo's .codex/agents. "
        f"Read the concrete project instructions before work: {instructions}."
    )


def _emit_subagent_context(hook_name: str, project: dict[str, Any] | None, board_slug: str) -> None:
    if "subagent" not in hook_name.lower() or "start" not in hook_name.lower() or not project:
        return
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SubagentStart",
                    "additionalContext": _context_message(project, board_slug),
                }
            }
        )
    )


def main(argv: list[str] | None = None) -> int:
    del argv
    payload = _read_hook_payload()
    db_path = Path(os.environ.get("CODEX_KANBAN_DB") or DEFAULT_DB_PATH)
    server_url = os.environ.get("CODEX_KANBAN_URL", "")
    cwd = _first_text(payload.get("cwd"), os.getcwd())

    store = KanbanStore(db_path)
    project = store.project_for_path(cwd)
    if not project:
        project = _auto_register_project(store, cwd, server_url)
    explicit_board = _explicit_board_slug(payload)
    if explicit_board:
        board_slug = slugify(explicit_board)
        project = _project_for_board(store, board_slug) or project
    else:
        board_slug = project["board_slug"] if project else store.default_board_slug()
    hook_name = _hook_name(payload)
    agent_type = _agent_type(payload)
    participant_id, raw_agent_id = _participant_id_for_hook(
        payload,
        hook_name,
        agent_type,
        board_slug,
        project.get("agent_profiles", []) if project else [],
    )
    card_external_id = _explicit_card_external_id(payload)
    status = _status_for_hook(hook_name)

    participant = {
        "id": participant_id,
        "kind": "agent" if "subagent" in hook_name.lower() else "system",
        "display_name": agent_type,
        "role": agent_type,
        "status": status,
        "board_slug": board_slug,
        "current_scope": cwd,
    }
    if card_external_id:
        participant["current_card_external_id"] = card_external_id
    event = {
        "board_slug": board_slug,
        "event_type": _event_type_for_hook(hook_name),
        "participant_id": participant_id,
        "card_external_id": card_external_id,
        "message": agent_type,
        "metadata": {
            "hook": hook_name,
            "cwd": cwd,
            "project": project["slug"] if project else "",
            "raw_agent_id": raw_agent_id,
        },
    }

    posted = False
    if server_url:
        _post_json(server_url, "/api/participants", participant)
        posted = _post_json(server_url, "/api/events", event)
    if not posted:
        store.upsert_participant(participant)
        store.create_event(event)

    _emit_subagent_context(hook_name, project, board_slug)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
