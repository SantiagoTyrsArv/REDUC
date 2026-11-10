"""Vector tile functions served by Martin (docs/04-api.md §2), checked on the seed."""

import math

from sqlalchemy import text
from sqlalchemy.orm import Session

SEED_LON = -74.0639
SEED_LAT = 4.6021
ZOOM = 15


def tile_of(lon: float, lat: float, zoom: int) -> tuple[int, int]:
    """Return the XYZ tile containing a WGS84 coordinate."""
    n = 2**zoom
    x = int((lon + 180.0) / 360.0 * n)
    lat_rad = math.radians(lat)
    y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return x, y


def fetch_tile(session: Session, function: str, x: int, y: int) -> bytes:
    """Call a tile function the same way Martin does."""
    assert function in {"tiles_edge_accessibility", "tiles_barrier"}
    result = session.execute(text(f"SELECT {function}(:z, :x, :y)"), {"z": ZOOM, "x": x, "y": y}).scalar_one()
    return bytes(result)


def test_edge_tile_contains_layer_and_properties(db_session: Session) -> None:
    """The seed tile is a non-empty MVT with the documented layer and property names."""
    x, y = tile_of(SEED_LON, SEED_LAT, ZOOM)
    tile = fetch_tile(db_session, "tiles_edge_accessibility", x, y)

    assert len(tile) > 0
    for name in (b"edge_accessibility", b"status", b"slope_pct", b"surface_class", b"verified", b"kind"):
        assert name in tile
    # Status values are encoded as plain strings in the MVT value table.
    assert b"accessible" in tile
    assert b"inaccessible" in tile


def test_barrier_tile_contains_layer_and_properties(db_session: Session) -> None:
    """Barriers of the published version are exposed with their documented properties."""
    x, y = tile_of(SEED_LON, SEED_LAT, ZOOM)
    tile = fetch_tile(db_session, "tiles_barrier", x, y)

    assert len(tile) > 0
    for name in (b"barrier", b"class", b"severity", b"verification_status", b"stairs"):
        assert name in tile


def test_tiles_outside_the_region_are_empty(db_session: Session) -> None:
    """A tile far from any region carries no features."""
    x, y = tile_of(10.0, 50.0, ZOOM)

    assert fetch_tile(db_session, "tiles_edge_accessibility", x, y) == b""
    assert fetch_tile(db_session, "tiles_barrier", x, y) == b""


def test_tiles_only_expose_the_published_version(db_session: Session) -> None:
    """Unpublishing the region hides its edges and barriers; the session rolls back afterwards."""
    x, y = tile_of(SEED_LON, SEED_LAT, ZOOM)
    db_session.execute(text("UPDATE region SET published_version_id = NULL"))

    assert fetch_tile(db_session, "tiles_edge_accessibility", x, y) == b""
    assert fetch_tile(db_session, "tiles_barrier", x, y) == b""
