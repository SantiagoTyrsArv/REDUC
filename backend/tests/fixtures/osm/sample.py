"""Synthetic OSM extract shared by the fixture generator and the importer tests.

At the equator 0.00009 degrees are ~10 m, which keeps the expected lengths easy to read.
Expected graph: 8 edges (3 + 1 footway, 1 steps, 2 road_shoulder, 1 crossing) and 9 nodes.
"""

from reduc.core.providers.osm.graph import OsmData, OsmNode, OsmWay

NODES = (
    OsmNode(1, 0.0, 0.0),
    OsmNode(20, 0.00054, 0.0),  # shape point only
    OsmNode(2, 0.00108, 0.0),
    OsmNode(3, 0.00144, 0.0),
    OsmNode(4, 0.00108, 0.00009),
    OsmNode(5, 0.00144, 0.00054),
    OsmNode(6, 0.00200, 0.00054),
    OsmNode(7, 0.00108, 0.00018, {"kerb": "raised", "kerb:height": "0.12"}),
    OsmNode(8, 0.00144, -0.00050),
    OsmNode(9, 0.00250, 0.00054),
    OsmNode(30, 0.00300, 0.00300),
    OsmNode(31, 0.00310, 0.00300),
    OsmNode(32, 0.00310, 0.00310),
)

WAYS = (
    OsmWay(100, (1, 20, 2, 3), {"highway": "footway", "surface": "asphalt", "width": "2"}),
    OsmWay(101, (2, 4), {"highway": "steps", "step_count": "6"}),
    OsmWay(102, (3, 5), {"highway": "residential", "name": "Calle de prueba"}),
    OsmWay(103, (5, 6), {"highway": "residential", "sidewalk": "separate"}),
    OsmWay(104, (4, 7), {"highway": "footway", "footway": "crossing"}),
    OsmWay(105, (30, 31, 32, 30), {"building": "yes"}),
    OsmWay(106, (3, 8), {"highway": "service", "access": "private"}),
    OsmWay(107, (6, 999, 9), {"highway": "path"}),
)

EXPECTED_EDGES = 8
EXPECTED_NODES = 9
EXPECTED_KINDS = {"footway": 4, "steps": 1, "road_shoulder": 2, "crossing": 1}


def sample_data() -> OsmData:
    return OsmData(nodes={node.id: node for node in NODES}, ways=WAYS)


def overpass_payload() -> dict[str, object]:
    """The same extract in the shape Overpass returns it."""
    elements: list[dict[str, object]] = [
        {"type": "way", "id": way.id, "nodes": list(way.node_ids), "tags": dict(way.tags)} for way in WAYS
    ]
    elements += [
        {
            "type": "node",
            "id": node.id,
            "lat": node.lat,
            "lon": node.lon,
            **({"tags": dict(node.tags)} if node.tags else {}),
        }
        for node in NODES
    ]
    return {"version": 0.6, "elements": elements}
