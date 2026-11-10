"""Image providers with recorded responses; nothing here touches the network (T-25)."""

import io
import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PIL import Image
from shapely.geometry import box
from tests.fixtures.images import PANORAMA_COLOURS, jpeg, jpeg_with_gps, meta, panorama

from reduc.core.providers.images import mapillary
from reduc.core.providers.images.base import (
    FakeImageProvider,
    ImageRejectedError,
    ProviderDisabledError,
    dedupe,
    split_cells,
)
from reduc.core.providers.images.mapillary import MapillaryProvider, is_allowed_image_url
from reduc.core.providers.images.panorama import split_panorama
from reduc.core.providers.images.streetview import StreetViewProvider
from reduc.core.providers.images.upload import UploadProvider, read_exif, upload_meta

FIXTURES = Path(__file__).parents[1] / "fixtures"
RECORDED = json.loads((FIXTURES / "mapillary" / "images_cell.json").read_text(encoding="utf-8"))
BOUNDARY = box(0.0, 0.0, 0.004, 0.004)


def test_split_cells_covers_the_box_with_small_cells() -> None:
    cells = split_cells((0.0, 0.0, 0.025, 0.01))

    assert len(cells) == 3
    assert cells[0][0] == 0.0 and cells[-1][2] == pytest.approx(0.025)
    assert all(east - west <= 0.01 + 1e-12 and north - south <= 0.01 + 1e-12 for west, south, east, north in cells)
    assert split_cells((0.0, 0.0, 0.001, 0.001)) == [(0.0, 0.0, 0.001, 0.001)]


def test_dedupe_keeps_the_most_recent_of_near_duplicates() -> None:
    day = timedelta(days=1)
    start = datetime(2026, 1, 1, tzinfo=UTC)
    one_metre = 1.0 / 111_320.0
    images = [
        meta("old", heading=90.0, captured=start),
        meta("new", lat=0.001 + one_metre, heading=100.0, captured=start + day),
        # Same spot but looking the other way: a different view of the street.
        meta("opposite", heading=270.0, captured=start),
        # Five metres away: far enough.
        meta("far", lat=0.001 + 5 * one_metre, heading=90.0, captured=start),
        meta("no-heading-a", lon=0.002, heading=None, captured=start),
        meta("no-heading-b", lon=0.002, heading=None, captured=start + day),
        # The compass wraps around: 355° and 5° are 10° apart.
        meta("wrap-a", lon=0.003, heading=355.0, captured=start),
        meta("wrap-b", lon=0.003, heading=5.0, captured=start + day),
    ]

    kept = {image.external_id for image in dedupe(images)}

    assert kept == {"new", "opposite", "far", "no-heading-b", "wrap-b"}


class RecordedApi:
    def __init__(self, pages: list[Mapping[str, Any]]) -> None:
        self.pages = pages
        self.calls: list[tuple[str, Mapping[str, str], Mapping[str, str]]] = []

    def __call__(self, url: str, params: Mapping[str, str], headers: Mapping[str, str]) -> Mapping[str, Any]:
        self.calls.append((url, params, headers))
        return self.pages[min(len(self.calls), len(self.pages)) - 1]


def test_mapillary_uses_computed_fields_and_filters_by_boundary_and_date() -> None:
    api = RecordedApi([RECORDED])
    provider = MapillaryProvider("token-secreto", api=api, download=lambda _url: b"")

    images = list(provider.list_images(BOUNDARY, since=datetime(2021, 1, 1, tzinfo=UTC)))

    # 3 has no SfM position, 4 is older than `since`, 5 lies outside the polygon.
    assert [image.external_id for image in images] == ["1000000000000001", "1000000000000002"]
    first, second = images
    assert (first.lon, first.lat, first.heading_deg) == (0.0010, 0.0010, 92.5)
    assert first.captured_at == datetime(2024, 6, 1, 12, 0, tzinfo=UTC)
    assert (first.license, first.attribution, first.is_panorama) == ("CC-BY-SA-4.0", "mapeadora_campus", False)
    assert (second.is_panorama, second.heading_deg) == (True, 10.0)
    assert provider.can_store()
    url, params, headers = api.calls[0]
    assert url == "https://graph.mapillary.com/images"
    assert params["bbox"] == "0.0000000,0.0000000,0.0040000,0.0040000"
    assert "computed_geometry" in params["fields"] and "computed_compass_angle" in params["fields"]
    # The token goes in a header only.
    assert headers["Authorization"] == "OAuth token-secreto"
    assert "token-secreto" not in json.dumps(dict(params))


def test_mapillary_quarters_a_cell_that_returns_a_full_page(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mapillary, "PAGE_LIMIT", 2)
    item = RECORDED["data"][0]
    full = {"data": [item, {**item, "id": "duplicate-in-next-cell"}]}
    quarters = [{"data": [{**item, "id": f"quarter-{index}"}]} for index in range(4)]
    api = RecordedApi([full, *quarters])
    provider = MapillaryProvider("t", api=api, download=lambda _url: b"")

    images = list(provider.list_images(BOUNDARY, since=None))

    assert len(api.calls) == 5
    assert [image.external_id for image in images] == [f"quarter-{index}" for index in range(4)]
    assert len({call[1]["bbox"] for call in api.calls}) == 5


def test_mapillary_only_downloads_from_its_own_hosts_and_needs_a_token() -> None:
    downloaded: list[str] = []
    provider = MapillaryProvider(
        "t", api=RecordedApi([RECORDED]), download=lambda url: downloaded.append(url) or b"jpg"
    )
    image = next(iter(provider.list_images(BOUNDARY, None)))

    assert provider.fetch(image) == b"jpg"
    assert downloaded == [RECORDED["data"][0]["thumb_2048_url"]]
    for url in (
        "http://scontent.xx.fbcdn.net/a.jpg",
        "https://169.254.169.254/latest/meta-data/",
        "https://fbcdn.net.evil.example/a.jpg",
        "https://evil.example/?x=.fbcdn.net",
        "file:///etc/passwd",
    ):
        assert not is_allowed_image_url(url)
        with pytest.raises(ValueError, match="outside its own hosts"):
            provider.fetch(meta("x").__class__(**{**image.__dict__, "source": url}))
    with pytest.raises(ProviderDisabledError):
        MapillaryProvider("")


def test_panorama_is_split_into_four_views_facing_each_direction() -> None:
    views = split_panorama(panorama(), size=64)

    assert [(view.name, view.offset_deg) for view in views] == [
        ("front", 0.0),
        ("right", 90.0),
        ("back", 180.0),
        ("left", 270.0),
    ]
    for view in views:
        pixels = np.asarray(Image.open(io.BytesIO(view.jpeg)).convert("RGB")).astype(int)
        assert pixels.shape == (64, 64, 3)
        centre = pixels[32, 32]
        assert np.abs(centre - np.array(PANORAMA_COLOURS[view.name])).max() < 40


def test_upload_reads_position_heading_and_date_from_exif() -> None:
    info = read_exif(jpeg_with_gps(lon=-74.0651, lat=4.6012, heading=135.0))

    assert (info.lon, info.lat) == (pytest.approx(-74.0651, abs=1e-6), pytest.approx(4.6012, abs=1e-6))
    assert info.heading_deg == 135.0
    assert info.captured_at == datetime(2026, 3, 14, 10, 30, tzinfo=UTC)
    assert (info.width_px, info.height_px) == (80, 60)
    assert info.fov_deg == pytest.approx(69.4, abs=0.2)
    # Portrait photos are stored rotated: the upright size is what detections refer to.
    rotated = read_exif(jpeg_with_gps(orientation=6))
    assert (rotated.width_px, rotated.height_px) == (60, 80)

    data = jpeg_with_gps(heading=None)
    manual = upload_meta(data, heading_deg=450.0)
    assert (manual.provider, manual.license, manual.heading_deg) == ("upload", "own", 90.0)
    assert manual.external_id == upload_meta(data, heading_deg=10.0).external_id
    assert upload_meta(jpeg_with_gps(heading=135.0), heading_deg=20.0).heading_deg == 20.0


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (jpeg(), "GPS"),
        (jpeg_with_gps(lon=0.0, lat=0.0), "no es válida"),
        (b"not an image", "JPEG válida"),
        (panorama(), "Solo se aceptan fotos JPEG"),
        (b"\xff\xd8" + b"0" * (20 * 1024 * 1024), "20 MB"),
    ],
)
def test_upload_rejects_unusable_files(data: bytes, message: str) -> None:
    with pytest.raises(ImageRejectedError, match=message):
        read_exif(data)


def test_upload_without_any_heading_asks_for_one() -> None:
    with pytest.raises(ImageRejectedError, match="rumbo"):
        upload_meta(jpeg_with_gps(heading=None))
    provider = UploadProvider()
    assert list(provider.list_images(BOUNDARY, None)) == []
    assert provider.can_store()


def test_street_view_is_off_unless_explicitly_enabled_and_never_stores() -> None:
    for key, enabled in (("", False), ("", True), ("a-key", False)):
        with pytest.raises(ProviderDisabledError, match="ADR-006"):
            StreetViewProvider(key, enabled=enabled)

    recorded = json.loads((FIXTURES / "streetview" / "metadata_ok.json").read_text(encoding="utf-8"))
    requests: list[Mapping[str, str]] = []

    def metadata(_url: str, params: Mapping[str, str]) -> Any:
        requests.append(params)
        return recorded if len(requests) == 1 else {"status": "ZERO_RESULTS"}

    provider = StreetViewProvider("a-key", enabled=True, metadata=metadata, image=lambda _url, params: b"view")
    images = list(provider.list_images(box(0.0009, 0.0009, 0.0011, 0.0011), since=None))

    assert not provider.can_store()
    assert [image.external_id for image in images] == [f"SYNTHETIC_PANO_ID_0001:{h}" for h in (0, 90, 180, 270)]
    assert {image.license for image in images} == {"google-tos"}
    assert images[1].heading_deg == 90.0 and images[1].captured_at == datetime(2023, 8, 1, tzinfo=UTC)
    assert provider.fetch(images[0]) == b"view"
    assert list(provider.list_images(box(0.0009, 0.0009, 0.0011, 0.0011), since=datetime(2024, 1, 1, tzinfo=UTC))) == []


def test_fake_provider_filters_like_a_real_one() -> None:
    old = meta("old", captured=datetime(2020, 1, 1, tzinfo=UTC))
    provider = FakeImageProvider([(meta("in"), b"a"), (meta("out", lon=1.0), b"b"), (old, b"c")], failing={"old"})

    assert [image.external_id for image in provider.list_images(BOUNDARY, datetime(2021, 1, 1, tzinfo=UTC))] == ["in"]
    assert provider.fetch(meta("in")) == b"a"
    with pytest.raises(OSError, match="simulated"):
        provider.fetch(old)


def test_oversized_panoramas_are_rejected_before_decoding(monkeypatch: pytest.MonkeyPatch) -> None:
    from reduc.core.providers.images import panorama as panorama_module

    monkeypatch.setattr(panorama_module, "MAX_PANORAMA_PIXELS", 1000)
    with pytest.raises(panorama_module.PanoramaTooLargeError):
        split_panorama(panorama(400, 200))


def test_street_view_errors_never_carry_the_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    from reduc.core.providers.images import streetview

    def failing(url: str, params: Mapping[str, str], timeout: float) -> httpx.Response:
        raise httpx.ConnectError(f"cannot reach {url}?key={params['key']}")

    monkeypatch.setattr(streetview.httpx, "get", failing)
    with pytest.raises(streetview.StreetViewRequestError) as raised:
        streetview.http_json(streetview.METADATA_URL, {"key": "CLAVE-SECRETA"})
    assert "CLAVE-SECRETA" not in str(raised.value)
    assert raised.value.__cause__ is None

    monkeypatch.setattr(streetview.httpx, "get", lambda *args, **kwargs: httpx.Response(403))
    with pytest.raises(streetview.StreetViewRequestError, match="403"):
        streetview.http_bytes(streetview.IMAGE_URL, {"key": "CLAVE-SECRETA"})
