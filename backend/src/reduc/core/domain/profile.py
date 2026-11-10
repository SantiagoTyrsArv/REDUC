"""Mobility profiles and their conservative accessibility limits."""

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal

Device = Literal["manual", "manual_assisted", "electric", "scooter"]
DEVICE_TYPES: tuple[Device, ...] = ("manual", "manual_assisted", "electric", "scooter")


@dataclass(frozen=True)
class Weights:
    """Soft-cost weights; each value is bounded to the documented 0..3 range."""

    slope: float = 1.0
    surface: float = 1.0
    uncertainty: float = 1.0

    def __post_init__(self) -> None:
        """Reject values that could disable or destabilize the cost function accidentally."""
        for name, value in (("slope", self.slope), ("surface", self.surface), ("uncertainty", self.uncertainty)):
            if not math.isfinite(value) or not 0.0 <= value <= 3.0:
                raise ValueError(f"{name} must be finite and between 0 and 3")


@dataclass(frozen=True)
class MobilityProfile:
    """Accessibility constraints and preferences for one mobility device."""

    device: Device
    max_uphill_pct: float
    max_downhill_pct: float
    max_cross_slope_pct: float
    max_step_cm: float
    min_width_m: float
    max_surface_class: int
    require_curb_ramps: bool
    avoid_unverified: bool
    speed_mps: float
    weights: Weights = field(default_factory=Weights)

    def __post_init__(self) -> None:
        """Validate all values before they reach either cost implementation."""
        if self.device not in DEVICE_TYPES:
            raise ValueError(f"Unsupported mobility device: {self.device}")
        for name, value in (
            ("max_uphill_pct", self.max_uphill_pct),
            ("max_downhill_pct", self.max_downhill_pct),
            ("max_cross_slope_pct", self.max_cross_slope_pct),
            ("speed_mps", self.speed_mps),
        ):
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be finite and greater than zero")
        for name, value in (("max_step_cm", self.max_step_cm), ("min_width_m", self.min_width_m)):
            if not math.isfinite(value) or value < 0.0:
                raise ValueError(f"{name} must be finite and non-negative")
        if not 0 <= self.max_surface_class <= 4:
            raise ValueError("max_surface_class must be between 0 and 4")


PROFILE_PRESETS: Mapping[Device, MobilityProfile] = MappingProxyType(
    {
        "manual": MobilityProfile(
            device="manual",
            max_uphill_pct=6.0,
            max_downhill_pct=8.0,
            max_cross_slope_pct=3.0,
            max_step_cm=2.0,
            min_width_m=0.9,
            max_surface_class=2,
            require_curb_ramps=True,
            avoid_unverified=False,
            speed_mps=0.9,
        ),
        "manual_assisted": MobilityProfile(
            device="manual_assisted",
            max_uphill_pct=10.0,
            max_downhill_pct=10.0,
            max_cross_slope_pct=4.0,
            max_step_cm=4.0,
            min_width_m=0.9,
            max_surface_class=3,
            require_curb_ramps=True,
            avoid_unverified=False,
            speed_mps=1.0,
        ),
        "electric": MobilityProfile(
            device="electric",
            max_uphill_pct=12.0,
            max_downhill_pct=10.0,
            max_cross_slope_pct=5.0,
            max_step_cm=5.0,
            min_width_m=1.0,
            max_surface_class=3,
            require_curb_ramps=True,
            avoid_unverified=False,
            speed_mps=1.3,
        ),
        "scooter": MobilityProfile(
            device="scooter",
            max_uphill_pct=10.0,
            max_downhill_pct=10.0,
            max_cross_slope_pct=5.0,
            max_step_cm=3.0,
            min_width_m=1.1,
            max_surface_class=2,
            require_curb_ramps=True,
            avoid_unverified=False,
            speed_mps=1.5,
        ),
    }
)
