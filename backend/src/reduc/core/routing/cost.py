"""Single source of truth for directional accessibility costs in Python and SQL."""

from dataclasses import dataclass

from reduc.core.domain.profile import MobilityProfile

BLOCKED_COST = -1.0

SqlParams = dict[str, float | int | bool]


@dataclass(frozen=True)
class EdgeCostInput:
    """Accessibility attributes needed to cost an edge in either direction."""

    length_m: float
    kind: str
    max_slope_pct: float
    cross_slope_pct: float | None
    width_m: float | None
    surface_class: int
    has_steps: bool
    max_step_height_cm: float | None
    curb_ramp_start: str
    curb_ramp_end: str
    obstacle_level: int
    sidewalk_missing: bool
    data_confidence: float
    verified: bool
    has_confirmed_critical_barrier: bool


def _directional_curb_ramp(edge: EdgeCostInput, reverse: bool) -> str:
    return edge.curb_ramp_start if reverse else edge.curb_ramp_end


def _is_blocked(
    profile: MobilityProfile,
    edge: EdgeCostInput,
    reverse: bool,
    allow_unverified: bool,
    allow_unknown_curb_ramps: bool,
) -> bool:
    """Apply every hard restriction, failing closed for confirmed critical barriers and unknown steps."""
    slope = -edge.max_slope_pct if reverse else edge.max_slope_pct
    curb_ramp = _directional_curb_ramp(edge, reverse)
    return (
        edge.has_confirmed_critical_barrier
        or (edge.has_steps and (edge.max_step_height_cm is None or edge.max_step_height_cm > profile.max_step_cm))
        or slope > profile.max_uphill_pct
        or slope < -profile.max_downhill_pct
        or (edge.cross_slope_pct is not None and abs(edge.cross_slope_pct) > profile.max_cross_slope_pct)
        or (edge.width_m is not None and edge.width_m < profile.min_width_m)
        or edge.surface_class > profile.max_surface_class
        or edge.obstacle_level == 2
        or (profile.require_curb_ramps and edge.kind == "crossing" and curb_ramp == "no")
        or (profile.avoid_unverified and not allow_unverified and not edge.verified)
        or (
            profile.require_curb_ramps
            and profile.avoid_unverified
            and not allow_unknown_curb_ramps
            and edge.kind == "crossing"
            and curb_ramp == "unknown"
        )
    )


def _slope_penalty(profile: MobilityProfile, slope: float) -> float:
    if slope > 0.0:
        return profile.weights.slope * (slope / profile.max_uphill_pct) ** 2
    if slope < 0.0:
        return profile.weights.slope * 0.5 * (abs(slope) / profile.max_downhill_pct) ** 2
    return 0.0


def edge_cost(
    profile: MobilityProfile,
    edge: EdgeCostInput,
    *,
    reverse: bool = False,
    allow_unverified: bool = False,
    allow_unknown_curb_ramps: bool = False,
) -> float:
    """Return equivalent meters, or -1 when the edge cannot be traversed in this direction."""
    if _is_blocked(profile, edge, reverse, allow_unverified, allow_unknown_curb_ramps):
        return BLOCKED_COST

    slope = -edge.max_slope_pct if reverse else edge.max_slope_pct
    curb_ramp_unknown = edge.kind == "crossing" and _directional_curb_ramp(edge, reverse) == "unknown"
    penalty = (
        _slope_penalty(profile, slope)
        + profile.weights.surface * 0.25 * edge.surface_class
        + (0.3 if edge.obstacle_level == 1 else 0.0)
        + (0.5 if edge.kind == "road_shoulder" or edge.sidewalk_missing else 0.0)
        + profile.weights.uncertainty * 0.6 * (1.0 - edge.data_confidence)
        + (0.4 if curb_ramp_unknown else 0.0)
    )
    return edge.length_m * (1.0 + penalty)


def _slope_penalty_sql(slope: str) -> str:
    uphill_ratio = f"({slope} / :max_uphill_pct)"
    downhill_ratio = f"(ABS({slope}) / :max_downhill_pct)"
    return (
        f"CASE WHEN {slope} > 0 THEN :weight_slope * {uphill_ratio} * {uphill_ratio} "
        f"WHEN {slope} < 0 THEN :weight_slope * 0.5 * {downhill_ratio} * {downhill_ratio} "
        "ELSE 0.0 END"
    )


def _cost_sql(reverse: bool) -> str:
    """Build one SQL expression using the same rules and constants as edge_cost."""
    slope = "(-max_slope_pct)" if reverse else "max_slope_pct"
    curb_ramp = "curb_ramp_start" if reverse else "curb_ramp_end"
    crossing = "kind = 'crossing'"
    confirmed_critical = """EXISTS (
            SELECT 1 FROM barrier b
            WHERE (b.edge_id = routing_edge.id OR b.node_id IN (routing_edge.source, routing_edge.target))
              AND b.severity = 'critical' AND b.verification_status = 'confirmed'
        )"""
    blocked = f"""
        {confirmed_critical}
        OR (has_steps AND (max_step_height_cm IS NULL OR max_step_height_cm > :max_step_cm))
        OR {slope} > :max_uphill_pct
        OR {slope} < -:max_downhill_pct
        OR (cross_slope_pct IS NOT NULL AND ABS(cross_slope_pct) > :max_cross_slope_pct)
        OR (width_m IS NOT NULL AND width_m < :min_width_m)
        OR surface_class > :max_surface_class
        OR obstacle_level = 2
        OR (:require_curb_ramps AND {crossing} AND {curb_ramp} = 'no')
        OR (:avoid_unverified AND NOT :allow_unverified AND NOT verified)
        OR (
            :require_curb_ramps AND :avoid_unverified AND NOT :allow_unknown_curb_ramps
            AND {crossing} AND {curb_ramp} = 'unknown'
        )
    """
    slope_penalty = _slope_penalty_sql(slope)
    return f"""CASE WHEN {blocked} THEN -1.0 ELSE length_m * (
        1.0
        + ({slope_penalty})
        + :weight_surface * 0.25 * surface_class
        + CASE WHEN obstacle_level = 1 THEN 0.3 ELSE 0.0 END
        + CASE WHEN kind = 'road_shoulder' OR sidewalk_missing THEN 0.5 ELSE 0.0 END
        + :weight_uncertainty * 0.6 * (1.0 - data_confidence)
        + CASE WHEN {crossing} AND {curb_ramp} = 'unknown' THEN 0.4 ELSE 0.0 END
    ) END"""


def build_cost_sql(
    profile: MobilityProfile, *, allow_unverified: bool = False, allow_unknown_curb_ramps: bool = False
) -> tuple[str, SqlParams]:
    """Return a parameterized pgRouting-compatible SELECT with forward and reverse costs."""
    params: SqlParams = {
        "max_uphill_pct": profile.max_uphill_pct,
        "max_downhill_pct": profile.max_downhill_pct,
        "max_cross_slope_pct": profile.max_cross_slope_pct,
        "max_step_cm": profile.max_step_cm,
        "min_width_m": profile.min_width_m,
        "max_surface_class": profile.max_surface_class,
        "require_curb_ramps": profile.require_curb_ramps,
        "avoid_unverified": profile.avoid_unverified,
        "allow_unverified": allow_unverified,
        "allow_unknown_curb_ramps": allow_unknown_curb_ramps,
        "weight_slope": profile.weights.slope,
        "weight_surface": profile.weights.surface,
        "weight_uncertainty": profile.weights.uncertainty,
    }
    sql = (
        "SELECT routing_edge.*, "
        f"{_cost_sql(reverse=False)} AS cost, "
        f"{_cost_sql(reverse=True)} AS reverse_cost "
        "FROM routing_edge"
    )
    return sql, params
