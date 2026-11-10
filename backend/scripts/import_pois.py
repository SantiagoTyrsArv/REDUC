"""Import named places of a region from OpenStreetMap as searchable POIs.

    uv run python scripts/import_pois.py --slug mi-campus

Only POIs that came from OSM (tagged with their OSM id) are replaced on each run; places
added by hand are kept. Data © OpenStreetMap contributors (ODbL).
"""

import argparse
import sys
from collections.abc import Callable, Mapping
from typing import Any

from geoalchemy2.elements import WKTElement
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from structlog import get_logger

from reduc.core.db.models import Poi, Region
from reduc.core.db.session import SessionLocal
from reduc.core.providers.osm.overpass import DEFAULT_ENDPOINT, http_transport
from reduc.settings import get_settings

Transport = Callable[[str, str], Mapping[str, Any]]
MAX_POIS = 2000
MAX_NAME_LENGTH = 120


def build_query(bbox: tuple[float, float, float, float], timeout_s: int = 60) -> str:
    """Named buildings, amenities, shops, offices and entrances; `out center` gives one point per way."""
    west, south, east, north = bbox
    box = f"{south:.7f},{west:.7f},{north:.7f},{east:.7f}"
    selectors = (
        '["name"]["building"]',
        '["name"]["amenity"]',
        '["name"]["shop"]',
        '["name"]["office"]',
        '["entrance"]',
    )
    parts = "".join(f"nwr{selector}({box});" for selector in selectors)
    return f"[out:json][timeout:{timeout_s}];({parts});out center tags;"


def category_of(tags: Mapping[str, Any]) -> str:
    if "entrance" in tags:
        return "entrance"
    if tags.get("amenity") == "toilets":
        return "toilet"
    if tags.get("amenity") == "parking":
        return "parking"
    if "building" in tags and "amenity" not in tags and "shop" not in tags and "office" not in tags:
        return "building"
    return "service" if any(key in tags for key in ("amenity", "shop", "office")) else "building"


def parse_pois(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    """One POI per named OSM element, deduplicated by name and category."""
    pois: dict[tuple[str, str], dict[str, Any]] = {}
    for element in payload.get("elements", []):
        tags = element.get("tags") or {}
        center = element.get("center") or element
        name = str(tags.get("name") or tags.get("ref") or "").strip()[:MAX_NAME_LENGTH]
        if not name or "lat" not in center or "lon" not in center:
            continue
        category = category_of(tags)
        wheelchair = str(tags.get("wheelchair", "")).lower()
        pois.setdefault(
            (name.lower(), category),
            {
                "name": name,
                "category": category,
                "lon": float(center["lon"]),
                "lat": float(center["lat"]),
                # Only an explicit `wheelchair=yes` counts; unknown is never presented as accessible.
                "accessible_entrance": wheelchair == "yes",
                "tags": {
                    "osm": f"{element.get('type')}/{element.get('id')}",
                    **({"wheelchair": wheelchair} if wheelchair else {}),
                },
            },
        )
    return sorted(pois.values(), key=lambda poi: (poi["category"], poi["name"]))[:MAX_POIS]


def import_pois(session: Session, slug: str, transport: Transport = http_transport, endpoint: str = "") -> int:
    region = session.scalar(select(Region).where(Region.slug == slug))
    if region is None:
        raise ValueError(f"No existe la región {slug}")
    box = session.execute(
        text(
            "SELECT ST_XMin(boundary), ST_YMin(boundary), ST_XMax(boundary), ST_YMax(boundary) "
            "FROM region WHERE id = :id"
        ),
        {"id": region.id},
    ).one()
    bbox = (float(box[0]), float(box[1]), float(box[2]), float(box[3]))
    pois = parse_pois(transport(endpoint or DEFAULT_ENDPOINT, build_query(bbox)))
    session.execute(text("DELETE FROM poi WHERE region_id = :id AND tags ? 'osm'"), {"id": region.id})
    inside = 0
    for poi in pois:
        within = session.execute(
            text("SELECT ST_Covers(boundary, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)) FROM region WHERE id = :id"),
            {"id": region.id, "lon": poi["lon"], "lat": poi["lat"]},
        ).scalar_one()
        if not within:
            continue
        session.add(
            Poi(
                region_id=region.id,
                name=poi["name"],
                category=poi["category"],
                geom=WKTElement(f"POINT({poi['lon']!r} {poi['lat']!r})", srid=4326),
                accessible_entrance=poi["accessible_entrance"],
                tags=poi["tags"],
            )
        )
        inside += 1
    session.flush()
    return inside


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Importa lugares con nombre de OSM como POIs de una región.")
    parser.add_argument("--slug", required=True)
    args = parser.parse_args(argv)
    try:
        with SessionLocal() as session:
            count = import_pois(session, args.slug, endpoint=get_settings().overpass_endpoint)
            session.commit()
    except ValueError as error:
        sys.stderr.write(f"{error}\n")
        return 2
    get_logger("reduc.scripts").info("pois_imported", slug=args.slug, pois=count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
