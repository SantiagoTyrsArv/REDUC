"""Shared helpers for admin API tests: an app wired to the test database and throwaway users."""

import uuid
from collections.abc import Callable, Generator
from contextlib import contextmanager
from typing import Any

from fastapi.testclient import TestClient
from scripts.create_admin import upsert_user
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from reduc.api.deps import get_storage
from reduc.api.main import create_app
from reduc.core.db.session import get_session
from reduc.core.storage import InMemoryStorage
from reduc.settings import Settings

JWT_SECRET = "test-secret-that-is-long-enough-0123456789"
PASSWORD = "una-clave-larga-de-prueba"


class CountingLimiter:
    def __init__(self, limit: int = 10_000) -> None:
        self.limit = limit
        self.count = 0

    async def allows(self, _client_ip: str) -> bool:
        self.count += 1
        return self.count <= self.limit


@contextmanager
def admin_client(
    engine: Engine,
    settings: Settings | None = None,
    login_limiter: CountingLimiter | None = None,
    configure: Callable[[Any], None] | None = None,
) -> Generator[TestClient]:
    app = create_app(
        settings or Settings(cors_origins="http://localhost:5173", jwt_secret=JWT_SECRET),
        CountingLimiter(),
        login_limiter,
    )
    storage = InMemoryStorage()

    def session_override() -> Generator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_storage] = lambda: storage
    app.state.test_storage = storage
    if configure is not None:
        configure(app)
    with TestClient(app) as client:
        yield client


@contextmanager
def temporary_user(engine: Engine, role: str = "admin", active: bool = True) -> Generator[tuple[str, uuid.UUID]]:
    """A committed user with a unique email, removed afterwards with everything it authored."""
    email = f"{role}-{uuid.uuid4().hex[:10]}@example.org"
    with Session(engine) as session:
        user, _ = upsert_user(session, email, PASSWORD, role)
        user.is_active = active
        session.commit()
        user_id = user.id
    try:
        yield email, user_id
    finally:
        with Session(engine) as session:
            session.execute(text("DELETE FROM verification WHERE user_id = :id"), {"id": user_id})
            session.execute(
                text("UPDATE pipeline_run SET requested_by = NULL WHERE requested_by = :id"), {"id": user_id}
            )
            session.execute(text("DELETE FROM app_user WHERE id = :id"), {"id": user_id})
            session.commit()


def login(client: TestClient, email: str, password: str = PASSWORD) -> dict[str, Any]:
    response = client.post("/v1/admin/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def bearer(client: TestClient, email: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {login(client, email)['access_token']}"}
