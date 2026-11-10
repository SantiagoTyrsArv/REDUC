"""Unit tests for every hard restriction and soft accessibility penalty."""

from dataclasses import replace

import pytest

from reduc.core.domain.profile import PROFILE_PRESETS
from reduc.core.routing.cost import BLOCKED_COST, EdgeCostInput, build_cost_sql, edge_cost

PROFILE = PROFILE_PRESETS["manual"]
BASE_EDGE = EdgeCostInput(
    length_m=100.0,
    kind="sidewalk",
    max_slope_pct=0.0,
    cross_slope_pct=1.0,
    width_m=1.5,
    surface_class=0,
    has_steps=False,
    max_step_height_cm=None,
    curb_ramp_start="n/a",
    curb_ramp_end="n/a",
    obstacle_level=0,
    sidewalk_missing=False,
    data_confidence=1.0,
    verified=True,
    has_confirmed_critical_barrier=False,
)


@pytest.mark.parametrize(
    "edge",
    [
        pytest.param(replace(BASE_EDGE, has_steps=True, max_step_height_cm=2.1), id="step-too-high"),
        pytest.param(replace(BASE_EDGE, has_steps=True, max_step_height_cm=None), id="unknown-step-height"),
        pytest.param(replace(BASE_EDGE, max_slope_pct=6.1), id="uphill-too-steep"),
        pytest.param(replace(BASE_EDGE, max_slope_pct=-8.1), id="downhill-too-steep"),
        pytest.param(replace(BASE_EDGE, cross_slope_pct=3.1), id="cross-slope-too-steep"),
        pytest.param(replace(BASE_EDGE, width_m=0.89), id="narrow-passage"),
        pytest.param(replace(BASE_EDGE, surface_class=3), id="surface-too-irregular"),
        pytest.param(replace(BASE_EDGE, obstacle_level=2), id="blocking-obstacle"),
        pytest.param(replace(BASE_EDGE, has_confirmed_critical_barrier=True), id="confirmed-critical-barrier"),
    ],
)
def test_hard_restrictions_block_the_edge(edge: EdgeCostInput) -> None:
    """Every documented hard constraint returns pgRouting's blocked cost."""
    assert edge_cost(PROFILE, edge) == BLOCKED_COST


def test_slope_limit_depends_on_direction() -> None:
    """A slope can be impossible uphill while remaining exactly at the downhill limit."""
    edge = replace(BASE_EDGE, max_slope_pct=8.0)

    assert edge_cost(PROFILE, edge) == BLOCKED_COST
    assert edge_cost(PROFILE, edge, reverse=True) > 0.0


def test_steps_without_a_reported_step_are_not_blocked() -> None:
    """An absent height only fails closed when the data says steps exist."""
    assert edge_cost(PROFILE, BASE_EDGE) == 100.0


def test_curb_ramp_restriction_uses_the_arrival_end() -> None:
    """Forward and reverse traversal inspect opposite ends of a crossing."""
    edge = replace(BASE_EDGE, kind="crossing", curb_ramp_start="n/a", curb_ramp_end="no")

    assert edge_cost(PROFILE, edge) == BLOCKED_COST
    assert edge_cost(PROFILE, edge, reverse=True) > 0.0


def test_curb_ramp_outside_a_crossing_is_not_applicable() -> None:
    """A curb value on an ordinary sidewalk does not invent a crossing restriction."""
    edge = replace(BASE_EDGE, curb_ramp_end="no")

    assert edge_cost(PROFILE, edge) == 100.0


def test_unverified_edges_follow_the_profile_preference() -> None:
    """Unverified data is penalized by confidence but only prohibited on request."""
    edge = replace(BASE_EDGE, verified=False, data_confidence=0.5)
    conservative = replace(PROFILE, avoid_unverified=True)

    assert edge_cost(PROFILE, edge) == 130.0
    assert edge_cost(conservative, edge) == BLOCKED_COST
    assert edge_cost(conservative, edge, allow_unverified=True) == 130.0


def test_unknown_curb_ramp_is_penalized_or_blocked() -> None:
    """Unknown crossings receive a soft penalty unless both conservative options are enabled."""
    edge = replace(BASE_EDGE, kind="crossing", curb_ramp_end="unknown")
    conservative = replace(PROFILE, avoid_unverified=True)

    assert edge_cost(PROFILE, edge) == 140.0
    assert edge_cost(conservative, edge) == BLOCKED_COST
    assert edge_cost(conservative, edge, allow_unverified=True) == BLOCKED_COST
    assert edge_cost(conservative, edge, allow_unverified=True, allow_unknown_curb_ramps=True) == 140.0


def test_soft_penalties_are_additive_equivalent_meters() -> None:
    """All soft components compose without double-counting a missing sidewalk."""
    edge = replace(
        BASE_EDGE,
        kind="crossing",
        max_slope_pct=3.0,
        surface_class=2,
        obstacle_level=1,
        sidewalk_missing=True,
        data_confidence=0.5,
        curb_ramp_end="unknown",
    )

    assert edge_cost(PROFILE, edge) == pytest.approx(325.0)


def test_sql_builder_exposes_both_directions_and_all_profile_params() -> None:
    """The SQL contract is suitable for pgRouting and keeps profile values parameterized."""
    sql, params = build_cost_sql(PROFILE)

    assert "routing_edge.*" in sql
    assert " AS cost" in sql
    assert " AS reverse_cost" in sql
    assert "b.severity = 'critical'" in sql
    assert "b.verification_status = 'confirmed'" in sql
    assert params["max_uphill_pct"] == 6.0
    assert params["max_downhill_pct"] == 8.0
    assert params["weight_slope"] == 1.0
