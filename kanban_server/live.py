from __future__ import annotations

import queue
import threading
from typing import Any


class EventBroker:
    """Fan out coalesced board invalidations without serializing snapshots."""

    def __init__(self) -> None:
        self._clients: dict[queue.Queue[dict[str, Any]], str] = {}
        self._lock = threading.Lock()

    def subscribe(self, board_slug: str) -> queue.Queue[dict[str, Any]]:
        client: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)
        with self._lock:
            self._clients[client] = board_slug
        return client

    def unsubscribe(self, client: queue.Queue[dict[str, Any]]) -> None:
        with self._lock:
            self._clients.pop(client, None)

    def publish_change(self, board_slug: str) -> None:
        message = {"event": "change", "data": {"board_slug": board_slug}}
        with self._lock:
            clients = [client for client, board in self._clients.items() if board == board_slug]
        for client in clients:
            try:
                client.put_nowait(message)
            except queue.Full:
                pass

    def board_slugs(self) -> set[str]:
        with self._lock:
            return set(self._clients.values())
