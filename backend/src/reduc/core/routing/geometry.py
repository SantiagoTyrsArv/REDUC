"""Small pure geometry helpers over WGS84 lon/lat coordinates."""

import math

Coord = tuple[float, float]
EARTH_RADIUS_M = 6_371_008.8


def haversine_m(a: Coord, b: Coord) -> float:
    """Great-circle distance in meters between two lon/lat points."""
    lat1, lat2 = math.radians(a[1]), math.radians(b[1])
    delta_lat = lat2 - lat1
    delta_lon = math.radians(b[0] - a[0])
    h = math.sin(delta_lat / 2.0) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2.0) ** 2
    return 2.0 * EARTH_RADIUS_M * math.asin(math.sqrt(min(1.0, h)))


def bearing_deg(a: Coord, b: Coord) -> float:
    """Initial bearing from a to b in degrees, 0 = north, clockwise."""
    lat1, lat2 = math.radians(a[1]), math.radians(b[1])
    delta_lon = math.radians(b[0] - a[0])
    y = math.sin(delta_lon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(delta_lon)
    return math.degrees(math.atan2(y, x)) % 360.0


def turn_angle_deg(bearing_in: float, bearing_out: float) -> float:
    """Signed heading change in (-180, 180]; positive means a turn to the right."""
    delta = (bearing_out - bearing_in + 180.0) % 360.0 - 180.0
    return 180.0 if delta == -180.0 else delta


def destination_point(origin: Coord, bearing: float, distance_m: float) -> Coord:
    """Geodesic destination on a sphere; accurate to centimeters at street scale."""
    angular = distance_m / EARTH_RADIUS_M
    theta = math.radians(bearing)
    lat1, lon1 = math.radians(origin[1]), math.radians(origin[0])
    lat2 = math.asin(math.sin(lat1) * math.cos(angular) + math.cos(lat1) * math.sin(angular) * math.cos(theta))
    lon2 = lon1 + math.atan2(
        math.sin(theta) * math.sin(angular) * math.cos(lat1),
        math.cos(angular) - math.sin(lat1) * math.sin(lat2),
    )
    return (math.degrees(lon2), math.degrees(lat2))


def line_length_m(coords: tuple[Coord, ...] | list[Coord]) -> float:
    """Length in meters of a polyline."""
    return sum(haversine_m(coords[i], coords[i + 1]) for i in range(len(coords) - 1))


def cut_line(coords: tuple[Coord, ...], start: float, end: float) -> tuple[Coord, ...]:
    """Return the part of a polyline between two planar fractions, like ST_LineSubstring."""
    start, end = max(0.0, min(1.0, start)), max(0.0, min(1.0, end))
    if end < start:
        raise ValueError("end must not be smaller than start")
    if len(coords) < 2:
        return coords
    lengths = [math.dist(coords[i], coords[i + 1]) for i in range(len(coords) - 1)]
    total = sum(lengths)
    if total == 0.0:
        return (coords[0], coords[-1])
    start_d, end_d = start * total, end * total
    result: list[Coord] = []
    walked = 0.0
    for index, length in enumerate(lengths):
        a, b = coords[index], coords[index + 1]
        seg_start, seg_end = walked, walked + length
        walked = seg_end
        if seg_end < start_d or seg_start > end_d or length == 0.0:
            continue
        lo = max(start_d, seg_start)
        hi = min(end_d, seg_end)
        for d in (lo, hi):
            t = (d - seg_start) / length
            point = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
            if not result or result[-1] != point:
                result.append(point)
    if len(result) == 1:
        result.append(result[0])
    return tuple(result)
