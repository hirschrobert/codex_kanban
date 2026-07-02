from __future__ import annotations

import threading
from pathlib import Path

from .cards import CardStoreMixin
from .dependencies import DependencyStoreMixin
from .overview import OverviewStoreMixin
from .participants import ParticipantEventStoreMixin
from .projects import ProjectStoreMixin
from .schema import SchemaStoreMixin
from .serialization import SerializationCoordinationMixin
from .support import DEFAULT_DB_PATH
from .workflows import WorkflowStoreMixin


class KanbanStore(
    SchemaStoreMixin,
    ProjectStoreMixin,
    OverviewStoreMixin,
    CardStoreMixin,
    ParticipantEventStoreMixin,
    WorkflowStoreMixin,
    DependencyStoreMixin,
    SerializationCoordinationMixin,
):
    def __init__(
        self, db_path: str | Path | None = None, *, preferred_board_slug: str | None = None
    ):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.preferred_board_slug = preferred_board_slug
        self._lock = threading.RLock()
        self.migrate()
