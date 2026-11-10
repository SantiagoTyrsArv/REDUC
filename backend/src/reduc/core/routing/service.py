"""Application service: region lookup, routing and narrative for one request."""

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from reduc.core.db.repositories.routing import (
    BarrierRecord,
    EdgeRecord,
    find_region_for_points,
    load_barriers,
    load_edges,
    load_region_pois,
    locate_fraction,
)
from reduc.core.domain.profile import MobilityProfile
from reduc.core.routing.cost import BLOCKED_COST, edge_cost
from reduc.core.routing.engine import Coordinate, RoutePath, RoutingEngine
from reduc.core.routing.geometry import Coord, cut_line
from reduc.core.routing.messages import Locale, barrier_message
from reduc.core.routing.narrative import (
    BLOCKED_PENALTY,
    NearbyPoi,
    RouteNarrative,
    TraversedEdge,
    describe_route,
)
from reduc.core.routing.pgrouting import PgrRoutingEngine

MIN_TRAVERSED_M = 0.05


class OutsideRegionError(ValueError):
    """Raised when the endpoints are not inside one active published region."""


@dataclass(frozen=True)
class BlockingBarrier:
    id: uuid.UUID
    barrier_class: str
    location: Coord
    message: str


@dataclass(frozen=True)
class ShortestReference:
    distance_m: float
    blocking_barriers: tuple[BlockingBarrier, ...]


@dataclass(frozen=True)
class RoutePlan:
    """Result of one route request, accessible or not."""

    region: str
    map_version: int
    routes: tuple[RouteNarrative, ...]
    shortest: ShortestReference | None
    fallback: RouteNarrative | None
    relaxed_constraints: tuple[str, ...]


def traverse(
    path: RoutePath,
    edges: dict[int, EdgeRecord],
    origin_fraction: float,
    destination_fraction: float,
    profile: MobilityProfile,
) -> tuple[TraversedEdge, ...]:
    """Orient each edge along the direction of travel and trim the first and last ones."""
    records = [edges[edge_id] for edge_id in path.edge_ids]
    count = len(records)
    traversed: list[TraversedEdge] = []
    for index, record in enumerate(records):
        if count == 1:
            forward = origin_fraction <= destination_fraction
            start, end = sorted((origin_fraction, destination_fraction))
        else:
            if index < count - 1:
                following = records[index + 1]
                forward = record.target in (following.source, following.target)
            else:
                previous = records[index - 1]
                forward = record.source in (previous.source, previous.target)
            start, end = 0.0, 1.0
            if index == 0:
                start, end = (origin_fraction, 1.0) if forward else (0.0, origin_fraction)
            elif index == count - 1:
                start, end = (0.0, destination_fraction) if forward else (destination_fraction, 1.0)
        coords = cut_line(record.coords, start, end)
        if not forward:
            coords = tuple(reversed(coords))
        attributes = record.cost_input
        cost = edge_cost(profile, attributes, reverse=not forward)
        blocked = cost == BLOCKED_COST
        penalty = BLOCKED_PENALTY if blocked else cost / max(attributes.length_m, 1e-9) - 1.0
        traversed.append(
            TraversedEdge(
                edge_id=record.id,
                coords=coords,
                length_m=attributes.length_m * (end - start),
                kind=attributes.kind,
                slope_pct=attributes.max_slope_pct if forward else -attributes.max_slope_pct,
                width_m=attributes.width_m,
                surface_class=attributes.surface_class,
                curb_ramp=attributes.curb_ramp_end if forward else attributes.curb_ramp_start,
                sidewalk_missing=attributes.sidewalk_missing,
                verified=attributes.verified,
                penalty=penalty,
                blocked=blocked,
            )
        )
    return tuple(traversed)


class RouteService:
    """Compute and describe routes over the published map of the matching region."""

    def __init__(self, session: Session, engine: RoutingEngine | None = None) -> None:
        self.session = session
        self.engine: RoutingEngine = engine or PgrRoutingEngine(session)

    def plan(
        self,
        origin: Coordinate,
        destination: Coordinate,
        profile: MobilityProfile,
        *,
        alternatives: int = 0,
        include_shortest: bool = False,
        locale: Locale = "es",
    ) -> RoutePlan:
        """Raise OutsideRegionError or NoNearbyPathError; otherwise always return a plan."""
        origin_xy, destination_xy = (origin.lon, origin.lat), (destination.lon, destination.lat)
        region = find_region_for_points(self.session, origin_xy, destination_xy)
        if region is None:
            raise OutsideRegionError("Origin and destination are not inside one active region")
        result = self.engine.route(
            region.map_version_id,
            origin,
            destination,
            profile,
            alternatives=alternatives,
            include_shortest=include_shortest,
        )
        paths = [*result.routes]
        if result.fallback_route is not None:
            paths.append(result.fallback_route)
        if result.shortest is not None:
            paths.append(result.shortest)
        edges = load_edges(self.session, [edge_id for path in paths for edge_id in path.edge_ids])
        pois = tuple(NearbyPoi(poi.name, poi.location) for poi in load_region_pois(self.session, region.id))
        fractions: dict[tuple[int, bool], float] = {}

        def fraction(edge_id: int, is_origin: bool) -> float:
            key = (edge_id, is_origin)
            if key not in fractions:
                point = origin_xy if is_origin else destination_xy
                fractions[key] = locate_fraction(self.session, edge_id, point)
            return fractions[key]

        def walk(path: RoutePath) -> tuple[TraversedEdge, ...]:
            if not path.edge_ids:
                return ()
            first, last = path.edge_ids[0], path.edge_ids[-1]
            walked = traverse(path, edges, fraction(first, True), fraction(last, False), profile)
            # Snapping exactly onto a node leaves zero-length stubs that would only add noise.
            return tuple(edge for edge in walked if edge.length_m >= MIN_TRAVERSED_M)

        def narrate(path: RoutePath) -> RouteNarrative:
            narrative = describe_route(walk(path), profile, locale, pois)
            if narrative.coords:
                return narrative
            return RouteNarrative(
                coords=(origin_xy, destination_xy),
                distance_m=0.0,
                duration_s=0,
                accessibility_score=100,
                verified_pct=100.0,
                max_slope_pct=0.0,
                caution_segments=0,
                segments=(),
                instructions=(),
            )

        shortest: ShortestReference | None = None
        if result.shortest is not None:
            barriers = load_barriers(self.session, result.blocking_barrier_ids)
            shortest = ShortestReference(
                distance_m=round(sum(edge.length_m for edge in walk(result.shortest)), 1),
                blocking_barriers=tuple(self._blocking(barrier, locale) for barrier in barriers),
            )
        return RoutePlan(
            region=region.slug,
            map_version=region.map_version_number,
            routes=tuple(narrate(path) for path in result.routes),
            shortest=shortest,
            fallback=narrate(result.fallback_route) if result.fallback_route is not None else None,
            relaxed_constraints=result.relaxed_constraints,
        )

    @staticmethod
    def _blocking(barrier: BarrierRecord, locale: Locale) -> BlockingBarrier:
        return BlockingBarrier(
            id=barrier.id,
            barrier_class=barrier.barrier_class,
            location=barrier.location,
            message=barrier_message(locale, barrier.barrier_class, barrier.attributes),
        )
