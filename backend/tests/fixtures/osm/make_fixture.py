"""Regenerate `sample.osm.pbf` and `sample.osm` from `sample.py`.

Run from `backend/`: `uv run python -m tests.fixtures.osm.make_fixture`
"""

from pathlib import Path
from xml.sax.saxutils import quoteattr

import osmium
from tests.fixtures.osm.sample import NODES, WAYS

HERE = Path(__file__).parent


def write_pbf(path: Path) -> None:
    path.unlink(missing_ok=True)
    writer = osmium.SimpleWriter(str(path))
    for node in NODES:
        writer.add_node(osmium.osm.mutable.Node(id=node.id, location=(node.lon, node.lat), tags=dict(node.tags)))
    for way in WAYS:
        writer.add_way(osmium.osm.mutable.Way(id=way.id, nodes=list(way.node_ids), tags=dict(way.tags)))
    writer.close()


def write_xml(path: Path) -> None:
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<osm version="0.6" generator="reduc-fixture">']
    for node in NODES:
        lines.append(f'  <node id="{node.id}" lat="{node.lat}" lon="{node.lon}">')
        lines += [f"    <tag k={quoteattr(k)} v={quoteattr(v)}/>" for k, v in node.tags.items()]
        lines.append("  </node>")
    for way in WAYS:
        lines.append(f'  <way id="{way.id}">')
        lines += [f'    <nd ref="{ref}"/>' for ref in way.node_ids]
        lines += [f"    <tag k={quoteattr(k)} v={quoteattr(v)}/>" for k, v in way.tags.items()]
        lines.append("  </way>")
    lines.append("</osm>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    write_pbf(HERE / "sample.osm.pbf")
    write_xml(HERE / "sample.osm")
