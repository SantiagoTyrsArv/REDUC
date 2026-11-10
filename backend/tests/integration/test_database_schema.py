"""Database migrations and entity persistence tests on real PostGIS."""

from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from geoalchemy2.elements import WKTElement
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from testcontainers.community.postgres import PostgresContainer

from reduc.core.db.models import (
    AppUser,
    Barrier,
    Detection,
    Edge,
    EdgeAccessibility,
    Image,
    MapVersion,
    Node,
    PipelineRun,
    PipelineStageRun,
    Poi,
    Region,
    Verification,
)

BACKEND_ROOT = Path(__file__).parents[2]
DATABASE_IMAGE = "pgrouting/pgrouting:16-3.5-3.7"


@pytest.fixture(scope="module")
def database_url() -> Generator[str]:
    """Provide an isolated database with all required geospatial extensions."""
    with PostgresContainer(DATABASE_IMAGE, username="reduc", password="reduc", dbname="reduc") as postgres:
        yield postgres.get_connection_url().replace("postgresql+psycopg2://", "postgresql+psycopg://")


def migration_config(database_url: str) -> Config:
    """Build Alembic configuration for the isolated database."""
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return config


def test_migrations_and_all_entities(database_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Both migration directions work and every ORM entity can be persisted and read."""
    monkeypatch.setenv("REDUC_DATABASE_URL", database_url)
    from reduc.settings import get_settings

    get_settings.cache_clear()
    config = migration_config(database_url)
    command.upgrade(config, "head")
    command.downgrade(config, "base")
    command.upgrade(config, "head")

    engine = create_engine(database_url)
    with Session(engine) as session:
        region = Region(
            slug="test-region",
            name="Región de prueba",
            boundary=WKTElement("MULTIPOLYGON(((0 0,1 0,1 1,0 1,0 0)))", srid=4326),
            utm_srid=32618,
            config={},
            is_active=True,
        )
        session.add(region)
        session.flush()
        version = MapVersion(region_id=region.id, number=1, status="published")
        session.add(version)
        session.flush()
        region.published_version_id = version.id

        source = Node(map_version_id=version.id, geom=WKTElement("POINT(0.1 0.1)", srid=4326), kind="junction")
        target = Node(map_version_id=version.id, geom=WKTElement("POINT(0.2 0.2)", srid=4326), kind="crossing")
        session.add_all([source, target])
        session.flush()
        edge = Edge(
            map_version_id=version.id,
            source=source.id,
            target=target.id,
            geom=WKTElement("LINESTRING(0.1 0.1,0.2 0.2)", srid=4326),
            length_m=10,
            kind="sidewalk",
        )
        session.add(edge)
        session.flush()
        accessibility = EdgeAccessibility(
            edge_id=edge.id,
            slope_pct=1,
            max_slope_pct=1,
            surface_class=0,
            has_steps=False,
            curb_ramp_start="n/a",
            curb_ramp_end="yes",
            obstacle_level=0,
            sidewalk_missing=False,
            data_confidence=1,
            verified=True,
            coverage="imagery",
            status="accessible",
        )
        image = Image(
            region_id=region.id,
            provider="upload",
            external_id="image-1",
            captured_at=datetime.now(UTC),
            geom=WKTElement("POINT(0.1 0.1)", srid=4326),
            is_panorama=False,
            camera_height_m=1.5,
            width_px=100,
            height_px=100,
            license="own",
            privacy_blurred=True,
            status="processed",
        )
        session.add_all([accessibility, image])
        session.flush()
        barrier = Barrier(
            map_version_id=version.id,
            barrier_class="curb_no_ramp",
            severity="critical",
            geom=WKTElement("POINT(0.2 0.2)", srid=4326),
            edge_id=edge.id,
            node_id=target.id,
            confidence=1,
            n_observations=1,
            source="manual",
            verification_status="confirmed",
        )
        session.add(barrier)
        session.flush()
        detection = Detection(
            image_id=image.id,
            model_version="det-test",
            detection_class="curb_no_ramp",
            score=0.9,
            bbox=[1, 2, 3, 4],
            barrier_id=barrier.id,
        )
        user = AppUser(email="admin@example.com", password_hash="not-a-real-hash", role="admin")
        session.add_all([detection, user])
        session.flush()
        barrier.representative_detection_id = detection.id
        verification = Verification(barrier_id=barrier.id, user_id=user.id, action="confirm")
        poi = Poi(
            region_id=region.id,
            name="Biblioteca",
            category="entrance",
            geom=WKTElement("POINT(0.1 0.1)", srid=4326),
            accessible_entrance=True,
        )
        run = PipelineRun(region_id=region.id, map_version_id=version.id, requested_by=user.id, status="queued")
        session.add_all([verification, poi, run])
        session.flush()
        stage = PipelineStageRun(pipeline_run_id=run.id, stage="import_osm", status="succeeded", progress=1)
        session.add(stage)
        session.commit()

        for entity in (
            Region,
            MapVersion,
            Node,
            Edge,
            EdgeAccessibility,
            Image,
            Detection,
            Barrier,
            AppUser,
            Verification,
            Poi,
            PipelineRun,
            PipelineStageRun,
        ):
            assert len(session.query(entity).all()) == (2 if entity is Node else 1), entity.__name__

        session.execute(text("REFRESH MATERIALIZED VIEW routing_edge"))
        assert session.execute(text("SELECT count(*) FROM routing_edge")).scalar_one() == 1
