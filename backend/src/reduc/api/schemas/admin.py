"""Request and response contracts of the admin API (docs/04-api.md §3)."""

import uuid
from typing import Literal

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
