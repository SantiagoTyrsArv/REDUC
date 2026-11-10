"""Edge accessibility attributes from OSM tags, elevation, barriers and field measurements.

Rules of docs/05-pipeline-vision.md §9. Pure logic: every input arrives as plain data.
When information is missing the result is pessimistic or carries a low `data_confidence`,
never an optimistic guess.
"""

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Literal

from reduc.core.domain.profile import PROFILE_PRESETS
from reduc.core.domain.taxonomy import MIN_EFFECTIVE_CONFIDENCE
from reduc.core.routing.cost import BLOCKED_COST, EdgeCostInput, edge_cost

Position = Literal["edge", "start", "end"]
Coverage = Literal["imagery", "osm_only", "none"]

#: Confidence of an edge by how it was observed, before looking at its individual facts.
COVERAGE_CONFIDENCE: dict[str, float] = {"imagery": 0.8, "osm_only": 0.3, "none": 0.1}
#: Confidence of the slope by where it came from. No slope at all is the least trustworthy.
SLOPE_CONFIDENCE: dict[str | None, float] = {"osm_incline": 0.9, "dem": 0.9, "dem_lowres": 0.5, None: 0.4}
#: Width assumed for a sidewalk reported as narrow when nobody measured it (below every preset).
NARROW_DEFAULT_WIDTH_M = 0.8
BLOCKING_CLEAR_WIDTH_M = 0.6
CAUTION_SLOPE_PCT = 3.0
CAUTION_WIDTH_M = 1.2
LOW_CONFIDENCE = 0.3

SURFACE_CLASS: dict[str, int] = {
    "asphalt": 0,
    "concrete": 0,
    "concrete:plates": 0,
    "paved": 0,
    "metal": 0,
    "rubber": 0,
    "paving_stones": 1,
    "concrete:lanes": 1,
    "bricks": 1,
    "brick": 1,
    "wood": 1,
    "tiles": 1,
    "sett": 2,
    "cobblestone": 2,
    "compacted": 2,
    "fine_gravel": 2,
    "unhewn_cobblestone": 3,
    "gravel": 3,
    "pebblestone": 3,
    "grass": 3,
    "grass_paver": 3,
    "dirt": 3,
    "earth": 3,
    "ground": 3,
    "unpaved": 3,
    "woodchips": 3,
    "sand": 4,
    "mud": 4,
    "rock": 4,
}
SMOOTHNESS_CLASS: dict[str, int] = {
    "excellent": 0,
    "good": 0,
    "intermediate": 1,
    "bad": 2,
    "very_bad": 3,
    "horrible": 4,
    "very_horrible": 4,
    "impassable": 4,
}
ACCESSIBILITY_TAGS = frozenset({"surface", "smoothness", "width", "incline", "wheelchair", "sidewalk", "kerb", "ramp"})
OVERRIDABLE = frozenset(
    {
        "slope_pct",
        "max_slope_pct",
        "cross_slope_pct",
        "width_m",
        "surface_class",
        "has_steps",
        "max_step_height_cm",
        "curb_ramp_start",
        "curb_ramp_end",
        "obstacle_level",
        "sidewalk_missing",
    }
)
CURB_VALUES = frozenset({"yes", "no", "unknown", "n/a"})

_NUMBER = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*(m|cm|mm)?\s*$")


@dataclass(frozen=True)
class EdgeFacts:
    """Everything known about one edge before looking at its barriers."""

    kind: str
    length_m: float
    tags: Mapping[str, Any] = field(default_factory=dict)
    slope_pct: float | None = None
    max_slope_pct: float | None = None
    slope_source: str | None = None
    start_node_tags: Mapping[str, Any] = field(default_factory=dict)
    end_node_tags: Mapping[str, Any] = field(default_factory=dict)
    overrides: Mapping[str, Any] = field(default_factory=dict)
    coverage: str = "none"
    #: 75th percentile of the surface classifier over the images of the edge, when available.
    surface_p75: int | None = None
    #: Free width measured by the segmentation model, when available.
    measured_width_m: float | None = None


@dataclass(frozen=True)
class BarrierFact:
    barrier_class: str
    severity: str
    confidence: float
    verification_status: str
    position: Position = "edge"
    attributes: Mapping[str, Any] = field(default_factory=dict)

    @property
    def effective(self) -> bool:
        """Whether the barrier changes attributes: not rejected, and either reviewed or likely enough."""
        if self.verification_status == "rejected":
            return False
        return self.verification_status in {"confirmed", "corrected"} or self.confidence >= MIN_EFFECTIVE_CONFIDENCE


@dataclass(frozen=True)
class EdgeAttributes:
    """The columns of `edge_accessibility`."""

    slope_pct: float
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
    coverage: str
    status: str


def parse_length_m(value: Any) -> float | None:
    """Meters from an OSM length such as `1.5`, `1,5 m` or `150 cm`."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value) if math.isfinite(value) and value > 0 else None
    if not isinstance(value, str):
        return None
    match = _NUMBER.match(value)
    if match is None:
        return None
    number = float(match.group(1).replace(",", "."))
    meters = number * {"m": 1.0, "cm": 0.01, "mm": 0.001}[match.group(2) or "m"]
    return meters if meters > 0 else None


def osm_surface_class(tags: Mapping[str, Any], kind: str) -> int:
    """Surface class from `surface`/`smoothness`; the worse of the two wins."""
    surface = SURFACE_CLASS.get(str(tags.get("surface", "")).lower())
    smoothness = SMOOTHNESS_CLASS.get(str(tags.get("smoothness", "")).lower())
    known = [value for value in (surface, smoothness) if value is not None]
    if known:
        return max(known)
    # Untagged: informal paths are rarely paved; everything else is assumed good but not perfect.
    return 2 if kind == "path" else 1


def coverage_of(tags: Mapping[str, Any], has_imagery: bool) -> Coverage:
    if has_imagery:
        return "imagery"
    return "osm_only" if any(key in tags for key in ACCESSIBILITY_TAGS) else "none"


def _number(attributes: Mapping[str, Any], key: str) -> float | None:
    value = attributes.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        return None
    return float(value)


def _curb_ramp(node_tags: Mapping[str, Any], barriers: Sequence[BarrierFact]) -> str:
    """State of the curb at one end of a crossing. Evidence of a missing ramp wins over a ramp."""
    kerb = str(node_tags.get("kerb", "")).lower()
    classes = {barrier.barrier_class for barrier in barriers}
    if "curb_no_ramp" in classes or kerb == "raised":
        return "no"
    if "curb_ramp" in classes or kerb in {"lowered", "flush"}:
        return "yes"
    return "unknown"


def _steps(facts: EdgeFacts, on_edge: Sequence[BarrierFact]) -> tuple[bool, float | None]:
    steps = [barrier for barrier in on_edge if barrier.barrier_class in {"stairs", "single_step"}]
    if facts.kind != "steps" and not steps:
        return False, None
    # A staircase, or any step nobody measured, has an unknown height and therefore blocks.
    heights = [_number(barrier.attributes, "step_height_cm") for barrier in steps]
    if facts.kind == "steps" or any(barrier.barrier_class == "stairs" for barrier in steps) or None in heights:
        return True, None
    return True, max(height for height in heights if height is not None)


def _obstacle_level(facts: EdgeFacts, on_edge: Sequence[BarrierFact]) -> int:
    if str(facts.tags.get("wheelchair", "")).lower() == "no":
        return 2
    level = 0
    for barrier in on_edge:
        if barrier.barrier_class != "obstacle":
            continue
        clear = _number(barrier.attributes, "clear_width_m")
        blocking = barrier.attributes.get("blocking") is True or (clear is not None and clear < BLOCKING_CLEAR_WIDTH_M)
        level = max(level, 2 if blocking else 1)
    return level


def _width(facts: EdgeFacts, on_edge: Sequence[BarrierFact]) -> float | None:
    candidates = [parse_length_m(facts.tags.get("width")), facts.measured_width_m]
    for barrier in on_edge:
        if barrier.barrier_class in {"narrow_sidewalk", "obstacle"}:
            clear = _number(barrier.attributes, "clear_width_m")
            if clear is None and barrier.barrier_class == "narrow_sidewalk":
                clear = NARROW_DEFAULT_WIDTH_M
            candidates.append(clear)
    known = [value for value in candidates if value is not None]
    return round(min(known), 2) if known else None


def _status(attributes: EdgeAttributes, kind: str, length_m: float, confirmed_critical: bool) -> str:
    """Colour of the edge on the map, judged with the standard manual-wheelchair profile."""
    cost_input = EdgeCostInput(
        length_m=length_m,
        kind=kind,
        max_slope_pct=attributes.max_slope_pct,
        cross_slope_pct=attributes.cross_slope_pct,
        width_m=attributes.width_m,
        surface_class=attributes.surface_class,
        has_steps=attributes.has_steps,
        max_step_height_cm=attributes.max_step_height_cm,
        curb_ramp_start=attributes.curb_ramp_start,
        curb_ramp_end=attributes.curb_ramp_end,
        obstacle_level=attributes.obstacle_level,
        sidewalk_missing=attributes.sidewalk_missing,
        data_confidence=attributes.data_confidence,
        verified=attributes.verified,
        has_confirmed_critical_barrier=confirmed_critical,
    )
    profile = PROFILE_PRESETS["manual"]
    blocked = [edge_cost(profile, cost_input, reverse=reverse) == BLOCKED_COST for reverse in (False, True)]
    if all(blocked):
        return "inaccessible"
    if any(blocked):
        return "caution"
    if not attributes.verified and attributes.data_confidence <= LOW_CONFIDENCE:
        return "unknown"
    caution = (
        abs(attributes.max_slope_pct) > CAUTION_SLOPE_PCT
        or attributes.surface_class >= 2
        or (attributes.width_m is not None and attributes.width_m < CAUTION_WIDTH_M)
        or attributes.obstacle_level == 1
        or attributes.sidewalk_missing
        or kind == "road_shoulder"
        or (kind == "crossing" and "unknown" in (attributes.curb_ramp_start, attributes.curb_ramp_end))
        or attributes.has_steps
    )
    return "caution" if caution else "accessible"


def _apply_overrides(attributes: EdgeAttributes, overrides: Mapping[str, Any]) -> EdgeAttributes:
    """Field measurements replace computed values; malformed entries are ignored, not trusted."""
    changes: dict[str, Any] = {}
    for key, value in overrides.items():
        if key not in OVERRIDABLE:
            continue
        if key in {"curb_ramp_start", "curb_ramp_end"}:
            if value in CURB_VALUES:
                changes[key] = value
        elif key in {"has_steps", "sidewalk_missing"}:
            if isinstance(value, bool):
                changes[key] = value
        elif key in {"surface_class", "obstacle_level"}:
            limit = 4 if key == "surface_class" else 2
            if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= limit:
                changes[key] = value
        elif value is None and key in {"cross_slope_pct", "width_m", "max_step_height_cm"}:
            changes[key] = None
        elif isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value):
            changes[key] = float(value)
    if "slope_pct" in changes and "max_slope_pct" not in changes:
        # One inclinometer reading describes the whole edge.
        changes["max_slope_pct"] = changes["slope_pct"]
    return replace(attributes, **changes)


def compute_attributes(facts: EdgeFacts, barriers: Sequence[BarrierFact] = ()) -> EdgeAttributes:
    """Derive the accessibility attributes of one edge."""
    effective = [barrier for barrier in barriers if barrier.effective]
    on_edge = [barrier for barrier in effective if barrier.position == "edge"]
    at_start = [barrier for barrier in effective if barrier.position == "start"]
    at_end = [barrier for barrier in effective if barrier.position == "end"]

    has_steps, step_height = _steps(facts, on_edge)

    surface = max(osm_surface_class(facts.tags, facts.kind), facts.surface_p75 or 0)
    if any(barrier.barrier_class == "surface_damage" for barrier in on_edge):
        surface += 1
    surface = min(4, surface)

    is_crossing = facts.kind == "crossing"
    curb_start = _curb_ramp(facts.start_node_tags, at_start) if is_crossing else "n/a"
    curb_end = _curb_ramp(facts.end_node_tags, at_end) if is_crossing else "n/a"

    sidewalk_missing = str(facts.tags.get("sidewalk", "")).lower() in {"no", "none"} or any(
        barrier.barrier_class == "no_sidewalk" for barrier in on_edge
    )

    # "Verified" means a person looked: every barrier reviewed, or the edge marked as reviewed and clean.
    all_reviewed = all(barrier.verification_status != "unverified" for barrier in barriers)
    verified = all_reviewed and (bool(barriers) or facts.overrides.get("reviewed") is True)

    slope_measured = "slope_pct" in facts.overrides or "max_slope_pct" in facts.overrides
    confidences = [1.0 if verified else COVERAGE_CONFIDENCE.get(facts.coverage, COVERAGE_CONFIDENCE["none"])]
    confidences.append(1.0 if slope_measured else SLOPE_CONFIDENCE.get(facts.slope_source, SLOPE_CONFIDENCE[None]))
    confidences += [barrier.confidence for barrier in effective if barrier.verification_status == "unverified"]
    if any(barrier.barrier_class == "steep_slope_visual" for barrier in on_edge) and not slope_measured:
        # The photo suggests a slope the elevation model may be missing.
        confidences.append(0.4)

    attributes = EdgeAttributes(
        slope_pct=facts.slope_pct if facts.slope_pct is not None else 0.0,
        max_slope_pct=facts.max_slope_pct
        if facts.max_slope_pct is not None
        else (facts.slope_pct if facts.slope_pct is not None else 0.0),
        cross_slope_pct=None,
        width_m=_width(facts, on_edge),
        surface_class=surface,
        has_steps=has_steps,
        max_step_height_cm=step_height,
        curb_ramp_start=curb_start,
        curb_ramp_end=curb_end,
        obstacle_level=_obstacle_level(facts, on_edge),
        sidewalk_missing=sidewalk_missing,
        data_confidence=round(max(0.0, min(1.0, min(confidences))), 3),
        verified=verified,
        coverage=facts.coverage,
        status="unknown",
    )
    attributes = _apply_overrides(attributes, facts.overrides)
    confirmed_critical = any(
        barrier.severity == "critical" and barrier.verification_status == "confirmed" for barrier in barriers
    )
    return replace(attributes, status=_status(attributes, facts.kind, facts.length_m, confirmed_critical))
