"""Detection taxonomy shared by the detector, fusion and attribute rules (docs/05 §5)."""

from typing import Final

BARRIER_CLASSES: Final[tuple[str, ...]] = (
    "stairs",
    "single_step",
    "curb_no_ramp",
    "curb_ramp",
    "ramp",
    "obstacle",
    "surface_damage",
    "steep_slope_visual",
    "no_sidewalk",
    "narrow_sidewalk",
)

#: Positive findings: they are stored like barriers but never block or penalize an edge.
POSITIVE_CLASSES: Final[frozenset[str]] = frozenset({"curb_ramp", "ramp"})

#: Classes that describe a point of the network (a corner or crossing) rather than a stretch.
NODE_CLASSES: Final[frozenset[str]] = frozenset({"curb_no_ramp", "curb_ramp"})

DEFAULT_SEVERITY: Final[dict[str, str]] = {
    "stairs": "critical",
    "single_step": "critical",
    "curb_no_ramp": "critical",
    "curb_ramp": "minor",
    "ramp": "minor",
    "obstacle": "major",
    "surface_damage": "major",
    "steep_slope_visual": "minor",
    "no_sidewalk": "major",
    "narrow_sidewalk": "major",
}

#: A barrier below this confidence does not change edge attributes until a person confirms it.
MIN_EFFECTIVE_CONFIDENCE: Final[float] = 0.5

VERIFIED_STATUSES: Final[frozenset[str]] = frozenset({"confirmed", "rejected", "corrected"})


def severity_for(barrier_class: str, attributes: dict[str, object] | None = None) -> str:
    """Default severity; a single step known to be at most 2 cm high is only minor."""
    if barrier_class == "single_step" and attributes:
        height = attributes.get("step_height_cm")
        if isinstance(height, int | float) and height <= 2.0:
            return "minor"
    return DEFAULT_SEVERITY.get(barrier_class, "major")
