"""Admin authentication: login, token refresh and the current user."""

from datetime import timedelta

from fastapi import APIRouter, Request
from sqlalchemy import select

from reduc.api.auth import CurrentUser, SessionDep, SettingsDep, not_configured, unauthorized
from reduc.api.errors import ApiError
from reduc.api.schemas.admin import LoginRequest, RefreshRequest, TokenPairOut, UserOut
from reduc.api.schemas.public import ErrorOut
from reduc.core.db.models import AppUser
from reduc.core.security import (
    AuthNotConfiguredError,
    InvalidTokenError,
    create_token,
    decode_token,
    hash_password,
    needs_rehash,
    verify_password,
)
from reduc.settings import Settings

router = APIRouter(prefix="/v1/admin/auth", tags=["admin"])

ERRORS: dict[int | str, dict[str, type[ErrorOut]]] = {401: {"model": ErrorOut}, 429: {"model": ErrorOut}}


def _token_pair(settings: Settings, user: AppUser) -> TokenPairOut:
    access = timedelta(minutes=settings.jwt_access_minutes)
    try:
        return TokenPairOut(
            access_token=create_token(settings.jwt_secret, user.id, user.role, "access", access),
            refresh_token=create_token(
                settings.jwt_secret, user.id, user.role, "refresh", timedelta(days=settings.jwt_refresh_days)
            ),
            expires_in=int(access.total_seconds()),
        )
    except AuthNotConfiguredError as error:
        raise not_configured() from error


async def _limit_attempts(request: Request) -> None:
    client_ip = request.client.host if request.client else "unknown"
    if not await request.app.state.login_limiter.allows(client_ip):
        raise ApiError("rate_limited", "Límite de solicitudes excedido", "Demasiados intentos; espera un minuto", 429)


@router.post("/login", response_model=TokenPairOut, responses=ERRORS)
async def login(body: LoginRequest, request: Request, session: SessionDep, settings: SettingsDep) -> TokenPairOut:
    """Exchange email and password for an access token (15 min) and a refresh token (7 days)."""
    await _limit_attempts(request)
    user = session.scalar(select(AppUser).where(AppUser.email == body.email.strip()))
    # Unknown, inactive and wrong-password cases are indistinguishable for the caller.
    valid = verify_password(body.password, user.password_hash if user is not None else None)
    if user is None or not valid or not user.is_active:
        raise unauthorized("Correo o contraseña incorrectos")
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)
        session.commit()
    return _token_pair(settings, user)


@router.post("/refresh", response_model=TokenPairOut, responses=ERRORS)
async def refresh(body: RefreshRequest, request: Request, session: SessionDep, settings: SettingsDep) -> TokenPairOut:
    """Issue a new token pair. The user must still exist and be active."""
    await _limit_attempts(request)
    try:
        claims = decode_token(settings.jwt_secret, body.refresh_token, "refresh")
    except AuthNotConfiguredError as error:
        raise not_configured() from error
    except InvalidTokenError as error:
        raise unauthorized() from error
    user = session.get(AppUser, claims.user_id)
    if user is None or not user.is_active:
        raise unauthorized()
    return _token_pair(settings, user)


@router.get("/me", response_model=UserOut, responses={401: {"model": ErrorOut}})
def me(user: CurrentUser) -> UserOut:
    """The authenticated user, so the panel knows which sections to show."""
    return UserOut(id=user.id, email=user.email, role=user.role)  # type: ignore[arg-type]
