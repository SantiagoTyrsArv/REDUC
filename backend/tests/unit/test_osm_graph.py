"""OSM importer: classification, splitting, subdivision and the three readers (docs/05 §2)."""

import itertools
from collections import Counter
from pathlib import Path

import pytest
from tests.fixtures.osm.sample import (
    EXPECTED_EDGES,
    EXPECTED_KINDS,
    EXPECTED_NODES,
    overpass_payload,
    sample_data,
)

from reduc.core.providers.osm.graph import (
    MAX_EDGE_M,
    GraphDraft,
    OsmData,
    OsmNode,
    OsmWay,
    build_graph,
    classify_way,
    connected_components,
    line_length_m,
    node_kind,
)
from reduc.core.providers.osm.overpass import OverpassSource, build_query, expand_bbox
from reduc.core.providers.osm.readers import from_osm_xml, from_overpass_json, from_pbf, read_osm_file

FIXTURES = Path(__file__).parents[1] / "fixtures" / "osm"


def signature(draft: GraphDraft) -> list[tuple[int | None, int | None, int, str, float]]:
    """Topology independent of local keys: OSM ids of the endpoints, way, kind and length."""
    osm_id = {node.key: node.osm_id for node in draft.nodes}
    return sorted(
        ((osm_id[e.source], osm_id[e.target], e.osm_way_id, e.kind, round(e.length_m, 1)) for e in draft.edges),
        key=str,
    )


@pytest.mark.parametrize(
    ("tags", "expected"),
    [
        ({"highway": "footway"}, "footway"),
        ({"highway": "pedestrian"}, "footway"),
        ({"highway": "corridor"}, "footway"),
        ({"highway": "path"}, "path"),
        ({"highway": "steps"}, "steps"),
        ({"highway": "steps", "ramp": "yes"}, "steps"),
        ({"highway": "footway", "footway": "crossing"}, "crossing"),
        ({"highway": "footway", "footway": "sidewalk"}, "sidewalk"),
        ({"highway": "footway", "ramp": "yes"}, "ramp"),
        ({"highway": "residential"}, "road_shoulder"),
        ({"highway": "residential", "sidewalk": "no"}, "road_shoulder"),
        ({"highway": "tertiary", "sidewalk": "both"}, "sidewalk"),
        ({"highway": "residential", "sidewalk": "separate"}, None),
        ({"highway": "residential", "sidewalk:left": "separate", "sidewalk:right": "separate"}, None),
        ({"highway": "footway", "foot": "no"}, None),
        ({"highway": "service", "access": "private"}, None),
        ({"highway": "service", "access": "private", "foot": "yes"}, "road_shoulder"),
        ({"highway": "motorway"}, None),
        ({"building": "yes"}, None),
    ],
)
def test_classify_way(tags: dict[str, str], expected: str | None) -> None:
    assert classify_way(tags) == expected


def test_node_kind_priority() -> None:
    assert node_kind({"highway": "elevator"}, 1) == "elevator"
    assert node_kind({"highway": "crossing", "kerb": "lowered"}, 4) == "crossing"
    assert node_kind({"kerb": "raised"}, 2) == "curb"
    assert node_kind({"entrance": "main"}, 1) == "entrance"
    assert node_kind({}, 3) == "junction"
    assert node_kind({}, 2) == "other"


def test_sample_graph_has_expected_counts_and_topology() -> None:
    draft = build_graph(sample_data())

    assert len(draft.edges) == EXPECTED_EDGES
    assert len(draft.nodes) == EXPECTED_NODES
    assert Counter(edge.kind for edge in draft.edges) == EXPECTED_KINDS
    assert len(connected_components(draft)) == 1
    # Private, separately-mapped and non-highway ways never enter the graph.
    assert {edge.osm_way_id for edge in draft.edges} == {100, 101, 102, 104}

    kinds = {node.osm_id: node.kind for node in draft.nodes if node.osm_id is not None}
    assert kinds == {1: "other", 2: "junction", 3: "other", 4: "other", 5: "other", 7: "curb"}
    assert sum(node.osm_id is None for node in draft.nodes) == 3
    curb = next(node for node in draft.nodes if node.osm_id == 7)
    assert curb.tags == {"kerb": "raised", "kerb:height": "0.12"}


def test_long_ways_are_subdivided_into_equal_pieces() -> None:
    draft = build_graph(sample_data())

    footway = [edge for edge in draft.edges if edge.osm_way_id == 100]
    assert [round(edge.length_m) for edge in footway] == [40, 40, 40, 40]
    assert all(edge.length_m <= MAX_EDGE_M for edge in draft.edges)
    # Pieces chain end to end and keep the way's tags.
    for previous, current in itertools.pairwise(footway):
        assert previous.target == current.source
        assert previous.coords[-1] == current.coords[0]
    assert footway[0].tags == {"highway": "footway", "surface": "asphalt", "width": "2"}
    # The shape point (node 20) falls inside the second piece and is preserved.
    assert any((0.00054, 0.0) in edge.coords for edge in footway)
    shoulder = [edge for edge in draft.edges if edge.kind == "road_shoulder"]
    assert [round(edge.length_m) for edge in shoulder] == [30, 30]


def test_total_length_is_preserved() -> None:
    data = sample_data()
    draft = build_graph(data)

    def way_length(way_id: int) -> float:
        way = next(item for item in data.ways if item.id == way_id)
        return line_length_m((data.nodes[ref].lon, data.nodes[ref].lat) for ref in way.node_ids)

    for way_id in (100, 101, 102, 104):
        built = sum(edge.length_m for edge in draft.edges if edge.osm_way_id == way_id)
        assert built == pytest.approx(way_length(way_id), abs=0.01)


def test_ways_break_at_tagged_nodes_and_self_intersections() -> None:
    nodes = {
        1: OsmNode(1, 0.0, 0.0),
        2: OsmNode(2, 0.0001, 0.0, {"highway": "crossing"}),
        3: OsmNode(3, 0.0002, 0.0),
        4: OsmNode(4, 0.0002, 0.0001),
        5: OsmNode(5, 0.0001, 0.0001),
    }
    crossing = build_graph(OsmData(nodes, (OsmWay(1, (1, 2, 3), {"highway": "footway"}),)))
    assert len(crossing.edges) == 2
    assert next(node for node in crossing.nodes if node.osm_id == 2).kind == "crossing"

    loop = build_graph(OsmData(nodes, (OsmWay(2, (1, 2, 3, 4, 5, 2), {"highway": "path"}),)))
    # The way touches node 2 twice, so it is split there: a stem and a closed loop.
    assert len(loop.edges) == 2
    assert {edge.kind for edge in loop.edges} == {"path"}


def test_bbox_clips_ways_at_the_last_inside_node() -> None:
    draft = build_graph(sample_data(), bbox=(-0.001, -0.001, 0.0012, 0.001))

    assert {edge.osm_way_id for edge in draft.edges} == {100, 101, 104}
    assert sum(edge.length_m for edge in draft.edges if edge.osm_way_id == 100) == pytest.approx(120.1, abs=0.2)


def test_build_is_deterministic() -> None:
    assert build_graph(sample_data()) == build_graph(sample_data())


def test_all_readers_produce_the_same_graph(tmp_path: Path) -> None:
    expected = signature(build_graph(sample_data()))

    assert signature(build_graph(from_overpass_json(overpass_payload()))) == expected
    assert signature(build_graph(from_osm_xml(FIXTURES / "sample.osm"))) == expected
    assert signature(build_graph(from_pbf(FIXTURES / "sample.osm.pbf"))) == expected
    assert signature(build_graph(read_osm_file(FIXTURES / "sample.osm.pbf"))) == expected
    with pytest.raises(ValueError, match="Unsupported"):
        read_osm_file(tmp_path / "map.geojson")


def test_pbf_fixture_matches_expected_counts() -> None:
    """Acceptance of T-20: the bundled .pbf yields the expected number of edges and topology."""
    draft = build_graph(read_osm_file(FIXTURES / "sample.osm.pbf"))

    assert (len(draft.nodes), len(draft.edges)) == (EXPECTED_NODES, EXPECTED_EDGES)
    assert Counter(edge.kind for edge in draft.edges) == EXPECTED_KINDS
    assert [len(component) for component in connected_components(draft)] == [EXPECTED_NODES]


def test_overpass_source_uses_the_injected_transport() -> None:
    requests: list[tuple[str, str]] = []

    def transport(endpoint: str, query: str) -> dict[str, object]:
        requests.append((endpoint, query))
        return overpass_payload()

    data = OverpassSource(endpoint="https://overpass.test/api", transport=transport).fetch(
        (-0.001, -0.002, 0.003, 0.004)
    )

    assert len(build_graph(data).edges) == EXPECTED_EDGES
    endpoint, query = requests[0]
    assert endpoint == "https://overpass.test/api"
    # Overpass wants south,west,north,east.
    assert "(-0.0020000,-0.0010000,0.0040000,0.0030000)" in query
    assert "steps" in query and "residential" in query
    assert build_query((0, 0, 1, 1)).startswith("[out:json]")


def test_expand_bbox_adds_a_metric_margin() -> None:
    west, south, east, north = expand_bbox((0.0, 0.0, 0.001, 0.001), 111.32)

    assert south == pytest.approx(-0.001)
    assert north == pytest.approx(0.002)
    assert west == pytest.approx(-0.001, rel=1e-3)
    assert east == pytest.approx(0.002, rel=1e-3)
