"""Property-based equivalence between the Python and SQL cost implementations."""

import sqlite3
from contextlib import closing
from dataclasses import asdict

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from reduc.core.domain.profile import DEVICE_TYPES, MobilityProfile, Weights
from reduc.core.routing.cost import EdgeCostInput, build_cost_sql, edge_cost

finite_weights = st.floats(min_value=0.0, max_value=3.0)
profiles = st.builds(
    MobilityProfile,
    device=st.sampled_from(DEVICE_TYPES),
    max_uphill_pct=st.floats(min_value=0.5, max_value=20.0),
    max_downhill_pct=st.floats(min_value=0.5, max_value=20.0),
    max_cross_slope_pct=st.floats(min_value=0.5, max_value=10.0),
    max_step_cm=st.floats(min_value=0.0, max_value=10.0),
    min_width_m=st.floats(min_value=0.0, max_value=2.0),
    max_surface_class=st.integers(min_value=0, max_value=4),
    require_curb_ramps=st.booleans(),
    avoid_unverified=st.booleans(),
    speed_mps=st.floats(min_value=0.2, max_value=3.0),
    weights=st.builds(Weights, slope=finite_weights, surface=finite_weights, uncertainty=finite_weights),
)
edges = st.builds(
    EdgeCostInput,
    length_m=st.floats(min_value=0.1, max_value=1000.0),
    kind=st.sampled_from(("sidewalk", "footway", "path", "crossing", "steps", "ramp", "road_shoulder")),
    max_slope_pct=st.floats(min_value=-20.0, max_value=20.0),
    cross_slope_pct=st.one_of(st.none(), st.floats(min_value=-10.0, max_value=10.0)),
    width_m=st.one_of(st.none(), st.floats(min_value=0.2, max_value=4.0)),
    surface_class=st.integers(min_value=0, max_value=4),
    has_steps=st.booleans(),
    max_step_height_cm=st.one_of(st.none(), st.floats(min_value=0.0, max_value=20.0)),
    curb_ramp_start=st.sampled_from(("yes", "no", "unknown", "n/a")),
    curb_ramp_end=st.sampled_from(("yes", "no", "unknown", "n/a")),
    obstacle_level=st.integers(min_value=0, max_value=2),
    sidewalk_missing=st.booleans(),
    data_confidence=st.floats(min_value=0.0, max_value=1.0),
    verified=st.booleans(),
    has_confirmed_critical_barrier=st.booleans(),
)

SCHEMA = """
CREATE TABLE routing_edge (
    id INTEGER PRIMARY KEY,
    source INTEGER NOT NULL,
    target INTEGER NOT NULL,
    length_m REAL NOT NULL,
    kind TEXT NOT NULL,
    max_slope_pct REAL NOT NULL,
    cross_slope_pct REAL NULL,
    width_m REAL NULL,
    surface_class INTEGER NOT NULL,
    has_steps BOOLEAN NOT NULL,
    max_step_height_cm REAL NULL,
    curb_ramp_start TEXT NOT NULL,
    curb_ramp_end TEXT NOT NULL,
    obstacle_level INTEGER NOT NULL,
    sidewalk_missing BOOLEAN NOT NULL,
    data_confidence REAL NOT NULL,
    verified BOOLEAN NOT NULL,
    has_confirmed_critical_barrier BOOLEAN NOT NULL
);
CREATE TABLE barrier (
    edge_id INTEGER NULL,
    node_id INTEGER NULL,
    severity TEXT NOT NULL,
    verification_status TEXT NOT NULL
);
"""

INSERT_EDGE = """
INSERT INTO routing_edge (
    id, source, target, length_m, kind, max_slope_pct, cross_slope_pct, width_m,
    surface_class, has_steps, max_step_height_cm, curb_ramp_start, curb_ramp_end,
    obstacle_level, sidewalk_missing, data_confidence, verified, has_confirmed_critical_barrier
) VALUES (
    1, 10, 20, :length_m, :kind, :max_slope_pct, :cross_slope_pct, :width_m,
    :surface_class, :has_steps, :max_step_height_cm, :curb_ramp_start, :curb_ramp_end,
    :obstacle_level, :sidewalk_missing, :data_confidence, :verified, 0
)
"""


def _sql_costs(
    profile: MobilityProfile, edge: EdgeCostInput, allow_unverified: bool, allow_unknown_curb_ramps: bool
) -> tuple[float, float]:
    """Execute generated SQL against the same synthetic edge used by Python."""
    sql, params = build_cost_sql(
        profile,
        allow_unverified=allow_unverified,
        allow_unknown_curb_ramps=allow_unknown_curb_ramps,
    )
    with closing(sqlite3.connect(":memory:")) as connection:
        connection.executescript(SCHEMA)
        connection.execute(INSERT_EDGE, asdict(edge))
        if edge.has_confirmed_critical_barrier:
            connection.execute(
                "INSERT INTO barrier (edge_id, node_id, severity, verification_status) "
                "VALUES (1, NULL, 'critical', 'confirmed')"
            )
        row = connection.execute(f"SELECT cost, reverse_cost FROM ({sql}) AS costed", params).fetchone()
    assert row is not None
    return float(row[0]), float(row[1])


@given(
    profile=profiles,
    edge=edges,
    allow_unverified=st.booleans(),
    allow_unknown_curb_ramps=st.booleans(),
)
@settings(max_examples=100, deadline=None)
def test_python_and_sql_costs_are_equivalent(
    profile: MobilityProfile, edge: EdgeCostInput, allow_unverified: bool, allow_unknown_curb_ramps: bool
) -> None:
    """Arbitrary profiles, edges and fallback flags produce identical costs."""
    forward_sql, reverse_sql = _sql_costs(profile, edge, allow_unverified, allow_unknown_curb_ramps)
    options = {
        "allow_unverified": allow_unverified,
        "allow_unknown_curb_ramps": allow_unknown_curb_ramps,
    }

    assert forward_sql == pytest.approx(edge_cost(profile, edge, **options), rel=1e-10, abs=1e-10)
    assert reverse_sql == pytest.approx(edge_cost(profile, edge, reverse=True, **options), rel=1e-10, abs=1e-10)
