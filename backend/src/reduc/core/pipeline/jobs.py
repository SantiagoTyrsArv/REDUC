"""Pipeline runs: which stages exist, how a run is created, executed, resumed and cancelled.

Each stage runs in its own transaction, so a failed or cancelled stage leaves the draft as
the previous stage wrote it and the run can be resumed from that stage. Progress and the
cancellation flag travel through a second, short-lived session so that the panel sees them
while the stage transaction is still open.
"""

import uuid
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, sessionmaker

from reduc.core.db.models import MapVersion, PipelineRun, PipelineStageRun, Region
from reduc.core.pipeline.context import PipelineCancelledError, PipelineDeps, StageContext, StageStats
from reduc.core.pipeline.stages import build_routing_graph, compute_attributes, elevation, import_osm

StageFn = Callable[[StageContext], StageStats]

#: Order matters: every stage consumes what the previous ones wrote.
STAGES: dict[str, StageFn] = {
    "import_osm": import_osm.run,
    "elevation": elevation.run,
    "compute_attributes": compute_attributes.run,
    "build_routing_graph": build_routing_graph.run,
}
STAGE_ORDER: tuple[str, ...] = (
    "import_osm",
    "elevation",
    "ingest_images",
    "detect",
    "geolocate",
    "fuse",
    "compute_attributes",
    "build_routing_graph",
)
ACTIVE_STATUSES = ("queued", "running")
FINAL_STATUSES = ("succeeded", "failed", "cancelled")

log = structlog.get_logger("reduc.pipeline")


class PipelineRequestError(Exception):
    """The requested run is not possible; the message is safe to show to the administrator."""


def available_stages() -> tuple[str, ...]:
    return tuple(stage for stage in STAGE_ORDER if stage in STAGES)


def resolve_stages(requested: Sequence[str]) -> list[str]:
    """`["all"]` or a subset, returned in execution order without duplicates."""
    if not requested or list(requested) == ["all"]:
        return list(available_stages())
    unknown = [stage for stage in requested if stage not in STAGE_ORDER]
    if unknown:
        raise PipelineRequestError(f"Etapas desconocidas: {', '.join(sorted(set(unknown)))}")
    pending = [stage for stage in requested if stage not in STAGES]
    if pending:
        raise PipelineRequestError(f"Etapas aún no disponibles: {', '.join(sorted(set(pending)))}")
    return [stage for stage in STAGE_ORDER if stage in set(requested)]


def create_run(
    session: Session,
    region_id: uuid.UUID,
    stages: Sequence[str] = ("all",),
    map_version: str | uuid.UUID = "new",
    requested_by: uuid.UUID | None = None,
) -> PipelineRun:
    """Create a queued run on a new or existing draft. One active run per region at a time."""
    region = session.get(Region, region_id, with_for_update=True)
    if region is None:
        raise PipelineRequestError("La región no existe")
    selected = resolve_stages(stages)
    active = session.scalar(
        select(func.count())
        .select_from(PipelineRun)
        .where(PipelineRun.region_id == region_id, PipelineRun.status.in_(ACTIVE_STATUSES))
    )
    if active:
        raise PipelineRequestError("Ya hay una ejecución en curso para esta región")

    if map_version == "new":
        last = session.scalar(select(func.max(MapVersion.number)).where(MapVersion.region_id == region_id)) or 0
        version = MapVersion(region_id=region_id, number=last + 1, status="draft")
        session.add(version)
        session.flush()
    else:
        found = session.get(MapVersion, uuid.UUID(str(map_version)))
        if found is None or found.region_id != region_id:
            raise PipelineRequestError("La versión no pertenece a esta región")
        if found.status != "draft":
            raise PipelineRequestError("Solo se puede procesar una versión en borrador")
        version = found

    run = PipelineRun(
        region_id=region_id,
        map_version_id=version.id,
        requested_by=requested_by,
        status="queued",
        params={"stages": selected},
    )
    session.add(run)
    session.flush()
    session.add_all(
        PipelineStageRun(pipeline_run_id=run.id, stage=stage, status="queued", progress=0.0) for stage in selected
    )
    session.flush()
    return run


def cancel_run(session: Session, run_id: uuid.UUID) -> PipelineRun | None:
    """Mark a run as cancelled. A running stage stops at its next batch and is rolled back."""
    run = session.get(PipelineRun, run_id, with_for_update=True)
    if run is None:
        return None
    if run.status in ACTIVE_STATUSES:
        now = datetime.now(UTC)
        run.status = "cancelled"
        run.finished_at = now
        session.execute(
            update(PipelineStageRun)
            .where(PipelineStageRun.pipeline_run_id == run_id, PipelineStageRun.status == "queued")
            .values(status="cancelled", finished_at=now)
        )
        session.flush()
    return run


def stage_runs(session: Session, run_id: uuid.UUID) -> list[PipelineStageRun]:
    rows = session.scalars(select(PipelineStageRun).where(PipelineStageRun.pipeline_run_id == run_id)).all()
    return sorted(rows, key=lambda row: STAGE_ORDER.index(row.stage))


def _set_stage(factory: sessionmaker[Session], stage_id: uuid.UUID, **values: Any) -> None:
    with factory() as session:
        session.execute(update(PipelineStageRun).where(PipelineStageRun.id == stage_id).values(**values))
        session.commit()


def _set_run(factory: sessionmaker[Session], run_id: uuid.UUID, only_if_active: bool = True, **values: Any) -> None:
    with factory() as session:
        statement = update(PipelineRun).where(PipelineRun.id == run_id)
        if only_if_active:
            # Never overwrite a cancellation requested while the stage was running.
            statement = statement.where(PipelineRun.status.in_(ACTIVE_STATUSES))
        session.execute(statement.values(**values))
        session.commit()


def _is_cancelled(factory: sessionmaker[Session], run_id: uuid.UUID) -> bool:
    with factory() as session:
        return session.scalar(select(PipelineRun.status).where(PipelineRun.id == run_id)) == "cancelled"


def execute_run(factory: sessionmaker[Session], run_id: uuid.UUID, deps: PipelineDeps) -> str:
    """Run the queued stages of a run in order and return its final status."""
    with factory() as session:
        run = session.get(PipelineRun, run_id)
        if run is None:
            raise PipelineRequestError("La ejecución no existe")
        if run.status != "queued":
            # Delivered twice by the queue, or cancelled before a worker picked it up.
            return run.status
        region_id, version_id = run.region_id, run.map_version_id
        stages = [(row.id, row.stage) for row in stage_runs(session, run_id) if row.status == "queued"]
    _set_run(factory, run_id, status="running", started_at=datetime.now(UTC))

    final = "succeeded"
    for stage_id, stage in stages:
        if _is_cancelled(factory, run_id):
            final = "cancelled"
            break
        _set_stage(factory, stage_id, status="running", started_at=datetime.now(UTC), progress=0.0, error=None)
        last_reported = -1.0

        def report(fraction: float, stage_id: uuid.UUID = stage_id) -> None:
            nonlocal last_reported
            # One write per percent at most; a stage may call this thousands of times.
            if fraction - last_reported >= 0.01 or fraction >= 1.0:
                last_reported = fraction
                _set_stage(factory, stage_id, progress=round(fraction, 4))

        try:
            with factory() as session:
                region = session.get(Region, region_id)
                assert region is not None
                ctx = StageContext(
                    session=session,
                    region=region,
                    map_version_id=version_id,
                    deps=deps,
                    report=report,
                    is_cancelled=lambda: _is_cancelled(factory, run_id),
                )
                stats = STAGES[stage](ctx)
                session.commit()
        except PipelineCancelledError:
            _set_stage(factory, stage_id, status="cancelled", finished_at=datetime.now(UTC))
            final = "cancelled"
            break
        except Exception as error:
            log.exception("pipeline_stage_failed", run_id=str(run_id), stage=stage)
            # Only the exception type and message are stored; never a traceback with local values.
            message = f"{type(error).__name__}: {error}"[:500]
            _set_stage(factory, stage_id, status="failed", finished_at=datetime.now(UTC), error=message)
            final = "failed"
            break
        _set_stage(factory, stage_id, status="succeeded", progress=1.0, stats=stats, finished_at=datetime.now(UTC))
        log.info("pipeline_stage_succeeded", run_id=str(run_id), stage=stage)

    now = datetime.now(UTC)
    if final != "succeeded":
        with factory() as session:
            session.execute(
                update(PipelineStageRun)
                .where(PipelineStageRun.pipeline_run_id == run_id, PipelineStageRun.status == "queued")
                .values(status="cancelled", finished_at=now)
            )
            session.commit()
    _set_run(factory, run_id, only_if_active=final != "cancelled", status=final, finished_at=now)
    return final
