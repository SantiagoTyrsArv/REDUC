"""Tests for the deterministic development seed."""

import os
from collections.abc import Generator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from scripts.seed_dev import seed_dev
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session
from testcontainers.community.postgres import PostgresContainer

from reduc.core.db.models import Barrier, Edge, EdgeAccessibility, Node, Poi, Region
from reduc.settings import get_settings

BACKEND_ROOT = Path(__file__).parents[2]


@pytest.fixture(scope="module")
def seed_database_url() -> Generator[str]:
    """Provide a clean migrated database for seed tests."""
    with PostgresContainer(
        "pgrouting/pgrouting:16-3.5-3.7", username="reduc", password="reduc", dbname="reduc"
    ) as postgres:
        url = postgres.get_connection_url().replace("postgresql+psycopg2://", "postgresql+psycopg://")
        config = Config(str(BACKEND_ROOT / "alembic.ini"))
        config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
        os.environ["REDUC_DATABASE_URL"] = url
        get_settings.cache_clear()
        command.upgrade(config, "head")
        yield url


def test_seed_is_complete_and_idempotent(seed_database_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """The seed has the expected graph and a second run replaces rather than duplicates it."""
    monkeypatch.setenv("REDUC_DATABASE_URL", seed_database_url)
    get_settings.cache_clear()
    engine = create_engine(seed_database_url)

    with Session(engine) as session:
        first = seed_dev(session)
        session.commit()
        second = seed_dev(session)
        session.execute(text("REFRESH MATERIALIZED VIEW routing_edge"))
        session.commit()

        assert (first.nodes, first.edges, first.barriers, first.pois) == (36, 60, 3, 8)
        assert (second.nodes, second.edges, second.barriers, second.pois) == (36, 60, 3, 8)
        assert session.scalar(select(func.count()).select_from(Node)) == 36
        assert session.scalar(select(func.count()).select_from(Edge)) == 60
        assert session.scalar(select(func.count()).select_from(EdgeAccessibility)) == 60
        assert session.scalar(select(func.count()).select_from(Barrier)) == 3
        assert session.scalar(select(func.count()).select_from(Poi)) == 8
        assert session.scalar(select(func.count()).select_from(Region)) == 1
        assert session.execute(text("SELECT count(*) FROM routing_edge")).scalar_one() == 60

        special_cases = session.execute(
            select(Edge.kind, EdgeAccessibility.max_slope_pct, EdgeAccessibility.curb_ramp_end)
            .join(EdgeAccessibility)
            .where(Edge.kind.in_(["steps", "crossing", "footway"]))
        ).all()
        assert ("steps", 0.0, "n/a") in special_cases
        assert ("footway", 12.0, "n/a") in special_cases
        assert ("crossing", 0.0, "no") in special_cases
