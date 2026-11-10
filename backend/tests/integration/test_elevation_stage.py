"""Elevation stage on a synthetic tilted raster (T-21)."""

import uuid
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.unit.test_elevation import lon_at, write_plane

from reduc.core.db.models import Edge, Node, Region
from reduc.core.db.repositories.graph import replace_graph
from reduc.core.pipeline.context import PipelineCancelledError, PipelineDeps, StageContext
from reduc.core.pipeline.stages import elevation
from reduc.core.providers.elevation.base import ConstantElevation
from reduc.core.providers.elevation.raster_file import RasterFileElevation
from reduc.core.providers.osm.graph import OsmData, OsmNode, OsmWay, build_graph

LAT_A, LAT_B = 0.0003, 0.0006


def graph() -> OsmData:
    """90 m east on a 5 % plane, a level stretch north, a tagged ramp and a way leaving the raster."""
    nodes = (
        OsmNode(1, lon_at(10.0), LAT_A),
        OsmNode(2, lon_at(100.0), LAT_A),
        OsmNode(3, lon_at(100.0), LAT_B),
        OsmNode(4, lon_at(140.0), LAT_B),
        OsmNode(5, lon_at(300.0), LAT_B),
    )
    ways = (
        OsmWay(1, (1, 2), {"highway": "footway"}),
        OsmWay(2, (2, 3), {"highway": "footway"}),
        OsmWay(3, (3, 4), {"highway": "footway", "incline": "-8%"}),
        OsmWay(4, (4, 5), {"highway": "footway"}),
    )
    return OsmData(nodes={node.id: node for node in nodes}, ways=ways)


def context(session: Session, version_id: uuid.UUID, deps: PipelineDeps) -> StageContext:
    region = session.scalars(select(Region)).first()
    assert region is not None
    return StageContext(session=session, region=region, map_version_id=version_id, deps=deps)


def edges_of(session: Session, version_id: uuid.UUID, way: int) -> list[Edge]:
    return list(
        session.scalars(select(Edge).where(Edge.map_version_id == version_id, Edge.osm_way_id == way).order_by(Edge.id))
    )


def test_slopes_come_from_the_raster_and_incline_tags_win(
    db_session: Session, draft_version_id: uuid.UUID, tmp_path: Path
) -> None:
    write_plane(tmp_path / "dem.tif", slope_east_pct=5.0)
    replace_graph(db_session, draft_version_id, build_graph(graph()))
    source = RasterFileElevation(tmp_path / "dem.tif")
    progress: list[float] = []
    ctx = context(db_session, draft_version_id, PipelineDeps(elevation_source=lambda _region: source))
    ctx.report = progress.append

    stats = elevation.run(ctx)
    db_session.expire_all()

    eastward = edges_of(db_session, draft_version_id, 1)
    assert len(eastward) == 2
    for edge in eastward:
        assert edge.slope_pct == pytest.approx(5.0, abs=0.2)
        assert edge.max_slope_pct == pytest.approx(5.0, abs=0.3)
        assert edge.slope_source == "dem"
    (level,) = edges_of(db_session, draft_version_id, 2)
    assert level.slope_pct == pytest.approx(0.0, abs=0.1)
    (ramp,) = edges_of(db_session, draft_version_id, 3)
    assert (ramp.slope_pct, ramp.max_slope_pct, ramp.slope_source) == (-8.0, -8.0, "osm_incline")
    # The last stretch lies outside the raster: no slope is invented for it.
    leaving = edges_of(db_session, draft_version_id, 4)
    assert leaving[-1].slope_pct is None and leaving[-1].slope_source is None

    first = db_session.scalar(select(Node).where(Node.map_version_id == draft_version_id, Node.osm_id == 1))
    outside = db_session.scalar(select(Node).where(Node.map_version_id == draft_version_id, Node.osm_id == 5))
    assert first is not None and outside is not None
    assert first.elevation_m == pytest.approx(100.5, abs=0.05)
    assert outside.elevation_m is None
    assert stats["edges_by_slope_source"]["osm_incline"] == 1
    assert stats["edges_by_slope_source"]["none"] >= 1
    assert progress[-1] == 1.0


def test_stage_is_idempotent_and_flags_low_resolution_models(db_session: Session, draft_version_id: uuid.UUID) -> None:
    replace_graph(db_session, draft_version_id, build_graph(graph()))
    coarse = PipelineDeps(elevation_source=lambda _region: ConstantElevation(12.0, resolution_m=30.0))

    first = elevation.run(context(db_session, draft_version_id, coarse))
    second = elevation.run(context(db_session, draft_version_id, coarse))
    db_session.expire_all()

    assert first == second
    (level,) = edges_of(db_session, draft_version_id, 2)
    assert (level.slope_pct, level.slope_source) == (0.0, "dem_lowres")

    # Without an elevation model only surveyed inclines remain.
    elevation.run(context(db_session, draft_version_id, PipelineDeps()))
    db_session.expire_all()
    (level,) = edges_of(db_session, draft_version_id, 2)
    (ramp,) = edges_of(db_session, draft_version_id, 3)
    assert level.slope_pct is None
    assert ramp.slope_source == "osm_incline"


def test_cancellation_stops_between_batches(db_session: Session, draft_version_id: uuid.UUID) -> None:
    replace_graph(db_session, draft_version_id, build_graph(graph()))
    ctx = context(db_session, draft_version_id, PipelineDeps())
    ctx.is_cancelled = lambda: True

    with pytest.raises(PipelineCancelledError):
        elevation.run(ctx)
