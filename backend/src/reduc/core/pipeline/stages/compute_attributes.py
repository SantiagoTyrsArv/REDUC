"""Stage 7: `edge_accessibility` of every edge of the draft (docs/05 §9)."""

import uuid
from collections import defaultdict
from collections.abc import Iterable
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from reduc.core.domain.attributes import BarrierFact, EdgeFacts, compute_attributes, coverage_of
from reduc.core.pipeline.context import BATCH_SIZE, StageContext, StageStats

#: An image this close to an edge counts as having photographed it.
IMAGE_COVERAGE_M = 15.0

_EDGES = text(
    """
    SELECT e.id, e.kind, e.length_m, e.tags, e.slope_pct, e.max_slope_pct, e.slope_source, e.overrides,
           e.source, e.target, s.tags AS start_tags, t.tags AS end_tags,
           EXISTS (
               SELECT 1 FROM image i
               WHERE i.region_id = :region AND i.status <> 'failed'
                 AND ST_DWithin(i.geom::geography, e.geom::geography, :coverage_m)
           ) AS has_imagery
    FROM edge e JOIN node s ON s.id = e.source JOIN node t ON t.id = e.target
    WHERE e.map_version_id = :version AND (CAST(:edge_ids AS bigint[]) IS NULL OR e.id = ANY(:edge_ids))
    ORDER BY e.id
    """
)
_BARRIERS = text(
    """
    SELECT class, severity, confidence, verification_status, attributes, edge_id, node_id
    FROM barrier WHERE map_version_id = :version AND (edge_id IS NOT NULL OR node_id IS NOT NULL)
    """
)
_UPSERT = text(
    """
    INSERT INTO edge_accessibility (
        edge_id, slope_pct, max_slope_pct, cross_slope_pct, width_m, surface_class, has_steps,
        max_step_height_cm, curb_ramp_start, curb_ramp_end, obstacle_level, sidewalk_missing,
        data_confidence, verified, coverage, status, computed_at
    ) VALUES (
        :edge_id, :slope_pct, :max_slope_pct, :cross_slope_pct, :width_m, :surface_class, :has_steps,
        :max_step_height_cm, :curb_ramp_start, :curb_ramp_end, :obstacle_level, :sidewalk_missing,
        :data_confidence, :verified, :coverage, :status, now()
    )
    ON CONFLICT (edge_id) DO UPDATE SET
        slope_pct = EXCLUDED.slope_pct, max_slope_pct = EXCLUDED.max_slope_pct,
        cross_slope_pct = EXCLUDED.cross_slope_pct, width_m = EXCLUDED.width_m,
        surface_class = EXCLUDED.surface_class, has_steps = EXCLUDED.has_steps,
        max_step_height_cm = EXCLUDED.max_step_height_cm, curb_ramp_start = EXCLUDED.curb_ramp_start,
        curb_ramp_end = EXCLUDED.curb_ramp_end, obstacle_level = EXCLUDED.obstacle_level,
        sidewalk_missing = EXCLUDED.sidewalk_missing, data_confidence = EXCLUDED.data_confidence,
        verified = EXCLUDED.verified, coverage = EXCLUDED.coverage, status = EXCLUDED.status,
        computed_at = now(), updated_at = now()
    """
)


def _fact(row: Any, position: str) -> BarrierFact:
    return BarrierFact(
        barrier_class=row[0],
        severity=row.severity,
        confidence=float(row.confidence),
        verification_status=row.verification_status,
        position=position,  # type: ignore[arg-type]
        attributes=row.attributes or {},
    )


def recompute_edges(
    session: Session,
    region_id: uuid.UUID,
    map_version_id: uuid.UUID,
    edge_ids: Iterable[int] | None = None,
    on_batch: Any = None,
) -> dict[str, int]:
    """Rewrite the attributes of the given edges (all when None). Also used after each verification."""
    ids = None if edge_ids is None else sorted(set(edge_ids))
    if ids is not None and not ids:
        return {}
    by_edge: dict[int, list[Any]] = defaultdict(list)
    by_node: dict[int, list[Any]] = defaultdict(list)
    for row in session.execute(_BARRIERS, {"version": map_version_id}):
        if row.edge_id is not None:
            by_edge[row.edge_id].append(row)
        if row.node_id is not None:
            by_node[row.node_id].append(row)

    edges = session.execute(
        _EDGES,
        {"version": map_version_id, "region": region_id, "coverage_m": IMAGE_COVERAGE_M, "edge_ids": ids},
    ).all()
    statuses: dict[str, int] = defaultdict(int)
    for start in range(0, len(edges), BATCH_SIZE):
        rows = []
        for edge in edges[start : start + BATCH_SIZE]:
            barriers = (
                [_fact(row, "edge") for row in by_edge.get(edge.id, ())]
                + [_fact(row, "start") for row in by_node.get(edge.source, ())]
                + [_fact(row, "end") for row in by_node.get(edge.target, ())]
            )
            tags = edge.tags or {}
            facts = EdgeFacts(
                kind=edge.kind,
                length_m=float(edge.length_m),
                tags=tags,
                slope_pct=edge.slope_pct,
                max_slope_pct=edge.max_slope_pct,
                slope_source=edge.slope_source,
                start_node_tags=edge.start_tags or {},
                end_node_tags=edge.end_tags or {},
                overrides=edge.overrides or {},
                coverage=coverage_of(tags, bool(edge.has_imagery)),
            )
            attributes = compute_attributes(facts, barriers)
            statuses[attributes.status] += 1
            rows.append({"edge_id": edge.id, **attributes.__dict__})
        session.execute(_UPSERT, rows)
        if on_batch is not None:
            on_batch(start + len(rows), len(edges))
    return dict(statuses)


def run(ctx: StageContext) -> StageStats:
    statuses = recompute_edges(ctx.session, ctx.region.id, ctx.map_version_id, None, ctx.checkpoint)
    return {"edges": sum(statuses.values()), "by_status": statuses}
