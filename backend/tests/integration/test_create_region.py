"""Creating regions from a polygon or a center point (alta de región para el MVP)."""

import pytest
from scripts.create_region import (
    default_config,
    multipolygon_from_geojson,
    square_around,
    upsert_region,
    utm_srid,
)
from sqlalchemy import text
from sqlalchemy.orm import Session


def test_utm_zone_follows_the_point() -> None:
    assert utm_srid(-74.07, 4.6) == 32618
    assert utm_srid(-77.29, 1.23) == 32618
    assert utm_srid(-77.29, -1.23) == 32718
    assert utm_srid(0.5, 0.0) == 32631


def test_square_and_geojson_shapes() -> None:
    square = square_around(-77.29, 1.23, 500.0)
    ring = square[0][0]
    assert ring[0] == ring[-1] and len(ring) == 5
    assert (ring[2][1] - ring[0][1]) * 111_320.0 == pytest.approx(1000.0, abs=0.5)
    polygon = {"type": "Polygon", "coordinates": square[0]}
    assert multipolygon_from_geojson({"type": "Feature", "geometry": polygon}) == square
    assert (
        multipolygon_from_geojson({"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": polygon}]})
        == square
    )
    assert multipolygon_from_geojson({"type": "MultiPolygon", "coordinates": square}) == square
    for bad in ({"type": "Point", "coordinates": [0, 0]}, {"type": "FeatureCollection", "features": []}, []):
        with pytest.raises(ValueError):
            multipolygon_from_geojson(bad)
    with pytest.raises(ValueError, match="radio"):
        square_around(0.0, 0.0, 50_000.0)


def test_region_is_created_inactive_and_updated_in_place(db_session: Session) -> None:
    config = default_config("dem/prueba.tif", None, mapillary=False)

    region, created = upsert_region(db_session, "prueba-alta", "Prueba", square_around(-77.29, 1.23, 300.0), config)
    again, created_again = upsert_region(
        db_session, "prueba-alta", "Prueba 2", square_around(-77.29, 1.23, 600.0), config
    )

    assert (created, created_again) == (True, False)
    assert again.id == region.id and again.name == "Prueba 2"
    assert (region.is_active, region.published_version_id, region.utm_srid) == (False, None, 32618)
    assert config["image_sources"][2] == {"provider": "streetview", "enabled": False}
    assert config["elevation"] == {"source": "raster_file", "path": "dem/prueba.tif"}
    side = db_session.execute(
        text("SELECT sqrt(ST_Area(boundary::geography)) FROM region WHERE id = :id"), {"id": region.id}
    ).scalar_one()
    assert side == pytest.approx(1200.0, rel=0.01)


@pytest.mark.parametrize("slug", ["Con Espacios", "MAYUS", "", "raro_/../"])
def test_invalid_slugs_and_rings_are_rejected(db_session: Session, slug: str) -> None:
    with pytest.raises(ValueError, match="slug"):
        upsert_region(db_session, slug, "x", square_around(0.1, 0.1, 100.0), {})
    with pytest.raises(ValueError, match="anillo"):
        upsert_region(db_session, "abierto", "x", [[[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]]]], {})
