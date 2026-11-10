"""Google Street View: optional and OFF by default (docs/05 §4, ADR-006).

Google Maps Platform terms restrict storing imagery and building derived databases from it.
This provider therefore never stores images (`can_store() == False`) and refuses to work
unless the deployment sets an API key AND the region explicitly enables it, which must only
happen after the team has a licence or agreement that allows this use.
"""

from collections.abc import Callable, Iterator, Mapping
from datetime import UTC, datetime
from typing import Any

import httpx

from reduc.core.providers.images.base import Boundary, ImageMeta, ProviderDisabledError

METADATA_URL = "https://maps.googleapis.com/maps/api/streetview/metadata"
IMAGE_URL = "https://maps.googleapis.com/maps/api/streetview"
LICENSE = "google-tos"
VIEW_SIZE = 640
VIEW_FOV_DEG = 90.0
HEADINGS_DEG = (0.0, 90.0, 180.0, 270.0)
#: Spacing of the probe grid; each point asks for the nearest panorama.
GRID_STEP_DEG = 0.0003
MAX_PROBES = 2000

Transport = Callable[[str, Mapping[str, str]], Any]


class StreetViewRequestError(Exception):
    """A request failed. The message never contains the URL, because the API key travels in it."""


def _get(url: str, params: Mapping[str, str], timeout: float) -> httpx.Response:
    try:
        response = httpx.get(url, params=dict(params), timeout=timeout)
    except httpx.HTTPError as error:
        # httpx messages include the full URL with `key=...`; errors end up in logs and in the run record.
        raise StreetViewRequestError(f"Street View no respondió ({type(error).__name__})") from None
    if response.status_code >= 400:
        raise StreetViewRequestError(f"Street View respondió {response.status_code}")
    return response


def http_json(url: str, params: Mapping[str, str]) -> Any:
    return _get(url, params, 30.0).json()


def http_bytes(url: str, params: Mapping[str, str]) -> Any:
    return _get(url, params, 60.0).content


class StreetViewProvider:
    name = "streetview"

    def __init__(
        self,
        api_key: str,
        enabled: bool = False,
        metadata: Transport = http_json,
        image: Transport = http_bytes,
    ) -> None:
        if not enabled or not api_key:
            raise ProviderDisabledError(
                "Street View está desactivado: requiere REDUC_STREETVIEW_API_KEY y habilitarlo en la región "
                "tras confirmar la licencia (ADR-006)"
            )
        self._key = api_key
        self._metadata = metadata
        self._image = image

    def can_store(self) -> bool:
        return False

    def list_images(self, boundary: Boundary, since: datetime | None) -> Iterator[ImageMeta]:
        from shapely.geometry import Point

        west, south, east, north = boundary.bounds
        seen: set[str] = set()
        probes = 0
        lat = south
        while lat <= north and probes < MAX_PROBES:
            lon = west
            while lon <= east and probes < MAX_PROBES:
                if boundary.covers(Point(lon, lat)):
                    probes += 1
                    yield from self._probe(lon, lat, boundary, since, seen)
                lon += GRID_STEP_DEG
            lat += GRID_STEP_DEG

    def _probe(
        self, lon: float, lat: float, boundary: Boundary, since: datetime | None, seen: set[str]
    ) -> Iterator[ImageMeta]:
        from shapely.geometry import Point

        payload = self._metadata(
            METADATA_URL, {"location": f"{lat:.7f},{lon:.7f}", "source": "outdoor", "key": self._key}
        )
        if not isinstance(payload, Mapping) or payload.get("status") != "OK" or payload.get("pano_id") in seen:
            return
        location = payload.get("location") or {}
        try:
            pano_lon, pano_lat = float(location["lng"]), float(location["lat"])
            year, month = (int(part) for part in str(payload.get("date", "")).split("-")[:2])
            captured = datetime(year, month, 1, tzinfo=UTC)
        except (KeyError, TypeError, ValueError):
            return
        pano_id = str(payload["pano_id"])
        seen.add(pano_id)
        if (since is not None and captured < since) or not boundary.covers(Point(pano_lon, pano_lat)):
            return
        for heading in HEADINGS_DEG:
            yield ImageMeta(
                provider="streetview",
                external_id=f"{pano_id}:{int(heading)}",
                captured_at=captured,
                lon=pano_lon,
                lat=pano_lat,
                heading_deg=heading,
                width_px=VIEW_SIZE,
                height_px=VIEW_SIZE,
                license=LICENSE,
                attribution="Google",
                fov_deg=VIEW_FOV_DEG,
                camera_height_m=2.5,
                source={"pano": pano_id, "heading": heading},
            )

    def fetch(self, meta: ImageMeta) -> bytes:
        source = meta.source or {}
        data: bytes = self._image(
            IMAGE_URL,
            {
                "pano": str(source["pano"]),
                "heading": f"{float(source['heading']):.0f}",
                "fov": f"{VIEW_FOV_DEG:.0f}",
                "pitch": "0",
                "size": f"{VIEW_SIZE}x{VIEW_SIZE}",
                "key": self._key,
            },
        )
        return data
