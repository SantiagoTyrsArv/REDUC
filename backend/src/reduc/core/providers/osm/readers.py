"""Readers that turn OSM sources into `OsmData`: Overpass JSON, OSM XML and `.osm.pbf` files."""

import xml.etree.ElementTree as ET
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from reduc.core.providers.osm.graph import OsmData, OsmNode, OsmWay, classify_way


def from_overpass_json(payload: Mapping[str, Any]) -> OsmData:
    """Parse the `elements` array returned by Overpass with `out body; >; out skel qt;`."""
    nodes: dict[int, OsmNode] = {}
    ways: list[OsmWay] = []
    for element in payload.get("elements", []):
        kind = element.get("type")
        if kind == "node" and "lat" in element and "lon" in element:
            # A node may appear twice (with and without tags); keep the tagged version.
            previous = nodes.get(int(element["id"]))
            tags = dict(element.get("tags") or (previous.tags if previous else {}))
            nodes[int(element["id"])] = OsmNode(int(element["id"]), float(element["lon"]), float(element["lat"]), tags)
        elif kind == "way":
            ways.append(
                OsmWay(
                    int(element["id"]),
                    tuple(int(ref) for ref in element.get("nodes", [])),
                    dict(element.get("tags") or {}),
                )
            )
    return OsmData(nodes=nodes, ways=tuple(ways))


def from_osm_xml(path: Path) -> OsmData:
    """Parse a plain `.osm` XML export."""
    nodes: dict[int, OsmNode] = {}
    ways: list[OsmWay] = []
    for _, element in ET.iterparse(path, events=("end",)):
        if element.tag == "node":
            tags = {tag.attrib["k"]: tag.attrib["v"] for tag in element.findall("tag")}
            node_id = int(element.attrib["id"])
            nodes[node_id] = OsmNode(node_id, float(element.attrib["lon"]), float(element.attrib["lat"]), tags)
            element.clear()
        elif element.tag == "way":
            tags = {tag.attrib["k"]: tag.attrib["v"] for tag in element.findall("tag")}
            refs = tuple(int(nd.attrib["ref"]) for nd in element.findall("nd"))
            ways.append(OsmWay(int(element.attrib["id"]), refs, tags))
            element.clear()
    return OsmData(nodes=nodes, ways=tuple(ways))


def from_pbf(path: Path) -> OsmData:
    """Read a `.osm.pbf` extract in two passes so only the nodes of walkable ways are kept."""
    import osmium

    ways: list[OsmWay] = []
    needed: set[int] = set()
    for way in osmium.FileProcessor(str(path), osmium.osm.WAY):
        if not isinstance(way, osmium.osm.Way):
            continue
        tags = {tag.k: tag.v for tag in way.tags}
        if classify_way(tags) is None:
            continue
        refs = tuple(int(node.ref) for node in way.nodes)
        ways.append(OsmWay(int(way.id), refs, tags))
        needed.update(refs)

    nodes: dict[int, OsmNode] = {}
    for node in osmium.FileProcessor(str(path), osmium.osm.NODE):
        if isinstance(node, osmium.osm.Node) and node.id in needed and node.location.valid():
            nodes[int(node.id)] = OsmNode(
                int(node.id), float(node.location.lon), float(node.location.lat), {tag.k: tag.v for tag in node.tags}
            )
    return OsmData(nodes=nodes, ways=tuple(ways))


def read_osm_file(path: Path) -> OsmData:
    """Dispatch on the file extension."""
    name = path.name.lower()
    if name.endswith(".pbf"):
        return from_pbf(path)
    if name.endswith(".osm") or name.endswith(".xml"):
        return from_osm_xml(path)
    raise ValueError(f"Unsupported OSM file: {path.name}")
