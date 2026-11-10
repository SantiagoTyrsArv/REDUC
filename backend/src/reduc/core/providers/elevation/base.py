"""Elevation sources behind one interface (docs/05-pipeline-vision.md §3)."""

from collections.abc import Sequence
from typing import Protocol

LonLat = tuple[float, float]


class ElevationSource(Protocol):
    """Samples ground elevation in meters; None where the model has no data."""

    #: Low-resolution models (e.g. SRTM 30 m) lower the confidence of the derived slopes.
    resolution_m: float

    def sample(self, points: Sequence[LonLat]) -> list[float | None]: ...


class ConstantElevation:
    """Flat terrain. Used in tests and as an explicit choice for flat regions."""

    def __init__(self, elevation_m: float = 0.0, resolution_m: float = 1.0) -> None:
        self.elevation_m = elevation_m
        self.resolution_m = resolution_m

    def sample(self, points: Sequence[LonLat]) -> list[float | None]:
        return [self.elevation_m for _ in points]
