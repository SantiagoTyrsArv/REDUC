"""Persistence of the pedestrian graph of one draft map version."""

import uuid
from dataclasses import dataclass

from geoalchemy2.elements import WKTElement
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from reduc.core.db.models import Barrier, Edge, EdgeAccessibility, MapVersion, Node
from reduc.core.providers.osm.graph import GraphDraft

BATCH_SIZE = 500


class VersionNotDraftError(Exception):
    """Raised when a stage tries to rewrite a published or archived version."""


@dataclass(frozen=True)
class GraphCounts:
    nodes: int
    edges: int


def require_draft(session: Session, map_version_id: uuid.UUID) -> MapVersion:
    """Stages only ever write to drafts; published maps are immutable."""
    version = session.get(MapVersion, map_version_id)
    if version is None or version.status != "draft":
        raise VersionNotDraftError(str(map_version_id))
    return version


def clear_graph(session: Session, map_version_id: uuid.UUID) -> None:
    """Remove nodes and edges of a draft together with everything derived from them."""
    edge_ids = select(Edge.id).where(Edge.map_version_id == map_version_id)
    session.execute(delete(EdgeAccessibility).where(EdgeAccessibility.edge_id.in_(edge_ids)))
    # Barriers survive a re-import; they are re-attached to the new graph by later stages.
    session.execute(update(Barrier).where(Barrier.map_version_id == map_version_id).values(edge_id=None, node_id=None))
    session.execute(delete(Edge).where(Edge.map_version_id == map_version_id))
    session.execute(delete(Node).where(Node.map_version_id == map_version_id))


def replace_graph(session: Session, map_version_id: uuid.UUID, draft: GraphDraft) -> GraphCounts:
    """Idempotently write a graph draft: previous nodes and edges of the version are replaced."""
    require_draft(session, map_version_id)
    clear_graph(session, map_version_id)

    ids: dict[int, int] = {}
    for start in range(0, len(draft.nodes), BATCH_SIZE):
        batch = draft.nodes[start : start + BATCH_SIZE]
        rows = [
            Node(
                map_version_id=map_version_id,
                osm_id=item.osm_id,
                geom=WKTElement(f"POINT({item.lon!r} {item.lat!r})", srid=4326),
                kind=item.kind,
                tags=dict(item.tags),
            )
            for item in batch
        ]
        session.add_all(rows)
        session.flush()
        ids.update({item.key: row.id for item, row in zip(batch, rows, strict=True)})

    for start in range(0, len(draft.edges), BATCH_SIZE):
        session.add_all(
            Edge(
                map_version_id=map_version_id,
                source=ids[item.source],
                target=ids[item.target],
                osm_way_id=item.osm_way_id,
                geom=WKTElement(
                    "LINESTRING(" + ",".join(f"{lon!r} {lat!r}" for lon, lat in item.coords) + ")", srid=4326
                ),
                length_m=item.length_m,
                kind=item.kind,
                tags=dict(item.tags),
            )
            for item in draft.edges[start : start + BATCH_SIZE]
        )
        session.flush()
    return GraphCounts(nodes=len(draft.nodes), edges=len(draft.edges))
