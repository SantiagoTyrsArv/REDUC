"""Slope of an edge from an elevation profile (docs/05-pipeline-vision.md §3). Pure logic."""

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from statistics import median

SAMPLE_SPACING_M = 5.0
SLOPE_WINDOW_M = 10.0
EARTH_RADIUS_M = 6_371_008.8

LonLat = tuple[float, float]


@dataclass(frozen=True)
class EdgeSlope:
    """Signed slopes in the source→target direction, in percent."""

    slope_pct: float
    max_slope_pct: float


def _haversine_m(a: LonLat, b: LonLat) -> float:
    d_lat = math.radians(b[1] - a[1])
    d_lon = math.radians(b[0] - a[0])
    h = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(a[1])) * math.cos(math.radians(b[1])) * math.sin(d_lon / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(min(1.0, h)))


def sample_line(coords: Sequence[LonLat], spacing_m: float = SAMPLE_SPACING_M) -> tuple[list[LonLat], list[float]]:
    """Points every `spacing_m` along a polyline, always including both ends.

    Returns the points and their distance from the start. The spacing is shrunk slightly so the
    samples are evenly distributed over the whole length.
    """
    if len(coords) < 2:
        raise ValueError("A line needs at least two points")
    lengths = [_haversine_m(coords[i - 1], coords[i]) for i in range(1, len(coords))]
    total = sum(lengths)
    if total <= 0.0:
        return [coords[0], coords[-1]], [0.0, 0.0]
    intervals = max(1, math.ceil(total / spacing_m - 1e-9))
    targets = [total * k / intervals for k in range(intervals + 1)]
    points: list[LonLat] = []
    walked = 0.0
    segment = 0
    for target in targets:
        while segment < len(lengths) - 1 and walked + lengths[segment] < target:
            walked += lengths[segment]
            segment += 1
        length = lengths[segment]
        t = 0.0 if length == 0.0 else min(1.0, max(0.0, (target - walked) / length))
        start, end = coords[segment], coords[segment + 1]
        points.append((start[0] + (end[0] - start[0]) * t, start[1] + (end[1] - start[1]) * t))
    return points, targets


def smooth(values: Sequence[float]) -> list[float]:
    """Moving median of 3; the two ends are kept as measured."""
    if len(values) < 3:
        return list(values)
    return [values[0], *(median(values[i - 1 : i + 2]) for i in range(1, len(values) - 1)), values[-1]]


def fill_gaps(values: Sequence[float | None]) -> list[float] | None:
    """Linearly fill missing samples; None when fewer than two samples are known."""
    known = [(index, value) for index, value in enumerate(values) if value is not None and math.isfinite(value)]
    if len(known) < 2:
        return None
    filled: list[float] = []
    for index in range(len(values)):
        before = [item for item in known if item[0] <= index]
        after = [item for item in known if item[0] >= index]
        if not before:
            filled.append(after[0][1])
        elif not after or before[-1][0] == after[0][0]:
            filled.append(before[-1][1])
        else:
            (i0, v0), (i1, v1) = before[-1], after[0]
            filled.append(v0 + (v1 - v0) * (index - i0) / (i1 - i0))
    return filled


def edge_slope(
    distances_m: Sequence[float], elevations_m: Sequence[float | None], window_m: float = SLOPE_WINDOW_M
) -> EdgeSlope | None:
    """Global slope and the steepest slope over any `window_m` stretch.

    `max_slope_pct` keeps the sign of the steepest window so that traversing the edge backwards
    is simply its negation. Returns None when the profile has too few valid samples.
    """
    if len(distances_m) != len(elevations_m):
        raise ValueError("distances and elevations must have the same length")
    filled = fill_gaps(elevations_m)
    total = distances_m[-1] - distances_m[0] if distances_m else 0.0
    if filled is None or total <= 0.0:
        return None
    profile = smooth(filled)
    overall = 100.0 * (profile[-1] - profile[0]) / total

    steepest = overall
    if total > window_m:
        steepest = 0.0
        for start in range(len(profile)):
            # First sample at least one window away; the profile is evenly spaced.
            end = next(
                (j for j in range(start + 1, len(profile)) if distances_m[j] - distances_m[start] >= window_m - 1e-6),
                None,
            )
            if end is None:
                break
            slope = 100.0 * (profile[end] - profile[start]) / (distances_m[end] - distances_m[start])
            if abs(slope) > abs(steepest):
                steepest = slope
    return EdgeSlope(slope_pct=round(overall, 2), max_slope_pct=round(steepest, 2))


_INCLINE_NUMBER = re.compile(r"^\s*([+-]?\d+(?:[.,]\d+)?)\s*(%|°|deg)?\s*$")


def parse_incline(tag: str | None) -> float | None:
    """Slope in percent from an OSM `incline` value, or None when it carries no magnitude.

    `up`/`down` only give a direction, so they do not override the elevation model.
    """
    if tag is None:
        return None
    match = _INCLINE_NUMBER.match(tag)
    if match is None:
        return None
    value = float(match.group(1).replace(",", "."))
    if match.group(2) in {"°", "deg"}:
        if abs(value) >= 89.0:
            return None
        value = 100.0 * math.tan(math.radians(value))
    return round(value, 2) if abs(value) <= 100.0 else None
