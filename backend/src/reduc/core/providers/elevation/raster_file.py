"""Elevation from a local GeoTIFF digital elevation model, with bilinear interpolation."""

import math
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pyproj import Transformer

LonLat = tuple[float, float]


class RasterFileElevation:
    """Reads the first band of a raster. The file is loaded once; campus DEMs are small."""

    def __init__(self, path: Path) -> None:
        import rasterio

        with rasterio.open(path) as dataset:
            self._band: Any = dataset.read(1).astype("float64")
            self._inverse = dataset.transform.__invert__()
            self._nodata = dataset.nodata
            crs = dataset.crs
            self.resolution_m = self._resolution_m(dataset.res, crs, dataset.bounds)
        self._to_raster = (
            None if crs is None or crs.to_epsg() == 4326 else Transformer.from_crs(4326, crs, always_xy=True)
        )

    @staticmethod
    def _resolution_m(res: tuple[float, float], crs: Any, bounds: Any) -> float:
        if crs is not None and crs.is_geographic:
            latitude = math.radians((bounds.top + bounds.bottom) / 2)
            return float(max(res[0] * 111_320.0 * math.cos(latitude), res[1] * 111_320.0))
        return float(max(res))

    def _value(self, row: int, col: int) -> float | None:
        if not (0 <= row < self._band.shape[0] and 0 <= col < self._band.shape[1]):
            return None
        value = float(self._band[row, col])
        if not math.isfinite(value) or (self._nodata is not None and value == self._nodata):
            return None
        return value

    def sample(self, points: Sequence[LonLat]) -> list[float | None]:
        results: list[float | None] = []
        for lon, lat in points:
            x, y = (lon, lat) if self._to_raster is None else self._to_raster.transform(lon, lat)
            # Pixel coordinates of the point, measured from pixel centers.
            inv = self._inverse
            col_f = inv.a * x + inv.b * y + inv.c - 0.5
            row_f = inv.d * x + inv.e * y + inv.f - 0.5
            col0, row0 = math.floor(col_f), math.floor(row_f)
            fx, fy = col_f - col0, row_f - row0
            corners = [
                (self._value(row0, col0), (1 - fx) * (1 - fy)),
                (self._value(row0, col0 + 1), fx * (1 - fy)),
                (self._value(row0 + 1, col0), (1 - fx) * fy),
                (self._value(row0 + 1, col0 + 1), fx * fy),
            ]
            usable = [(value, weight) for value, weight in corners if value is not None and weight > 0.0]
            total = sum(weight for _, weight in usable)
            # Near the border or next to nodata cells, renormalise over the valid neighbours.
            results.append(None if total <= 0.0 else sum(value * weight for value, weight in usable) / total)
        return results
