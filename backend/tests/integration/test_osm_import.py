"""Writing an imported OSM graph to PostGIS (T-20)."""

import uuid
from pathlib import Path

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session
from tests.fixtures.osm.sample import EXPECTED_EDGES, EXPECTED_KINDS, EXPECTED_NODES

from reduc.core.db.models import Barrier, Edge, MapVersion, Node, Region
from reduc.core.db.repositories.graph import VersionNotDraftError, replace_graph
from reduc.core.providers.osm.graph import build_graph
from reduc.core.providers.osm.readers import read_osm_file

FIXTURE = Path(__file__).parents[1] / "fixtures" / "osm" / "sample.osm.pbf"


def draft_version(session: Session) -> uuid.UUID:
    region = session.scalars(select(Region)).first()
    assert region is not None
    version = MapVersion(region_id=region.id, number=99, status="draft")
    session.add(version)
    session.flush()
    return version.id


def test_pbf_import_writes_expected_graph(db_session: Session) -> None:
    version_id = draft_version(db_session)

    counts = replace_graph(db_session, version_id, build_graph(read_osm_file(FIXTURE)))

    assert (counts.nodes, counts.edges) == (EXPECTED_NODES, EXPECTED_EDGES)
    kinds = dict(
        db_session.execute(
            select(Edge.kind, func.count()).where(Edge.map_version_id == version_id).group_by(Edge.kind)
        ).all()
    )
    assert kinds == EXPECTED_KINDS
    # Every edge starts and ends exactly on its nodes and its stored length matches the geometry.
    mismatches = db_session.execute(
        text(
            """
            SELECT count(*) FROM edge e
            JOIN node s ON s.id = e.source JOIN node t ON t.id = e.target
            WHERE e.map_version_id = :version
              AND (NOT ST_Equals(ST_StartPoint(e.geom), s.geom)
                   OR NOT ST_Equals(ST_EndPoint(e.geom), t.geom)
                   OR abs(ST_Length(e.geom::geography) - e.length_m) > 0.5
                   OR e.length_m > 50.0)
            """
        ),
        {"version": version_id},
    ).scalar_one()
    assert mismatches == 0
    # pgRouting sees a single connected component.
    components = db_session.execute(
        text(
            """
            SELECT count(DISTINCT component) FROM pgr_connectedComponents(
                format('SELECT id, source, target, length_m::float8 AS cost, length_m::float8 AS reverse_cost
                        FROM edge WHERE map_version_id = %L', CAST(:version AS text)))
            """
        ),
        {"version": str(version_id)},
    ).scalar_one()
    assert components == 1


def test_import_is_idempotent_and_keeps_barriers(db_session: Session) -> None:
    version_id = draft_version(db_session)
    draft = build_graph(read_osm_file(FIXTURE))
    replace_graph(db_session, version_id, draft)
    edge_id = db_session.scalars(select(Edge.id).where(Edge.map_version_id == version_id)).first()
    barrier = Barrier(
        map_version_id=version_id,
        barrier_class="stairs",
        severity="critical",
        geom="SRID=4326;POINT(0.00108 0.00005)",
        edge_id=edge_id,
        confidence=0.9,
        n_observations=1,
        source="vision",
        verification_status="unverified",
    )
    db_session.add(barrier)
    db_session.flush()

    replace_graph(db_session, version_id, draft)

    assert (
        db_session.scalar(select(func.count()).select_from(Node).where(Node.map_version_id == version_id))
        == EXPECTED_NODES
    )
    assert (
        db_session.scalar(select(func.count()).select_from(Edge).where(Edge.map_version_id == version_id))
        == EXPECTED_EDGES
    )
    db_session.refresh(barrier)
    # The barrier is kept for re-association, detached from the edge that no longer exists.
    assert barrier.edge_id is None


def test_published_versions_cannot_be_rewritten(db_session: Session) -> None:
    published = db_session.scalars(select(MapVersion).where(MapVersion.status == "published")).first()
    assert published is not None

    with pytest.raises(VersionNotDraftError):
        replace_graph(db_session, published.id, build_graph(read_osm_file(FIXTURE)))
    assert db_session.scalar(select(func.count()).select_from(Edge).where(Edge.map_version_id == published.id)) == 60
