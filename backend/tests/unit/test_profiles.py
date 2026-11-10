"""Tests for mobility presets and profile validation."""

from dataclasses import FrozenInstanceError

import pytest

from reduc.core.domain.profile import DEVICE_TYPES, PROFILE_PRESETS, MobilityProfile, Weights


def test_presets_match_the_specification() -> None:
    """All four public presets expose the documented accessibility limits."""
    expected = {
        "manual": (6.0, 8.0, 3.0, 2.0, 0.9, 2, 0.9),
        "manual_assisted": (10.0, 10.0, 4.0, 4.0, 0.9, 3, 1.0),
        "electric": (12.0, 10.0, 5.0, 5.0, 1.0, 3, 1.3),
        "scooter": (10.0, 10.0, 5.0, 3.0, 1.1, 2, 1.5),
    }

    assert tuple(PROFILE_PRESETS) == DEVICE_TYPES
    for device, values in expected.items():
        profile = PROFILE_PRESETS[device]  # type: ignore[index]
        assert (
            profile.max_uphill_pct,
            profile.max_downhill_pct,
            profile.max_cross_slope_pct,
            profile.max_step_cm,
            profile.min_width_m,
            profile.max_surface_class,
            profile.speed_mps,
        ) == values
        assert profile.require_curb_ramps is True
        assert profile.avoid_unverified is False
        assert profile.weights == Weights()


def test_profiles_are_immutable() -> None:
    """Route calculations cannot mutate a shared preset."""
    with pytest.raises(FrozenInstanceError):
        PROFILE_PRESETS["manual"].speed_mps = 2.0  # type: ignore[misc]


@pytest.mark.parametrize("weight", ["slope", "surface", "uncertainty"])
@pytest.mark.parametrize("value", [-0.1, 3.1, float("nan"), float("inf")])
def test_weights_reject_out_of_range_values(weight: str, value: float) -> None:
    """Invalid weights are rejected before generating either implementation."""
    with pytest.raises(ValueError, match=weight):
        Weights(**{weight: value})  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_uphill_pct", 0.0),
        ("max_downhill_pct", -1.0),
        ("max_cross_slope_pct", float("nan")),
        ("max_step_cm", -0.1),
        ("min_width_m", -0.1),
        ("max_surface_class", 5),
        ("speed_mps", 0.0),
    ],
)
def test_profiles_reject_invalid_limits(field: str, value: float) -> None:
    """Invalid thresholds cannot silently produce unsafe or nonsensical routes."""
    profile = PROFILE_PRESETS["manual"]
    values = {name: getattr(profile, name) for name in profile.__dataclass_fields__}
    values[field] = value

    with pytest.raises(ValueError, match=field):
        MobilityProfile(**values)  # type: ignore[arg-type]
