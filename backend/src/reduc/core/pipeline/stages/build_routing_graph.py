"""Stage 8: refresh the `routing_edge` view that pgRouting reads."""

from sqlalchemy import text

from reduc.core.pipeline.context import StageContext, StageStats


def run(ctx: StageContext) -> StageStats:
    """Refresh the view and report edges that would be invisible to routing."""
    ctx.checkpoint(0, 1)
    missing: int = ctx.session.execute(
        text(
            "SELECT count(*) FROM edge e LEFT JOIN edge_accessibility a ON a.edge_id = e.id "
            "WHERE e.map_version_id = :version AND a.edge_id IS NULL"
        ),
        {"version": ctx.map_version_id},
    ).scalar_one()
    ctx.session.execute(text("REFRESH MATERIALIZED VIEW routing_edge"))
    routable: int = ctx.session.execute(
        text("SELECT count(*) FROM routing_edge WHERE map_version_id = :version"), {"version": ctx.map_version_id}
    ).scalar_one()
    ctx.checkpoint(1, 1)
    return {"routing_edges": int(routable), "edges_without_attributes": int(missing)}
