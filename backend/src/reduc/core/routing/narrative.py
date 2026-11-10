"""Turn a sequence of traversed edges into segments, warnings, instructions and scores.

Everything here is pure: the service layer loads edges, orients and trims them, and this
module explains the result to the user without touching the database.
"""

from dataclasses import dataclass

from reduc.core.domain.profile import MobilityProfile
from reduc.core.routing.geometry import Coord, bearing_deg, haversine_m, turn_angle_deg
from reduc.core.routing.messages import Locale, translate

TURN_THRESHOLD_DEG = 30.0
U_TURN_THRESHOLD_DEG = 150.0
POI_RADIUS_M = 20.0
UPHILL_SLOW_THRESHOLD_PCT = 5.0
UPHILL_SLOW_FACTOR = 0.7
BLOCKED_PENALTY = 2.0
_SPECIAL_KINDS = frozenset({"crossing", "steps", "ramp", "elevator", "road_shoulder"})
_DIRECTIONS = ("n", "ne", "e", "se", "s", "sw", "w", "nw")


@dataclass(frozen=True)
class TraversedEdge:
    """One graph edge as travelled: oriented, trimmed at the endpoints and already costed."""

    edge_id: int
    coords: tuple[Coord, ...]
    length_m: float
    kind: str
    slope_pct: float
    width_m: float | None
    surface_class: int
    curb_ramp: str
    sidewalk_missing: bool
    verified: bool
    penalty: float
    blocked: bool = False


@dataclass(frozen=True)
class NearbyPoi:
    """A named place that can anchor a turn instruction."""

    name: str
    location: Coord


@dataclass(frozen=True)
class RouteWarning:
    code: str
    severity: str
    message: str


@dataclass(frozen=True)
class RouteSegment:
    edge_ids: tuple[int, ...]
    coords: tuple[Coord, ...]
    distance_m: float
    status: str
    slope_pct: float
    surface_class: int
    warnings: tuple[RouteWarning, ...]


@dataclass(frozen=True)
class RouteInstruction:
    distance_m: float
    text: str
    maneuver: str
    location: Coord


@dataclass(frozen=True)
class RouteNarrative:
    """Everything the API returns for one route besides its identifier."""

    coords: tuple[Coord, ...]
    distance_m: float
    duration_s: int
    accessibility_score: int
    verified_pct: float
    max_slope_pct: float
    caution_segments: int
    segments: tuple[RouteSegment, ...]
    instructions: tuple[RouteInstruction, ...]


def edge_warning_codes(edge: TraversedEdge, profile: MobilityProfile) -> tuple[tuple[str, str], ...]:
    """Return stable (code, severity) pairs for one edge under one profile."""
    found: list[tuple[str, str]] = []
    if edge.blocked:
        found.append(("exceeds_profile", "major"))
    if edge.slope_pct > 0.0:
        ratio = edge.slope_pct / profile.max_uphill_pct
        if ratio >= 0.6 and edge.slope_pct >= 3.0:
            found.append(("slope_moderate", "major" if ratio >= 0.9 else "minor"))
    elif edge.slope_pct < 0.0:
        ratio = abs(edge.slope_pct) / profile.max_downhill_pct
        if ratio >= 0.6 and abs(edge.slope_pct) >= 3.0:
            found.append(("slope_steep_downhill", "major" if ratio >= 0.9 else "minor"))
    if edge.surface_class >= 2:
        found.append(("surface_irregular", "major" if edge.surface_class >= 3 else "minor"))
    if not edge.verified:
        found.append(("unverified_segment", "minor"))
    if edge.kind == "crossing" and edge.curb_ramp == "unknown":
        found.append(("curb_ramp_unknown", "major"))
    if edge.width_m is not None and edge.width_m < profile.min_width_m + 0.2:
        found.append(("narrow_passage", "minor"))
    if edge.kind == "road_shoulder" or edge.sidewalk_missing:
        found.append(("road_shoulder", "major"))
    return tuple(found)


def _edge_status(edge: TraversedEdge, codes: tuple[tuple[str, str], ...]) -> str:
    if edge.blocked:
        return "inaccessible"
    return "caution" if codes else "accessible"


def _group_key(edge: TraversedEdge, profile: MobilityProfile) -> tuple[object, ...]:
    codes = edge_warning_codes(edge, profile)
    kind = edge.kind if edge.kind in _SPECIAL_KINDS else "path"
    return (_edge_status(edge, codes), codes, edge.surface_class, kind)


def _merge_coords(edges: list[TraversedEdge]) -> tuple[Coord, ...]:
    merged: list[Coord] = []
    for edge in edges:
        for coord in edge.coords:
            if not merged or merged[-1] != coord:
                merged.append(coord)
    if len(merged) == 1:
        merged.append(merged[0])
    return tuple(merged)


def _segment(edges: list[TraversedEdge], profile: MobilityProfile, locale: Locale) -> RouteSegment:
    codes = edge_warning_codes(edges[0], profile)
    distance = sum(edge.length_m for edge in edges)
    steepest = max(edges, key=lambda edge: abs(edge.slope_pct))
    widths = [edge.width_m for edge in edges if edge.width_m is not None]
    params = {
        "slope": round(abs(steepest.slope_pct)),
        "length": max(1, round(distance)),
        "width": f"{min(widths):.1f}" if widths else "?",
    }
    warnings = tuple(
        RouteWarning(code=code, severity=severity, message=translate(locale, f"warning.{code}", **params))
        for code, severity in codes
    )
    return RouteSegment(
        edge_ids=tuple(edge.edge_id for edge in edges),
        coords=_merge_coords(edges),
        distance_m=round(distance, 1),
        status=_edge_status(edges[0], codes),
        slope_pct=round(steepest.slope_pct, 1),
        surface_class=max(edge.surface_class for edge in edges),
        warnings=warnings,
    )


def build_segments(
    edges: tuple[TraversedEdge, ...], profile: MobilityProfile, locale: Locale
) -> tuple[RouteSegment, ...]:
    """Group consecutive edges that share status, warnings and surface."""
    groups: list[list[TraversedEdge]] = []
    previous_key: tuple[object, ...] | None = None
    for edge in edges:
        key = _group_key(edge, profile)
        if key == previous_key:
            groups[-1].append(edge)
        else:
            groups.append([edge])
            previous_key = key
    return tuple(_segment(group, profile, locale) for group in groups)


def accessibility_score(edges: tuple[TraversedEdge, ...], segments: tuple[RouteSegment, ...]) -> int:
    """100 minus the length-weighted soft penalty (x40) and 10 points per major warning."""
    total = sum(edge.length_m for edge in edges)
    mean_penalty = sum(edge.penalty * edge.length_m for edge in edges) / total if total > 0.0 else 0.0
    majors = sum(1 for segment in segments for warning in segment.warnings if warning.severity == "major")
    return round(max(0.0, min(100.0, 100.0 - mean_penalty * 40.0 - 10.0 * majors)))


def duration_seconds(edges: tuple[TraversedEdge, ...], profile: MobilityProfile) -> int:
    """Travel time using the profile speed, slowed on climbs steeper than five percent."""
    seconds = 0.0
    for edge in edges:
        factor = UPHILL_SLOW_FACTOR if edge.slope_pct > UPHILL_SLOW_THRESHOLD_PCT else 1.0
        seconds += edge.length_m / (profile.speed_mps * factor)
    return round(seconds)


def _first_bearing(coords: tuple[Coord, ...]) -> float | None:
    for index in range(len(coords) - 1):
        if coords[index] != coords[index + 1]:
            return bearing_deg(coords[index], coords[index + 1])
    return None


def _last_bearing(coords: tuple[Coord, ...]) -> float | None:
    for index in range(len(coords) - 1, 0, -1):
        if coords[index - 1] != coords[index]:
            return bearing_deg(coords[index - 1], coords[index])
    return None


def _nearest_poi(location: Coord, pois: tuple[NearbyPoi, ...]) -> NearbyPoi | None:
    best: tuple[float, NearbyPoi] | None = None
    for poi in pois:
        distance = haversine_m(location, poi.location)
        if distance <= POI_RADIUS_M and (best is None or distance < best[0]):
            best = (distance, poi)
    return best[1] if best else None


def build_instructions(
    edges: tuple[TraversedEdge, ...], pois: tuple[NearbyPoi, ...], locale: Locale
) -> tuple[RouteInstruction, ...]:
    """Emit depart, one maneuver per heading change above thirty degrees, and arrive."""
    usable = tuple(edge for edge in edges if len(edge.coords) >= 2)
    if not usable:
        return ()
    maneuvers: list[tuple[str, Coord, NearbyPoi | None]] = [("depart", usable[0].coords[0], None)]
    legs = [0.0]
    for index, edge in enumerate(usable):
        if index > 0:
            incoming = _last_bearing(usable[index - 1].coords)
            outgoing = _first_bearing(edge.coords)
            if incoming is not None and outgoing is not None:
                angle = turn_angle_deg(incoming, outgoing)
                if abs(angle) > TURN_THRESHOLD_DEG:
                    kind = "u_turn" if abs(angle) > U_TURN_THRESHOLD_DEG else ("right" if angle > 0 else "left")
                    location = edge.coords[0]
                    maneuvers.append((kind, location, _nearest_poi(location, pois)))
                    legs.append(0.0)
        legs[-1] += edge.length_m
    instructions: list[RouteInstruction] = []
    start_bearing = _first_bearing(usable[0].coords) or 0.0
    for (kind, location, poi), leg in zip(maneuvers, legs, strict=True):
        distance = max(1, round(leg))
        if kind == "depart":
            direction = translate(locale, f"direction.{_DIRECTIONS[round(start_bearing / 45.0) % 8]}")
            message = translate(locale, "instruction.depart", direction=direction, distance=distance)
        elif poi is not None and kind in ("left", "right"):
            message = translate(locale, f"instruction.{kind}_poi", poi=poi.name, distance=distance)
        else:
            message = translate(locale, f"instruction.{kind}", distance=distance)
        instructions.append(RouteInstruction(distance_m=round(leg, 1), text=message, maneuver=kind, location=location))
    instructions.append(
        RouteInstruction(
            distance_m=0.0,
            text=translate(locale, "instruction.arrive"),
            maneuver="arrive",
            location=usable[-1].coords[-1],
        )
    )
    return tuple(instructions)


def describe_route(
    edges: tuple[TraversedEdge, ...],
    profile: MobilityProfile,
    locale: Locale,
    pois: tuple[NearbyPoi, ...] = (),
) -> RouteNarrative:
    """Build the complete user-facing description of one route."""
    segments = build_segments(edges, profile, locale)
    total = sum(edge.length_m for edge in edges)
    verified = sum(edge.length_m for edge in edges if edge.verified)
    steepest = max(edges, key=lambda edge: abs(edge.slope_pct), default=None)
    return RouteNarrative(
        coords=_merge_coords(list(edges)) if edges else (),
        distance_m=round(total, 1),
        duration_s=duration_seconds(edges, profile),
        accessibility_score=accessibility_score(edges, segments),
        verified_pct=round(100.0 * verified / total, 1) if total > 0.0 else 0.0,
        max_slope_pct=round(steepest.slope_pct, 1) if steepest else 0.0,
        caution_segments=sum(1 for segment in segments if segment.status != "accessible"),
        segments=segments,
        instructions=build_instructions(edges, pois, locale),
    )
