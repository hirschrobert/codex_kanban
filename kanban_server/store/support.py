from __future__ import annotations

import json
import os
import re
import tomllib
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_DEFAULT_HOME = os.environ.get("CODEX_KANBAN_HOME")
DEFAULT_HOME = (
    Path(_DEFAULT_HOME).expanduser() if _DEFAULT_HOME else Path.home() / ".codex" / "codex-kanban"
)
DEFAULT_DB_PATH = Path(os.environ.get("CODEX_KANBAN_DB", DEFAULT_HOME / "kanban.sqlite3"))

LANES = (
    {"status": "backlog", "title": "Backlog", "position": 10},
    {"status": "ready", "title": "Ready", "position": 20},
    {"status": "in_progress", "title": "In Progress", "position": 30},
    {"status": "review", "title": "Review", "position": 40},
    {"status": "blocked", "title": "Blocked", "position": 50},
    {"status": "done", "title": "Done", "position": 60},
)

LANE_STATUSES = {lane["status"] for lane in LANES}
ACTIVE_CONFLICT_STATUSES = {"in_progress", "blocked"}
ACTIVE_CARD_STATUSES = {"in_progress", "review"}
ACTIVE_PARTICIPANT_STATUSES = {"running", "reviewing"}
DEPENDENCY_ADVANCEMENT_STATUSES = {"in_progress", "review", "done"}
DEPENDENCY_RESOLVED_STATUSES = {"done"}
REPEAT_CADENCES = {"none", "daily", "weekly", "monthly"}
DEFAULT_REPEAT_TIME = "01:00"
DEFAULT_REPEAT_TIMEZONE = "Europe/Berlin"
DEFAULT_OVERVIEW_DONE_LIMIT = 5
STALE_AFTER_SECONDS = int(os.environ.get("CODEX_KANBAN_STALE_AFTER_SECONDS", "300"))
MAX_ACTIVE_AGENTS_PER_PROJECT = int(
    os.environ.get("CODEX_KANBAN_MAX_ACTIVE_AGENTS_PER_PROJECT", "4")
)
MAX_ACTIVE_IMPLEMENTERS_PER_PROJECT = int(
    os.environ.get("CODEX_KANBAN_MAX_ACTIVE_IMPLEMENTERS_PER_PROJECT", "1")
)
MAX_ACTIVE_AGENTS_GLOBAL = int(os.environ.get("CODEX_KANBAN_MAX_ACTIVE_AGENTS_GLOBAL", "0"))
PRIORITIES = {"low", "normal", "high", "urgent"}
PARTICIPANT_KINDS = {"agent", "human", "system"}
LOCAL_COMMENT_AUTHOR_NAME = "local developer"
LEGACY_LOCAL_COMMENT_AUTHOR_NAMES = {"local human"}
DEFAULT_AI_AGENT_MANAGER_DISPLAY_NAME = "AI Agent Manager"
DEFAULT_AI_AGENT_MANAGER_ROLE = "Main AI agent coordinating Kanban cards through the CLI."
DEFAULT_AI_AGENT_MANAGER_SUFFIX = "ai-agent-manager"
PARTICIPANT_STATUSES = {
    "idle",
    "running",
    "waiting",
    "waiting_approval",
    "blocked",
    "reviewing",
    "done",
    "offline",
}

JSON_LIST_FIELDS = {
    "affected_paths",
    "deployment_dispositions",
    "files_changed",
    "checks",
    "assumptions",
    "follow_up_cards",
}

PROJECT_JSON_FIELDS = {
    "paths",
    "instruction_paths",
    "agent_profiles",
}

GENERIC_AGENT_PROFILES = {
    "kanban_auditor": "Read-only board/card, handoff, stale-state, and release-containment audit.",
    "domain_model_steward": (
        "Read-only terminology, ubiquitous-language, and data-model impact review."
    ),
    "architecture_impact_analyst": (
        "Read-only blast-radius, boundary, and architectural impact analysis."
    ),
    "api_contract_steward": "Read-only OpenAPI, AsyncAPI, schema, and contract-first review.",
    "project_architect": "Read-only architecture, contracts, release-train, and risk analysis.",
    "project_implementer": "Bounded implementation worker with scoped file ownership.",
    "project_reviewer": "Read-only correctness, regression, security, and test review.",
    "project_release_manager": "Read-only release, CI/CD, packaging, and deploy-readiness review.",
    "test_strategist": "Read-only test strategy, coverage, and verification planning.",
}

AGENT_PROFILE_FILE_SUFFIXES = {".toml", ".json", ".md", ".txt"}
CODEX_KANBAN_REPO_ROOT = Path(__file__).resolve().parents[2]

CARD_TEXT_FIELDS = {
    "external_id",
    "title",
    "description",
    "status",
    "assignee_id",
    "owner_id",
    "intake_kind",
    "intake_source",
    "reported_by",
    "impact",
    "evidence",
    "priority",
    "target_repo",
    "target_branch",
    "starting_target_sha",
    "handoff_target_sha",
    "feature_branch",
    "worktree_path",
    "blocker_reason",
    "repeat_cadence",
    "repeat_time",
    "repeat_timezone",
}


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "item"


def agent_profile_id(value: Any) -> str:
    if isinstance(value, dict):
        value = (
            value.get("name")
            or value.get("id")
            or value.get("display_name")
            or value.get("profile")
        )
    text = str(value or "").strip()
    if not text:
        return ""
    return slugify(text).replace("-", "_")


def merge_agent_profiles(*groups: Any) -> list[str]:
    profiles: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for item in _normalise_list(group):
            profile = agent_profile_id(item)
            if not profile or profile in seen:
                continue
            seen.add(profile)
            profiles.append(profile)
    return profiles


def discover_project_agent_profiles(
    root_path: str | Path | None,
    paths: list[Any] | None = None,
) -> list[str]:
    candidates: list[Any] = []
    if root_path:
        candidates.append(root_path)
    candidates.extend(paths or [])

    agent_dirs: list[Path] = []
    seen_dirs: set[Path] = set()
    for candidate in candidates:
        raw_path = candidate.get("path") if isinstance(candidate, dict) else candidate
        if not raw_path:
            continue
        try:
            agent_dir = Path(str(raw_path)).expanduser().resolve() / ".codex" / "agents"
        except (OSError, RuntimeError):
            continue
        if agent_dir in seen_dirs or not agent_dir.is_dir():
            continue
        seen_dirs.add(agent_dir)
        agent_dirs.append(agent_dir)
    return discover_agent_profiles_from_dirs(agent_dirs)


def discover_default_agent_profiles() -> list[str]:
    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser()
    return discover_agent_profiles_from_dirs(
        [
            CODEX_KANBAN_REPO_ROOT / ".codex" / "agents",
            codex_home / "agents",
        ]
    )


def discover_agent_profiles_from_dirs(agent_dirs: Sequence[str | Path]) -> list[str]:
    profiles: list[str] = []
    seen_dirs: set[Path] = set()
    for raw_dir in agent_dirs:
        try:
            agent_dir = Path(raw_dir).expanduser().resolve()
        except (OSError, RuntimeError):
            continue
        if agent_dir in seen_dirs or not agent_dir.is_dir():
            continue
        seen_dirs.add(agent_dir)
        for path in sorted(agent_dir.iterdir()):
            if not path.is_file() or path.name.startswith("."):
                continue
            if path.stem.lower() in {"readme", "agents"}:
                continue
            if path.suffix.lower() not in AGENT_PROFILE_FILE_SUFFIXES:
                continue
            profile = _profile_from_agent_file(path)
            if profile:
                profiles.append(profile)
    return merge_agent_profiles(profiles)


def _profile_from_agent_file(path: Path) -> str:
    raw_name: Any = path.stem
    if path.suffix.lower() == ".toml":
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            data = {}
        if isinstance(data, dict):
            raw_name = data.get("name") or data.get("id") or data.get("display_name") or raw_name
    elif path.suffix.lower() == ".json":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        if isinstance(data, dict):
            raw_name = data.get("name") or data.get("id") or data.get("display_name") or raw_name
    return agent_profile_id(raw_name)


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"))


def _json_loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _normalise_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return []
        if value.startswith("["):
            parsed = _json_loads(value, [])
            return parsed if isinstance(parsed, list) else []
        return [part.strip() for part in re.split(r"[\n,]+", value) if part.strip()]
    return [value]


def _normalise_deployment_dispositions(value: Any) -> list[dict[str, str]]:
    dispositions: list[dict[str, str]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for item in _normalise_list(value):
        entry = _deployment_disposition_entry(item)
        if not entry:
            continue
        key = (
            entry.get("label", ""),
            entry.get("path", ""),
            entry.get("status", ""),
            entry.get("note", ""),
        )
        if key in seen:
            continue
        seen.add(key)
        dispositions.append(entry)
    return dispositions


def _deployment_disposition_entry(value: Any) -> dict[str, str] | None:
    if isinstance(value, dict):
        path = _clean_deployment_text(
            value.get("path")
            or value.get("repo")
            or value.get("repository")
            or value.get("worktree")
            or value.get("target")
        )
        label = _clean_deployment_text(value.get("label") or value.get("app") or value.get("name"))
        status = _clean_deployment_text(
            value.get("status") or value.get("disposition") or value.get("state")
        )
        note = _clean_deployment_text(
            value.get("note") or value.get("reason") or value.get("detail")
        )
    else:
        label, path, status, note = _parse_deployment_disposition_text(str(value or ""))

    if not path and label:
        path, label = label, ""
    if not path:
        return None
    entry = {"path": path, "status": status or "pending"}
    if label:
        entry["label"] = label
    if note:
        entry["note"] = note
    return entry


def _parse_deployment_disposition_text(value: str) -> tuple[str, str, str, str]:
    text = value.strip()
    if not text:
        return "", "", "", ""
    if text.startswith("{"):
        parsed = _json_loads(text, {})
        if isinstance(parsed, dict):
            entry = _deployment_disposition_entry(parsed)
            if entry:
                return (
                    entry.get("label", ""),
                    entry.get("path", ""),
                    entry.get("status", ""),
                    entry.get("note", ""),
                )
    target, separator, disposition = text.partition("=")
    if separator:
        label, path = _deployment_target_parts(target)
        status, note = _deployment_status_parts(disposition)
        return label, path, status, note

    parts = [_clean_deployment_text(part) for part in text.split("|")]
    parts = [part for part in parts if part]
    if len(parts) >= 4:
        return parts[0], parts[1], parts[2], "|".join(parts[3:])
    if len(parts) == 3:
        return "", parts[0], parts[1], parts[2]
    if len(parts) == 2:
        return "", parts[0], parts[1], ""
    return "", parts[0] if parts else "", "pending", ""


def _deployment_target_parts(value: str) -> tuple[str, str]:
    parts = [_clean_deployment_text(part) for part in value.split("|", 1)]
    if len(parts) == 2:
        return parts[0], parts[1]
    return "", parts[0] if parts else ""


def _deployment_status_parts(value: str) -> tuple[str, str]:
    if "|" in value:
        status, note = value.split("|", 1)
        return _clean_deployment_text(status), _clean_deployment_text(note)
    status, separator, note = value.partition(":")
    return _clean_deployment_text(status), _clean_deployment_text(note) if separator else ""


def _clean_deployment_text(value: Any) -> str:
    return _normalise_text_newlines(str(value or "")).strip()


def _normalise_metadata(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return {}
        parsed = _json_loads(value, {})
        return parsed if isinstance(parsed, dict) else {"text": value}
    return {"value": value}


def _normalise_text_newlines(text: str) -> str:
    return (
        text.replace("\\r\\n", "\n")
        .replace("\\n", "\n")
        .replace("\\r", "\n")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
    )


def _normalise_comment_author_name(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.strip()
    if cleaned.lower() in LEGACY_LOCAL_COMMENT_AUTHOR_NAMES:
        return LOCAL_COMMENT_AUTHOR_NAME
    return cleaned or None


__all__ = [
    "DEFAULT_HOME",
    "DEFAULT_DB_PATH",
    "LANES",
    "LANE_STATUSES",
    "ACTIVE_CONFLICT_STATUSES",
    "ACTIVE_CARD_STATUSES",
    "ACTIVE_PARTICIPANT_STATUSES",
    "DEPENDENCY_ADVANCEMENT_STATUSES",
    "DEPENDENCY_RESOLVED_STATUSES",
    "REPEAT_CADENCES",
    "DEFAULT_REPEAT_TIME",
    "DEFAULT_REPEAT_TIMEZONE",
    "STALE_AFTER_SECONDS",
    "MAX_ACTIVE_AGENTS_PER_PROJECT",
    "MAX_ACTIVE_IMPLEMENTERS_PER_PROJECT",
    "MAX_ACTIVE_AGENTS_GLOBAL",
    "PRIORITIES",
    "PARTICIPANT_KINDS",
    "LOCAL_COMMENT_AUTHOR_NAME",
    "LEGACY_LOCAL_COMMENT_AUTHOR_NAMES",
    "DEFAULT_AI_AGENT_MANAGER_DISPLAY_NAME",
    "DEFAULT_AI_AGENT_MANAGER_ROLE",
    "DEFAULT_AI_AGENT_MANAGER_SUFFIX",
    "PARTICIPANT_STATUSES",
    "JSON_LIST_FIELDS",
    "PROJECT_JSON_FIELDS",
    "GENERIC_AGENT_PROFILES",
    "AGENT_PROFILE_FILE_SUFFIXES",
    "CODEX_KANBAN_REPO_ROOT",
    "CARD_TEXT_FIELDS",
    "utc_now",
    "_utc_datetime",
    "slugify",
    "agent_profile_id",
    "merge_agent_profiles",
    "discover_default_agent_profiles",
    "discover_agent_profiles_from_dirs",
    "discover_project_agent_profiles",
    "_profile_from_agent_file",
    "_json_dumps",
    "_json_loads",
    "_normalise_list",
    "_normalise_deployment_dispositions",
    "_normalise_metadata",
    "_normalise_text_newlines",
    "_normalise_comment_author_name",
]
