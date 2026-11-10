"""Public endpoints over the seeded region on real PostGIS/pgRouting."""

from collections.abc import Generator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from scripts.seed_dev import ORIGIN_LAT, ORIGIN_LON, STEP_LAT, STEP_LON
from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from reduc.api.deps import get_storage
from reduc.api.main import create_app
from reduc.core.db.models import Barrier, Detection, Image
from reduc.core.db.session import get_session
from reduc.core.storage import InMemoryStorage
from reduc.settings import Settings


class AllowAll:
    async def allows(self, _client_ip: str) -> bool:
        return True


def grid(row: float, column: float) -> list[float]:
    return [ORIGIN_LON + column * STEP_LON, ORIGIN_LAT + row * STEP_LAT]


MANUAL: dict[str, Any] = {
    "device": "manual",
    "max_uphill_pct": 6.0,
    "max_downhill_pct": 8.0,
    "max_cross_slope_pct": 3.0,
    "max_step_cm": 2.0,
    "min_width_m": 0.9,
    "max_surface_class": 2,
    "require_curb_ramps": True,
    "avoid_unverified": False,
    "speed_mps": 0.9,
    "weights": {"slope": 1.0, "surface": 1.0, "uncertainty": 1.0},
}


@pytest.fixture
def client(shared_engine: Engine) -> Generator[TestClient]:
    app = create_app(Settings(cors_origins="http://localhost:5173"), AllowAll())
    storage = InMemoryStorage()

    def session_override() -> Generator[Session]:
        with Session(shared_engine) as session:
            yield session

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_storage] = lambda: storage
    with TestClient(app) as test_client:
        yield test_client


def test_regions_lists_the_published_seed(client: TestClient) -> None:
    response = client.get("/v1/regions")

    assert response.status_code == 200
    (region,) = response.json()
    assert region["slug"] == "campus-piloto"
    assert region["map_version"]["number"] == 1
    assert region["stats"]["edges"] == 60
    assert region["stats"]["coverage_pct"] == 100.0
    assert 90.0 < region["stats"]["verified_pct"] < 100.0
    assert region["bbox"] == [-74.066, 4.6, -74.061, 4.604]
    assert region["boundary"]["type"] == "MultiPolygon"


def test_pois_search_by_partial_text_and_category(client: TestClient) -> None:
    by_text = client.get("/v1/regions/campus-piloto/pois", params={"q": "biblio"}).json()
    by_category = client.get("/v1/regions/campus-piloto/pois", params={"category": "toilet"}).json()
    everything = client.get("/v1/regions/campus-piloto/pois").json()

    assert [poi["name"] for poi in by_text] == ["Biblioteca"]
    assert [poi["name"] for poi in by_category] == ["Baño accesible"]
    assert len(everything) == 8
    assert by_text[0]["location"] == pytest.approx(grid(4, 1))


def test_pois_of_unknown_region_is_404(client: TestClient) -> None:
    response = client.get("/v1/regions/nowhere/pois")

    assert response.status_code == 404
    assert response.json()["type"] == "not_found"


def test_presets_match_the_specification(client: TestClient) -> None:
    presets = client.get("/v1/profiles/presets").json()

    assert [preset["id"] for preset in presets] == ["manual", "manual_assisted", "electric", "scooter"]
    assert presets[0]["profile"] == MANUAL


def test_route_avoids_stairs_and_explains_the_shortest(client: TestClient) -> None:
    body = {"origin": grid(2, 1.5), "destination": grid(2, 3.5), "profile": MANUAL, "locale": "es"}

    response = client.post("/v1/routes", json=body)

    assert response.status_code == 200
    payload = response.json()
    assert payload["region"] == "campus-piloto"
    assert payload["map_version"] == 1
    route = payload["routes"][0]
    assert route["id"] == "r1"
    assert route["distance_m"] == pytest.approx(200.0, abs=1.0)
    assert route["duration_s"] == pytest.approx(200 / 0.9, abs=2)
    assert route["accessibility_score"] >= 90
    assert route["verified_pct"] == 100.0
    assert route["geometry"]["coordinates"][0] == pytest.approx(grid(2, 1.5))
    assert route["geometry"]["coordinates"][-1] == pytest.approx(grid(2, 3.5))
    assert route["instructions"][0]["maneuver"] == "depart"
    assert route["instructions"][-1]["maneuver"] == "arrive"
    assert len(route["instructions"]) == 6
    assert sum(segment["distance_m"] for segment in route["segments"]) == pytest.approx(route["distance_m"], abs=0.5)
    shortest = payload["shortest"]
    assert shortest["distance_m"] == pytest.approx(100.0, abs=1.0)
    assert [barrier["class"] for barrier in shortest["blocking_barriers"]] == ["stairs"]
    assert shortest["blocking_barriers"][0]["message"] == "Escalera de 6 escalones"
    assert shortest["blocking_barriers"][0]["location"] == pytest.approx(grid(2, 2.5))


def test_route_alternatives_are_distinct(client: TestClient) -> None:
    body = {"origin": grid(0, 0), "destination": grid(3, 3), "profile": MANUAL, "alternatives": 2}

    routes = client.post("/v1/routes", json=body).json()["routes"]

    assert 1 <= len(routes) <= 3
    assert len({tuple(map(tuple, route["geometry"]["coordinates"])) for route in routes}) == len(routes)


def test_route_warnings_are_localized(client: TestClient) -> None:
    body = {"origin": grid(3, 0), "destination": grid(4, 0), "profile": MANUAL, "alternatives": 0}

    spanish = client.post("/v1/routes", json={**body, "locale": "es"}).json()["routes"][0]
    english = client.post("/v1/routes", json={**body, "locale": "en"}).json()["routes"][0]

    assert spanish["segments"][0]["status"] == "caution"
    assert spanish["segments"][0]["warnings"][0]["code"] == "slope_moderate"
    assert spanish["segments"][0]["warnings"][0]["message"].startswith("Pendiente de subida")
    assert english["segments"][0]["warnings"][0]["message"].startswith("Uphill slope")
    assert spanish["max_slope_pct"] == 4.5


def test_route_outside_region(client: TestClient) -> None:
    response = client.post("/v1/routes", json={"origin": [0.0, 0.0], "destination": grid(1, 1), "profile": MANUAL})

    assert response.status_code == 422
    assert response.json()["type"] == "outside_region"


def test_route_without_nearby_path(client: TestClient) -> None:
    far_corner = [-74.0612, 4.6002]

    response = client.post("/v1/routes", json={"origin": far_corner, "destination": grid(1, 1), "profile": MANUAL})

    assert response.status_code == 422
    body = response.json()
    assert body["type"] == "no_nearby_path"
    assert body["extra"] == {"endpoint": "origin"}


def test_route_validation_error(client: TestClient) -> None:
    response = client.post(
        "/v1/routes",
        json={"origin": grid(0, 0), "destination": grid(1, 1), "profile": {**MANUAL, "max_surface_class": 9}},
    )

    assert response.status_code == 422
    assert response.json()["type"] == "validation_error"


def test_no_accessible_route_returns_fallback(client: TestClient, shared_engine: Engine) -> None:
    """A profile that cannot climb anything gets the least-bad route and the relaxed constraints."""
    strict = {**MANUAL, "max_uphill_pct": 0.5, "max_downhill_pct": 0.5}
    body = {"origin": grid(0, 0), "destination": grid(0, 2), "profile": strict}

    response = client.post("/v1/routes", json=body)

    assert response.status_code == 422
    payload = response.json()
    assert payload["type"] == "no_accessible_route"
    assert payload["title"] == "No existe una ruta accesible"
    extra = payload["extra"]
    assert extra["violated_constraints"][-1] == "slope"
    fallback = extra["fallback_route"]
    assert fallback["id"] == "fallback"
    assert fallback["distance_m"] == pytest.approx(100.0, abs=1.0)
    assert all(segment["status"] == "inaccessible" for segment in fallback["segments"])
    assert fallback["segments"][0]["warnings"][0]["code"] == "exceeds_profile"
    assert fallback["accessibility_score"] < 20


def test_barrier_detail_and_missing_barrier(client: TestClient, shared_engine: Engine) -> None:
    with Session(shared_engine) as session:
        barrier_id = session.scalar(select(Barrier.id).where(Barrier.barrier_class == "stairs"))

    response = client.get(f"/v1/barriers/{barrier_id}")
    missing = client.get("/v1/barriers/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 200
    body = response.json()
    assert body["class"] == "stairs"
    assert body["severity"] == "critical"
    assert body["verification_status"] == "confirmed"
    assert body["description"] == "Escalera de 6 escalones"
    assert body["photo_url"] is None
    assert missing.status_code == 404


def test_barrier_photo_requires_a_permissive_license(client: TestClient, shared_engine: Engine) -> None:
    with Session(shared_engine) as session:
        barrier = session.scalar(select(Barrier).where(Barrier.barrier_class == "curb_no_ramp"))
        assert barrier is not None
        region_id = session.execute(text("SELECT id FROM region")).scalar_one()
        image = Image(
            region_id=region_id,
            provider="upload",
            captured_at=barrier.created_at,
            geom=barrier.geom,
            is_panorama=False,
            width_px=10,
            height_px=10,
            license="own",
            attribution="Equipo REDUC",
            privacy_blurred=True,
            status="processed",
        )
        session.add(image)
        session.flush()
        detection = Detection(
            image_id=image.id,
            model_version="fake",
            detection_class="curb_no_ramp",
            score=0.9,
            bbox=[0, 0, 5, 5],
            crop_key="crops/test.jpg",
        )
        session.add(detection)
        session.flush()
        barrier.representative_detection_id = detection.id
        session.commit()
        barrier_id, image_id = barrier.id, image.id

    allowed = client.get(f"/v1/barriers/{barrier_id}").json()
    with Session(shared_engine) as session:
        session.execute(text("UPDATE image SET license = 'google-tos' WHERE id = :id"), {"id": image_id})
        session.commit()
    restricted = client.get(f"/v1/barriers/{barrier_id}").json()

    assert allowed["photo_url"] == "memory://crops/test.jpg?expires=900"
    assert allowed["attribution"] == "Equipo REDUC"
    assert restricted["photo_url"] is None
    assert restricted["attribution"] is None
