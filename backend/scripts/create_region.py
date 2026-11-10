"""Create or update a region from a GeoJSON polygon or from a center point and a radius.

    uv run python scripts/create_region.py --slug mi-campus --name "Mi campus" \
        --center -77.2899 1.2298 --radius-m 500 --elevation-path dem/mi-campus.tif

Nothing about any particular place lives in the code: the region is data (CLAUDE.md).
The region starts inactive and without a published version; run the pipeline and publish
a version to make it visible to the app.
"""

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

from geoalchemy2.elements import WKTElement
from sqlalchemy import select
from sqlalchemy.orm import Session
from structlog import get_logger

from reduc.core.db.models import Region
from reduc.core.db.session import SessionLocal

M_PER_DEG = 111_320.0
MAX_RADIUS_M = 5_000.0


def utm_srid(lon: float, lat: float) -> int:
    """EPSG code of the WGS84 UTM zone that contains the point."""
    zone = min(60, max(1, math.floor((lon + 180.0) / 6.0) + 1))
    return (32600 if lat >= 0 else 32700) + zone


def square_around(lon: float, lat: float, radius_m: float) -> list[list[list[list[float]]]]:
    """MultiPolygon coordinates of a square with the given half-side, in meters."""
    if not 0 < radius_m <= MAX_RADIUS_M:
        raise ValueError(f"El radio debe estar entre 1 y {MAX_RADIUS_M:.0f} m")
    d_lat = radius_m / M_PER_DEG
    d_lon = radius_m / (M_PER_DEG * math.cos(math.radians(lat)))
    west, east, south, north = lon - d_lon, lon + d_lon, lat - d_lat, lat + d_lat
    return [[[[west, south], [east, south], [east, north], [west, north], [west, south]]]]


def multipolygon_from_geojson(document: Any) -> list[list[list[list[float]]]]:
    """Accept a Feature, a FeatureCollection with one feature, a Polygon or a MultiPolygon."""
    if isinstance(document, dict) and document.get("type") == "FeatureCollection":
        features = document.get("features") or []
        if len(features) != 1:
            raise ValueError("El GeoJSON debe contener exactamente un polígono")
        document = features[0]
    if isinstance(document, dict) and document.get("type") == "Feature":
        document = document.get("geometry")
    if not isinstance(document, dict):
        raise ValueError("GeoJSON no válido")
    if document.get("type") == "Polygon":
        return [document["coordinates"]]
    if document.get("type") == "MultiPolygon":
        coordinates: list[list[list[list[float]]]] = document["coordinates"]
        return coordinates
    raise ValueError("La geometría debe ser Polygon o MultiPolygon")


def to_wkt(coordinates: list[list[list[list[float]]]]) -> str:
    polygons = []
    for polygon in coordinates:
        rings = []
        for ring in polygon:
            points = [(float(point[0]), float(point[1])) for point in ring]
            if len(points) < 4 or points[0] != points[-1]:
                raise ValueError("Cada anillo necesita al menos 4 puntos y debe estar cerrado")
            if any(not (-180 <= lon <= 180 and -90 <= lat <= 90) for lon, lat in points):
                raise ValueError("Coordenadas fuera de rango; el orden es [lon, lat]")
            rings.append("(" + ",".join(f"{lon!r} {lat!r}" for lon, lat in points) + ")")
        polygons.append("(" + ",".join(rings) + ")")
    if not polygons:
        raise ValueError("El polígono está vacío")
    return "MULTIPOLYGON(" + ",".join(polygons) + ")"


def default_config(elevation_path: str | None, osm_path: str | None, mapillary: bool) -> dict[str, Any]:
    return {
        "image_sources": [
            {"provider": "mapillary", "enabled": mapillary, "min_captured_at": "2021-01-01", "max_images": 20000},
            {"provider": "upload", "enabled": True},
            {"provider": "streetview", "enabled": False},
        ],
        "elevation": {"source": "raster_file", "path": elevation_path} if elevation_path else {"source": "none"},
        "osm": {"source": "file", "path": osm_path, "buffer_m": 100}
        if osm_path
        else {"source": "overpass", "buffer_m": 100},
        "thresholds": {"detection_min_score": 0.35, "fusion_radius_m": 4.0, "snap_max_m": 8.0},
    }


def upsert_region(
    session: Session,
    slug: str,
    name: str,
    coordinates: list[list[list[list[float]]]],
    config: dict[str, Any],
) -> tuple[Region, bool]:
    """Create the region, or replace name, boundary and config of an existing one."""
    if not slug or not all(character.isalnum() or character == "-" for character in slug) or slug != slug.lower():
        raise ValueError("El slug solo admite minúsculas, números y guiones")
    wkt = to_wkt(coordinates)
    first = coordinates[0][0][0]
    srid = utm_srid(float(first[0]), float(first[1]))
    region = session.scalar(select(Region).where(Region.slug == slug))
    created = region is None
    if region is None:
        region = Region(slug=slug, name=name, utm_srid=srid, config=config, is_active=False)
        session.add(region)
    else:
        region.name, region.utm_srid, region.config = name, srid, config
    region.boundary = WKTElement(wkt, srid=4326)
    session.flush()
    return region, created


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Crea o actualiza una región.")
    parser.add_argument("--slug", required=True)
    parser.add_argument("--name", required=True)
    shape = parser.add_mutually_exclusive_group(required=True)
    shape.add_argument("--geojson", type=Path, help="Archivo GeoJSON con un Polygon o MultiPolygon")
    shape.add_argument("--center", type=float, nargs=2, metavar=("LON", "LAT"))
    parser.add_argument("--radius-m", type=float, default=400.0, help="Semilado del cuadrado si se usa --center")
    parser.add_argument("--elevation-path", help="GeoTIFF relativo a REDUC_DATA_DIR o s3://bucket/clave")
    parser.add_argument("--osm-path", help="Extracto .osm.pbf local en lugar de Overpass")
    parser.add_argument("--mapillary", action="store_true", help="Habilitar Mapillary (requiere REDUC_MAPILLARY_TOKEN)")
    parser.add_argument("--active", action="store_true", help="Marcar la región como activa (visible al publicar)")
    args = parser.parse_args(argv)
    try:
        if args.geojson is not None:
            coordinates = multipolygon_from_geojson(json.loads(args.geojson.read_text(encoding="utf-8")))
        else:
            coordinates = square_around(args.center[0], args.center[1], args.radius_m)
        config = default_config(args.elevation_path, args.osm_path, args.mapillary)
        with SessionLocal() as session:
            region, created = upsert_region(session, args.slug, args.name, coordinates, config)
            if args.active:
                region.is_active = True
            session.commit()
    except (ValueError, KeyError, OSError, json.JSONDecodeError) as error:
        sys.stderr.write(f"{error}\n")
        return 2
    get_logger("reduc.scripts").info(
        "region_saved", region_id=str(region.id), slug=region.slug, utm_srid=region.utm_srid, created=created
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
