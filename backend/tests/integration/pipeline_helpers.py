"""Throwaway regions for pipeline tests, committed for real and removed afterwards."""

import uuid
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from geoalchemy2.elements import WKTElement
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from tests.fixtures.osm.sample import sample_data

from reduc.core.db.models import Region
from reduc.core.pipeline.context import PipelineDeps
from reduc.core.providers.elevation.base import ConstantElevation

#: Covers the synthetic OSM extract of `tests/fixtures/osm/sample.py`, which sits at (0, 0).
SAMPLE_BOUNDARY = "MULTIPOLYGON(((-0.0005 -0.001,0.004 -0.001,0.004 0.004,-0.0005 0.004,-0.0005 -0.001)))"

_PURGE = (
    "DELETE FROM pipeline_stage_run WHERE pipeline_run_id IN (SELECT id FROM pipeline_run WHERE region_id = :id)",
    "DELETE FROM pipeline_run WHERE region_id = :id",
    "UPDATE region SET published_version_id = NULL WHERE id = :id",
    "UPDATE barrier SET representative_detection_id = NULL "
    "WHERE map_version_id IN (SELECT id FROM map_version WHERE region_id = :id)",
    "DELETE FROM detection WHERE image_id IN (SELECT id FROM image WHERE region_id = :id)",
    "DELETE FROM verification WHERE barrier_id IN (SELECT b.id FROM barrier b "
    "JOIN map_version v ON v.id = b.map_version_id WHERE v.region_id = :id)",
    "DELETE FROM barrier WHERE map_version_id IN (SELECT id FROM map_version WHERE region_id = :id)",
    "DELETE FROM edge_accessibility WHERE edge_id IN (SELECT e.id FROM edge e "
    "JOIN map_version v ON v.id = e.map_version_id WHERE v.region_id = :id)",
    "DELETE FROM edge WHERE map_version_id IN (SELECT id FROM map_version WHERE region_id = :id)",
    "DELETE FROM node WHERE map_version_id IN (SELECT id FROM map_version WHERE region_id = :id)",
    "DELETE FROM map_version WHERE region_id = :id",
    "DELETE FROM image WHERE region_id = :id",
    "DELETE FROM poi WHERE region_id = :id",
    "DELETE FROM region WHERE id = :id",
    "REFRESH MATERIALIZED VIEW routing_edge",
)


def purge_region(engine: Engine, region_id: uuid.UUID) -> None:
    with Session(engine) as session:
        for statement in _PURGE:
            session.execute(text(statement), {"id": region_id})
        session.commit()


@contextmanager
def temporary_region(
    engine: Engine, config: dict[str, Any] | None = None, boundary: str = SAMPLE_BOUNDARY, utm_srid: int = 32631
) -> Generator[uuid.UUID]:
    """An inactive region with no published version, so it never shows up in public endpoints."""
    with Session(engine) as session:
        region = Region(
            slug=f"prueba-{uuid.uuid4().hex[:10]}",
            name="Región de prueba del pipeline",
            boundary=WKTElement(boundary, srid=4326),
            utm_srid=utm_srid,
            config=config or {"osm": {"source": "overpass", "buffer_m": 100}},
            is_active=False,
        )
        session.add(region)
        session.commit()
        region_id = region.id
    try:
        yield region_id
    finally:
        purge_region(engine, region_id)


def factory_for(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def sample_deps() -> PipelineDeps:
    """Fakes: the synthetic OSM extract and flat terrain. No network."""
    return PipelineDeps(
        osm_source=lambda _region, _bbox: sample_data(),
        elevation_source=lambda _region: ConstantElevation(10.0),
    )
