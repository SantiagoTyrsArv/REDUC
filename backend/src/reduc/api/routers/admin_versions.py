"""Admin endpoints for map versions: list, validate and publish (docs/04 §3-4)."""

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Query
from sqlalchemy import text

from reduc.api.auth import AdminUser, SessionDep
from reduc.api.errors import ApiError
from reduc.api.schemas.admin import MapVersionAdminOut, ValidationIssueOut, ValidationOut
from reduc.api.schemas.public import ErrorOut
from reduc.core.pipeline.publish import (
    PublishValidationError,
    VersionNotFoundError,
    VersionStateError,
    publish_version,
    validate_version,
)

router = APIRouter(prefix="/v1/admin", tags=["admin"])
ERRORS: dict[int | str, dict[str, type[ErrorOut]]] = {
    401: {"model": ErrorOut},
    403: {"model": ErrorOut},
    404: {"model": ErrorOut},
}
log = structlog.get_logger("reduc.api.versions")

_VERSIONS = text(
    """
    SELECT v.id, v.region_id, v.number, v.status, v.created_at, v.published_at, v.notes,
           (SELECT count(*) FROM edge e WHERE e.map_version_id = v.id) AS edges,
           (SELECT count(*) FROM barrier b WHERE b.map_version_id = v.id
              AND b.verification_status <> 'rejected') AS barriers,
           (SELECT count(*) FROM barrier b WHERE b.map_version_id = v.id
              AND b.verification_status = 'unverified') AS unverified_barriers
    FROM map_version v
    WHERE (CAST(:region AS uuid) IS NULL OR v.region_id = :region) AND (CAST(:id AS uuid) IS NULL OR v.id = :id)
    ORDER BY v.region_id, v.number DESC
    LIMIT 200
    """
)


def _versions(session: SessionDep, region: uuid.UUID | None, version: uuid.UUID | None) -> list[MapVersionAdminOut]:
    rows = session.execute(_VERSIONS, {"region": region, "id": version}).mappings()
    return [MapVersionAdminOut(**row) for row in rows]


def _not_found() -> ApiError:
    return ApiError("not_found", "Recurso no encontrado", "La versión no existe", 404)


@router.get("/map-versions", response_model=list[MapVersionAdminOut], responses=ERRORS)
def list_map_versions(
    session: SessionDep, _user: AdminUser, region: Annotated[uuid.UUID | None, Query()] = None
) -> list[MapVersionAdminOut]:
    """Versions of one region (or of all), newest first."""
    return _versions(session, region, None)


@router.get("/map-versions/{version_id}/validation", response_model=ValidationOut, responses=ERRORS)
def validate_map_version(version_id: uuid.UUID, session: SessionDep, _user: AdminUser) -> ValidationOut:
    """Dry run of the publication checks, so the panel can show what is missing."""
    try:
        issues = validate_version(session, version_id)
    except VersionNotFoundError as error:
        raise _not_found() from error
    session.commit()
    return ValidationOut(
        publishable=not issues, issues=[ValidationIssueOut(code=issue.code, detail=issue.detail) for issue in issues]
    )


@router.post(
    "/map-versions/{version_id}/publish",
    response_model=MapVersionAdminOut,
    responses={**ERRORS, 409: {"model": ErrorOut}, 422: {"model": ErrorOut}},
)
def publish_map_version(version_id: uuid.UUID, session: SessionDep, user: AdminUser) -> MapVersionAdminOut:
    """Publish a draft if it passes every check; the previous published version is archived."""
    try:
        publish_version(session, version_id)
    except VersionNotFoundError as error:
        raise _not_found() from error
    except VersionStateError as error:
        session.rollback()
        raise ApiError(
            "conflict", "La versión no es un borrador", "Solo se publican versiones en borrador", 409
        ) from error
    except PublishValidationError as error:
        session.rollback()
        raise ApiError(
            "validation_error",
            "La versión no supera las validaciones",
            "Corrige los problemas indicados antes de publicar",
            422,
            {"issues": [{"code": issue.code, "detail": issue.detail} for issue in error.issues]},
        ) from error
    session.commit()
    log.info("map_version_published", version_id=str(version_id), user_id=str(user.id))
    return _versions(session, None, version_id)[0]
