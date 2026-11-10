"""Public endpoints: regions, places, profile presets, routes and barriers."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from reduc.api.deps import get_storage
from reduc.api.errors import ApiError
from reduc.api.schemas.public import (
    BarrierOut,
    BlockingBarrierOut,
    ErrorOut,
    InstructionOut,
    LineStringOut,
    MapVersionOut,
    NoAccessibleRouteError,
    NoAccessibleRouteExtra,
    PoiOut,
    PresetOut,
    ProfileModel,
    RegionOut,
    RegionStatsOut,
    RouteOut,
    RouteRequest,
    RoutesResponse,
    SegmentOut,
    ShortestOut,
    WarningOut,
)
from reduc.core.db.repositories import public as public_repo
from reduc.core.db.session import get_session
from reduc.core.domain.profile import DEVICE_TYPES, PROFILE_PRESETS
from reduc.core.routing.engine import Coordinate, NoNearbyPathError
from reduc.core.routing.messages import barrier_message, normalize_locale, translate
from reduc.core.routing.narrative import RouteNarrative
from reduc.core.routing.service import OutsideRegionError, RouteService, ShortestReference
from reduc.core.storage import STORABLE_LICENSES, ObjectStorage

router = APIRouter(prefix="/v1", tags=["public"])
SessionDep = Annotated[Session, Depends(get_session)]
StorageDep = Annotated[ObjectStorage | None, Depends(get_storage)]


def _route_out(route_id: str, narrative: RouteNarrative) -> RouteOut:
    return RouteOut(
        id=route_id,
        geometry=LineStringOut(coordinates=list(narrative.coords)),
        distance_m=narrative.distance_m,
        duration_s=narrative.duration_s,
        accessibility_score=narrative.accessibility_score,
        verified_pct=narrative.verified_pct,
        max_slope_pct=narrative.max_slope_pct,
        caution_segments=narrative.caution_segments,
        segments=[
            SegmentOut(
                edge_ids=list(segment.edge_ids),
                geometry=LineStringOut(coordinates=list(segment.coords)),
                distance_m=segment.distance_m,
                status=segment.status,  # type: ignore[arg-type]
                slope_pct=segment.slope_pct,
                surface_class=segment.surface_class,
                warnings=[
                    WarningOut(code=w.code, severity=w.severity, message=w.message)  # type: ignore[arg-type]
                    for w in segment.warnings
                ],
            )
            for segment in narrative.segments
        ],
        instructions=[
            InstructionOut(
                distance_m=step.distance_m,
                text=step.text,
                maneuver=step.maneuver,  # type: ignore[arg-type]
                location=step.location,
            )
            for step in narrative.instructions
        ],
    )


def _shortest_out(shortest: ShortestReference | None) -> ShortestOut | None:
    if shortest is None:
        return None
    return ShortestOut(
        distance_m=shortest.distance_m,
        blocking_barriers=[
            BlockingBarrierOut(
                id=barrier.id, barrier_class=barrier.barrier_class, location=barrier.location, message=barrier.message
            )
            for barrier in shortest.blocking_barriers
        ],
    )


@router.get("/regions", response_model=list[RegionOut])
def list_regions(session: SessionDep) -> list[RegionOut]:
    """Active regions with a published map version."""
    return [
        RegionOut(
            id=region.id,
            slug=region.slug,
            name=region.name,
            bbox=region.bbox,
            boundary=region.boundary,
            map_version=MapVersionOut(
                id=region.map_version_id, number=region.map_version_number, published_at=region.published_at
            ),
            stats=RegionStatsOut(
                edges=region.edges, coverage_pct=region.coverage_pct, verified_pct=region.verified_pct
            ),
        )
        for region in public_repo.list_active_regions(session)
    ]


@router.get("/regions/{slug}/pois", response_model=list[PoiOut], responses={404: {"model": ErrorOut}})
def list_pois(
    slug: str,
    session: SessionDep,
    q: Annotated[str | None, Query(max_length=80)] = None,
    category: Annotated[str | None, Query(max_length=40)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[PoiOut]:
    """Search places of one region by text and category."""
    if not public_repo.region_exists(session, slug):
        raise ApiError("not_found", "Recurso no encontrado", "La región no existe", 404)
    return [
        PoiOut(
            id=poi.id,
            name=poi.name,
            category=poi.category,
            location=poi.location,
            accessible_entrance=poi.accessible_entrance,
        )
        for poi in public_repo.search_pois(session, slug, q.strip() if q else None, category, limit)
    ]


@router.get("/profiles/presets", response_model=list[PresetOut])
def list_presets() -> list[PresetOut]:
    """Mobility profile templates (docs/06-enrutamiento.md §2)."""
    return [PresetOut(id=device, profile=ProfileModel.from_domain(PROFILE_PRESETS[device])) for device in DEVICE_TYPES]


@router.post(
    "/routes",
    response_model=RoutesResponse,
    responses={422: {"model": ErrorOut | NoAccessibleRouteError}, 429: {"model": ErrorOut}},
)
def compute_routes(body: RouteRequest, session: SessionDep) -> RoutesResponse:
    """Accessible routes for the given profile, with the shortest route as a reference."""
    locale = normalize_locale(body.locale)
    try:
        origin = Coordinate(*body.origin)
        destination = Coordinate(*body.destination)
        profile = body.profile.to_domain()
    except ValueError as error:
        raise ApiError("validation_error", "Solicitud inválida", str(error), 422) from error
    try:
        plan = RouteService(session).plan(
            origin,
            destination,
            profile,
            alternatives=body.alternatives,
            include_shortest=body.include_shortest,
            locale=locale,
        )
    except OutsideRegionError as error:
        raise ApiError(
            "outside_region",
            translate(locale, "error.outside_region.title"),
            translate(locale, "error.outside_region.detail"),
            422,
        ) from error
    except NoNearbyPathError as error:
        raise ApiError(
            "no_nearby_path",
            translate(locale, "error.no_nearby_path.title"),
            translate(locale, f"error.no_nearby_path.{error.endpoint}"),
            422,
            {"endpoint": error.endpoint},
        ) from error

    shortest = _shortest_out(plan.shortest)
    if not plan.routes:
        fallback = _route_out("fallback", plan.fallback) if plan.fallback is not None else None
        extra = NoAccessibleRouteExtra(
            region=plan.region,
            map_version=plan.map_version,
            fallback_route=fallback,
            violated_constraints=list(plan.relaxed_constraints),
            shortest=shortest,
        )
        detail_key = "error.no_accessible_route.fallback" if fallback else "error.no_accessible_route.none"
        raise ApiError(
            "no_accessible_route",
            translate(locale, "error.no_accessible_route.title"),
            translate(locale, detail_key),
            422,
            extra.model_dump(mode="json", by_alias=True),
        )
    return RoutesResponse(
        region=plan.region,
        map_version=plan.map_version,
        routes=[_route_out(f"r{index + 1}", narrative) for index, narrative in enumerate(plan.routes)],
        shortest=shortest,
    )


@router.get("/barriers/{barrier_id}", response_model=BarrierOut, responses={404: {"model": ErrorOut}})
def get_barrier(
    barrier_id: uuid.UUID,
    session: SessionDep,
    storage: StorageDep,
    locale: Annotated[str, Query(max_length=10)] = "es",
) -> BarrierOut:
    """Detail of one barrier of a published map; the photo is exposed only when its license allows it."""
    barrier = public_repo.get_published_barrier(session, barrier_id)
    if barrier is None:
        raise ApiError("not_found", "Recurso no encontrado", "La barrera no existe", 404)
    photo_url: str | None = None
    if storage is not None and barrier.crop_key and barrier.image_license in STORABLE_LICENSES:
        photo_url = storage.presigned_url(barrier.crop_key, 900)
    return BarrierOut(
        id=barrier.id,
        barrier_class=barrier.barrier_class,
        severity=barrier.severity,  # type: ignore[arg-type]
        location=barrier.location,
        attributes=barrier.attributes,
        confidence=barrier.confidence,
        n_observations=barrier.n_observations,
        source=barrier.source,
        verification_status=barrier.verification_status,
        description=barrier_message(normalize_locale(locale), barrier.barrier_class, barrier.attributes),
        photo_url=photo_url,
        attribution=barrier.attribution if photo_url else None,
    )
