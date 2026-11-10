"""SQLAlchemy models for the versioned accessibility map."""

import uuid
from datetime import datetime
from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, CITEXT, JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from reduc.core.db.session import Base


class TimestampMixin:
    """Common creation and update timestamps."""

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Region(Base, TimestampMixin):
    __tablename__ = "region"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    boundary: Mapped[Any] = mapped_column(Geometry("MULTIPOLYGON", srid=4326))
    utm_srid: Mapped[int]
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    published_version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("map_version.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class MapVersion(Base, TimestampMixin):
    __tablename__ = "map_version"
    __table_args__ = (CheckConstraint("status IN ('draft','published','archived')"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    region_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("region.id"))
    number: Mapped[int]
    status: Mapped[str] = mapped_column(Text, default="draft")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)


class Node(Base, TimestampMixin):
    __tablename__ = "node"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    map_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("map_version.id"))
    osm_id: Mapped[int | None] = mapped_column(BigInteger)
    geom: Mapped[Any] = mapped_column(Geometry("POINT", srid=4326))
    elevation_m: Mapped[float | None]
    kind: Mapped[str] = mapped_column(Text)
    tags: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class Edge(Base, TimestampMixin):
    __tablename__ = "edge"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    map_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("map_version.id"))
    source: Mapped[int] = mapped_column(BigInteger, ForeignKey("node.id"))
    target: Mapped[int] = mapped_column(BigInteger, ForeignKey("node.id"))
    osm_way_id: Mapped[int | None] = mapped_column(BigInteger)
    geom: Mapped[Any] = mapped_column(Geometry("LINESTRING", srid=4326))
    length_m: Mapped[float]
    kind: Mapped[str] = mapped_column(Text)
    tags: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    #: Written by the elevation stage; signed in the source→target direction.
    slope_pct: Mapped[float | None]
    max_slope_pct: Mapped[float | None]
    slope_source: Mapped[str | None] = mapped_column(Text)
    #: Attributes measured in the field; they win over everything the pipeline computes.
    overrides: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")


class EdgeAccessibility(Base, TimestampMixin):
    __tablename__ = "edge_accessibility"

    edge_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("edge.id"), primary_key=True)
    slope_pct: Mapped[float]
    max_slope_pct: Mapped[float]
    cross_slope_pct: Mapped[float | None]
    width_m: Mapped[float | None]
    surface_class: Mapped[int] = mapped_column(SmallInteger)
    has_steps: Mapped[bool]
    max_step_height_cm: Mapped[float | None]
    curb_ramp_start: Mapped[str] = mapped_column(Text)
    curb_ramp_end: Mapped[str] = mapped_column(Text)
    obstacle_level: Mapped[int] = mapped_column(SmallInteger)
    sidewalk_missing: Mapped[bool]
    data_confidence: Mapped[float]
    verified: Mapped[bool]
    coverage: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Image(Base, TimestampMixin):
    __tablename__ = "image"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    region_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("region.id"))
    provider: Mapped[str] = mapped_column(Text)
    external_id: Mapped[str | None] = mapped_column(Text)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    geom: Mapped[Any] = mapped_column(Geometry("POINT", srid=4326))
    heading_deg: Mapped[float | None]
    pitch_deg: Mapped[float | None]
    fov_deg: Mapped[float | None]
    is_panorama: Mapped[bool]
    camera_height_m: Mapped[float] = mapped_column(default=2.0)
    storage_key: Mapped[str | None] = mapped_column(Text)
    width_px: Mapped[int]
    height_px: Mapped[int]
    license: Mapped[str] = mapped_column(Text)
    attribution: Mapped[str | None] = mapped_column(Text)
    privacy_blurred: Mapped[bool]
    status: Mapped[str] = mapped_column(Text)


class Detection(Base, TimestampMixin):
    __tablename__ = "detection"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    image_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("image.id"))
    model_version: Mapped[str] = mapped_column(Text)
    detection_class: Mapped[str] = mapped_column("class", Text)
    score: Mapped[float]
    bbox: Mapped[list[int]] = mapped_column(ARRAY(Integer))
    mask_key: Mapped[str | None] = mapped_column(Text)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    geom: Mapped[Any | None] = mapped_column(Geometry("POINT", srid=4326))
    geo_error_m: Mapped[float | None]
    barrier_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("barrier.id"))
    crop_key: Mapped[str | None] = mapped_column(Text)


class Barrier(Base, TimestampMixin):
    __tablename__ = "barrier"
    __table_args__ = (
        CheckConstraint("severity IN ('critical','major','minor')"),
        CheckConstraint("verification_status IN ('unverified','confirmed','rejected','corrected')"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    map_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("map_version.id"))
    barrier_class: Mapped[str] = mapped_column("class", Text)
    severity: Mapped[str] = mapped_column(Text)
    geom: Mapped[Any] = mapped_column(Geometry("POINT", srid=4326))
    edge_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("edge.id"))
    node_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("node.id"))
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    confidence: Mapped[float]
    n_observations: Mapped[int]
    source: Mapped[str] = mapped_column(Text)
    verification_status: Mapped[str] = mapped_column(Text)
    representative_detection_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("detection.id"))


class AppUser(Base, TimestampMixin):
    __tablename__ = "app_user"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(CITEXT, unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    #: Embedded in every token; bumping it revokes all sessions of the user.
    token_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class Verification(Base):
    __tablename__ = "verification"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    barrier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("barrier.id"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id"))
    action: Mapped[str] = mapped_column(Text)
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Poi(Base, TimestampMixin):
    __tablename__ = "poi"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    region_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("region.id"))
    name: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(Text)
    geom: Mapped[Any] = mapped_column(Geometry("POINT", srid=4326))
    accessible_entrance: Mapped[bool]
    tags: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    search_vector: Mapped[Any] = mapped_column(TSVECTOR, Computed("to_tsvector('spanish', name)"))


class PipelineRun(Base, TimestampMixin):
    __tablename__ = "pipeline_run"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    region_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("region.id"))
    map_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("map_version.id"))
    requested_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id"))
    status: Mapped[str] = mapped_column(Text)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PipelineStageRun(Base, TimestampMixin):
    __tablename__ = "pipeline_stage_run"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    pipeline_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pipeline_run.id"))
    stage: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    progress: Mapped[float] = mapped_column(default=0)
    stats: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
