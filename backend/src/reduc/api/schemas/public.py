"""Request and response contracts of the public API (docs/04-api.md §2)."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from reduc.core.domain.profile import MobilityProfile, Weights

LonLat = tuple[float, float]
DeviceName = Literal["manual", "manual_assisted", "electric", "scooter"]


class ErrorOut(BaseModel):
    """Uniform error body."""

    type: str
    title: str
    detail: str
    status: int
    extra: dict[str, Any] | None = None


class HealthOut(BaseModel):
    status: str
    db: str
    version: str


class WeightsModel(BaseModel):
    slope: float = Field(1.0, ge=0.0, le=3.0)
    surface: float = Field(1.0, ge=0.0, le=3.0)
    uncertainty: float = Field(1.0, ge=0.0, le=3.0)


class ProfileModel(BaseModel):
    """Mobility profile; it travels in each request and is never stored."""

    device: DeviceName
    max_uphill_pct: float = Field(gt=0.0, le=30.0)
    max_downhill_pct: float = Field(gt=0.0, le=30.0)
    max_cross_slope_pct: float = Field(gt=0.0, le=20.0)
    max_step_cm: float = Field(ge=0.0, le=30.0)
    min_width_m: float = Field(ge=0.0, le=3.0)
    max_surface_class: int = Field(ge=0, le=4)
    require_curb_ramps: bool
    avoid_unverified: bool
    speed_mps: float = Field(gt=0.0, le=5.0)
    weights: WeightsModel = Field(default_factory=lambda: WeightsModel())

    def to_domain(self) -> MobilityProfile:
        return MobilityProfile(
            device=self.device,
            max_uphill_pct=self.max_uphill_pct,
            max_downhill_pct=self.max_downhill_pct,
            max_cross_slope_pct=self.max_cross_slope_pct,
            max_step_cm=self.max_step_cm,
            min_width_m=self.min_width_m,
            max_surface_class=self.max_surface_class,
            require_curb_ramps=self.require_curb_ramps,
            avoid_unverified=self.avoid_unverified,
            speed_mps=self.speed_mps,
            weights=Weights(self.weights.slope, self.weights.surface, self.weights.uncertainty),
        )

    @classmethod
    def from_domain(cls, profile: MobilityProfile) -> "ProfileModel":
        return cls(
            device=profile.device,
            max_uphill_pct=profile.max_uphill_pct,
            max_downhill_pct=profile.max_downhill_pct,
            max_cross_slope_pct=profile.max_cross_slope_pct,
            max_step_cm=profile.max_step_cm,
            min_width_m=profile.min_width_m,
            max_surface_class=profile.max_surface_class,
            require_curb_ramps=profile.require_curb_ramps,
            avoid_unverified=profile.avoid_unverified,
            speed_mps=profile.speed_mps,
            weights=WeightsModel(
                slope=profile.weights.slope, surface=profile.weights.surface, uncertainty=profile.weights.uncertainty
            ),
        )


class PresetOut(BaseModel):
    id: DeviceName
    profile: ProfileModel


class RouteRequest(BaseModel):
    origin: LonLat
    destination: LonLat
    profile: ProfileModel
    alternatives: int = Field(2, ge=0, le=2)
    include_shortest: bool = True
    locale: str = "es"


class LineStringOut(BaseModel):
    type: Literal["LineString"] = "LineString"
    coordinates: list[LonLat]


class WarningOut(BaseModel):
    code: str
    severity: Literal["minor", "major"]
    message: str


class SegmentOut(BaseModel):
    edge_ids: list[int]
    geometry: LineStringOut
    distance_m: float
    status: Literal["accessible", "caution", "inaccessible"]
    slope_pct: float
    surface_class: int
    warnings: list[WarningOut]


class InstructionOut(BaseModel):
    distance_m: float
    text: str
    maneuver: Literal["depart", "left", "right", "u_turn", "arrive"]
    location: LonLat


class RouteOut(BaseModel):
    id: str
    geometry: LineStringOut
    distance_m: float
    duration_s: int
    accessibility_score: int
    verified_pct: float
    max_slope_pct: float
    caution_segments: int
    segments: list[SegmentOut]
    instructions: list[InstructionOut]


class BlockingBarrierOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: uuid.UUID
    barrier_class: str = Field(alias="class")
    location: LonLat
    message: str


class ShortestOut(BaseModel):
    distance_m: float
    blocking_barriers: list[BlockingBarrierOut]


class RoutesResponse(BaseModel):
    region: str
    map_version: int
    routes: list[RouteOut]
    shortest: ShortestOut | None = None


class NoAccessibleRouteExtra(BaseModel):
    """Shape of `extra` in a `no_accessible_route` error."""

    region: str
    map_version: int
    fallback_route: RouteOut | None
    violated_constraints: list[str]
    shortest: ShortestOut | None = None


class NoAccessibleRouteError(BaseModel):
    """Error body returned when no route satisfies the hard constraints."""

    type: Literal["no_accessible_route"]
    title: str
    detail: str
    status: int
    extra: NoAccessibleRouteExtra


class MapVersionOut(BaseModel):
    id: uuid.UUID
    number: int
    published_at: datetime | None


class RegionStatsOut(BaseModel):
    edges: int
    coverage_pct: float
    verified_pct: float


class RegionOut(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    bbox: tuple[float, float, float, float]
    boundary: dict[str, Any]
    map_version: MapVersionOut
    stats: RegionStatsOut


class PoiOut(BaseModel):
    id: uuid.UUID
    name: str
    category: str
    location: LonLat
    accessible_entrance: bool


class BarrierOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: uuid.UUID
    barrier_class: str = Field(alias="class")
    severity: Literal["critical", "major", "minor"]
    location: LonLat
    attributes: dict[str, Any]
    confidence: float
    n_observations: int
    source: str
    verification_status: str
    description: str
    photo_url: str | None = None
    attribution: str | None = None
