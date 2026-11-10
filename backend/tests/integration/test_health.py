"""Tests for operational API behavior without external services."""

from fastapi.testclient import TestClient

from reduc.api.main import create_app
from reduc.settings import Settings


class FakeRateLimiter:
    """Deterministic in-memory rate limiter."""

    def __init__(self, limit: int = 60) -> None:
        self.limit = limit
        self.count = 0

    async def allows(self, _client_ip: str) -> bool:
        self.count += 1
        return self.count <= self.limit


def make_client(limiter: FakeRateLimiter | None = None) -> TestClient:
    """Create an API client with infrastructure replaced by test doubles."""
    app = create_app(
        Settings(cors_origins="http://localhost:5173"),
        limiter or FakeRateLimiter(),
    )
    return TestClient(app)


def test_health(monkeypatch) -> None:
    """Health reports a reachable database."""
    monkeypatch.setattr("reduc.api.main.check_database", lambda _url: True)
    response = make_client().get("/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "ok", "version": "0.1.0"}


def test_health_degraded(monkeypatch) -> None:
    """Health does not claim the database is available when it is not."""
    monkeypatch.setattr("reduc.api.main.check_database", lambda _url: False)
    response = make_client().get("/v1/health")

    assert response.json()["db"] == "unavailable"


def test_not_found_uses_error_contract() -> None:
    """Unknown resources use the common error schema."""
    response = make_client().get("/v1/missing")

    assert response.status_code == 404
    assert response.json() == {
        "type": "not_found",
        "title": "Recurso no encontrado",
        "detail": "Not Found",
        "status": 404,
    }


def test_metrics_and_cors() -> None:
    """Prometheus metrics and configured browser origins are enabled."""
    response = make_client().get("/metrics", headers={"Origin": "http://localhost:5173"})

    assert response.status_code == 200
    assert "reduc_http_requests_total" in response.text
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_route_rate_limit() -> None:
    """The sixty-first route request in the window is rejected."""
    client = make_client(FakeRateLimiter(limit=60))

    for _ in range(60):
        assert client.post("/v1/routes").status_code == 422
    response = client.post("/v1/routes")

    assert response.status_code == 429
    assert response.json()["type"] == "rate_limited"
    assert response.headers["retry-after"] == "60"
