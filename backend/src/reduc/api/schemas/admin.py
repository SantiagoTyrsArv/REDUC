"""Request and response contracts of the admin API (docs/04-api.md §3)."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=1024)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=4096)


class TokenPairOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    #: Seconds until the access token expires.
    expires_in: int


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    role: Literal["admin", "verifier"]


class PipelineRunRequest(BaseModel):
    #: `["all"]` or any subset of the stage names; they always run in pipeline order.
    stages: list[str] = Field(default_factory=lambda: ["all"], max_length=16)
    #: `"new"` creates the next draft; an id re-runs stages on an existing draft.
    map_version: str = Field("new", max_length=64)


class StageRunOut(BaseModel):
    stage: str
    status: str
    progress: float
    stats: dict[str, Any]
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None


class PipelineRunOut(BaseModel):
    id: uuid.UUID
    region_id: uuid.UUID
    map_version_id: uuid.UUID
    map_version_number: int
    status: str
    stages: list[StageRunOut]
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
