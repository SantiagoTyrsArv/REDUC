"""Admin endpoints for pipeline runs (docs/04 §3)."""

import uuid
from collections.abc import Callable
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from reduc.api.auth import AdminUser, SessionDep
from reduc.api.deps import get_enqueue_run
from reduc.api.errors import ApiError
from reduc.api.schemas.admin import PipelineRunOut, PipelineRunRequest, StageRunOut
from reduc.api.schemas.public import ErrorOut
from reduc.core.db.models import MapVersion, PipelineRun, Region
from reduc.core.pipeline.jobs import PipelineRequestError, cancel_run, create_run, stage_runs

router = APIRouter(prefix="/v1/admin", tags=["admin"])
EnqueueDep = Annotated[Callable[[uuid.UUID], None], Depends(get_enqueue_run)]
ERRORS: dict[int | str, dict[str, type[ErrorOut]]] = {
    401: {"model": ErrorOut},
    403: {"model": ErrorOut},
    404: {"model": ErrorOut},
}
log = structlog.get_logger("reduc.api.pipeline")


def not_found(what: str) -> ApiError:
    return ApiError("not_found", "Recurso no encontrado", f"{what} no existe", 404)


def run_out(session: Session, run: PipelineRun) -> PipelineRunOut:
    number = session.scalar(select(MapVersion.number).where(MapVersion.id == run.map_version_id))
    return PipelineRunOut(
        id=run.id,
        region_id=run.region_id,
        map_version_id=run.map_version_id,
        map_version_number=int(number or 0),
        status=run.status,
        stages=[
            StageRunOut(
                stage=row.stage,
                status=row.status,
                progress=row.progress,
                stats=row.stats or {},
                error=row.error,
                started_at=row.started_at,
                finished_at=row.finished_at,
            )
            for row in stage_runs(session, run.id)
        ],
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
    )


@router.post(
    "/regions/{region_id}/pipeline-runs",
    response_model=PipelineRunOut,
    status_code=202,
    responses={**ERRORS, 409: {"model": ErrorOut}, 422: {"model": ErrorOut}},
)
def start_pipeline_run(
    region_id: uuid.UUID, body: PipelineRunRequest, session: SessionDep, user: AdminUser, enqueue: EnqueueDep
) -> PipelineRunOut:
    """Queue the requested stages on a new draft version, or on an existing draft."""
    if session.get(Region, region_id) is None:
        raise not_found("La región")
    try:
        run = create_run(session, region_id, body.stages, body.map_version, requested_by=user.id)
    except (PipelineRequestError, ValueError) as error:
        session.rollback()
        conflict = "en curso" in str(error)
        raise ApiError(
            "conflict" if conflict else "validation_error",
            "No se puede iniciar la ejecución",
            str(error) if isinstance(error, PipelineRequestError) else "Versión de mapa no válida",
            409 if conflict else 422,
        ) from error
    session.commit()
    try:
        enqueue(run.id)
    except Exception as error:
        # The queue is down: do not leave a run that nobody will ever pick up.
        log.exception("pipeline_enqueue_failed", run_id=str(run.id))
        cancel_run(session, run.id)
        run.status = "failed"
        session.commit()
        raise ApiError("queue_unavailable", "Cola no disponible", "No se pudo encolar la ejecución", 503) from error
    return run_out(session, run)


@router.get("/regions/{region_id}/pipeline-runs", response_model=list[PipelineRunOut], responses=ERRORS)
def list_pipeline_runs(
    region_id: uuid.UUID, session: SessionDep, _user: AdminUser, limit: Annotated[int, Query(ge=1, le=50)] = 20
) -> list[PipelineRunOut]:
    """Most recent runs of a region."""
    runs = session.scalars(
        select(PipelineRun)
        .where(PipelineRun.region_id == region_id)
        .order_by(PipelineRun.created_at.desc())
        .limit(limit)
    ).all()
    return [run_out(session, run) for run in runs]


@router.get("/pipeline-runs/{run_id}", response_model=PipelineRunOut, responses=ERRORS)
def get_pipeline_run(run_id: uuid.UUID, session: SessionDep, _user: AdminUser) -> PipelineRunOut:
    run = session.get(PipelineRun, run_id)
    if run is None:
        raise not_found("La ejecución")
    return run_out(session, run)


@router.post("/pipeline-runs/{run_id}/cancel", response_model=PipelineRunOut, responses=ERRORS)
def cancel_pipeline_run(run_id: uuid.UUID, session: SessionDep, _user: AdminUser) -> PipelineRunOut:
    """Cancel a queued or running run; a finished run is returned unchanged."""
    run = cancel_run(session, run_id)
    if run is None:
        raise not_found("La ejecución")
    session.commit()
    return run_out(session, run)
