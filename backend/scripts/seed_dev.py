"""Create a deterministic 6x6 accessibility region for local development."""

from dataclasses import dataclass
from typing import Any

from geoalchemy2.elements import WKTElement
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from structlog import get_logger

from reduc.core.db.models import Barrier, Edge, EdgeAccessibility, MapVersion, Node, Poi, Region
from reduc.core.db.session import SessionLocal

GRID_SIZE = 6
ORIGIN_LON = -74.065
ORIGIN_LAT = 4.601
STEP_LON = 0.00045
STEP_LAT = 0.00045


@dataclass(frozen=True)
class SeedStats:
    """Number of entities created by the synthetic seed."""

    nodes: int
    edges: int
    barriers: int
    pois: int


def point(row: int, column: int) -> WKTElement:
    """Return a seed-only synthetic coordinate; production regions remain configurable."""
    return WKTElement(f"POINT({ORIGIN_LON + column * STEP_LON} {ORIGIN_LAT + row * STEP_LAT})", srid=4326)


def seed_dev(session: Session) -> SeedStats:
    """Replace the synthetic region atomically and return its entity counts."""
    existing = session.scalar(select(Region).where(Region.slug == "campus-piloto"))
    if existing is not None:
        session.delete(existing)
        session.flush()

    region = Region(
        slug="campus-piloto",
        name="Campus piloto sintético",
        boundary=WKTElement(
            "MULTIPOLYGON(((-74.066 4.600,-74.061 4.600,-74.061 4.604,-74.066 4.604,-74.066 4.600)))",
            srid=4326,
        ),
        utm_srid=32618,
        config={"image_sources": [], "thresholds": {"fusion_radius_m": 4.0, "snap_max_m": 8.0}},
        is_active=True,
    )
    session.add(region)
    session.flush()
    version = MapVersion(region_id=region.id, number=1, status="published", notes="Seed sintético de desarrollo")
    session.add(version)
    session.flush()
    region.published_version_id = version.id

    nodes: dict[tuple[int, int], Node] = {}
    for row in range(GRID_SIZE):
        for column in range(GRID_SIZE):
            kind = "crossing" if (row, column) == (1, 5) else "junction"
            node = Node(map_version_id=version.id, geom=point(row, column), elevation_m=2600 + row * 2, kind=kind)
            nodes[row, column] = node
    session.add_all(nodes.values())
    session.flush()

    default_attributes: dict[str, Any] = {
        "kind": "sidewalk",
        "slope": 1.0,
        "has_steps": False,
        "step_height": None,
        "ramp_start": "n/a",
        "ramp_end": "n/a",
        "status": "accessible",
        "surface_class": 0,
        "width_m": 1.5,
        "verified": True,
        "data_confidence": 1.0,
        "coverage": "imagery",
    }
    special_edges: dict[tuple[int, int, int, int], dict[str, Any]] = {
        (2, 2, 2, 3): {"kind": "steps", "slope": 0.0, "has_steps": True, "step_height": 12.0, "status": "inaccessible"},
        (4, 4, 5, 4): {"kind": "footway", "slope": 12.0, "status": "caution"},
        (1, 4, 1, 5): {"kind": "crossing", "slope": 0.0, "ramp_end": "no", "status": "inaccessible"},
        (0, 3, 0, 4): {"surface_class": 2, "status": "caution"},
        (3, 0, 4, 0): {"slope": 4.5, "status": "caution"},
        (3, 4, 3, 5): {"width_m": 1.0, "status": "caution"},
        (5, 1, 5, 2): {"verified": False, "data_confidence": 0.3, "coverage": "osm_only", "status": "unknown"},
    }

    def attributes_for(key: tuple[int, int, int, int]) -> dict[str, Any]:
        return {**default_attributes, **special_edges.get(key, {})}

    edges: dict[tuple[int, int, int, int], Edge] = {}
    for row in range(GRID_SIZE):
        for column in range(GRID_SIZE):
            neighbors = []
            if column + 1 < GRID_SIZE:
                neighbors.append((row, column + 1))
            if row + 1 < GRID_SIZE:
                neighbors.append((row + 1, column))
            for target_row, target_column in neighbors:
                key = (row, column, target_row, target_column)
                edge = Edge(
                    map_version_id=version.id,
                    source=nodes[row, column].id,
                    target=nodes[target_row, target_column].id,
                    geom=WKTElement(
                        f"LINESTRING({ORIGIN_LON + column * STEP_LON} {ORIGIN_LAT + row * STEP_LAT},"
                        f"{ORIGIN_LON + target_column * STEP_LON} {ORIGIN_LAT + target_row * STEP_LAT})",
                        srid=4326,
                    ),
                    length_m=50,
                    kind=attributes_for(key)["kind"],
                    tags={"surface": "concrete"},
                )
                edges[key] = edge
    session.add_all(edges.values())
    session.flush()

    for key, edge in edges.items():
        attributes = attributes_for(key)
        session.add(
            EdgeAccessibility(
                edge_id=edge.id,
                slope_pct=attributes["slope"],
                max_slope_pct=attributes["slope"],
                cross_slope_pct=1,
                width_m=attributes["width_m"],
                surface_class=attributes["surface_class"],
                has_steps=attributes["has_steps"],
                max_step_height_cm=attributes["step_height"],
                curb_ramp_start=attributes["ramp_start"],
                curb_ramp_end=attributes["ramp_end"],
                obstacle_level=0,
                sidewalk_missing=False,
                data_confidence=attributes["data_confidence"],
                verified=attributes["verified"],
                coverage=attributes["coverage"],
                status=attributes["status"],
            )
        )

    barrier_specs = (
        ((2, 2, 2, 3), "stairs", "critical", 12.0),
        ((4, 4, 5, 4), "steep_slope_visual", "major", 12.0),
        ((1, 4, 1, 5), "curb_no_ramp", "critical", 12.0),
    )
    for key, barrier_class, severity, height in barrier_specs:
        edge = edges[key]
        session.add(
            Barrier(
                map_version_id=version.id,
                barrier_class=barrier_class,
                severity=severity,
                geom=WKTElement(
                    f"POINT({ORIGIN_LON + (key[1] + key[3]) / 2 * STEP_LON} "
                    f"{ORIGIN_LAT + (key[0] + key[2]) / 2 * STEP_LAT})",
                    srid=4326,
                ),
                edge_id=edge.id,
                attributes=(
                    {"slope_pct": height}
                    if barrier_class == "steep_slope_visual"
                    else {"step_height_cm": height, "step_count": 6}
                    if barrier_class == "stairs"
                    else {"step_height_cm": height}
                ),
                confidence=1,
                n_observations=1,
                source="osm",
                verification_status="confirmed",
            )
        )

    for name, category, row, column in (
        ("Edificio central", "building", 0, 0),
        ("Entrada accesible", "entrance", 0, 1),
        ("Baño accesible", "toilet", 2, 2),
        ("Parqueadero accesible", "parking", 5, 5),
        ("Biblioteca", "building", 4, 1),
        ("Cafetería central", "service", 3, 3),
        ("Auditorio", "building", 0, 5),
        ("Enfermería", "service", 5, 0),
    ):
        session.add(
            Poi(
                region_id=region.id,
                name=name,
                category=category,
                geom=point(row, column),
                accessible_entrance=True,
            )
        )

    session.flush()
    return SeedStats(nodes=len(nodes), edges=len(edges), barriers=len(barrier_specs), pois=8)


def main() -> None:
    """Run the seed using REDUC_DATABASE_URL and commit atomically."""
    with SessionLocal() as session:
        stats = seed_dev(session)
        session.execute(text("REFRESH MATERIALIZED VIEW routing_edge"))
        session.commit()
        get_logger().info("seed_completed", region="campus-piloto", **stats.__dict__)


if __name__ == "__main__":
    main()
