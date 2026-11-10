"""Stage 2: node elevations and per-edge slopes from the elevation model (docs/05 §3)."""

from typing import Any

from sqlalchemy import text

from reduc.core.domain.elevation import edge_slope, parse_incline, sample_line
from reduc.core.pipeline.context import BATCH_SIZE, StageContext, StageStats
from reduc.core.providers.elevation.base import ElevationSource

#: Above this cell size (e.g. SRTM 30 m) slopes are kept but flagged as unreliable.
LOW_RESOLUTION_M = 10.0

_UPDATE_NODE = text("UPDATE node SET elevation_m = :elevation WHERE id = :id")
_UPDATE_EDGE = text(
    "UPDATE edge SET slope_pct = :slope, max_slope_pct = :max_slope, slope_source = :source WHERE id = :id"
)


def _edge_values(row: Any, source: ElevationSource | None, dem_label: str) -> dict[str, Any]:
    # A surveyed `incline` tag is more trustworthy than any elevation model.
    incline = parse_incline((row.tags or {}).get("incline"))
    if incline is not None:
        return {"id": row.id, "slope": incline, "max_slope": incline, "source": "osm_incline"}
    if source is not None:
        coords = [(float(point[0]), float(point[1])) for point in row.geometry["coordinates"]]
        points, distances = sample_line(coords)
        slope = edge_slope(distances, source.sample(points))
        if slope is not None:
            return {"id": row.id, "slope": slope.slope_pct, "max_slope": slope.max_slope_pct, "source": dem_label}
    return {"id": row.id, "slope": None, "max_slope": None, "source": None}


def run(ctx: StageContext) -> StageStats:
    """Rewrite `node.elevation_m` and the slope columns of every edge of the draft."""
    factory = ctx.deps.elevation_source
    source = factory(ctx.region) if factory is not None else None
    dem_label = "dem" if source is None or source.resolution_m <= LOW_RESOLUTION_M else "dem_lowres"
    params = {"version": ctx.map_version_id}
    session = ctx.session

    nodes = session.execute(
        text("SELECT id, ST_X(geom) AS lon, ST_Y(geom) AS lat FROM node WHERE map_version_id = :version ORDER BY id"),
        params,
    ).all()
    edges = session.execute(
        text(
            "SELECT id, tags, ST_AsGeoJSON(geom)::json AS geometry FROM edge "
            "WHERE map_version_id = :version ORDER BY id"
        ),
        params,
    ).all()
    total = len(nodes) + len(edges)

    nodes_with_elevation = 0
    for start in range(0, len(nodes), BATCH_SIZE):
        batch = nodes[start : start + BATCH_SIZE]
        values: list[float | None] = (
            source.sample([(row.lon, row.lat) for row in batch]) if source is not None else [None] * len(batch)
        )
        nodes_with_elevation += sum(value is not None for value in values)
        session.execute(
            _UPDATE_NODE, [{"id": row.id, "elevation": value} for row, value in zip(batch, values, strict=True)]
        )
        ctx.checkpoint(start + len(batch), total)

    by_source: dict[str, int] = {"dem": 0, "dem_lowres": 0, "osm_incline": 0, "none": 0}
    for start in range(0, len(edges), BATCH_SIZE):
        updates = [_edge_values(row, source, dem_label) for row in edges[start : start + BATCH_SIZE]]
        for update in updates:
            by_source[update["source"] or "none"] += 1
        session.execute(_UPDATE_EDGE, updates)
        ctx.checkpoint(len(nodes) + start + len(updates), total)

    return {
        "nodes": len(nodes),
        "nodes_with_elevation": nodes_with_elevation,
        "edges": len(edges),
        "edges_by_slope_source": by_source,
        "resolution_m": None if source is None else source.resolution_m,
    }
