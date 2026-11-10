"""Authentication dependencies of the admin API: bearer JWT and role checks."""

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from reduc.api.errors import ApiError
from reduc.core.db.models import AppUser
from reduc.core.db.session import get_session
from reduc.core.security import AuthNotConfiguredError, InvalidTokenError, decode_token
from reduc.settings import Settings

_bearer = HTTPBearer(auto_error=False, description="Token de acceso obtenido en /v1/admin/auth/login")

SessionDep = Annotated[Session, Depends(get_session)]
CredentialsDep = Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]


def unauthorized(detail: str = "Credenciales inválidas o sesión caducada") -> ApiError:
    return ApiError("unauthorized", "No autorizado", detail, 401)


def not_configured() -> ApiError:
    return ApiError("auth_unavailable", "Autenticación no disponible", "El servidor no tiene configurado JWT", 503)


def app_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


SettingsDep = Annotated[Settings, Depends(app_settings)]


def current_user(credentials: CredentialsDep, session: SessionDep, settings: SettingsDep) -> AppUser:
    """The active user behind a valid access token. The role is read from the database, not the token."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise unauthorized("Falta el token de acceso")
    try:
        claims = decode_token(settings.jwt_secret, credentials.credentials, "access")
    except AuthNotConfiguredError as error:
        raise not_configured() from error
    except InvalidTokenError as error:
        raise unauthorized() from error
    user = session.get(AppUser, claims.user_id)
    if user is None or not user.is_active:
        raise unauthorized()
    return user


CurrentUser = Annotated[AppUser, Depends(current_user)]


def require_role(role: str) -> Callable[[AppUser], AppUser]:
    """Dependency factory. `admin` can do everything a `verifier` can."""

    def dependency(user: CurrentUser) -> AppUser:
        if user.role != "admin" and user.role != role:
            raise ApiError("forbidden", "Acceso prohibido", "Tu rol no permite esta operación", 403)
        return user

    return dependency


AdminUser = Annotated[AppUser, Depends(require_role("admin"))]
VerifierUser = Annotated[AppUser, Depends(require_role("verifier"))]
