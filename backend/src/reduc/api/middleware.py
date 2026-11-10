"""HTTP middleware for metrics, request logs and route rate limits."""

import time
from collections.abc import Awaitable, Callable

import structlog
from fastapi import Request
from fastapi.responses import JSONResponse
from prometheus_client import Counter, Histogram
from starlette.responses import Response

from reduc.api.errors import error_body

REQUEST_COUNT = Counter("reduc_http_requests_total", "HTTP requests", ["method", "path", "status"])
REQUEST_DURATION = Histogram("reduc_http_request_duration_seconds", "HTTP request duration", ["method", "path"])


async def observe_request(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    """Record request metrics and logs without exact coordinates or request bodies."""
    started = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - started
    path = request.url.path
    REQUEST_COUNT.labels(request.method, path, str(response.status_code)).inc()
    REQUEST_DURATION.labels(request.method, path).observe(duration)
    structlog.get_logger("reduc.http").info(
        "request_completed",
        method=request.method,
        path=path,
        status_code=response.status_code,
        duration_ms=round(duration * 1000, 2),
    )
    return response


async def limit_route_requests(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    """Apply the route-specific IP limit before route computation."""
    if request.method == "POST" and request.url.path == "/v1/routes":
        client_ip = request.client.host if request.client else "unknown"
        if not await request.app.state.rate_limiter.allows(client_ip):
            return JSONResponse(
                status_code=429,
                content=error_body(
                    "rate_limited",
                    "Límite de solicitudes excedido",
                    "Se permiten 60 cálculos de ruta por minuto",
                    429,
                ),
                headers={"Retry-After": "60"},
            )
    return await call_next(request)
