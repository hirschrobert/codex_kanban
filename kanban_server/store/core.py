from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

from .archival import CardArchivalStoreMixin
from .cards import CardStoreMixin
from .dependencies import DependencyStoreMixin
from .events import EventRelationStoreMixin
from .overview import OverviewStoreMixin
from .participants import ParticipantEventStoreMixin
from .projects import ProjectStoreMixin
from .schema import SchemaStoreMixin
from .serialization import SerializationCoordinationMixin
from .support import DEFAULT_DB_PATH
from .workflows import WorkflowStoreMixin

_T = TypeVar("_T")


class StoreOperationGate:
    """Compatibility context manager for older `with self._lock` call sites.

    SQLite WAL mode plus busy timeouts are the concurrency boundary. Keeping this
    object non-blocking lets concurrent HTTP handler threads and async offloads
    use separate SQLite connections instead of serializing every store call.
    """

    def __enter__(self) -> StoreOperationGate:
        return self

    def __exit__(self, *exc_info: object) -> bool:
        return False


class KanbanStore(
    SchemaStoreMixin,
    ProjectStoreMixin,
    OverviewStoreMixin,
    CardArchivalStoreMixin,
    CardStoreMixin,
    ParticipantEventStoreMixin,
    EventRelationStoreMixin,
    WorkflowStoreMixin,
    DependencyStoreMixin,
    SerializationCoordinationMixin,
):
    def __init__(
        self, db_path: str | Path | None = None, *, preferred_board_slug: str | None = None
    ):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.preferred_board_slug = preferred_board_slug
        self._lock = StoreOperationGate()
        self.migrate()

    async def run_async(
        self,
        operation: Callable[..., _T],
        /,
        *args: Any,
        **kwargs: Any,
    ) -> _T:
        return await asyncio.to_thread(operation, *args, **kwargs)

    async def snapshot_async(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return await self.run_async(self.snapshot, *args, **kwargs)

    async def overview_async(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return await self.run_async(self.overview, *args, **kwargs)

    async def get_card_async(self, *args: Any, **kwargs: Any) -> dict[str, Any] | None:
        return await self.run_async(self.get_card, *args, **kwargs)

    async def create_card_async(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return await self.run_async(self.create_card, *args, **kwargs)

    async def update_card_async(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return await self.run_async(self.update_card, *args, **kwargs)

    async def add_card_comment_async(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return await self.run_async(self.add_card_comment, *args, **kwargs)

    async def create_event_async(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return await self.run_async(self.create_event, *args, **kwargs)

    async def list_events_async(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return await self.run_async(self.list_events, *args, **kwargs)

    async def upsert_participant_async(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return await self.run_async(self.upsert_participant, *args, **kwargs)

    async def register_project_async(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return await self.run_async(self.register_project, *args, **kwargs)
