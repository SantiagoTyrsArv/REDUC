"""Mapillary API v4 (docs/05 §4): the default image source. CC BY-SA 4.0, attribution required."""

from collections.abc import Callable, Iterator, Mapping
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

import httpx

from reduc.core.providers.images.base import Bbox, Boundary, ImageMeta, ProviderDisabledError, split_cells

API_URL = "https://graph.mapillary.com/images"
FIELDS = "id,captured_at,computed_geometry,computed_compass_angle,camera_type,thumb_2048_url,creator,width,height"
PAGE_LIMIT = 2000
#: Below this size a full page is accepted as is instead of splitting again.
MIN_CELL_DEG = 0.0005
LICENSE = "CC-BY-SA-4.0"
PANORAMA_TYPES = frozenset({"spherical", "equirectangular"})
#: Thumbnails are only downloaded from Mapillary's own hosts, whatever URL the API returns.
ALLOWED_IMAGE_HOSTS = (".fbcdn.net", ".mapillary.com")
MAX_IMAGE_BYTES = 30 * 1024 * 1024
USER_AGENT = "app-reduc/0.1 (accessible routing research)"

ApiTransport = Callable[[str, Mapping[str, str], Mapping[str, str]], Mapping[str, Any]]
Download = Callable[[str], bytes]


def http_api(url: str, params: Mapping[str, str], headers: Mapping[str, str]) -> Mapping[str, Any]:
    response = httpx.get(url, params=dict(params), headers=dict(headers), timeout=60.0)
    response.raise_for_status()
    payload: Mapping[str, Any] = response.json()
    return payload


def http_download(url: str) -> bytes:
    with httpx.stream("GET", url, headers={"User-Agent": USER_AGENT}, timeout=60.0, follow_redirects=False) as response:
        response.raise_for_status()
        chunks: list[bytes] = []
        size = 0
        for chunk in response.iter_bytes():
            size += len(chunk)
            if size > MAX_IMAGE_BYTES:
                raise ValueError("image larger than the allowed maximum")
            chunks.append(chunk)
        return b"".join(chunks)


def is_allowed_image_url(url: str) -> bool:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    return parts.scheme == "https" and any(host.endswith(suffix) for suffix in ALLOWED_IMAGE_HOSTS)


class MapillaryProvider:
    name = "mapillary"

    def __init__(self, token: str, api: ApiTransport = http_api, download: Download = http_download) -> None:
        if not token:
            raise ProviderDisabledError("Falta REDUC_MAPILLARY_TOKEN")
        # The token travels in a header, never in the URL, so it cannot leak through logs.
        self._headers = {"Authorization": f"OAuth {token}", "User-Agent": USER_AGENT}
        self._api = api
        self._download = download

    def can_store(self) -> bool:
        return True

    def _cell(self, cell: Bbox) -> Iterator[Mapping[str, Any]]:
        west, south, east, north = cell
        params = {
            "bbox": f"{west:.7f},{south:.7f},{east:.7f},{north:.7f}",
            "fields": FIELDS,
            "limit": str(PAGE_LIMIT),
        }
        data = list(self._api(API_URL, params, self._headers).get("data") or [])
        if len(data) >= PAGE_LIMIT and max(east - west, north - south) > MIN_CELL_DEG:
            # A full page means the cell holds more images than one request returns: quarter it.
            for quarter in split_cells(cell, max(east - west, north - south) / 2.0):
                yield from self._cell(quarter)
        else:
            yield from data

    @staticmethod
    def _meta(item: Mapping[str, Any]) -> ImageMeta | None:
        """SfM-corrected position and heading (`computed_*`); items without them are unusable."""
        geometry = item.get("computed_geometry") or {}
        coordinates = geometry.get("coordinates")
        url = item.get("thumb_2048_url")
        if not coordinates or len(coordinates) < 2 or not url or item.get("captured_at") is None:
            return None
        angle = item.get("computed_compass_angle")
        creator = item.get("creator") or {}
        is_panorama = str(item.get("camera_type") or "").lower() in PANORAMA_TYPES
        return ImageMeta(
            provider="mapillary",
            external_id=str(item["id"]),
            captured_at=datetime.fromtimestamp(int(item["captured_at"]) / 1000.0, UTC),
            lon=float(coordinates[0]),
            lat=float(coordinates[1]),
            heading_deg=None if angle is None else float(angle) % 360.0,
            width_px=int(item.get("width") or 0),
            height_px=int(item.get("height") or 0),
            license=LICENSE,
            attribution=str(creator.get("username")) if creator.get("username") else "Mapillary",
            is_panorama=is_panorama,
            source=str(url),
        )

    def list_images(self, boundary: Boundary, since: datetime | None) -> Iterator[ImageMeta]:
        from shapely.geometry import Point

        seen: set[str] = set()
        for cell in split_cells(boundary.bounds):
            for item in self._cell(cell):
                meta = self._meta(item)
                if meta is None or meta.external_id in seen:
                    continue
                seen.add(meta.external_id)
                if since is not None and meta.captured_at < since:
                    continue
                if boundary.covers(Point(meta.lon, meta.lat)):
                    yield meta

    def fetch(self, meta: ImageMeta) -> bytes:
        url = str(meta.source or "")
        if not is_allowed_image_url(url):
            raise ValueError("Mapillary returned an image URL outside its own hosts")
        return self._download(url)
