"""Overpass client: downloads the pedestrian network inside a bounding box."""

from collections.abc import Callable, Mapping
from typing import Any

import httpx

from reduc.core.providers.osm.graph import PEDESTRIAN_HIGHWAYS, ROAD_HIGHWAYS, Bbox, OsmData
from reduc.core.providers.osm.readers import from_overpass_json

DEFAULT_ENDPOINT = "https://overpass-api.de/api/interpreter"
USER_AGENT = "app-reduc/0.1 (accessible routing research)"

Transport = Callable[[str, str], Mapping[str, Any]]


def build_query(bbox: Bbox, timeout_s: int = 120) -> str:
    """Overpass QL for every walkable way in the box plus the nodes they reference.

    Overpass expects (south, west, north, east).
    """
    west, south, east, north = bbox
    highways = "|".join(sorted(PEDESTRIAN_HIGHWAYS | ROAD_HIGHWAYS))
    box = f"{south:.7f},{west:.7f},{north:.7f},{east:.7f}"
    return f'[out:json][timeout:{timeout_s}];(way["highway"~"^({highways})$"]({box}););out body;>;out body qt;'


def expand_bbox(bbox: Bbox, buffer_m: float) -> Bbox:
    """Grow a box by a margin in meters (docs/03 §3, `osm.buffer_m`)."""
    import math

    west, south, east, north = bbox
    d_lat = buffer_m / 111_320.0
    d_lon = buffer_m / (111_320.0 * max(0.01, math.cos(math.radians((south + north) / 2))))
    return (west - d_lon, south - d_lat, east + d_lon, north + d_lat)


def http_transport(endpoint: str, query: str) -> Mapping[str, Any]:
    """Default transport. Tests inject a recorded response instead (no network in tests)."""
    response = httpx.post(endpoint, data={"data": query}, headers={"User-Agent": USER_AGENT}, timeout=180.0)
    response.raise_for_status()
    payload: Mapping[str, Any] = response.json()
    return payload


class OverpassSource:
    """Fetches OSM data for a box through a replaceable transport."""

    def __init__(self, endpoint: str = DEFAULT_ENDPOINT, transport: Transport = http_transport) -> None:
        self._endpoint = endpoint
        self._transport = transport

    def fetch(self, bbox: Bbox) -> OsmData:
        return from_overpass_json(self._transport(self._endpoint, build_query(bbox)))
