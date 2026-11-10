"""Consistent HTTP error responses for the public and admin APIs."""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class ApiError(Exception):
    """Domain error that can be returned using the public error contract."""

    def __init__(
        self,
        error_type: str,
        title: str,
        detail: str,
        status: int,
        extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(detail)
        self.error_type = error_type
        self.title = title
        self.detail = detail
        self.status = status
        self.extra = extra


def error_body(
    error_type: str,
    title: str,
    detail: str,
    status: int,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the RFC 9457-inspired response body used by the specification."""
    body: dict[str, Any] = {"type": error_type, "title": title, "detail": detail, "status": status}
    if extra is not None:
        body["extra"] = extra
    return body


def register_error_handlers(app: FastAPI) -> None:
    """Register exception handlers without exposing internal error details."""

    @app.exception_handler(ApiError)
    async def handle_api_error(_request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status,
            content=error_body(exc.error_type, exc.title, exc.detail, exc.status, exc.extra),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=error_body("validation_error", "Solicitud inválida", str(exc.errors()), 422),
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        titles = {401: "No autorizado", 403: "Acceso prohibido", 404: "Recurso no encontrado", 429: "Límite excedido"}
        error_types = {401: "unauthorized", 403: "forbidden", 404: "not_found", 429: "rate_limited"}
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(
                error_types.get(exc.status_code, "http_error"),
                titles.get(exc.status_code, "Error HTTP"),
                str(exc.detail),
                exc.status_code,
            ),
            headers=exc.headers,
        )
