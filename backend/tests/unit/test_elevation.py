"""Elevation sampling and slope computation (docs/05 §3), on synthetic terrain."""

from pathlib import Path

import numpy as np
import pytest
import rasterio
from pyproj import Transformer
from rasterio.transform import from_origin

from reduc.core.domain.elevation import edge_slope, fill_gaps, parse_incline, sample_line, smooth
from reduc.core.providers.elevation.base import ConstantElevation
from reduc.core.providers.elevation.raster_file import RasterFileElevation

# 1e-5 degrees of longitude at the equator, in meters.
M_PER_1E5_DEG = 1.1132


def write_plane(path: Path, slope_east_pct: float, crs: str = "EPSG:4326", nodata_block: bool = False) -> None:
    """A tilted plane rising towards the east, 1 m cells, covering ~220 m x 110 m at (0, 0)."""
    cell = 1e-5 / M_PER_1E5_DEG if crs == "EPSG:4326" else 1.0
    width, height = 220, 110
    columns = np.arange(width, dtype="float32") + 0.5
    band = np.tile(100.0 + columns * slope_east_pct / 100.0, (height, 1)).astype("float32")
    if nodata_block:
        band[:, 60:64] = -9999.0
    west = 0.0 if crs == "EPSG:4326" else 500000.0
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=width,
        height=height,
        count=1,
        dtype="float32",
        crs=crs,
        transform=from_origin(west, height * cell, cell, cell),
        nodata=-9999.0,
    ) as dataset:
        dataset.write(band, 1)


def lon_at(meters: float) -> float:
    return meters * 1e-5 / M_PER_1E5_DEG


def test_sample_line_covers_both_ends_at_five_meter_spacing() -> None:
    points, distances = sample_line([(0.0, 0.0), (lon_at(50.0), 0.0)])

    assert len(points) == 11
    assert points[0] == (0.0, 0.0)
    assert points[-1] == pytest.approx((lon_at(50.0), 0.0))
    assert distances == pytest.approx([5.0 * i for i in range(11)], abs=0.1)
    # A bend keeps the samples on the line.
    bent, bent_distances = sample_line([(0.0, 0.0), (lon_at(10.0), 0.0), (lon_at(10.0), lon_at(10.0))])
    assert bent_distances[-1] == pytest.approx(20.0, abs=0.15)
    assert bent[2] == pytest.approx((lon_at(10.0), 0.0), abs=1e-6)
    with pytest.raises(ValueError, match="two points"):
        sample_line([(0.0, 0.0)])


def test_smoothing_removes_a_single_spike() -> None:
    assert smooth([10.0, 10.0, 15.0, 10.0, 10.0]) == [10.0, 10.0, 10.0, 10.0, 10.0]
    assert smooth([1.0, 2.0]) == [1.0, 2.0]


def test_fill_gaps_interpolates_and_requires_two_samples() -> None:
    assert fill_gaps([None, 1.0, None, 3.0, None]) == [1.0, 1.0, 2.0, 3.0, 3.0]
    assert fill_gaps([None, 1.0, None]) is None


def test_uniform_incline_gives_the_same_global_and_maximum_slope(tmp_path: Path) -> None:
    """Acceptance of T-21: a synthetic tilted raster yields the slope it was built with."""
    path = tmp_path / "plane.tif"
    write_plane(path, slope_east_pct=5.0)
    source = RasterFileElevation(path)
    points, distances = sample_line([(lon_at(20.0), lon_at(50.0)), (lon_at(120.0), lon_at(50.0))])

    slope = edge_slope(distances, source.sample(points))

    assert slope is not None
    assert slope.slope_pct == pytest.approx(5.0, abs=0.05)
    assert slope.max_slope_pct == pytest.approx(5.0, abs=0.05)
    assert source.resolution_m == pytest.approx(1.0, abs=0.01)
    # Walking the same edge westwards is a descent of the same magnitude.
    reverse_points, reverse_distances = sample_line([(lon_at(120.0), lon_at(50.0)), (lon_at(20.0), lon_at(50.0))])
    reverse = edge_slope(reverse_distances, source.sample(reverse_points))
    assert reverse is not None and reverse.slope_pct == pytest.approx(-5.0, abs=0.05)
    # An edge along the contour line is flat.
    flat_points, flat_distances = sample_line([(lon_at(50.0), lon_at(20.0)), (lon_at(50.0), lon_at(90.0))])
    flat = edge_slope(flat_distances, source.sample(flat_points))
    assert flat is not None and abs(flat.slope_pct) < 0.01 and abs(flat.max_slope_pct) < 0.01


def test_projected_rasters_are_sampled_through_their_crs(tmp_path: Path) -> None:
    path = tmp_path / "utm.tif"
    write_plane(path, slope_east_pct=8.0, crs="EPSG:32631")
    source = RasterFileElevation(path)
    to_wgs = Transformer.from_crs(32631, 4326, always_xy=True)
    start, end = to_wgs.transform(500020.0, 50.0), to_wgs.transform(500120.0, 50.0)
    points, distances = sample_line([start, end])

    slope = edge_slope(distances, source.sample(points))

    assert slope is not None
    assert slope.slope_pct == pytest.approx(8.0, abs=0.1)
    assert source.resolution_m == 1.0


def test_maximum_slope_finds_a_short_steep_ramp() -> None:
    # 40 m flat, 10 m at 12 %, 50 m flat: 1.2 % overall but 12 % over the steepest 10 m.
    distances = [5.0 * i for i in range(21)]
    elevations: list[float | None] = [0.0 if d <= 40 else min(1.2, (d - 40) * 0.12) for d in distances]

    slope = edge_slope(distances, elevations)

    assert slope is not None
    assert slope.slope_pct == pytest.approx(1.2, abs=0.01)
    assert slope.max_slope_pct == pytest.approx(12.0, abs=0.01)
    downhill = edge_slope(distances, [-(value or 0.0) for value in elevations])
    assert downhill is not None and downhill.max_slope_pct == pytest.approx(-12.0, abs=0.01)


def test_nodata_cells_are_bridged_and_points_outside_are_unknown(tmp_path: Path) -> None:
    path = tmp_path / "holes.tif"
    write_plane(path, slope_east_pct=5.0, nodata_block=True)
    source = RasterFileElevation(path)
    points, distances = sample_line([(lon_at(20.0), lon_at(50.0)), (lon_at(120.0), lon_at(50.0))])

    slope = edge_slope(distances, source.sample(points))

    assert slope is not None and slope.slope_pct == pytest.approx(5.0, abs=0.1)
    assert source.sample([(1.0, 1.0)]) == [None]
    assert edge_slope([0.0, 5.0], [None, None]) is None
    assert edge_slope([0.0, 0.0], [1.0, 2.0]) is None
    with pytest.raises(ValueError, match="same length"):
        edge_slope([0.0], [1.0, 2.0])


def test_constant_elevation_is_flat() -> None:
    source = ConstantElevation(12.0)
    slope = edge_slope([0.0, 5.0, 10.0], source.sample([(0, 0), (0, 0), (0, 0)]))
    assert slope is not None and slope.slope_pct == 0.0 and slope.max_slope_pct == 0.0


@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        ("5%", 5.0),
        ("-3.5 %", -3.5),
        ("8", 8.0),
        ("2,5%", 2.5),
        ("10°", 17.63),
        ("-5deg", -8.75),
        ("up", None),
        ("down", None),
        ("steep", None),
        ("400%", None),
        ("90°", None),
        (None, None),
    ],
)
def test_parse_incline(tag: str | None, expected: float | None) -> None:
    assert parse_incline(tag) == expected
