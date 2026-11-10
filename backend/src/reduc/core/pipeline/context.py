"""What a pipeline stage receives: the draft it writes to and its replaceable dependencies."""

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from reduc.core.db.models import Region
from reduc.core.providers.elevation.base import ElevationSource
from reduc.core.providers.osm.graph import Bbox, OsmData

BATCH_SIZE = 500

StageStats = dict[str, Any]


class PipelineCancelledError(Exception):
    """Raised by a stage when the run was cancelled between two batches."""


@dataclass
class PipelineDeps:
    """Factories for everything a stage reaches outside the database.

    Production wiring lives in `pipeline/wiring.py`; tests pass fakes, so no stage ever
    touches the network.
    """

    #: Receives the region and the buffered bounding box (west, south, east, north) to download.
    osm_source: Callable[[Region, Bbox], OsmData] | None = None
    elevation_source: Callable[[Region], ElevationSource | None] | None = None
    extras: dict[str, Any] = field(default_factory=dict)


def _no_progress(_fraction: float) -> None:
    return None


def _never_cancelled() -> bool:
    return False


@dataclass
class StageContext:
    session: Session
    region: Region
    map_version_id: uuid.UUID
    deps: PipelineDeps
    #: Called with a fraction in 0..1 after each batch.
    report: Callable[[float], None] = _no_progress
    is_cancelled: Callable[[], bool] = _never_cancelled

    def checkpoint(self, done: int, total: int) -> None:
        """Report progress and stop cleanly when the run was cancelled."""
        if self.is_cancelled():
            raise PipelineCancelledError()
        self.report(1.0 if total <= 0 else min(1.0, done / total))

    @property
    def thresholds(self) -> dict[str, Any]:
        value = (self.region.config or {}).get("thresholds") or {}
        return dict(value)
