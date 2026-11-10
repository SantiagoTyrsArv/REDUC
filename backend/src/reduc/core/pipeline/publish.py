"""Map versions: validation before publishing and the publication itself (docs/04 §4, ADR-008).

A published version is what every user routes on, so publishing is explicit and refuses
any draft that fails a check. Nothing here ever edits a published version.
"""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from reduc.core.db.models import MapVersion, Region
from reduc.core.domain.profile import PROFILE_PRESETS, MobilityProfile, Weights
from reduc.core.routing.engine import Coordinate, NoNearbyPathError, RoutingEngine
from reduc.core.routing.pgrouting import PgrRoutingEngine

MIN_GIANT_COMPONENT_PCT = 95.0
CRITICAL_CONFIDENCE = 0.8
#: A regression route "passes" a point it must avoid when it comes closer than this.
AVOID_POINT_RADIUS_M = 3.0
MAX_REGRESSION_ROUTES = 200


@dataclass(frozen=True)
class ValidationIssue:
    """One reason a draft cannot be published. `code` is stable; `detail` is for people."""

    code: str
    detail: str


class VersionNotFoundError(Exception):
    pass


class VersionStateError(Exception):
    """The version is not a draft (already published or archived)."""


class PublishValidationError(Exception):
    def __init__(self, issues: list[ValidationIssue]) -> None:
        super().__init__("; ".join(issue.detail for issue in issues))
        self.issues = issues


def _profile(value: Any) -> MobilityProfile:
    """A preset name, or a full profile object as sent to `POST /v1/routes`."""
    if isinstance(value, str):
        return PROFILE_PRESETS[value]  # type: ignore[index]
    if isinstance(value, Mapping):
        fields = dict(value)
        weights = fields.pop("weights", None)
        return MobilityProfile(**fields, weights=Weights(**weights) if weights else Weights())
    raise ValueError("profile must be a preset name or an object")


def _coordinate(value: Any) -> Coordinate:
    lon, lat = value
    return Coordinate(float(lon), float(lat))


def _check_accessibility(session: Session, version_id: uuid.UUID) -> list[ValidationIssue]:
    row = session.execute(
        text(
            "SELECT count(*) AS edges, count(*) FILTER (WHERE a.edge_id IS NULL) AS missing "
            "FROM edge e LEFT JOIN edge_accessibility a ON a.edge_id = e.id WHERE e.map_version_id = :version"
        ),
        {"version": version_id},
    ).one()
    if row.edges == 0:
        return [ValidationIssue("empty_graph", "La versión no tiene tramos")]
    if row.missing:
        return [ValidationIssue("missing_accessibility", f"{row.missing} tramos no tienen atributos de accesibilidad")]
    return []


def _check_connectivity(session: Session, version_id: uuid.UUID) -> list[ValidationIssue]:
    nodes: int = session.execute(
        text("SELECT count(*) FROM node WHERE map_version_id = :version"), {"version": version_id}
    ).scalar_one()
    if nodes == 0:
        return []
    largest: int = session.execute(
        text(
            """
            SELECT COALESCE(max(size), 0) FROM (
                SELECT count(*) AS size FROM pgr_connectedComponents(
                    format('SELECT id, source, target, 1.0 AS cost, 1.0 AS reverse_cost
                            FROM edge WHERE map_version_id = %L', CAST(:version AS text)))
                GROUP BY component
            ) AS components
            """
        ),
        {"version": str(version_id)},
    ).scalar_one()
    pct = 100.0 * float(largest) / float(nodes)
    if pct < MIN_GIANT_COMPONENT_PCT:
        return [
            ValidationIssue(
                "disconnected_graph",
                f"Solo el {pct:.1f} % de los nodos está en la componente principal (mínimo 95 %)",
            )
        ]
    return []


def _check_barriers(session: Session, version_id: uuid.UUID) -> list[ValidationIssue]:
    loose: int = session.execute(
        text(
            "SELECT count(*) FROM barrier WHERE map_version_id = :version AND severity = 'critical' "
            "AND confidence >= :confidence AND verification_status <> 'rejected' "
            "AND edge_id IS NULL AND node_id IS NULL"
        ),
        {"version": version_id, "confidence": CRITICAL_CONFIDENCE},
    ).scalar_one()
    if loose:
        return [
            ValidationIssue(
                "unassociated_critical_barrier",
                f"{loose} barreras críticas con confianza ≥ 0,8 no están asociadas a ningún tramo o nodo",
            )
        ]
    return []


def _route_touches(session: Session, version_id: uuid.UUID, edge_ids: tuple[int, ...], case: Mapping[str, Any]) -> str:
    """Why the route violates the case's avoid rules, or an empty string."""
    barrier_ids = [uuid.UUID(str(value)) for value in case.get("must_avoid_barrier_ids") or []]
    if barrier_ids:
        known: int = session.execute(
            text("SELECT count(*) FROM barrier WHERE map_version_id = :version AND id = ANY(:ids)"),
            {"version": version_id, "ids": barrier_ids},
        ).scalar_one()
        if known != len(set(barrier_ids)):
            # Failing closed: a barrier we cannot find cannot be proven avoided.
            return "alguna barrera de must_avoid_barrier_ids no existe en esta versión"
        touched: int = session.execute(
            text(
                "SELECT count(*) FROM barrier b WHERE b.id = ANY(:ids) AND (b.edge_id = ANY(:edges) OR b.node_id IN "
                "(SELECT source FROM edge WHERE id = ANY(:edges) UNION SELECT target FROM edge WHERE id = ANY(:edges)))"
            ),
            {"ids": barrier_ids, "edges": list(edge_ids)},
        ).scalar_one()
        if touched:
            return "la ruta pasa por una barrera que debía evitar"
    for point in case.get("must_avoid_points") or []:
        avoid = _coordinate(point)
        near: int = session.execute(
            text(
                "SELECT count(*) FROM edge WHERE id = ANY(:edges) AND ST_DWithin(geom::geography, "
                "ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, :radius)"
            ),
            {"edges": list(edge_ids), "lon": avoid.lon, "lat": avoid.lat, "radius": AVOID_POINT_RADIUS_M},
        ).scalar_one()
        if near:
            return "la ruta pasa por un punto que debía evitar"
    return ""


def _check_regression(
    session: Session, region: Region, version_id: uuid.UUID, engine: RoutingEngine
) -> list[ValidationIssue]:
    cases = (region.config or {}).get("regression_routes") or []
    if not isinstance(cases, list):
        return [ValidationIssue("regression_invalid", "regression_routes debe ser una lista")]
    issues: list[ValidationIssue] = []
    for index, case in enumerate(cases[:MAX_REGRESSION_ROUTES], start=1):
        name = str(case.get("name") or f"ruta {index}") if isinstance(case, Mapping) else f"ruta {index}"
        try:
            result = engine.route(
                version_id, _coordinate(case["origin"]), _coordinate(case["destination"]), _profile(case["profile"])
            )
        except NoNearbyPathError:
            issues.append(ValidationIssue("regression_failed", f"{name}: no hay tramo a 50 m del origen o destino"))
            continue
        except (KeyError, TypeError, ValueError):
            issues.append(ValidationIssue("regression_invalid", f"{name}: definición no válida"))
            continue
        if not result.routes:
            issues.append(ValidationIssue("regression_failed", f"{name}: no existe ruta accesible"))
            continue
        route = result.routes[0]
        limit = case.get("max_distance_m")
        if isinstance(limit, int | float) and route.distance_m > float(limit):
            issues.append(
                ValidationIssue(
                    "regression_failed", f"{name}: la ruta mide {route.distance_m:.0f} m (máximo {float(limit):.0f} m)"
                )
            )
            continue
        try:
            reason = _route_touches(session, version_id, route.edge_ids, case)
        except (TypeError, ValueError):
            issues.append(ValidationIssue("regression_invalid", f"{name}: definición no válida"))
            continue
        if reason:
            issues.append(ValidationIssue("regression_failed", f"{name}: {reason}"))
    return issues


def validate_version(
    session: Session, version_id: uuid.UUID, engine: RoutingEngine | None = None
) -> list[ValidationIssue]:
    """Every reason the version cannot be published; an empty list means it can.

    Routing reads `routing_edge`, so the view is refreshed first: the checks then see exactly
    what users would get.
    """
    version = session.get(MapVersion, version_id)
    if version is None:
        raise VersionNotFoundError(str(version_id))
    region = session.get(Region, version.region_id)
    assert region is not None
    issues = _check_accessibility(session, version_id)
    issues += _check_connectivity(session, version_id)
    issues += _check_barriers(session, version_id)
    if not issues:
        session.execute(text("REFRESH MATERIALIZED VIEW routing_edge"))
        issues += _check_regression(session, region, version_id, engine or PgrRoutingEngine(session))
    return issues


def publish_version(session: Session, version_id: uuid.UUID, engine: RoutingEngine | None = None) -> MapVersion:
    """Validate and publish a draft; the previously published version becomes archived."""
    version = session.get(MapVersion, version_id)
    if version is None:
        raise VersionNotFoundError(str(version_id))
    # Serialise publications of one region.
    region = session.get(Region, version.region_id, with_for_update=True)
    assert region is not None
    session.refresh(version)
    if version.status != "draft":
        raise VersionStateError(version.status)
    issues = validate_version(session, version_id, engine)
    if issues:
        raise PublishValidationError(issues)

    now = datetime.now(UTC)
    for previous in session.scalars(
        select(MapVersion).where(MapVersion.region_id == region.id, MapVersion.status == "published")
    ):
        previous.status = "archived"
    version.status = "published"
    version.published_at = now
    region.published_version_id = version.id
    session.flush()
    return version
