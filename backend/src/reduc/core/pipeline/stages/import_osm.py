"""Stage 1: pedestrian network of the region from OpenStreetMap (docs/05 §2)."""

from sqlalchemy import text

from reduc.core.db.repositories.graph import replace_graph
from reduc.core.pipeline.context import StageContext, StageStats
from reduc.core.providers.osm.graph import Bbox, build_graph, connected_components
from reduc.core.providers.osm.overpass import expand_bbox

DEFAULT_BUFFER_M = 100.0


class StageConfigurationError(Exception):
    """A stage cannot run because the region or the deployment lacks something it needs."""


def region_bbox(ctx: StageContext) -> Bbox:
    row = ctx.session.execute(
        text(
            "SELECT ST_XMin(boundary) AS west, ST_YMin(boundary) AS south, "
            "ST_XMax(boundary) AS east, ST_YMax(boundary) AS north FROM region WHERE id = :id"
        ),
        {"id": ctx.region.id},
    ).one()
    return (float(row.west), float(row.south), float(row.east), float(row.north))


def run(ctx: StageContext) -> StageStats:
    """Replace the nodes and edges of the draft with the network inside the buffered boundary."""
    if ctx.deps.osm_source is None:
        raise StageConfigurationError("No hay fuente OSM configurada")
    osm_config = (ctx.region.config or {}).get("osm") or {}
    bbox = expand_bbox(region_bbox(ctx), float(osm_config.get("buffer_m", DEFAULT_BUFFER_M)))
    ctx.checkpoint(0, 3)
    data = ctx.deps.osm_source(ctx.region, bbox)
    ctx.checkpoint(1, 3)
    draft = build_graph(data, bbox=bbox)
    ctx.checkpoint(2, 3)
    counts = replace_graph(ctx.session, ctx.map_version_id, draft)
    components = connected_components(draft)
    ctx.checkpoint(3, 3)
    return {
        "nodes": counts.nodes,
        "edges": counts.edges,
        "components": len(components),
        "largest_component_pct": round(100.0 * len(components[0]) / counts.nodes, 1) if components else 0.0,
    }
