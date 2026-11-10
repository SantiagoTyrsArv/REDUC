"""Routing contracts independent of the graph implementation."""

import math
import uuid
from dataclasses import dataclass
from typing import Protocol

from reduc.core.domain.profile import MobilityProfile


@dataclass(frozen=True)
class Coordinate:
    """A WGS84 longitude/latitude pair."""

    lon: float
    lat: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.lon) or not -180.0 <= self.lon <= 180.0:
            raise ValueError("lon must be finite and between -180 and 180")
        if not math.isfinite(self.lat) or not -90.0 <= self.lat <= 90.0:
            raise ValueError("lat must be finite and between -90 and 90")


@dataclass(frozen=True)
class RoutePath:
    """One computed path; distance is physical and cost is equivalent meters."""

    path_id: int
    edge_ids: tuple[int, ...]
    distance_m: float
    cost_m: float


@dataclass(frozen=True)
class RoutingResult:
    """Accessible alternatives plus optional reference and fallback information."""

    routes: tuple[RoutePath, ...]
    shortest: RoutePath | None = None
    blocking_barrier_ids: tuple[uuid.UUID, ...] = ()
    fallback_route: RoutePath | None = None
    relaxed_constraints: tuple[str, ...] = ()

    @property
    def has_accessible_route(self) -> bool:
        return bool(self.routes)


class RoutingEngine(Protocol):
    """Interface consumed by the API and replaceable for large regions."""

    def route(
        self,
        map_version_id: uuid.UUID,
        origin: Coordinate,
        destination: Coordinate,
        profile: MobilityProfile,
        *,
        alternatives: int = 0,
        include_shortest: bool = False,
    ) -> RoutingResult:
        """Compute accessible paths and, when needed, a conservative fallback."""
        ...


class NoNearbyPathError(ValueError):
    """Raised when an endpoint has no graph edge within fifty meters."""

    def __init__(self, endpoint: str) -> None:
        self.endpoint = endpoint
        super().__init__(f"No path within 50 m of {endpoint}")
