"""Image ingestion stage with fake providers and in-memory storage (T-25)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from tests.fixtures.images import jpeg, meta, panorama
from tests.integration.pipeline_helpers import temporary_region

from reduc.core.db.models import Image, Region
from reduc.core.pipeline.context import PipelineDeps, StageContext
from reduc.core.pipeline.stages import ingest_images
from reduc.core.providers.images.base import FakeImageProvider
from reduc.core.storage import InMemoryStorage


def run_stage(engine: Engine, region_id: uuid.UUID, deps: PipelineDeps) -> dict[str, object]:
    with Session(engine) as session:
        region = session.get(Region, region_id)
        assert region is not None
        stats = ingest_images.run(StageContext(session=session, region=region, map_version_id=uuid.uuid4(), deps=deps))
        session.commit()
    return stats


def images_of(engine: Engine, region_id: uuid.UUID) -> list[Image]:
    with Session(engine) as session:
        return list(session.scalars(select(Image).where(Image.region_id == region_id).order_by(Image.external_id)))


def test_new_images_are_stored_once_and_failures_do_not_stop_the_stage(shared_engine: Engine) -> None:
    storage = InMemoryStorage()
    provider = FakeImageProvider(
        [
            (meta("a", lon=0.0010, provider="mapillary", license="CC-BY-SA-4.0"), jpeg(64, 48)),
            (meta("b", lon=0.0020, provider="mapillary", license="CC-BY-SA-4.0"), jpeg(32, 24)),
            (meta("broken", lon=0.0030, provider="mapillary"), b""),
            (meta("outside", lon=0.5, provider="mapillary"), jpeg()),
        ],
        name="mapillary",
        failing={"broken"},
    )
    deps = PipelineDeps(image_providers=lambda _region: [provider], storage=storage)
    with temporary_region(shared_engine) as region_id:
        first = run_stage(shared_engine, region_id, deps)
        second = run_stage(shared_engine, region_id, deps)

        rows = images_of(shared_engine, region_id)
        assert first["new"] == 2 and first["failed"] == 1
        assert first["providers"] == {  # type: ignore[comparison-overlap]
            "mapillary": {"listed": 3, "new": 2, "stored": 2, "failed": 1, "already_known": 0}
        }
        # The second run only retries the download that failed.
        assert second["new"] == 0 and second["failed"] == 1
        assert provider.fetched == ["a", "b", "broken", "broken"] or sorted(provider.fetched) == [
            "a",
            "b",
            "broken",
            "broken",
        ]
        assert [row.external_id for row in rows] == ["a", "b"]
        first_row = rows[0]
        assert (first_row.width_px, first_row.height_px, first_row.status) == (64, 48, "pending")
        assert (first_row.license, first_row.attribution) == ("CC-BY-SA-4.0", "Equipo REDUC")
        # Mapillary already blurs faces and plates.
        assert first_row.privacy_blurred is True
        assert first_row.storage_key == f"images/{region_id}/mapillary/a.jpg"
        assert storage.objects[first_row.storage_key] == jpeg(64, 48)
        assert len(storage.objects) == 2


def test_panoramas_become_four_perspective_images(shared_engine: Engine) -> None:
    storage = InMemoryStorage()
    pano = meta("p1", heading=350.0, provider="mapillary", is_panorama=True)
    provider = FakeImageProvider([(pano, panorama())], name="mapillary")
    deps = PipelineDeps(image_providers=lambda _region: [provider], storage=storage)
    with temporary_region(shared_engine) as region_id:
        run_stage(shared_engine, region_id, deps)
        again = run_stage(shared_engine, region_id, deps)

        rows = images_of(shared_engine, region_id)
        assert again["new"] == 0
        assert {row.external_id: row.heading_deg for row in rows} == {
            "p1:front": 350.0,
            "p1:right": 80.0,
            "p1:back": 170.0,
            "p1:left": 260.0,
        }
        assert all(row.fov_deg == 90.0 and not row.is_panorama and row.width_px == row.height_px for row in rows)
        assert f"images/{region_id}/mapillary/p1_front.jpg" in storage.objects


def test_non_storable_sources_keep_no_copy_and_caps_prefer_recent_images(shared_engine: Engine) -> None:
    storage = InMemoryStorage()
    google = FakeImageProvider(
        [(meta("g1", provider="streetview", license="google-tos"), jpeg())], name="streetview", storable=False
    )
    recent = [
        (
            meta(
                f"m{year}", lon=0.001 * (year - 2019), captured=datetime(year, 1, 1, tzinfo=UTC), provider="mapillary"
            ),
            jpeg(),
        )
        for year in (2020, 2021, 2022, 2023)
    ]
    mapillary = FakeImageProvider(recent, name="mapillary")
    deps = PipelineDeps(image_providers=lambda _region: [google, mapillary], storage=storage)
    config = {
        "image_sources": [
            {"provider": "mapillary", "enabled": True, "min_captured_at": "2021-01-01", "max_images": 2},
            {"provider": "streetview", "enabled": True},
        ]
    }
    with temporary_region(shared_engine, config=config) as region_id:
        run_stage(shared_engine, region_id, deps)

        rows = {row.external_id: row for row in images_of(shared_engine, region_id)}
        assert set(rows) == {"g1", "m2022", "m2023"}
        assert rows["g1"].storage_key is None and rows["g1"].license == "google-tos"
        assert all("streetview" not in key for key in storage.objects)
        # The bytes of images that cannot be stored are only available to the rest of this run.
        assert list(deps.extras["transient_images"]) == [rows["g1"].id]
