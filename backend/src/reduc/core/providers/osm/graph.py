"""Build the pedestrian graph from raw OSM data (docs/05-pipeline-vision.md §2).

Pure functions: no database, network or files. Ways are split at every intersection and
subdivided so that no edge is longer than 50 m, which lets barriers be located precisely.
"""

import math
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

MAX_EDGE_M = 50.0
EARTH_RADIUS_M = 6_371_008.8

PEDESTRIAN_HIGHWAYS = frozenset({"footway", "path", "pedestrian", "steps", "corridor"})
ROAD_HIGHWAYS = frozenset(
    {"living_street", "residential", "service", "tertiary", "secondary", "primary", "unclassified"}
)
EDGE_TAG_KEYS = (
    "highway",
    "footway",
    "name",
    "surface",
    "smoothness",
    "width",
    "incline",
    "wheelchair",
    "sidewalk",
    "kerb",
    "ramp",
    "ramp:wheelchair",
    "step_count",
    "handrail",
    "crossing",
    "tactile_paving",
    "lit",
)
NODE_TAG_KEYS = (
    "highway",
    "kerb",
    "kerb:height",
    "wheelchair",
    "crossing",
    "crossing:island",
    "entrance",
    "barrier",
    "tactile_paving",
    "elevator",
)
#: A node carrying one of these keys always becomes a graph node, even in the middle of a way.
BREAKING_NODE_KEYS = frozenset({"kerb", "entrance", "barrier"})

LonLat = tuple[float, float]
Bbox = tuple[float, float, float, float]


@dataclass(frozen=True)
class OsmNode:
    id: int
    lon: float
    lat: float
    tags: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class OsmWay:
    id: int
    node_ids: tuple[int, ...]
    tags: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class OsmData:
    nodes: Mapping[int, OsmNode]
    ways: tuple[OsmWay, ...]


@dataclass(frozen=True)
class DraftNode:
    """Graph node before it gets a database id; `key` is unique within one draft."""

    key: int
    osm_id: int | None
    lon: float
    lat: float
    kind: str
    tags: Mapping[str, str]


@dataclass(frozen=True)
class DraftEdge:
    source: int
    target: int
    osm_way_id: int
    coords: tuple[LonLat, ...]
    length_m: float
    kind: str
    tags: Mapping[str, str]


@dataclass(frozen=True)
class GraphDraft:
    nodes: tuple[DraftNode, ...]
    edges: tuple[DraftEdge, ...]


def haversine_m(a: LonLat, b: LonLat) -> float:
    """Great-circle distance in meters; accurate to centimeters at edge scale."""
    d_lat = math.radians(b[1] - a[1])
    d_lon = math.radians(b[0] - a[0])
    h = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(a[1])) * math.cos(math.radians(b[1])) * math.sin(d_lon / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(min(1.0, h)))


def line_length_m(coords: Iterable[LonLat]) -> float:
    points = list(coords)
    return sum(haversine_m(points[i - 1], points[i]) for i in range(1, len(points)))


def classify_way(tags: Mapping[str, str]) -> str | None:
    """Return the edge kind for a way, or None when pedestrians cannot or should not use it."""
    highway = tags.get("highway")
    if highway not in PEDESTRIAN_HIGHWAYS and highway not in ROAD_HIGHWAYS:
        return None
    foot = tags.get("foot")
    if foot == "no":
        return None
    if tags.get("access") in {"private", "no"} and foot not in {"yes", "designated", "permissive"}:
        return None
    if highway == "steps":
        return "steps"
    if highway in PEDESTRIAN_HIGHWAYS:
        if tags.get("footway") == "crossing" or tags.get("path") == "crossing":
            return "crossing"
        if tags.get("footway") == "sidewalk":
            return "sidewalk"
        if tags.get("ramp") == "yes":
            return "ramp"
        return "path" if highway == "path" else "footway"

    sidewalk = tags.get("sidewalk") or tags.get("sidewalk:both")
    if sidewalk == "separate" or (tags.get("sidewalk:left") == "separate" and tags.get("sidewalk:right") == "separate"):
        # The sidewalks are mapped as their own ways; routing along the axis would duplicate them.
        return None
    if sidewalk in {"both", "left", "right", "yes"}:
        return "sidewalk"
    # No sidewalk information: pedestrians share the carriageway, which the cost function penalizes.
    return "road_shoulder"


def node_kind(tags: Mapping[str, str], degree: int) -> str:
    if tags.get("highway") == "elevator":
        return "elevator"
    if tags.get("highway") == "crossing":
        return "crossing"
    if "kerb" in tags:
        return "curb"
    if "entrance" in tags:
        return "entrance"
    return "junction" if degree >= 3 else "other"


def _inside(node: OsmNode, bbox: Bbox | None) -> bool:
    return bbox is None or (bbox[0] <= node.lon <= bbox[2] and bbox[1] <= node.lat <= bbox[3])


def _parts(way: OsmWay, nodes: Mapping[int, OsmNode], bbox: Bbox | None) -> list[list[OsmNode]]:
    """Runs of consecutive usable nodes: missing references and nodes outside the box cut the way."""
    parts: list[list[OsmNode]] = []
    current: list[OsmNode] = []
    for node_id in way.node_ids:
        node = nodes.get(node_id)
        if node is not None and _inside(node, bbox):
            if not current or current[-1].id != node.id:
                current.append(node)
        else:
            if len(current) >= 2:
                parts.append(current)
            current = []
    if len(current) >= 2:
        parts.append(current)
    return parts


def _cut(coords: list[LonLat], pieces: int) -> list[list[LonLat]]:
    """Split a polyline into `pieces` parts of equal length, keeping its shape points."""
    total = line_length_m(coords)
    targets = [total * k / pieces for k in range(1, pieces)]
    result: list[list[LonLat]] = []
    current = [coords[0]]
    walked = 0.0
    index = 0
    for i in range(1, len(coords)):
        start, end = coords[i - 1], coords[i]
        segment = haversine_m(start, end)
        while index < len(targets) and segment > 0 and targets[index] <= walked + segment + 1e-9:
            t = (targets[index] - walked) / segment
            point = (start[0] + (end[0] - start[0]) * t, start[1] + (end[1] - start[1]) * t)
            if point != current[-1]:
                current.append(point)
            result.append(current)
            current = [point]
            index += 1
        walked += segment
        if end != current[-1]:
            current.append(end)
    result.append(current)
    return result


def build_graph(data: OsmData, bbox: Bbox | None = None, max_edge_m: float = MAX_EDGE_M) -> GraphDraft:
    """Turn OSM ways into graph nodes and edges, deterministically.

    `bbox` (west, south, east, north) clips the result; ways are cut at the last node inside it.
    """
    selected: list[tuple[OsmWay, str, list[OsmNode]]] = []
    for way in sorted(data.ways, key=lambda item: item.id):
        kind = classify_way(way.tags)
        if kind is None:
            continue
        for part in _parts(way, data.nodes, bbox):
            selected.append((way, kind, part))

    usage: Counter[int] = Counter()
    for _, _, part in selected:
        for position, node in enumerate(part):
            # Endpoints count twice so they always break the way.
            usage[node.id] += 2 if position in (0, len(part) - 1) else 1

    def breaks(node: OsmNode) -> bool:
        return (
            usage[node.id] > 1
            or node.tags.get("highway") in {"crossing", "elevator"}
            or any(key in node.tags for key in BREAKING_NODE_KEYS)
        )

    keys: dict[int, int] = {}
    osm_nodes: dict[int, OsmNode] = {}
    synthetic: list[tuple[int, LonLat]] = []
    degree: Counter[int] = Counter()
    edges: list[DraftEdge] = []
    next_key = 0

    def key_of(node: OsmNode) -> int:
        nonlocal next_key
        if node.id not in keys:
            keys[node.id] = next_key
            osm_nodes[next_key] = node
            next_key += 1
        return keys[node.id]

    def new_synthetic(point: LonLat) -> int:
        nonlocal next_key
        key = next_key
        synthetic.append((key, point))
        next_key += 1
        return key

    for way, kind, part in selected:
        tags = {key: way.tags[key] for key in EDGE_TAG_KEYS if key in way.tags}
        start = 0
        for position in range(1, len(part)):
            if position != len(part) - 1 and not breaks(part[position]):
                continue
            run = part[start : position + 1]
            start = position
            coords = [(node.lon, node.lat) for node in run]
            length = line_length_m(coords)
            if length < 0.01:
                continue
            pieces = max(1, math.ceil(length / max_edge_m - 1e-9))
            cut = _cut(coords, pieces) if pieces > 1 else [coords]
            source = key_of(run[0])
            for index, piece in enumerate(cut):
                target = key_of(run[-1]) if index == len(cut) - 1 else new_synthetic(piece[-1])
                edges.append(
                    DraftEdge(
                        source=source,
                        target=target,
                        osm_way_id=way.id,
                        coords=tuple(piece),
                        length_m=round(line_length_m(piece), 3),
                        kind=kind,
                        tags=tags,
                    )
                )
                degree[source] += 1
                degree[target] += 1
                source = target

    nodes: list[DraftNode] = []
    for key, node in osm_nodes.items():
        tags = {name: node.tags[name] for name in NODE_TAG_KEYS if name in node.tags}
        nodes.append(DraftNode(key, node.id, node.lon, node.lat, node_kind(node.tags, degree[key]), tags))
    nodes.extend(DraftNode(key, None, point[0], point[1], "other", {}) for key, point in synthetic)
    nodes.sort(key=lambda item: item.key)
    return GraphDraft(nodes=tuple(nodes), edges=tuple(edges))


def connected_components(draft: GraphDraft) -> list[set[int]]:
    """Connected components of the draft, largest first (used to validate imports)."""
    adjacency: dict[int, set[int]] = {node.key: set() for node in draft.nodes}
    for edge in draft.edges:
        adjacency[edge.source].add(edge.target)
        adjacency[edge.target].add(edge.source)
    seen: set[int] = set()
    components: list[set[int]] = []
    for start in adjacency:
        if start in seen:
            continue
        component = {start}
        stack = [start]
        while stack:
            for neighbour in adjacency[stack.pop()]:
                if neighbour not in component:
                    component.add(neighbour)
                    stack.append(neighbour)
        seen |= component
        components.append(component)
    return sorted(components, key=len, reverse=True)
