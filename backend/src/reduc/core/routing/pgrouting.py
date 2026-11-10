"""PostgreSQL/pgRouting implementation of the accessible routing engine."""

import math
import uuid
from collections.abc import Sequence
from dataclasses import replace
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import Session

from reduc.core.domain.profile import MobilityProfile
from reduc.core.routing.cost import build_cost_sql
from reduc.core.routing.engine import Coordinate, NoNearbyPathError, RoutePath, RoutingResult

MAX_SNAP_DISTANCE_M = 50.0
MAX_OVERLAP = 0.8


class PgrRoutingEngine:
    """Compute directional routes over one published map version."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.dialect: Dialect = session.get_bind().dialect

    def route(
        self,
        map_version_id: uuid.UUID,
        origin: Coordinate,
        destination: Coordinate,
        profile: MobilityProfile,
        *,
        alternatives: int = 0,
        include_shortest: bool = False,
    ) -> RoutingResult:
        """Snap endpoints, find accessible alternatives and relax only documented constraints."""
        if alternatives < 0:
            raise ValueError("alternatives must be non-negative")
        utm_srid = self._utm_srid(map_version_id)
        origin_snap = self._snap(map_version_id, origin, "origin")
        destination_snap = self._snap(map_version_id, destination, "destination")
        margin_m = max(500.0, self._haversine_m(origin, destination) * 0.30)

        routes = self._accessible_routes(
            map_version_id,
            origin,
            destination,
            origin_snap,
            destination_snap,
            profile,
            alternatives,
            utm_srid,
            margin_m,
        )
        fallback_route: RoutePath | None = None
        relaxed_constraints: tuple[str, ...] = ()
        if not routes:
            fallback_route, relaxed_constraints = self._fallback(
                map_version_id,
                origin,
                destination,
                origin_snap,
                destination_snap,
                profile,
                utm_srid,
                margin_m,
            )

        shortest: RoutePath | None = None
        blocking_barrier_ids: tuple[uuid.UUID, ...] = ()
        if include_shortest:
            shortest = self._shortest(
                map_version_id,
                origin,
                destination,
                origin_snap,
                destination_snap,
                utm_srid,
                margin_m,
            )
            if shortest is not None:
                blocking_barrier_ids = self._confirmed_critical_barriers(shortest.edge_ids)

        return RoutingResult(
            routes=routes,
            shortest=shortest,
            blocking_barrier_ids=blocking_barrier_ids,
            fallback_route=fallback_route,
            relaxed_constraints=relaxed_constraints,
        )

    def _utm_srid(self, map_version_id: uuid.UUID) -> int:
        value = self.session.execute(
            text(
                "SELECT r.utm_srid FROM region r "
                "JOIN map_version mv ON mv.region_id = r.id WHERE mv.id = :map_version_id"
            ),
            {"map_version_id": map_version_id},
        ).scalar_one_or_none()
        if value is None:
            raise ValueError("Unknown map version")
        return int(value)

    def _snap(self, map_version_id: uuid.UUID, point: Coordinate, endpoint: str) -> tuple[int, float]:
        """Locate the closest physical edge; accessibility is evaluated by pgRouting, including fallback."""
        row = (
            self.session.execute(
                text(
                    """
                WITH requested AS (
                    SELECT ST_SetSRID(ST_MakePoint(:lon, :lat), 4326) AS geom
                ), candidates AS (
                    SELECT re.id,
                           ST_LineLocatePoint(re.geom, requested.geom) AS fraction,
                           ST_Distance(re.geom::geography, requested.geom::geography) AS distance_m,
                           re.geom::geography <-> requested.geom::geography AS kNN_distance
                    FROM routing_edge re CROSS JOIN requested
                    WHERE re.map_version_id = :map_version_id
                    ORDER BY kNN_distance
                    LIMIT 1
                )
                SELECT id, fraction, distance_m FROM candidates
                """
                ),
                {"lon": point.lon, "lat": point.lat, "map_version_id": map_version_id},
            )
            .mappings()
            .first()
        )
        if row is None or float(row["distance_m"]) > MAX_SNAP_DISTANCE_M:
            raise NoNearbyPathError(endpoint)
        fraction = min(1.0 - 1e-6, max(1e-6, float(row["fraction"])))
        return int(row["id"]), fraction

    def _accessible_routes(
        self,
        map_version_id: uuid.UUID,
        origin: Coordinate,
        destination: Coordinate,
        origin_snap: tuple[int, float],
        destination_snap: tuple[int, float],
        profile: MobilityProfile,
        alternatives: int,
        utm_srid: int,
        margin_m: float,
        *,
        allow_unverified: bool = False,
        allow_unknown_curb_ramps: bool = False,
    ) -> tuple[RoutePath, ...]:
        points_sql = self._points_sql(origin_snap, destination_snap)
        for full_region in (False, True):
            edges_sql = self._edges_sql(
                map_version_id,
                origin,
                destination,
                profile,
                utm_srid,
                margin_m,
                full_region=full_region,
                allow_unverified=allow_unverified,
                allow_unknown_curb_ramps=allow_unknown_curb_ramps,
            )
            rows = (
                self.session.execute(
                    text(
                        """
                    SELECT path_id, path_seq, node, edge, cost, agg_cost
                    FROM pgr_withPointsKSP(
                        :edges_sql, :points_sql, -1, -2, :path_count,
                        directed := true, details := false
                    )
                    ORDER BY path_id, path_seq
                    """
                    ),
                    {"edges_sql": edges_sql, "points_sql": points_sql, "path_count": alternatives + 1},
                )
                .mappings()
                .all()
            )
            routes = self._routes_from_ksp(rows)
            if routes:
                return routes
        return ()

    def _fallback(
        self,
        map_version_id: uuid.UUID,
        origin: Coordinate,
        destination: Coordinate,
        origin_snap: tuple[int, float],
        destination_snap: tuple[int, float],
        profile: MobilityProfile,
        utm_srid: int,
        margin_m: float,
    ) -> tuple[RoutePath | None, tuple[str, ...]]:
        """Apply cumulative relaxations in the specified order, preserving all safety-critical restrictions."""
        relaxed = profile
        allow_unverified = False
        allow_unknown = False
        applied: list[str] = []
        for constraint in ("avoid_unverified", "curb_ramp_unknown", "surface_class", "slope"):
            if constraint == "avoid_unverified":
                allow_unverified = True
            elif constraint == "curb_ramp_unknown":
                allow_unknown = True
            elif constraint == "surface_class":
                relaxed = replace(relaxed, max_surface_class=min(4, relaxed.max_surface_class + 1))
            else:
                relaxed = replace(
                    relaxed,
                    max_uphill_pct=relaxed.max_uphill_pct + 2.0,
                    max_downhill_pct=relaxed.max_downhill_pct + 2.0,
                )
            applied.append(constraint)
            routes = self._accessible_routes(
                map_version_id,
                origin,
                destination,
                origin_snap,
                destination_snap,
                relaxed,
                0,
                utm_srid,
                margin_m,
                allow_unverified=allow_unverified,
                allow_unknown_curb_ramps=allow_unknown,
            )
            if routes:
                return routes[0], tuple(applied)
        return None, ()

    def _shortest(
        self,
        map_version_id: uuid.UUID,
        origin: Coordinate,
        destination: Coordinate,
        origin_snap: tuple[int, float],
        destination_snap: tuple[int, float],
        utm_srid: int,
        margin_m: float,
    ) -> RoutePath | None:
        points_sql = self._points_sql(origin_snap, destination_snap)
        for full_region in (False, True):
            base_sql = (
                "SELECT id, source, target, map_version_id, geom, "
                "length_m AS cost, length_m AS reverse_cost FROM routing_edge"
            )
            edges_sql = self._with_graph_filter(
                base_sql,
                map_version_id,
                origin,
                destination,
                utm_srid,
                margin_m,
                full_region=full_region,
                extra_params={},
            )
            rows = (
                self.session.execute(
                    text(
                        """
                    SELECT path_seq, node, edge, cost, agg_cost
                    FROM pgr_withPoints(
                        :edges_sql, :points_sql, -1, -2,
                        directed := true, details := false
                    )
                    ORDER BY path_seq
                    """
                    ),
                    {"edges_sql": edges_sql, "points_sql": points_sql},
                )
                .mappings()
                .all()
            )
            if rows:
                return self._route_from_rows(0, rows)
        return None

    def _edges_sql(
        self,
        map_version_id: uuid.UUID,
        origin: Coordinate,
        destination: Coordinate,
        profile: MobilityProfile,
        utm_srid: int,
        margin_m: float,
        *,
        full_region: bool,
        allow_unverified: bool,
        allow_unknown_curb_ramps: bool,
    ) -> str:
        base_sql, cost_params = build_cost_sql(
            profile,
            allow_unverified=allow_unverified,
            allow_unknown_curb_ramps=allow_unknown_curb_ramps,
        )
        return self._with_graph_filter(
            base_sql,
            map_version_id,
            origin,
            destination,
            utm_srid,
            margin_m,
            full_region=full_region,
            extra_params=cost_params,
        )

    def _with_graph_filter(
        self,
        base_sql: str,
        map_version_id: uuid.UUID,
        origin: Coordinate,
        destination: Coordinate,
        utm_srid: int,
        margin_m: float,
        *,
        full_region: bool,
        extra_params: dict[str, Any],
    ) -> str:
        bbox_filter = ""
        if not full_region:
            bbox_filter = """
              AND geom && ST_Transform(
                  ST_Expand(
                      ST_Transform(
                          ST_SetSRID(
                              ST_MakeLine(
                                  ST_MakePoint(:origin_lon, :origin_lat),
                                  ST_MakePoint(:destination_lon, :destination_lat)
                              ),
                              4326
                          ),
                          :utm_srid
                      ),
                      :margin_m
                  ),
                  4326
              )
            """
        sql = f"SELECT * FROM ({base_sql}) AS costed_edges WHERE map_version_id = :map_version_id {bbox_filter}"
        params: dict[str, Any] = {
            **extra_params,
            "map_version_id": map_version_id,
            "origin_lon": origin.lon,
            "origin_lat": origin.lat,
            "destination_lon": destination.lon,
            "destination_lat": destination.lat,
            "utm_srid": utm_srid,
            "margin_m": margin_m,
        }
        return self._literal_sql(sql, params)

    def _points_sql(self, origin: tuple[int, float], destination: tuple[int, float]) -> str:
        sql = """
            SELECT 1::INTEGER AS pid, CAST(:origin_edge AS BIGINT) AS edge_id,
                   CAST(:origin_fraction AS DOUBLE PRECISION) AS fraction
            UNION ALL
            SELECT 2::INTEGER, :destination_edge, :destination_fraction
        """
        return self._literal_sql(
            sql,
            {
                "origin_edge": origin[0],
                "origin_fraction": origin[1],
                "destination_edge": destination[0],
                "destination_fraction": destination[1],
            },
        )

    def _literal_sql(self, sql: str, params: dict[str, Any]) -> str:
        """Let SQLAlchemy render validated values into the SQL strings required by pgRouting."""
        statement = text(sql)
        present_params = {name: value for name, value in params.items() if name in statement._bindparams}
        statement = statement.bindparams(**present_params)
        return str(statement.compile(dialect=self.dialect, compile_kwargs={"literal_binds": True}))

    def _routes_from_ksp(self, rows: Sequence[Any]) -> tuple[RoutePath, ...]:
        grouped: dict[int, list[Any]] = {}
        for row in rows:
            grouped.setdefault(int(row["path_id"]), []).append(row)
        candidates = [self._route_from_rows(path_id, path_rows) for path_id, path_rows in sorted(grouped.items())]
        selected: list[RoutePath] = []
        for candidate in candidates:
            candidate_edges = set(candidate.edge_ids)
            if not candidate_edges:
                selected.append(candidate)
                continue
            overlaps = any(
                len(candidate_edges & set(route.edge_ids)) / len(candidate_edges) > MAX_OVERLAP for route in selected
            )
            if not overlaps:
                selected.append(candidate)
        return tuple(selected)

    def _route_from_rows(self, path_id: int, rows: Sequence[Any]) -> RoutePath:
        edge_ids = tuple(int(row["edge"]) for row in rows if int(row["edge"]) > 0)
        lengths = self._edge_lengths(edge_ids)
        return RoutePath(
            path_id=path_id,
            edge_ids=edge_ids,
            distance_m=sum(lengths[edge_id] for edge_id in edge_ids),
            cost_m=float(rows[-1]["agg_cost"]),
        )

    def _edge_lengths(self, edge_ids: tuple[int, ...]) -> dict[int, float]:
        if not edge_ids:
            return {}
        statement = text("SELECT id, length_m FROM routing_edge WHERE id IN :edge_ids").bindparams(
            bindparam("edge_ids", expanding=True)
        )
        rows = self.session.execute(statement, {"edge_ids": edge_ids}).all()
        return {int(row[0]): float(row[1]) for row in rows}

    def _confirmed_critical_barriers(self, edge_ids: tuple[int, ...]) -> tuple[uuid.UUID, ...]:
        if not edge_ids:
            return ()
        statement = text(
            "SELECT DISTINCT id FROM barrier "
            "WHERE edge_id IN :edge_ids AND severity = 'critical' AND verification_status = 'confirmed'"
        ).bindparams(bindparam("edge_ids", expanding=True))
        rows: Sequence[Any] = self.session.execute(statement, {"edge_ids": edge_ids}).scalars().all()
        return tuple(row if isinstance(row, uuid.UUID) else uuid.UUID(str(row)) for row in rows)

    @staticmethod
    def _haversine_m(origin: Coordinate, destination: Coordinate) -> float:
        radius_m = 6_371_008.8
        lat1, lat2 = math.radians(origin.lat), math.radians(destination.lat)
        delta_lat = lat2 - lat1
        delta_lon = math.radians(destination.lon - origin.lon)
        haversine = math.sin(delta_lat / 2.0) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2.0) ** 2
        return 2.0 * radius_m * math.asin(math.sqrt(haversine))
