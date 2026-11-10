"""Shared PostGIS container, migrated and seeded once per test session."""

import os
import uuid
from collections.abc import Generator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from scripts.seed_dev import seed_dev
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from testcontainers.community.postgres import PostgresContainer

from reduc.core.db.models import MapVersion, Region
from reduc.settings import get_settings

BACKEND_ROOT = Path(__file__).parents[2]
DATABASE_IMAGE = "pgrouting/pgrouting:16-3.5-3.7"


@pytest.fixture(scope="session")
def shared_engine() -> Generator[Engine]:
    """One migrated database with the synthetic seed for read-mostly integration tests."""
    with PostgresContainer(DATABASE_IMAGE, username="reduc", password="reduc", dbname="reduc") as postgres:
        url = postgres.get_connection_url().replace("postgresql+psycopg2://", "postgresql+psycopg://")
        previous = os.environ.get("REDUC_DATABASE_URL")
        os.environ["REDUC_DATABASE_URL"] = url
        get_settings.cache_clear()
        config = Config(str(BACKEND_ROOT / "alembic.ini"))
        config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
        command.upgrade(config, "head")
        engine = create_engine(url)
        with Session(engine) as session:
            seed_dev(session)
            session.execute(text("REFRESH MATERIALIZED VIEW routing_edge"))
            session.commit()
        yield engine
        engine.dispose()
        if previous is None:
            os.environ.pop("REDUC_DATABASE_URL", None)
        else:
            os.environ["REDUC_DATABASE_URL"] = previous
        get_settings.cache_clear()


@pytest.fixture
def db_session(shared_engine: Engine) -> Generator[Session]:
    """A session with changes rolled back after each test."""
    with Session(shared_engine) as session:
        yield session
        session.rollback()


@pytest.fixture
def draft_version_id(db_session: Session) -> uuid.UUID:
    """An empty draft version of the seed region, rolled back with the session."""
    region = db_session.scalars(select(Region)).first()
    assert region is not None
    version = MapVersion(region_id=region.id, number=1000, status="draft")
    db_session.add(version)
    db_session.flush()
    return version.id
