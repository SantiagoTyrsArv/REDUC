"""Read-side queries behind the public catalogue endpoints."""

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class RegionSummary:
    id: uuid.UUID
    slug: str
    name: str
    bbox: tuple[float, float, float, float]
    boundary: dict[str, Any]
    map_version_id: uuid.UUID
    map_version_number: int
    published_at: datetime | None
    edges: int
    coverage_pct: float
    verified_pct: float


@dataclass(frozen=True)
class PoiSummary:
    id: uuid.UUID
    name: str
    category: str
    location: tuple[float, float]
    accessible_entrance: bool


@dataclass(frozen=True)
class BarrierDetail:
    id: uuid.UUID
    barrier_class: str
    severity: str
    location: tuple[float, float]
    attributes: dict[str, Any]
    confidence: float
    n_observations: int
    source: str
    verification_status: str
    crop_key: str | None
    image_license: str | None
    attribution: str | None


def _uuid(value: Any) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


def list_active_regions(session: Session) -> list[RegionSummary]:
    """Active regions that have a published map version, with coverage statistics."""
    rows = session.execute(
        text(
            """
            SELECT r.id, r.slug, r.name, ST_AsGeoJSON(r.boundary) AS boundary,
                   ST_XMin(r.boundary) AS xmin, ST_YMin(r.boundary) AS ymin,
                   ST_XMax(r.boundary) AS xmax, ST_YMax(r.boundary) AS ymax,
                   mv.id AS map_version_id, mv.number, COALESCE(mv.published_at, mv.created_at) AS published_at,
                   COALESCE(s.edges, 0) AS edges,
                   COALESCE(s.coverage_pct, 0) AS coverage_pct,
                   COALESCE(s.verified_pct, 0) AS verified_pct
            FROM region r
            JOIN map_version mv ON mv.id = r.published_version_id
            LEFT JOIN LATERAL (
                SELECT count(*) AS edges,
                       100.0 * avg((a.coverage <> 'none')::int) AS coverage_pct,
                       100.0 * avg(a.verified::int) AS verified_pct
                FROM edge e JOIN edge_accessibility a ON a.edge_id = e.id
                WHERE e.map_version_id = mv.id
            ) s ON true
            WHERE r.is_active
            ORDER BY r.name
            """
        )
    ).mappings()
    return [
        RegionSummary(
            id=_uuid(row["id"]),
            slug=str(row["slug"]),
            name=str(row["name"]),
            bbox=(float(row["xmin"]), float(row["ymin"]), float(row["xmax"]), float(row["ymax"])),
            boundary=json.loads(row["boundary"]),
            map_version_id=_uuid(row["map_version_id"]),
            map_version_number=int(row["number"]),
            published_at=row["published_at"],
            edges=int(row["edges"]),
            coverage_pct=round(float(row["coverage_pct"]), 1),
            verified_pct=round(float(row["verified_pct"]), 1),
        )
        for row in rows
    ]


def region_exists(session: Session, slug: str) -> bool:
    """Whether an active region with this slug exists."""
    row = session.execute(text("SELECT 1 FROM region WHERE slug = :slug AND is_active"), {"slug": slug}).first()
    return row is not None


def search_pois(session: Session, slug: str, query: str | None, category: str | None, limit: int) -> list[PoiSummary]:
    """Spanish full-text search plus substring match so partial words find results while typing."""
    rows = session.execute(
        text(
            """
            SELECT p.id, p.name, p.category, ST_X(p.geom) AS lon, ST_Y(p.geom) AS lat, p.accessible_entrance
            FROM poi p JOIN region r ON r.id = p.region_id
            WHERE r.slug = :slug AND r.is_active
              AND (CAST(:category AS text) IS NULL OR p.category = CAST(:category AS text))
              AND (
                  CAST(:query AS text) IS NULL
                  OR p.search_vector @@ plainto_tsquery('spanish', CAST(:query AS text))
                  OR p.name ILIKE '%' || CAST(:query AS text) || '%'
              )
            ORDER BY p.accessible_entrance DESC, p.name
            LIMIT :limit
            """
        ),
        {"slug": slug, "query": query or None, "category": category or None, "limit": limit},
    ).mappings()
    return [
        PoiSummary(
            id=_uuid(row["id"]),
            name=str(row["name"]),
            category=str(row["category"]),
            location=(float(row["lon"]), float(row["lat"])),
            accessible_entrance=bool(row["accessible_entrance"]),
        )
        for row in rows
    ]


def get_published_barrier(session: Session, barrier_id: uuid.UUID) -> BarrierDetail | None:
    """A barrier of a published map version, with the image that best shows it."""
    row = (
        session.execute(
            text(
                """
                SELECT b.id, b.class, b.severity, ST_X(b.geom) AS lon, ST_Y(b.geom) AS lat, b.attributes,
                       b.confidence, b.n_observations, b.source, b.verification_status,
                       d.crop_key, i.license, i.attribution
                FROM barrier b
                JOIN region r ON r.published_version_id = b.map_version_id AND r.is_active
                LEFT JOIN detection d ON d.id = b.representative_detection_id
                LEFT JOIN image i ON i.id = d.image_id
                WHERE b.id = :barrier_id AND b.verification_status <> 'rejected'
                """
            ),
            {"barrier_id": barrier_id},
        )
        .mappings()
        .first()
    )
    if row is None:
        return None
    return BarrierDetail(
        id=_uuid(row["id"]),
        barrier_class=str(row["class"]),
        severity=str(row["severity"]),
        location=(float(row["lon"]), float(row["lat"])),
        attributes=dict(row["attributes"] or {}),
        confidence=float(row["confidence"]),
        n_observations=int(row["n_observations"]),
        source=str(row["source"]),
        verification_status=str(row["verification_status"]),
        crop_key=row["crop_key"],
        image_license=row["license"],
        attribution=row["attribution"],
    )
