"""Project a detection from image pixels to a point on the ground (docs/05 §7).

The spec gives the small-angle form (`bearing = heading + (x/width - 0.5)·fov`). This module
uses the exact pinhole model, which reduces to that formula near the image center and stays
accurate towards the borders. Flat ground at the camera's foot is assumed.
"""

import math
from dataclasses import dataclass

from pyproj import Geod

MIN_DISTANCE_M = 1.0
MAX_DISTANCE_M = 25.0
DISTANCE_ERROR_FACTOR = 0.15
#: Typical horizontal error of the camera position per image source, in meters.
SOURCE_GPS_ERROR_M = {"mapillary": 2.0, "upload": 5.0, "streetview": 2.0}
DEFAULT_GPS_ERROR_M = 5.0
DEFAULT_FOV_DEG = 70.0

_GEOD = Geod(ellps="WGS84")


@dataclass(frozen=True)
class CameraPose:
    """Where the camera was and how it was oriented.

    `pitch_deg` is the depression angle: positive when the camera looks below the horizon.
    `fov_deg` is the horizontal field of view.
    """

    lon: float
    lat: float
    heading_deg: float
    width_px: int
    height_px: int
    pitch_deg: float = 0.0
    fov_deg: float = DEFAULT_FOV_DEG
    camera_height_m: float = 2.0
    gps_error_m: float = DEFAULT_GPS_ERROR_M


@dataclass(frozen=True)
class GroundPoint:
    lon: float
    lat: float
    distance_m: float
    bearing_deg: float
    error_m: float
    #: False when the ray did not reach the ground and the distance is the clamp limit.
    on_ground: bool


def vertical_fov_deg(fov_deg: float, width_px: int, height_px: int) -> float:
    return math.degrees(2.0 * math.atan(math.tan(math.radians(fov_deg) / 2.0) * height_px / width_px))


def locate(pose: CameraPose, bbox: tuple[float, float, float, float]) -> GroundPoint:
    """Ground position of the object whose bounding box is `(x1, y1, x2, y2)` in pixels.

    The bottom center of the box is taken as the contact point with the ground.
    """
    x1, _, x2, y2 = bbox
    half_h = math.tan(math.radians(pose.fov_deg) / 2.0)
    half_v = half_h * pose.height_px / pose.width_px
    # Normalized image coordinates: u to the right, v downwards, unit forward distance.
    u = ((x1 + x2) / 2.0 / pose.width_px - 0.5) * 2.0 * half_h
    v = (y2 / pose.height_px - 0.5) * 2.0 * half_v

    pitch = math.radians(pose.pitch_deg)
    down = math.sin(pitch) + v * math.cos(pitch)
    forward = math.cos(pitch) - v * math.sin(pitch)
    on_ground = down > 1e-6 and forward > 0.0
    if on_ground:
        scale = pose.camera_height_m / down
        distance = math.hypot(scale * forward, scale * u)
        on_ground = distance <= MAX_DISTANCE_M
    else:
        distance = MAX_DISTANCE_M
    distance = min(MAX_DISTANCE_M, max(MIN_DISTANCE_M, distance))

    bearing = (pose.heading_deg + math.degrees(math.atan2(u, max(forward, 1e-9)))) % 360.0
    lon, lat, _ = _GEOD.fwd(pose.lon, pose.lat, bearing, distance)
    return GroundPoint(
        lon=lon,
        lat=lat,
        distance_m=distance,
        bearing_deg=bearing,
        error_m=round(DISTANCE_ERROR_FACTOR * distance + pose.gps_error_m, 2),
        on_ground=on_ground,
    )


def project_to_image(pose: CameraPose, lon: float, lat: float) -> tuple[float, float] | None:
    """Inverse of `locate`: pixel where a ground point appears, or None when it is not in view.

    Used by tests and by the review tools to draw a known barrier on a photo.
    """
    azimuth, _, distance = _GEOD.inv(pose.lon, pose.lat, lon, lat)
    relative = math.radians((azimuth - pose.heading_deg + 180.0) % 360.0 - 180.0)
    ahead = distance * math.cos(relative)
    right = distance * math.sin(relative)
    pitch = math.radians(pose.pitch_deg)
    # World offset (ahead, right, -height) expressed in the camera frame.
    forward = ahead * math.cos(pitch) + pose.camera_height_m * math.sin(pitch)
    down = -ahead * math.sin(pitch) + pose.camera_height_m * math.cos(pitch)
    if forward <= 0.0:
        return None
    half_h = math.tan(math.radians(pose.fov_deg) / 2.0)
    half_v = half_h * pose.height_px / pose.width_px
    x = (right / forward / (2.0 * half_h) + 0.5) * pose.width_px
    y = (down / forward / (2.0 * half_v) + 0.5) * pose.height_px
    if not (0.0 <= x <= pose.width_px and 0.0 <= y <= pose.height_px):
        return None
    return x, y
