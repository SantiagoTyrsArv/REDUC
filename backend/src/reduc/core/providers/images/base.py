"""Street-level image sources behind one interface (docs/05 §4)."""

import math
from collections import defaultdict
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

Bbox = tuple[float, float, float, float]

DEDUPE_DISTANCE_M = 3.0
DEDUPE_HEADING_DEG = 20.0
MAX_CELL_DEG = 0.01
M_PER_DEG = 111_320.0


class ProviderDisabledError(Exception):
    """The provider is switched off or lacks credentials; nothing was requested."""


class ImageRejectedError(Exception):
    """An image cannot be used; the message is safe to show to the person who uploaded it."""


@dataclass(frozen=True)
class ImageMeta:
    """What is known about an image before downloading it."""

    provider: str
    external_id: str
    captured_at: datetime
    lon: float
    lat: float
    heading_deg: float | None
    width_px: int
    height_px: int
    license: str
    attribution: str | None = None
    is_panorama: bool = False
    pitch_deg: float | None = None
    fov_deg: float | None = None
    camera_height_m: float = 2.0
    #: Provider-specific handle used by `fetch` (a URL, a key...). Never stored.
    source: Any = field(default=None, compare=False, repr=False)


class Boundary(Protocol):
    """The part of a shapely geometry the providers need."""

    @property
    def bounds(self) -> tuple[float, float, float, float]: ...

    def covers(self, other: Any) -> bool: ...


class ImageProvider(Protocol):
    name: str

    def list_images(self, boundary: Boundary, since: datetime | None) -> Iterator[ImageMeta]: ...

    def fetch(self, meta: ImageMeta) -> bytes: ...

    def can_store(self) -> bool:
        """Whether the licence allows keeping a copy of the image."""
        ...


def split_cells(bbox: Bbox, max_deg: float = MAX_CELL_DEG) -> list[Bbox]:
    """Cover a box with cells no larger than `max_deg` on each side, west→east then south→north."""
    west, south, east, north = bbox
    columns = max(1, math.ceil((east - west) / max_deg - 1e-9))
    rows = max(1, math.ceil((north - south) / max_deg - 1e-9))
    width, height = (east - west) / columns, (north - south) / rows
    return [
        (west + column * width, south + row * height, west + (column + 1) * width, south + (row + 1) * height)
        for row in range(rows)
        for column in range(columns)
    ]


def heading_difference(a: float, b: float) -> float:
    return abs((a - b + 180.0) % 360.0 - 180.0)


def dedupe(images: Iterable[ImageMeta]) -> list[ImageMeta]:
    """Drop near-duplicates: closer than 3 m and within 20° of heading, keeping the most recent.

    Two images without heading at the same spot are also duplicates; an image with heading
    and one without are kept, since they may look in different directions.
    """
    kept: list[ImageMeta] = []
    grid: dict[tuple[int, int], list[ImageMeta]] = defaultdict(list)
    ordered = sorted(images, key=lambda item: (item.captured_at, item.external_id), reverse=True)
    for image in ordered:
        x = image.lon * M_PER_DEG * math.cos(math.radians(image.lat))
        y = image.lat * M_PER_DEG
        cell = (math.floor(x / DEDUPE_DISTANCE_M), math.floor(y / DEDUPE_DISTANCE_M))
        duplicate = False
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for other in grid.get((cell[0] + dx, cell[1] + dy), ()):
                    ox = other.lon * M_PER_DEG * math.cos(math.radians(other.lat))
                    if math.hypot(x - ox, y - other.lat * M_PER_DEG) >= DEDUPE_DISTANCE_M:
                        continue
                    if image.heading_deg is None or other.heading_deg is None:
                        duplicate = image.heading_deg is None and other.heading_deg is None
                    else:
                        duplicate = heading_difference(image.heading_deg, other.heading_deg) < DEDUPE_HEADING_DEG
                    if duplicate:
                        break
                if duplicate:
                    break
            if duplicate:
                break
        if not duplicate:
            kept.append(image)
            grid[cell].append(image)
    return sorted(kept, key=lambda item: (item.captured_at, item.external_id))


class FakeImageProvider:
    """In-memory provider for tests and offline development."""

    def __init__(
        self,
        images: Sequence[tuple[ImageMeta, bytes]],
        name: str = "upload",
        storable: bool = True,
        failing: Iterable[str] = (),
    ) -> None:
        self.name = name
        self._images = {meta.external_id: (meta, data) for meta, data in images}
        self._storable = storable
        self._failing = set(failing)
        self.fetched: list[str] = []

    def list_images(self, boundary: Boundary, since: datetime | None) -> Iterator[ImageMeta]:
        from shapely.geometry import Point

        for meta, _ in self._images.values():
            if since is not None and meta.captured_at < since:
                continue
            if boundary.covers(Point(meta.lon, meta.lat)):
                yield meta

    def fetch(self, meta: ImageMeta) -> bytes:
        self.fetched.append(meta.external_id)
        if meta.external_id in self._failing:
            raise OSError("simulated download failure")
        return self._images[meta.external_id][1]

    def can_store(self) -> bool:
        return self._storable
