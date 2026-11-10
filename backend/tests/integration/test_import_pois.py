"""Importing POIs from a recorded Overpass response (no network)."""

from typing import Any

import pytest
from scripts.create_region import square_around, upsert_region
from scripts.import_pois import build_query, category_of, import_pois, parse_pois
from sqlalchemy import select
from sqlalchemy.orm import Session

from reduc.core.db.models import Poi

#: Shape of an Overpass `out center tags` response; names and ids are synthetic.
PAYLOAD: dict[str, Any] = {
    "elements": [
        {
            "type": "way",
            "id": 1,
            "center": {"lat": 0.1001, "lon": 0.1001},
            "tags": {"name": "Bloque A", "building": "university"},
        },
        {
            "type": "node",
            "id": 2,
            "lat": 0.1002,
            "lon": 0.1002,
            "tags": {"name": "Biblioteca", "amenity": "library", "wheelchair": "yes"},
        },
        {
            "type": "node",
            "id": 3,
            "lat": 0.1003,
            "lon": 0.1003,
            "tags": {"entrance": "main", "ref": "Entrada norte", "wheelchair": "no"},
        },
        {"type": "node", "id": 4, "lat": 0.1004, "lon": 0.1004, "tags": {"name": "Baños", "amenity": "toilets"}},
        {
            "type": "way",
            "id": 5,
            "center": {"lat": 0.1005, "lon": 0.1005},
            "tags": {"name": "Parqueadero", "amenity": "parking"},
        },
        {"type": "node", "id": 6, "lat": 0.1001, "lon": 0.1001, "tags": {"name": "bloque a", "building": "yes"}},
        {"type": "node", "id": 7, "lat": 0.1001, "lon": 0.1001, "tags": {"entrance": "yes"}},
        {"type": "node", "id": 8, "lat": 0.9, "lon": 0.9, "tags": {"name": "Fuera de la región", "shop": "kiosk"}},
        {"type": "way", "id": 9, "tags": {"name": "Sin posición", "building": "yes"}},
    ]
}


def test_query_and_categories() -> None:
    query = build_query((-77.3, 1.2, -77.2, 1.3))
    assert "(1.2000000,-77.3000000,1.3000000,-77.2000000)" in query and "out center tags" in query
    assert category_of({"entrance": "main"}) == "entrance"
    assert category_of({"amenity": "toilets"}) == "toilet"
    assert category_of({"building": "yes", "amenity": "cafe"}) == "service"
    assert category_of({"building": "yes"}) == "building"


def test_parse_keeps_named_places_once() -> None:
    pois = parse_pois(PAYLOAD)

    assert [(poi["name"], poi["category"]) for poi in pois] == [
        ("Bloque A", "building"),
        ("Entrada norte", "entrance"),
        ("Parqueadero", "parking"),
        ("Biblioteca", "service"),
        ("Fuera de la región", "service"),
        ("Baños", "toilet"),
    ]
    by_name = {poi["name"]: poi for poi in pois}
    # Accessibility is only claimed when OSM says so explicitly.
    assert by_name["Biblioteca"]["accessible_entrance"] is True
    assert by_name["Entrada norte"]["accessible_entrance"] is False
    assert by_name["Bloque A"]["accessible_entrance"] is False
    assert by_name["Bloque A"]["tags"] == {"osm": "way/1"}


def test_import_replaces_only_osm_pois_inside_the_region(db_session: Session) -> None:
    region, _ = upsert_region(db_session, "prueba-pois", "Prueba", square_around(0.1, 0.1, 400.0), {})
    manual = Poi(
        region_id=region.id,
        name="Punto manual",
        category="service",
        geom="SRID=4326;POINT(0.1 0.1)",
        accessible_entrance=True,
        tags={},
    )
    db_session.add(manual)
    db_session.flush()
    requests: list[str] = []

    def transport(_endpoint: str, query: str) -> dict[str, Any]:
        requests.append(query)
        return PAYLOAD

    assert import_pois(db_session, "prueba-pois", transport) == 5
    assert import_pois(db_session, "prueba-pois", transport) == 5

    names = sorted(db_session.scalars(select(Poi.name).where(Poi.region_id == region.id)))
    assert names == ["Baños", "Biblioteca", "Bloque A", "Entrada norte", "Parqueadero", "Punto manual"]
    assert len(requests) == 2
    with pytest.raises(ValueError, match="No existe"):
        import_pois(db_session, "no-existe", transport)
