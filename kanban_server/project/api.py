from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


def _request_json(
    server_url: str,
    path: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        server_url.rstrip("/") + path,
        data=data,
        headers={"Content-Type": "application/json"} if payload is not None else {},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8").strip()
        try:
            parsed = json.loads(detail)
        except json.JSONDecodeError:
            parsed = {}
        message = parsed.get("error") or detail or exc.reason
        raise SystemExit(f"{method} {path} failed: {message}") from exc
    except (OSError, urllib.error.URLError):
        return None


def _post_json(server_url: str, path: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    return _request_json(server_url, path, method="POST", payload=payload)


def _patch_json(server_url: str, path: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    return _request_json(server_url, path, method="PATCH", payload=payload)


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, indent=2))
