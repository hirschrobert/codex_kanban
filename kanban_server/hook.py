from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .ingest import _post_json
from .project.registration import auto_register_payload_for_cwd
from .store.core import KanbanStore
from .store.support import (
    DEFAULT_AI_AGENT_MANAGER_DISPLAY_NAME,
    DEFAULT_AI_AGENT_MANAGER_ROLE,
    DEFAULT_AI_AGENT_MANAGER_SUFFIX,
    DEFAULT_CODEX_SUBAGENTS_DISPLAY_NAME,
    DEFAULT_CODEX_SUBAGENTS_ROLE,
    DEFAULT_CODEX_SUBAGENTS_SUFFIX,
    DEFAULT_DB_PATH,
    GENERIC_AGENT_PROFILES,
    agent_profile_id,
    slugify,
)

KANBAN_HOOK_EVENTS = ("UserPromptSubmit", "SubagentStart", "SubagentStop", "Stop")


def _kanban_hook_group(event_name: str, *, repo: Path, server_url: str) -> dict[str, Any]:
    environment = {
        "CODEX_HOOK_EVENT": event_name,
        "CODEX_KANBAN_URL": server_url,
        "CODEX_KANBAN_REPO": str(repo),
        "PYTHONPATH": str(repo),
    }
    command = " ".join(
        [
            *(f"{key}={shlex.quote(value)}" for key, value in environment.items()),
            "python3 -m kanban_server.hook",
        ]
    )
    group: dict[str, Any] = {
        "hooks": [
            {
                "type": "command",
                "command": command,
                "timeout": 10,
                "statusMessage": f"Recording {event_name} in Kanban",
            }
        ]
    }
    if event_name.startswith("Subagent"):
        group["matcher"] = "*"
    return group


def _is_kanban_hook_group(group: Any) -> bool:
    if not isinstance(group, dict):
        return False
    handlers = group.get("hooks")
    if not isinstance(handlers, list):
        return False
    return any(
        isinstance(handler, dict) and "kanban_server.hook" in str(handler.get("command") or "")
        for handler in handlers
    )


def _merged_user_hooks(existing: dict[str, Any], *, repo: Path, server_url: str) -> dict[str, Any]:
    result = dict(existing)
    hooks = dict(existing.get("hooks") or {})
    for event_name in KANBAN_HOOK_EVENTS:
        groups = hooks.get(event_name)
        existing_groups = list(groups) if isinstance(groups, list) else []
        if not any(_is_kanban_hook_group(group) for group in existing_groups):
            existing_groups.append(_kanban_hook_group(event_name, repo=repo, server_url=server_url))
        hooks[event_name] = existing_groups
    result["hooks"] = hooks
    return result


def _install_user_hooks(path: Path, *, repo: Path, server_url: str) -> Path:
    existing: dict[str, Any] = {}
    if path.exists():
        parsed = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(parsed, dict):
            raise ValueError(f"hook configuration must be a JSON object: {path}")
        existing = parsed
    merged = _merged_user_hooks(existing, repo=repo.resolve(), server_url=server_url)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        handle.write(json.dumps(merged, indent=2) + "\n")
        temporary_path = Path(handle.name)
    temporary_path.replace(path)
    return path


def _install_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Install Codex Kanban lifecycle hooks.")
    parser.add_argument(
        "--hooks-path",
        type=Path,
        default=Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "hooks.json",
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path(os.environ.get("CODEX_KANBAN_REPO") or Path(__file__).resolve().parents[1]),
    )
    parser.add_argument(
        "--server-url",
        default=os.environ.get("CODEX_KANBAN_URL", "http://127.0.0.1:8766"),
    )
    return parser


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
        payload.get("session_id"),
        payload.get("sessionId"),
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
    if "subagent" in hook_name.lower():
        profile_id = agent_profile_id(agent_type)
        if profile_id in known_profiles:
            return slugify(f"{board_slug}-{profile_id}"), raw_agent_id
        return slugify(f"{board_slug}-{DEFAULT_CODEX_SUBAGENTS_SUFFIX}"), raw_agent_id
    return slugify(f"{board_slug}-{DEFAULT_AI_AGENT_MANAGER_SUFFIX}"), raw_agent_id


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


def _event_metadata(
    payload: dict[str, Any],
    *,
    hook_name: str,
    cwd: str,
    project_slug: str,
    raw_agent_id: str,
    agent_type: str,
) -> dict[str, str]:
    metadata = {
        "hook": hook_name,
        "cwd": cwd,
        "project": project_slug,
        "raw_agent_id": raw_agent_id,
        "agent_type": agent_type,
    }
    runtime_fields = {
        "model": _first_text(payload.get("model")),
        "session_id": _first_text(payload.get("session_id"), payload.get("sessionId")),
        "turn_id": _first_text(payload.get("turn_id"), payload.get("turnId")),
        "status": _status_for_hook(hook_name),
    }
    metadata.update({key: value for key, value in runtime_fields.items() if value})
    return metadata


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


def _auto_register_project(
    store: KanbanStore, cwd: str | Path, server_url: str
) -> dict[str, Any] | None:
    payload = auto_register_payload_for_cwd(cwd)
    if not payload:
        return None

    if server_url:
        project = _post_json_result(server_url, "/api/projects", payload)
        if project:
            return project
    return store.register_project(payload)


def _refresh_project_agents(
    store: KanbanStore,
    project: dict[str, Any] | None,
    server_url: str,
) -> dict[str, Any] | None:
    if not project:
        return None
    if server_url:
        refreshed = _post_json_result(server_url, "/api/projects", project)
        if refreshed:
            return refreshed
    result = store.refresh_project_agents(project["board_slug"])
    return result["project"] if result else project


def _context_message(project: dict[str, Any], board_slug: str) -> str:
    instructions = ", ".join(project.get("instruction_paths", []))
    profiles = ", ".join(project.get("agent_profiles", []))
    return (
        f"This workspace is registered with Codex Kanban board '{board_slug}'. "
        "Use the `codex-kanban` skill for the shared orchestration workflow: "
        "respect human-added cards, work only on the assigned card/scope, update "
        "status, and produce auditable handoffs. "
        "Codex Kanban does not require delegation or choose agents for the main "
        "agent. Decide whether native built-in agents, custom agents, registered "
        "Kanban profiles, or no delegation best fit the task. Registered profiles "
        "are optional offers; when deliberately selecting one, use its exact "
        "custom-agent name so its TOML configuration is loaded. "
        "When delegated work finishes, add a concise result comment to the "
        "parent coordination card so findings, decisions, blockers, and next "
        "steps stay with the topic context. "
        f"Available registered agent profiles for this project: {profiles}. "
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
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments[:1] == ["install"]:
        args = _install_parser().parse_args(arguments[1:])
        installed_path = _install_user_hooks(
            args.hooks_path,
            repo=args.repo,
            server_url=args.server_url,
        )
        print(f"Installed Codex Kanban hooks in {installed_path}")
        return 0
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
    project = _refresh_project_agents(store, project, server_url) or project
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
    participant = None
    if participant_id:
        is_subagent = "subagent" in hook_name.lower()
        is_native_subagent = participant_id == slugify(
            f"{board_slug}-{DEFAULT_CODEX_SUBAGENTS_SUFFIX}"
        )
        participant = {
            "id": participant_id,
            "kind": "agent",
            "display_name": (
                DEFAULT_CODEX_SUBAGENTS_DISPLAY_NAME
                if is_native_subagent
                else agent_type if is_subagent else DEFAULT_AI_AGENT_MANAGER_DISPLAY_NAME
            ),
            "role": (
                DEFAULT_CODEX_SUBAGENTS_ROLE
                if is_native_subagent
                else agent_type if is_subagent else DEFAULT_AI_AGENT_MANAGER_ROLE
            ),
            "status": "idle",
            "board_slug": board_slug,
            "current_scope": cwd,
        }
        if card_external_id:
            participant["current_card_external_id"] = card_external_id
    metadata = _event_metadata(
        payload,
        hook_name=hook_name,
        cwd=cwd,
        project_slug=project["slug"] if project else "",
        raw_agent_id=raw_agent_id,
        agent_type=agent_type,
    )
    if participant_id == slugify(f"{board_slug}-{DEFAULT_CODEX_SUBAGENTS_SUFFIX}"):
        metadata["binding_source"] = "native_subagent"
    event = {
        "board_slug": board_slug,
        "event_type": _event_type_for_hook(hook_name),
        "participant_id": participant_id or None,
        "card_external_id": card_external_id,
        "message": agent_type,
        "metadata": metadata,
    }

    posted = False
    if server_url:
        if participant:
            _post_json(server_url, "/api/participants", participant)
        posted = _post_json(server_url, "/api/events", event)
    if not posted:
        if participant:
            store.upsert_participant(participant)
        store.create_event(event)

    _emit_subagent_context(hook_name, project, board_slug)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
