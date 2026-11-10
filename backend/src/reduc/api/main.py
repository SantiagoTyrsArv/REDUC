"""FastAPI application factory and operational endpoints."""

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from reduc import __version__
from reduc.api.deps import check_database
from reduc.api.errors import register_error_handlers
from reduc.api.logging import configure_logging
from reduc.api.middleware import limit_route_requests, observe_request
from reduc.api.rate_limit import RateLimiter, RedisRateLimiter
from reduc.api.routers import admin_auth, admin_pipeline, admin_versions, public
from reduc.api.schemas.public import HealthOut
from reduc.settings import Settings, get_settings


def create_app(
    settings: Settings | None = None,
    rate_limiter: RateLimiter | None = None,
    login_limiter: RateLimiter | None = None,
) -> FastAPI:
    """Build the API with replaceable infrastructure for offline tests."""
    config = settings or get_settings()
    configure_logging()
    app = FastAPI(title="APP-REDUC", version=__version__)
    app.state.settings = config
    app.state.rate_limiter = rate_limiter or RedisRateLimiter(config.redis_url, config.rate_limit_routes_per_minute)
    # Tests that replace the route limiter get the same double for logins, so they never need Redis.
    app.state.login_limiter = (
        login_limiter
        or rate_limiter
        or RedisRateLimiter(config.redis_url, config.login_attempts_per_minute, scope="login")
    )

    app.middleware("http")(observe_request)
    app.middleware("http")(limit_route_requests)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )
    register_error_handlers(app)

    app.include_router(public.router)
    app.include_router(admin_auth.router)
    app.include_router(admin_pipeline.router)
    app.include_router(admin_versions.router)

    @app.get("/v1/health", response_model=HealthOut, tags=["public"])
    def health() -> dict[str, str]:
        """Return API and database health for orchestration checks."""
        database_ok = check_database(config.database_url)
        return {
            "status": "ok" if database_ok else "degraded",
            "db": "ok" if database_ok else "unavailable",
            "version": __version__,
        }

    @app.get("/metrics", include_in_schema=False)
    def metrics() -> Response:
        """Expose Prometheus process and HTTP metrics."""
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app


app = create_app()
