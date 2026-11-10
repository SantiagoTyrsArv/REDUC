"""Segments, warnings, instructions, score and duration of described routes."""

from dataclasses import replace

import pytest

from reduc.core.domain.profile import PROFILE_PRESETS
from reduc.core.routing.geometry import bearing_deg, cut_line, destination_point, haversine_m, turn_angle_deg
from reduc.core.routing.messages import barrier_message, normalize_locale, translate
from reduc.core.routing.narrative import (
    NearbyPoi,
    TraversedEdge,
    accessibility_score,
    build_instructions,
    build_segments,
    describe_route,
    duration_seconds,
    edge_warning_codes,
)

PROFILE = PROFILE_PRESETS["manual"]
ORIGIN = (-74.065, 4.601)
STEP = 0.00045


def edge(edge_id: int, start: tuple[float, float], end: tuple[float, float], **overrides: object) -> TraversedEdge:
    base = TraversedEdge(
        edge_id=edge_id,
        coords=(start, end),
        length_m=50.0,
        kind="sidewalk",
        slope_pct=0.0,
        width_m=1.5,
        surface_class=0,
        curb_ramp="n/a",
        sidewalk_missing=False,
        verified=True,
        penalty=0.0,
    )
    return replace(base, **overrides)  # type: ignore[arg-type]


def east(edge_id: int, column: int, **overrides: object) -> TraversedEdge:
    return edge(
        edge_id, (ORIGIN[0] + column * STEP, ORIGIN[1]), (ORIGIN[0] + (column + 1) * STEP, ORIGIN[1]), **overrides
    )


def codes(item: TraversedEdge) -> set[str]:
    return {code for code, _severity in edge_warning_codes(item, PROFILE)}


def test_flat_verified_edge_has_no_warnings() -> None:
    assert codes(east(1, 0)) == set()


@pytest.mark.parametrize(
    ("overrides", "code", "severity"),
    [
        ({"slope_pct": 4.0}, "slope_moderate", "minor"),
        ({"slope_pct": 5.8}, "slope_moderate", "major"),
        ({"slope_pct": -5.0}, "slope_steep_downhill", "minor"),
        ({"slope_pct": -7.5}, "slope_steep_downhill", "major"),
        ({"surface_class": 2}, "surface_irregular", "minor"),
        ({"surface_class": 3}, "surface_irregular", "major"),
        ({"verified": False}, "unverified_segment", "minor"),
        ({"kind": "crossing", "curb_ramp": "unknown"}, "curb_ramp_unknown", "major"),
        ({"width_m": 1.0}, "narrow_passage", "minor"),
        ({"kind": "road_shoulder"}, "road_shoulder", "major"),
        ({"sidewalk_missing": True}, "road_shoulder", "major"),
        ({"blocked": True}, "exceeds_profile", "major"),
    ],
)
def test_each_warning_rule(overrides: dict[str, object], code: str, severity: str) -> None:
    assert (code, severity) in edge_warning_codes(east(1, 0, **overrides), PROFILE)


def test_gentle_slopes_do_not_warn() -> None:
    assert codes(east(1, 0, slope_pct=2.0)) == set()
    assert codes(east(1, 0, slope_pct=-2.0)) == set()


def test_consecutive_similar_edges_are_grouped_into_segments() -> None:
    edges = (east(1, 0), east(2, 1), east(3, 2, slope_pct=5.0), east(4, 3, slope_pct=5.0), east(5, 4))

    segments = build_segments(edges, PROFILE, "es")

    assert [segment.edge_ids for segment in segments] == [(1, 2), (3, 4), (5,)]
    assert [segment.status for segment in segments] == ["accessible", "caution", "accessible"]
    assert segments[1].distance_m == 100.0
    assert segments[1].slope_pct == 5.0
    assert segments[1].warnings[0].message == "Pendiente de subida del 5 % durante 100 m"
    assert len(segments[0].coords) == 3


def test_warning_messages_are_localized() -> None:
    edges = (east(1, 0, slope_pct=5.0),)

    assert build_segments(edges, PROFILE, "en")[0].warnings[0].message == "Uphill slope of 5% for 50 m"


def test_blocked_edge_is_reported_as_inaccessible() -> None:
    segment = build_segments((east(1, 0, blocked=True),), PROFILE, "es")[0]

    assert segment.status == "inaccessible"
    assert segment.warnings[0].code == "exceeds_profile"


def test_score_follows_the_documented_formula() -> None:
    clean = (east(1, 0), east(2, 1))
    assert accessibility_score(clean, build_segments(clean, PROFILE, "es")) == 100

    penalized = (east(1, 0, penalty=0.5), east(2, 1, penalty=0.0))
    assert accessibility_score(penalized, build_segments(penalized, PROFILE, "es")) == 90

    with_major = (east(1, 0, kind="road_shoulder", penalty=0.5), east(2, 1))
    assert accessibility_score(with_major, build_segments(with_major, PROFILE, "es")) == 80

    awful = tuple(east(index, index, blocked=True, penalty=2.0, surface_class=index % 2) for index in range(6))
    assert accessibility_score(awful, build_segments(awful, PROFILE, "es")) == 0


def test_duration_slows_down_on_steep_climbs_only() -> None:
    flat = (east(1, 0),)
    climb = (east(1, 0, slope_pct=5.5),)
    descent = (east(1, 0, slope_pct=-7.0),)

    assert duration_seconds(flat, PROFILE) == round(50 / 0.9)
    assert duration_seconds(climb, PROFILE) == round(50 / (0.9 * 0.7))
    assert duration_seconds(descent, PROFILE) == round(50 / 0.9)


def test_instructions_cover_departure_turns_and_arrival() -> None:
    corner = (ORIGIN[0] + 2 * STEP, ORIGIN[1])
    north = edge(3, corner, (corner[0], corner[1] + STEP))
    west = edge(4, (corner[0], corner[1] + STEP), (corner[0] - STEP, corner[1] + STEP))
    edges = (east(1, 0), east(2, 1), north, west)

    instructions = build_instructions(edges, (NearbyPoi("Biblioteca", corner),), "es")

    assert [step.maneuver for step in instructions] == ["depart", "left", "left", "arrive"]
    assert instructions[0].text == "Sal hacia el este y continúa 100 m"
    assert instructions[0].distance_m == 100.0
    assert instructions[1].text == "Gira a la izquierda junto a Biblioteca y continúa 50 m"
    assert instructions[1].location == corner
    assert instructions[2].text == "Gira a la izquierda y continúa 50 m"
    assert instructions[3].text == "Has llegado a tu destino"


def test_right_turn_and_u_turn_are_distinguished() -> None:
    corner = (ORIGIN[0] + STEP, ORIGIN[1])
    south = edge(2, corner, (corner[0], corner[1] - STEP))
    back = edge(3, (corner[0], corner[1] - STEP), corner)

    instructions = build_instructions((east(1, 0), south, back), (), "en")

    assert [step.maneuver for step in instructions] == ["depart", "right", "u_turn", "arrive"]
    assert instructions[1].text == "Turn right and continue for 50 m"


def test_describe_route_summarizes_everything() -> None:
    edges = (east(1, 0), east(2, 1, slope_pct=5.5, verified=False, penalty=0.4))

    narrative = describe_route(edges, PROFILE, "es")

    assert narrative.distance_m == 100.0
    assert narrative.verified_pct == 50.0
    assert narrative.max_slope_pct == 5.5
    assert narrative.caution_segments == 1
    assert narrative.accessibility_score == 82
    assert narrative.duration_s == round(50 / 0.9 + 50 / (0.9 * 0.7))
    assert len(narrative.coords) == 3
    assert narrative.instructions[-1].maneuver == "arrive"


def test_empty_route_is_described_without_errors() -> None:
    narrative = describe_route((), PROFILE, "es")

    assert narrative.coords == ()
    assert narrative.distance_m == 0.0
    assert narrative.instructions == ()


def test_geometry_helpers() -> None:
    a, b = (0.0, 0.0), (0.0, 1.0)
    assert haversine_m(a, b) == pytest.approx(111_195, rel=1e-3)
    assert bearing_deg(a, b) == pytest.approx(0.0)
    assert bearing_deg(a, (1.0, 0.0)) == pytest.approx(90.0)
    assert turn_angle_deg(350.0, 20.0) == pytest.approx(30.0)
    assert turn_angle_deg(20.0, 350.0) == pytest.approx(-30.0)
    assert turn_angle_deg(0.0, 180.0) == 180.0
    moved = destination_point(a, 90.0, 1000.0)
    assert haversine_m(a, moved) == pytest.approx(1000.0, rel=1e-6)
    assert bearing_deg(a, moved) == pytest.approx(90.0, abs=1e-3)


def test_cut_line_matches_line_substring_semantics() -> None:
    line = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0))

    assert cut_line(line, 0.0, 1.0) == line
    assert cut_line(line, 0.25, 0.75) == ((0.5, 0.0), (1.0, 0.0), (1.0, 0.5))
    assert cut_line(line, 0.5, 0.5) == ((1.0, 0.0), (1.0, 0.0))
    with pytest.raises(ValueError):
        cut_line(line, 0.8, 0.2)


def test_messages_helpers() -> None:
    assert normalize_locale("en-US") == "en"
    assert normalize_locale("fr") == "es"
    assert normalize_locale(None) == "es"
    assert barrier_message("es", "stairs", {"step_count": 6}) == "Escalera de 6 escalones"
    assert barrier_message("es", "stairs", {}) == "Escalera"
    assert barrier_message("en", "single_step", {"step_height_cm": 12.0}) == "12 cm step"
    assert barrier_message("es", "unknown_class", {}) == "Barrera"
    assert translate("es", "instruction.arrive") == "Has llegado a tu destino"
