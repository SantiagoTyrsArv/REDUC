"""Read-side queries used by the routing service."""

import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from reduc.core.routing.cost import EdgeCostInput
from reduc.core.routing.geometry import Coord


@dataclass(frozen=True)
class RegionRef:
    """The region and published map version that serve one request."""

    id: uuid.UUID
    slug: str
    map_version_id: uuid.UUID
    map_version_number: int


@dataclass(frozen=True)
class EdgeRecord:
    """One routing edge with geometry in source-to-target order."""

    id: int
    source: int
    target: int
    coords: tuple[Coord, ...]
    cost_input: EdgeCostInput


@dataclass(frozen=True)
class BarrierRecord:
    id: uuid.UUID
    barrier_class: str
    location: Coord
    attributes: dict[str, Any]


@dataclass(frozen=True)
class PoiRecord:
    name: str
    location: Coord


def _as_uuid(value: Any) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


def find_region_for_points(session: Session, origin: Coord, destination: Coord) -> RegionRef | None:
    """Return the active published region containing both endpoints, if any."""
    row = (
        session.execute(
            text(
                """
                SELECT r.id, r.slug, mv.id AS map_version_id, mv.number
                FROM region r JOIN map_version mv ON mv.id = r.published_version_id
                WHERE r.is_active
                  AND ST_Covers(r.boundary, ST_SetSRID(ST_MakePoint(:olon, :olat), 4326))
                  AND ST_Covers(r.boundary, ST_SetSRID(ST_MakePoint(:dlon, :dlat), 4326))
                ORDER BY ST_Area(r.boundary) LIMIT 1
                """
            ),
            {"olon": origin[0], "olat": origin[1], "dlon": destination[0], "dlat": destination[1]},
        )
        .mappings()
        .first()
    )
    if row is None:
        return None
    return RegionRef(
        id=_as_uuid(row["id"]),
        slug=str(row["slug"]),
        map_version_id=_as_uuid(row["map_version_id"]),
        map_version_number=int(row["number"]),
    )


def load_edges(session: Session, edge_ids: Sequence[int]) -> dict[int, EdgeRecord]:
    """Load geometry and cost attributes for the edges of computed paths."""
    unique_ids = sorted(set(edge_ids))
    if not unique_ids:
        return {}
    statement = text(
        """
        SELECT re.id, re.source, re.target, re.length_m, re.kind, re.max_slope_pct, re.cross_slope_pct,
               re.width_m, re.surface_class, re.has_steps, re.max_step_height_cm, re.curb_ramp_start,
               re.curb_ramp_end, re.obstacle_level, re.sidewalk_missing, re.data_confidence, re.verified,
               ST_AsGeoJSON(re.geom) AS geojson,
               EXISTS (
                   SELECT 1 FROM barrier b
                   WHERE (b.edge_id = re.id OR b.node_id IN (re.source, re.target))
                     AND b.severity = 'critical' AND b.verification_status = 'confirmed'
               ) AS critical
        FROM routing_edge re WHERE re.id IN :edge_ids
        """
    ).bindparams(bindparam("edge_ids", expanding=True))
    records: dict[int, EdgeRecord] = {}
    for row in session.execute(statement, {"edge_ids": unique_ids}).mappings():
        coords = tuple((float(c[0]), float(c[1])) for c in json.loads(row["geojson"])["coordinates"])
        records[int(row["id"])] = EdgeRecord(
            id=int(row["id"]),
            source=int(row["source"]),
            target=int(row["target"]),
            coords=coords,
            cost_input=EdgeCostInput(
                length_m=float(row["length_m"]),
                kind=str(row["kind"]),
                max_slope_pct=float(row["max_slope_pct"]),
                cross_slope_pct=None if row["cross_slope_pct"] is None else float(row["cross_slope_pct"]),
                width_m=None if row["width_m"] is None else float(row["width_m"]),
                surface_class=int(row["surface_class"]),
                has_steps=bool(row["has_steps"]),
                max_step_height_cm=None if row["max_step_height_cm"] is None else float(row["max_step_height_cm"]),
                curb_ramp_start=str(row["curb_ramp_start"]),
                curb_ramp_end=str(row["curb_ramp_end"]),
                obstacle_level=int(row["obstacle_level"]),
                sidewalk_missing=bool(row["sidewalk_missing"]),
                data_confidence=float(row["data_confidence"]),
                verified=bool(row["verified"]),
                has_confirmed_critical_barrier=bool(row["critical"]),
            ),
        )
    return records


def locate_fraction(session: Session, edge_id: int, point: Coord) -> float:
    """Planar fraction of the closest position on an edge, matching the engine's snapping."""
    value: Any = session.execute(
        text(
            "SELECT ST_LineLocatePoint(geom, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)) "
            "FROM routing_edge WHERE id = :edge_id"
        ),
        {"lon": point[0], "lat": point[1], "edge_id": edge_id},
    ).scalar_one()
    return float(value)


def load_barriers(session: Session, barrier_ids: Sequence[uuid.UUID]) -> tuple[BarrierRecord, ...]:
    """Load the barriers that block the shortest reference route."""
    if not barrier_ids:
        return ()
    statement = text(
        "SELECT id, class, ST_X(geom) AS lon, ST_Y(geom) AS lat, attributes FROM barrier WHERE id IN :ids"
    ).bindparams(bindparam("ids", expanding=True))
    return tuple(
        BarrierRecord(
            id=_as_uuid(row["id"]),
            barrier_class=str(row["class"]),
            location=(float(row["lon"]), float(row["lat"])),
            attributes=dict(row["attributes"] or {}),
        )
        for row in session.execute(statement, {"ids": list(barrier_ids)}).mappings()
    )


def load_region_pois(session: Session, region_id: uuid.UUID, limit: int = 500) -> tuple[PoiRecord, ...]:
    """Named places used to anchor turn instructions."""
    rows = session.execute(
        text("SELECT name, ST_X(geom) AS lon, ST_Y(geom) AS lat FROM poi WHERE region_id = :region_id LIMIT :limit"),
        {"region_id": region_id, "limit": limit},
    ).mappings()
    return tuple(PoiRecord(name=str(row["name"]), location=(float(row["lon"]), float(row["lat"]))) for row in rows)
