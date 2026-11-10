"""Reproject a 360° equirectangular panorama into four perspective views (docs/05 §4)."""

import io
import math
from dataclasses import dataclass
from typing import Any

import numpy as np
from PIL import Image

VIEW_FOV_DEG = 90.0
#: Relative yaw of each view: ahead, right, behind, left.
VIEW_OFFSETS_DEG: tuple[tuple[str, float], ...] = (("front", 0.0), ("right", 90.0), ("back", 180.0), ("left", 270.0))
DEFAULT_VIEW_SIZE = 1024
#: Largest panorama decoded into memory (a 16K equirectangular image is about 128 MP).
MAX_PANORAMA_PIXELS = 140_000_000


class PanoramaTooLargeError(ValueError):
    pass


@dataclass(frozen=True)
class PerspectiveView:
    name: str
    #: Yaw relative to the center of the panorama, in degrees clockwise.
    offset_deg: float
    jpeg: bytes
    size_px: int


def perspective(equirect: Any, yaw_deg: float, size: int = DEFAULT_VIEW_SIZE, fov_deg: float = VIEW_FOV_DEG) -> Any:
    """Square pinhole view of an equirectangular array (H x W x C) looking `yaw_deg` from its center."""
    height, width = equirect.shape[:2]
    half = math.tan(math.radians(fov_deg) / 2.0)
    axis = (np.arange(size, dtype=np.float64) + 0.5) / size * 2.0 - 1.0
    u, v = np.meshgrid(axis * half, axis * half)
    yaw = math.radians(yaw_deg)
    # Ray (right=u, down=v, forward=1) rotated around the vertical axis.
    x = u * math.cos(yaw) + math.sin(yaw)
    z = -u * math.sin(yaw) + math.cos(yaw)
    longitude = np.arctan2(x, z)
    latitude = np.arctan2(-v, np.hypot(x, z))
    columns = np.floor((longitude / (2.0 * math.pi) + 0.5) * width).astype(np.int64) % width
    rows = np.clip(np.floor((0.5 - latitude / math.pi) * height).astype(np.int64), 0, height - 1)
    return equirect[rows, columns]


def split_panorama(data: bytes, size: int = DEFAULT_VIEW_SIZE, quality: int = 90) -> list[PerspectiveView]:
    """Four 90° views covering the whole horizon, as JPEG bytes."""
    with Image.open(io.BytesIO(data)) as source:
        # The size comes from the header, before any pixel is decoded.
        if source.width * source.height > MAX_PANORAMA_PIXELS:
            raise PanoramaTooLargeError("panorama larger than the allowed maximum")
        equirect = np.asarray(source.convert("RGB"))
    side = min(size, equirect.shape[0])
    views: list[PerspectiveView] = []
    for name, offset in VIEW_OFFSETS_DEG:
        buffer = io.BytesIO()
        Image.fromarray(perspective(equirect, offset, side)).save(buffer, format="JPEG", quality=quality)
        views.append(PerspectiveView(name=name, offset_deg=offset, jpeg=buffer.getvalue(), size_px=side))
    return views
