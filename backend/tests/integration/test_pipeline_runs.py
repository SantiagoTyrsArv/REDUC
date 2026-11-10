"""Pipeline orchestration: runs, stages, idempotency, failure and cancellation (T-22)."""

import uuid
from collections.abc import Sequence

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from tests.fixtures.osm.sample import EXPECTED_EDGES, EXPECTED_NODES, sample_data
from tests.integration.admin_helpers import admin_client, bearer, temporary_user
from tests.integration.pipeline_helpers import factory_for, sample_deps, temporary_region

from reduc.api.deps import get_enqueue_run
from reduc.core.db.models import Edge, EdgeAccessibility, MapVersion, PipelineRun
from reduc.core.pipeline.context import PipelineDeps
from reduc.core.pipeline.jobs import (
    PipelineRequestError,
    available_stages,
    cancel_run,
    create_run,
    execute_run,
    resolve_stages,
    stage_runs,
)
from reduc.core.providers.elevation.base import ConstantElevation

LonLat = tuple[float, float]


def new_run(engine: Engine, region_id: uuid.UUID, stages: Sequence[str] = ("all",), version: str = "new") -> uuid.UUID:
    with Session(engine) as session:
        run = create_run(session, region_id, stages, version)
        session.commit()
        return run.id


def statuses(engine: Engine, run_id: uuid.UUID) -> tuple[str, dict[str, str]]:
    with Session(engine) as session:
        run = session.get(PipelineRun, run_id)
        assert run is not None
        return run.status, {row.stage: row.status for row in stage_runs(session, run_id)}


def test_full_run_builds_a_routable_draft(shared_engine: Engine) -> None:
    with temporary_region(shared_engine) as region_id:
        run_id = new_run(shared_engine, region_id)

        final = execute_run(factory_for(shared_engine), run_id, sample_deps())

        status, stages = statuses(shared_engine, run_id)
        assert (final, status) == ("succeeded", "succeeded")
        assert stages == dict.fromkeys(available_stages(), "succeeded")
        with Session(shared_engine) as session:
            run = session.get(PipelineRun, run_id)
            assert run is not None and run.started_at is not None and run.finished_at is not None
            version = session.get(MapVersion, run.map_version_id)
            assert version is not None and (version.status, version.number) == ("draft", 1)
            rows = stage_runs(session, run_id)
            assert all(row.progress == 1.0 for row in rows)
            assert rows[0].stats["edges"] == EXPECTED_EDGES and rows[0].stats["nodes"] == EXPECTED_NODES
            assert rows[-1].stats == {"routing_edges": EXPECTED_EDGES, "edges_without_attributes": 0}
            by_kind = dict(
                session.execute(
                    select(Edge.kind, func.max(EdgeAccessibility.status))
                    .join(EdgeAccessibility, EdgeAccessibility.edge_id == Edge.id)
                    .where(Edge.map_version_id == version.id)
                    .group_by(Edge.kind)
                ).all()
            )
            # Stairs block the standard profile. With OSM as the only source nothing is shown as
            # accessible: the rest stays "unknown" until imagery or a person confirms it.
            assert by_kind["steps"] == "inaccessible"
            assert by_kind["road_shoulder"] == "unknown"
            assert "accessible" not in by_kind.values()
            steps = session.execute(
                text(
                    "SELECT has_steps, max_step_height_cm FROM routing_edge "
                    "WHERE map_version_id = :version AND kind = 'steps'"
                ),
                {"version": version.id},
            ).one()
            assert steps.has_steps is True and steps.max_step_height_cm is None


def test_rerunning_stages_on_the_same_draft_is_idempotent(shared_engine: Engine) -> None:
    with temporary_region(shared_engine) as region_id:
        factory = factory_for(shared_engine)
        first = new_run(shared_engine, region_id)
        execute_run(factory, first, sample_deps())
        with Session(shared_engine) as session:
            version_id = session.scalar(select(PipelineRun.map_version_id).where(PipelineRun.id == first))

        second = new_run(shared_engine, region_id, ["build_routing_graph", "compute_attributes"], str(version_id))
        assert execute_run(factory, second, sample_deps()) == "succeeded"
        # Delivering the same job twice does nothing.
        assert execute_run(factory, second, sample_deps()) == "succeeded"

        with Session(shared_engine) as session:
            assert [row.stage for row in stage_runs(session, second)] == ["compute_attributes", "build_routing_graph"]
            edges = session.scalar(select(func.count()).select_from(Edge).where(Edge.map_version_id == version_id))
            routable = session.execute(
                text("SELECT count(*) FROM routing_edge WHERE map_version_id = :version"), {"version": version_id}
            ).scalar_one()
            versions = session.scalar(
                select(func.count()).select_from(MapVersion).where(MapVersion.region_id == region_id)
            )
        assert (edges, routable, versions) == (EXPECTED_EDGES, EXPECTED_EDGES, 1)


def test_a_failing_stage_fails_the_run_and_keeps_the_error(shared_engine: Engine) -> None:
    def broken(_region: object, _bbox: object) -> None:
        raise RuntimeError("Overpass no responde")

    with temporary_region(shared_engine) as region_id:
        run_id = new_run(shared_engine, region_id)

        final = execute_run(factory_for(shared_engine), run_id, PipelineDeps(osm_source=broken))  # type: ignore[arg-type]

        status, stages = statuses(shared_engine, run_id)
        assert (final, status) == ("failed", "failed")
        assert stages["import_osm"] == "failed"
        assert set(stages.values()) == {"failed", "cancelled"}
        with Session(shared_engine) as session:
            failed = stage_runs(session, run_id)[0]
            assert failed.error == "RuntimeError: Overpass no responde"
            # A failed run frees the region for the next attempt.
            create_run(session, region_id)
            session.rollback()


def test_cancelling_rolls_back_the_running_stage_only(shared_engine: Engine) -> None:
    with temporary_region(shared_engine) as region_id:
        run_id = new_run(shared_engine, region_id)

        class CancelsWhileSampling(ConstantElevation):
            def sample(self, points: Sequence[LonLat]) -> list[float | None]:
                with Session(shared_engine) as session:
                    cancel_run(session, run_id)
                    session.commit()
                return super().sample(points)

        deps = PipelineDeps(
            osm_source=lambda _region, _bbox: sample_data(),
            elevation_source=lambda _region: CancelsWhileSampling(5.0),
        )

        final = execute_run(factory_for(shared_engine), run_id, deps)

        status, stages = statuses(shared_engine, run_id)
        assert (final, status) == ("cancelled", "cancelled")
        assert stages["import_osm"] == "succeeded"
        assert stages["elevation"] == "cancelled"
        assert stages["build_routing_graph"] == "cancelled"
        with Session(shared_engine) as session:
            version_id = session.scalar(select(PipelineRun.map_version_id).where(PipelineRun.id == run_id))
            edges = session.scalars(select(Edge).where(Edge.map_version_id == version_id)).all()
        # The imported graph stays; the half-done elevation stage left nothing behind.
        assert len(edges) == EXPECTED_EDGES
        assert all(edge.slope_source is None for edge in edges)


def test_run_requests_are_validated(shared_engine: Engine) -> None:
    assert resolve_stages(["build_routing_graph", "import_osm"]) == ["import_osm", "build_routing_graph"]
    with pytest.raises(PipelineRequestError, match="desconocidas"):
        resolve_stages(["drop_tables"])
    with temporary_region(shared_engine) as region_id, Session(shared_engine) as session:
        published = session.scalar(select(MapVersion.id).where(MapVersion.status == "published"))
        with pytest.raises(PipelineRequestError, match="no pertenece"):
            create_run(session, region_id, map_version=str(published))
        create_run(session, region_id)
        with pytest.raises(PipelineRequestError, match="en curso"):
            create_run(session, region_id)
        with pytest.raises(PipelineRequestError, match="no existe"):
            create_run(session, uuid.uuid4())
        session.rollback()


def test_admin_endpoints_queue_report_and_cancel(shared_engine: Engine) -> None:
    queued: list[uuid.UUID] = []

    with (
        temporary_region(shared_engine) as region_id,
        temporary_user(shared_engine, "admin") as (admin, admin_id),
        temporary_user(shared_engine, "verifier") as (verifier, _),
        admin_client(
            shared_engine,
            configure=lambda app: app.dependency_overrides.__setitem__(get_enqueue_run, lambda: queued.append),
        ) as client,
    ):
        headers = bearer(client, admin)
        url = f"/v1/admin/regions/{region_id}/pipeline-runs"

        assert client.post(url, json={}).status_code == 401
        assert client.post(url, json={}, headers=bearer(client, verifier)).status_code == 403
        assert (
            client.post(f"/v1/admin/regions/{uuid.uuid4()}/pipeline-runs", json={}, headers=headers).status_code == 404
        )
        assert client.post(url, json={"stages": ["nope"]}, headers=headers).status_code == 422

        created = client.post(url, json={"stages": ["all"], "map_version": "new"}, headers=headers)
        assert created.status_code == 202, created.text
        body = created.json()
        assert body["status"] == "queued"
        assert [stage["stage"] for stage in body["stages"]] == list(available_stages())
        assert queued == [uuid.UUID(body["id"])]
        with Session(shared_engine) as session:
            assert session.scalar(select(PipelineRun.requested_by).where(PipelineRun.id == queued[0])) == admin_id

        duplicate = client.post(url, json={}, headers=headers)
        assert (duplicate.status_code, duplicate.json()["type"]) == (409, "conflict")

        # The worker picks the job up; the panel polls the run.
        execute_run(factory_for(shared_engine), queued[0], sample_deps())
        polled = client.get(f"/v1/admin/pipeline-runs/{body['id']}", headers=headers).json()
        assert polled["status"] == "succeeded"
        assert polled["map_version_number"] == 1
        assert polled["stages"][0]["stats"]["edges"] == EXPECTED_EDGES
        listed = client.get(url, headers=headers).json()
        assert [run["id"] for run in listed] == [body["id"]]

        second = client.post(url, json={"map_version": polled["map_version_id"]}, headers=headers).json()
        cancelled = client.post(f"/v1/admin/pipeline-runs/{second['id']}/cancel", headers=headers)
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelled"
        assert {stage["status"] for stage in cancelled.json()["stages"]} == {"cancelled"}
        # A cancelled run is never executed, even if the queue delivers it later.
        assert execute_run(factory_for(shared_engine), uuid.UUID(second["id"]), sample_deps()) == "cancelled"
        assert client.get(f"/v1/admin/pipeline-runs/{uuid.uuid4()}", headers=headers).status_code == 404


def test_a_dead_queue_does_not_leave_a_stuck_run(shared_engine: Engine) -> None:
    def unavailable(_run_id: uuid.UUID) -> None:
        raise ConnectionError("redis down")

    with (
        temporary_region(shared_engine) as region_id,
        temporary_user(shared_engine, "admin") as (admin, _),
        admin_client(
            shared_engine,
            configure=lambda app: app.dependency_overrides.__setitem__(get_enqueue_run, lambda: unavailable),
        ) as client,
    ):
        headers = bearer(client, admin)
        url = f"/v1/admin/regions/{region_id}/pipeline-runs"

        response = client.post(url, json={}, headers=headers)

        assert (response.status_code, response.json()["type"]) == (503, "queue_unavailable")
        assert "redis" not in response.text
        assert [run["status"] for run in client.get(url, headers=headers).json()] == ["failed"]
