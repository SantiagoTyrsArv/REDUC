"""Mandatory routing behavior over the synthetic seed on real pgRouting."""

import os
from collections.abc import Generator
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from geoalchemy2.elements import WKTElement
from scripts.seed_dev import ORIGIN_LAT, ORIGIN_LON, STEP_LAT, STEP_LON, seed_dev
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from testcontainers.community.postgres import PostgresContainer

from reduc.core.db.models import Barrier, Edge, EdgeAccessibility, MapVersion, Node
from reduc.core.domain.profile import PROFILE_PRESETS
from reduc.core.routing.engine import Coordinate
from reduc.core.routing.pgrouting import PgrRoutingEngine
from reduc.settings import get_settings

BACKEND_ROOT = Path(__file__).parents[2]
DATABASE_IMAGE = "pgrouting/pgrouting:16-3.5-3.7"
PROFILE = PROFILE_PRESETS["manual"]


@dataclass(frozen=True)
class IsolatedCase:
    edge_id: int
    origin: Coordinate
    destination: Coordinate


@pytest.fixture(scope="module")
def seeded_engine() -> Generator[Engine]:
    """Provide one migrated and seeded database for all routing cases."""
    with PostgresContainer(DATABASE_IMAGE, username="reduc", password="reduc", dbname="reduc") as postgres:
        url = postgres.get_connection_url().replace("postgresql+psycopg2://", "postgresql+psycopg://")
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


@pytest.fixture
def session(seeded_engine: Engine) -> Generator[Session]:
    """Roll back case-specific graph changes and materialized-view refreshes."""
    with Session(seeded_engine) as database_session:
        yield database_session
        database_session.rollback()


def _isolated_edge(session: Session, *, critical_barrier: bool = False, **accessibility: Any) -> IsolatedCase:
    """Add a two-node edge to the seed so each hard constraint can be tested without a detour."""
    version = session.scalar(select(MapVersion).where(MapVersion.status == "published"))
    assert version is not None
    origin = Coordinate(-74.0635, 4.6038)
    destination = Coordinate(-74.0625, 4.6038)
    source = Node(
        map_version_id=version.id,
        geom=WKTElement(f"POINT({origin.lon} {origin.lat})", srid=4326),
        kind="junction",
    )
    target = Node(
        map_version_id=version.id,
        geom=WKTElement(f"POINT({destination.lon} {destination.lat})", srid=4326),
        kind="junction",
    )
    session.add_all([source, target])
    session.flush()
    edge = Edge(
        map_version_id=version.id,
        source=source.id,
        target=target.id,
        geom=WKTElement(f"LINESTRING({origin.lon} {origin.lat},{destination.lon} {destination.lat})", srid=4326),
        length_m=100.0,
        kind=accessibility.pop("kind", "sidewalk"),
    )
    session.add(edge)
    session.flush()
    max_slope_pct = accessibility.pop("max_slope_pct", 0.0)
    attributes = {
        "slope_pct": max_slope_pct,
        "max_slope_pct": max_slope_pct,
        "cross_slope_pct": 1.0,
        "width_m": 1.5,
        "surface_class": 0,
        "has_steps": False,
        "max_step_height_cm": None,
        "curb_ramp_start": "n/a",
        "curb_ramp_end": "n/a",
        "obstacle_level": 0,
        "sidewalk_missing": False,
        "data_confidence": 1.0,
        "verified": True,
        "coverage": "imagery",
        "status": "accessible",
        **accessibility,
    }
    session.add(EdgeAccessibility(edge_id=edge.id, **attributes))
    if critical_barrier:
        session.add(
            Barrier(
                map_version_id=version.id,
                barrier_class="stairs",
                severity="critical",
                geom=WKTElement(f"POINT({origin.lon} {origin.lat})", srid=4326),
                edge_id=edge.id,
                attributes={},
                confidence=1.0,
                n_observations=1,
                source="manual",
                verification_status="confirmed",
            )
        )
    session.flush()
    session.execute(text("REFRESH MATERIALIZED VIEW routing_edge"))
    return IsolatedCase(edge_id=edge.id, origin=origin, destination=destination)


def test_staircase_is_avoided_and_shortest_exposes_its_barrier(session: Session) -> None:
    """The accessible route detours around stairs while the unrestricted reference identifies them."""
    steps_id = session.scalar(select(Edge.id).where(Edge.kind == "steps"))
    barrier_id = session.scalar(select(Barrier.id).where(Barrier.edge_id == steps_id))
    origin = Coordinate(ORIGIN_LON + STEP_LON, ORIGIN_LAT + 2 * STEP_LAT)
    destination = Coordinate(ORIGIN_LON + 4 * STEP_LON, ORIGIN_LAT + 2 * STEP_LAT)

    result = PgrRoutingEngine(session).route(
        _published_version(session), origin, destination, PROFILE, alternatives=2, include_shortest=True
    )

    assert result.routes
    assert all(steps_id not in route.edge_ids for route in result.routes)
    assert result.shortest is not None
    assert steps_id in result.shortest.edge_ids
    assert barrier_id in result.blocking_barrier_ids


def test_slope_is_traversable_in_only_one_direction_until_fallback(session: Session) -> None:
    """Eight percent is uphill in one direction, legal downhill in the other, and only relaxed on request."""
    case = _isolated_edge(session, max_slope_pct=8.0)
    engine = PgrRoutingEngine(session)
    version = _published_version(session)

    uphill = engine.route(version, case.origin, case.destination, PROFILE)
    downhill = engine.route(version, case.destination, case.origin, PROFILE)

    assert not uphill.routes
    assert uphill.fallback_route is not None
    assert uphill.fallback_route.edge_ids == (case.edge_id,)
    assert uphill.relaxed_constraints[-1] == "slope"
    assert downhill.routes
    assert downhill.routes[0].edge_ids == (case.edge_id,)
    assert downhill.fallback_route is None


def test_crossing_without_ramp_is_not_silently_relaxed(session: Session) -> None:
    """A missing ramp blocks the arrival direction and is never enabled by unknown-ramp fallback."""
    case = _isolated_edge(session, kind="crossing", curb_ramp_end="no")
    engine = PgrRoutingEngine(session)
    version = _published_version(session)

    forward = engine.route(version, case.origin, case.destination, PROFILE)
    reverse = engine.route(version, case.destination, case.origin, PROFILE)

    assert not forward.routes
    assert forward.fallback_route is None
    assert reverse.routes
    assert reverse.routes[0].edge_ids == (case.edge_id,)


def test_unknown_curb_ramp_waits_for_its_own_fallback_step(session: Session) -> None:
    """Relaxing unverified edges alone does not bypass the separate unknown-ramp restriction."""
    case = _isolated_edge(session, kind="crossing", curb_ramp_end="unknown")
    conservative = replace(PROFILE, avoid_unverified=True)

    result = PgrRoutingEngine(session).route(_published_version(session), case.origin, case.destination, conservative)

    assert not result.routes
    assert result.fallback_route is not None
    assert result.fallback_route.edge_ids == (case.edge_id,)
    assert result.relaxed_constraints == ("avoid_unverified", "curb_ramp_unknown")


def test_insufficient_width_is_never_relaxed(session: Session) -> None:
    """The documented fallback does not weaken the minimum clear width."""
    case = _isolated_edge(session, width_m=0.5)

    result = PgrRoutingEngine(session).route(_published_version(session), case.origin, case.destination, PROFILE)

    assert not result.routes
    assert result.fallback_route is None


def test_no_accessible_route_returns_surface_fallback(session: Session) -> None:
    """Surface class is relaxed by one only after the original profile has no route."""
    case = _isolated_edge(session, surface_class=3)

    result = PgrRoutingEngine(session).route(_published_version(session), case.origin, case.destination, PROFILE)

    assert not result.routes
    assert result.fallback_route is not None
    assert result.fallback_route.edge_ids == (case.edge_id,)
    assert result.relaxed_constraints == ("avoid_unverified", "curb_ramp_unknown", "surface_class")


def test_confirmed_critical_barrier_is_never_relaxed(session: Session) -> None:
    """No fallback step can turn a confirmed critical barrier into an accessible route."""
    case = _isolated_edge(session, has_steps=True, max_step_height_cm=12.0, critical_barrier=True)

    result = PgrRoutingEngine(session).route(_published_version(session), case.origin, case.destination, PROFILE)

    assert not result.routes
    assert result.fallback_route is None


def _published_version(session: Session) -> Any:
    version_id = session.scalar(select(MapVersion.id).where(MapVersion.status == "published"))
    assert version_id is not None
    return version_id
