"""Map version validation and publication (T-24, docs/04 §4)."""

import uuid
from typing import Any

import pytest
from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from tests.fixtures.osm.sample import NODES, WAYS
from tests.integration.admin_helpers import admin_client, bearer, temporary_user
from tests.integration.pipeline_helpers import factory_for, sample_deps, temporary_region

from reduc.core.db.models import Barrier, MapVersion, PipelineRun, Region
from reduc.core.pipeline.context import PipelineDeps
from reduc.core.pipeline.jobs import create_run, execute_run
from reduc.core.pipeline.publish import (
    PublishValidationError,
    VersionStateError,
    publish_version,
    validate_version,
)
from reduc.core.providers.osm.graph import OsmData, OsmNode, OsmWay

#: Both ends of the 160 m footway of the synthetic extract.
WEST, EAST = [0.0, 0.0], [0.00144, 0.0]


def build_draft(
    engine: Engine, region_id: uuid.UUID, stages: tuple[str, ...] = ("all",), deps: PipelineDeps | None = None
) -> uuid.UUID:
    with Session(engine) as session:
        run = create_run(session, region_id, stages)
        session.commit()
        run_id, version_id = run.id, run.map_version_id
    assert execute_run(factory_for(engine), run_id, deps or sample_deps()) == "succeeded"
    return version_id


def codes(engine: Engine, version_id: uuid.UUID) -> list[str]:
    with Session(engine) as session:
        issues = validate_version(session, version_id)
        session.rollback()
    return [issue.code for issue in issues]


def set_config(engine: Engine, region_id: uuid.UUID, config: dict[str, Any]) -> None:
    with Session(engine) as session:
        region = session.get(Region, region_id)
        assert region is not None
        region.config = config
        session.commit()


def test_publishing_archives_the_previous_version(shared_engine: Engine) -> None:
    with temporary_region(shared_engine) as region_id:
        first = build_draft(shared_engine, region_id)
        second = build_draft(shared_engine, region_id)
        with Session(shared_engine) as session:
            publish_version(session, first)
            session.commit()
            assert session.scalar(select(Region.published_version_id).where(Region.id == region_id)) == first

            published = publish_version(session, second)
            session.commit()

            assert (published.status, published.number) == ("published", 2)
            assert published.published_at is not None
            assert session.scalar(select(MapVersion.status).where(MapVersion.id == first)) == "archived"
            assert session.scalar(select(Region.published_version_id).where(Region.id == region_id)) == second
            # Published and archived versions are immutable: neither can be published again or re-processed.
            for version_id in (first, second):
                with pytest.raises(VersionStateError):
                    publish_version(session, version_id)
            with pytest.raises(Exception, match="borrador"):
                create_run(session, region_id, map_version=str(second))
            session.rollback()


def test_drafts_without_attributes_or_edges_are_rejected(shared_engine: Engine) -> None:
    with temporary_region(shared_engine) as region_id:
        only_graph = build_draft(shared_engine, region_id, ("import_osm",))
        assert codes(shared_engine, only_graph) == ["missing_accessibility"]
        with Session(shared_engine) as session:
            empty = MapVersion(region_id=region_id, number=50, status="draft")
            session.add(empty)
            session.commit()
            empty_id = empty.id
        assert codes(shared_engine, empty_id) == ["empty_graph"]
        with Session(shared_engine) as session, pytest.raises(PublishValidationError) as raised:
            publish_version(session, only_graph)
        assert [issue.code for issue in raised.value.issues] == ["missing_accessibility"]
        with Session(shared_engine) as session:
            assert session.scalar(select(MapVersion.status).where(MapVersion.id == only_graph)) == "draft"


def test_a_fragmented_graph_is_rejected(shared_engine: Engine) -> None:
    island_nodes = (OsmNode(900, 0.0030, 0.0030), OsmNode(901, 0.0033, 0.0030))
    data = OsmData(
        nodes={node.id: node for node in (*NODES, *island_nodes)},
        ways=(*WAYS, OsmWay(900, (900, 901), {"highway": "footway"})),
    )
    with temporary_region(shared_engine) as region_id:
        deps = sample_deps()
        deps.osm_source = lambda _region, _bbox: data
        version_id = build_draft(shared_engine, region_id, deps=deps)

        # 9 of 11 nodes are in the main component: below the 95 % required.
        assert codes(shared_engine, version_id) == ["disconnected_graph"]


def test_loose_critical_barriers_block_publication(shared_engine: Engine) -> None:
    with temporary_region(shared_engine) as region_id:
        version_id = build_draft(shared_engine, region_id)
        with Session(shared_engine) as session:
            barrier = Barrier(
                map_version_id=version_id,
                barrier_class="stairs",
                severity="critical",
                geom="SRID=4326;POINT(0.0005 0.0002)",
                confidence=0.9,
                n_observations=2,
                source="vision",
                verification_status="unverified",
            )
            session.add(barrier)
            session.commit()
            barrier_id = barrier.id

        assert codes(shared_engine, version_id) == ["unassociated_critical_barrier"]
        # Rejecting it (a false positive) or a low confidence stops it from blocking.
        with Session(shared_engine) as session:
            session.execute(text("UPDATE barrier SET confidence = 0.5 WHERE id = :id"), {"id": barrier_id})
            session.commit()
        assert codes(shared_engine, version_id) == []
        with Session(shared_engine) as session:
            session.execute(
                text("UPDATE barrier SET confidence = 0.95, verification_status = 'rejected' WHERE id = :id"),
                {"id": barrier_id},
            )
            session.commit()
        assert codes(shared_engine, version_id) == []


def test_regression_routes_are_checked_on_the_draft(shared_engine: Engine) -> None:
    with temporary_region(shared_engine) as region_id:
        version_id = build_draft(shared_engine, region_id)
        base = {"origin": WEST, "destination": EAST, "profile": "manual"}

        set_config(shared_engine, region_id, {"regression_routes": [{**base, "max_distance_m": 200}]})
        assert codes(shared_engine, version_id) == []

        cases = [
            {**base, "name": "corta", "max_distance_m": 50},
            {**base, "name": "punto", "must_avoid_points": [[0.0005, 0.0]]},
            {**base, "name": "fantasma", "must_avoid_barrier_ids": [str(uuid.uuid4())]},
            {"origin": WEST, "destination": [0.5, 0.5], "profile": "manual", "name": "lejos"},
            {"origin": WEST, "profile": "manual", "name": "incompleta"},
            {**base, "profile": "jetpack", "name": "perfil"},
        ]
        set_config(shared_engine, region_id, {"regression_routes": cases})
        with Session(shared_engine) as session:
            issues = validate_version(session, version_id)
            session.rollback()

        assert [issue.code for issue in issues] == [
            "regression_failed",
            "regression_failed",
            "regression_failed",
            "regression_failed",
            "regression_invalid",
            "regression_invalid",
        ]
        assert "corta: la ruta mide" in issues[0].detail
        assert "punto que debía evitar" in issues[1].detail
        assert "no existe en esta versión" in issues[2].detail


def test_must_avoid_barrier_ids_detects_a_route_through_the_barrier(shared_engine: Engine) -> None:
    with temporary_region(shared_engine) as region_id:
        version_id = build_draft(shared_engine, region_id)
        with Session(shared_engine) as session:
            edge_id = session.execute(
                text("SELECT id FROM edge WHERE map_version_id = :version AND osm_way_id = 100 ORDER BY id LIMIT 1"),
                {"version": version_id},
            ).scalar_one()
            barrier = Barrier(
                map_version_id=version_id,
                barrier_class="obstacle",
                severity="major",
                geom="SRID=4326;POINT(0.0002 0.0)",
                edge_id=edge_id,
                confidence=0.6,
                n_observations=1,
                source="vision",
                verification_status="unverified",
            )
            session.add(barrier)
            session.commit()
            barrier_id = str(barrier.id)
        case = {"origin": WEST, "destination": EAST, "profile": "manual", "must_avoid_barrier_ids": [barrier_id]}
        set_config(shared_engine, region_id, {"regression_routes": [case]})

        with Session(shared_engine) as session:
            issues = validate_version(session, version_id)
            session.rollback()

        assert [issue.code for issue in issues] == ["regression_failed"]
        assert "barrera que debía evitar" in issues[0].detail


def test_admin_endpoints_and_public_routing_after_publishing(shared_engine: Engine) -> None:
    with (
        temporary_region(shared_engine) as region_id,
        temporary_user(shared_engine, "admin") as (admin, _),
        temporary_user(shared_engine, "verifier") as (verifier, _),
        admin_client(shared_engine) as client,
    ):
        incomplete = build_draft(shared_engine, region_id, ("import_osm",))
        complete = build_draft(shared_engine, region_id)
        headers = bearer(client, admin)

        assert client.get("/v1/admin/map-versions").status_code == 401
        assert (
            client.post(f"/v1/admin/map-versions/{complete}/publish", headers=bearer(client, verifier)).status_code
            == 403
        )
        listed = client.get(f"/v1/admin/map-versions?region={region_id}", headers=headers).json()
        assert [(item["number"], item["status"], item["edges"]) for item in listed] == [
            (2, "draft", 8),
            (1, "draft", 8),
        ]

        dry = client.get(f"/v1/admin/map-versions/{incomplete}/validation", headers=headers).json()
        assert dry == {
            "publishable": False,
            "issues": [{"code": "missing_accessibility", "detail": "8 tramos no tienen atributos de accesibilidad"}],
        }
        rejected = client.post(f"/v1/admin/map-versions/{incomplete}/publish", headers=headers)
        assert rejected.status_code == 422
        assert rejected.json()["extra"]["issues"][0]["code"] == "missing_accessibility"

        published = client.post(f"/v1/admin/map-versions/{complete}/publish", headers=headers)
        assert published.status_code == 200, published.text
        assert published.json()["status"] == "published"
        again = client.post(f"/v1/admin/map-versions/{complete}/publish", headers=headers)
        assert (again.status_code, again.json()["type"]) == (409, "conflict")
        assert client.post(f"/v1/admin/map-versions/{uuid.uuid4()}/publish", headers=headers).status_code == 404

        # Users only ever see the published version, and only once the region is active.
        with Session(shared_engine) as session:
            session.execute(text("UPDATE region SET is_active = true WHERE id = :id"), {"id": region_id})
            session.commit()
            run_versions = session.scalars(select(PipelineRun.map_version_id).where(PipelineRun.region_id == region_id))
            assert set(run_versions) == {incomplete, complete}
        route = client.post("/v1/routes", json={"origin": WEST, "destination": EAST, "profile": PROFILE})
        assert route.status_code == 200, route.text
        body = route.json()
        assert body["map_version"] == 2
        assert body["routes"][0]["distance_m"] == pytest.approx(160.0, abs=3.0)


PROFILE: dict[str, Any] = {
    "device": "manual",
    "max_uphill_pct": 6.0,
    "max_downhill_pct": 8.0,
    "max_cross_slope_pct": 3.0,
    "max_step_cm": 2.0,
    "min_width_m": 0.9,
    "max_surface_class": 2,
    "require_curb_ramps": True,
    "avoid_unverified": False,
    "speed_mps": 0.9,
    "weights": {"slope": 1.0, "surface": 1.0, "uncertainty": 1.0},
}
