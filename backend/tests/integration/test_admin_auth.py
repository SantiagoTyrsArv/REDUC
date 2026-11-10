"""Admin authentication over the real database (T-23)."""

from fastapi import FastAPI
from scripts.create_admin import upsert_user
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from tests.integration.admin_helpers import (
    JWT_SECRET,
    PASSWORD,
    CountingLimiter,
    admin_client,
    bearer,
    login,
    temporary_user,
)

from reduc.api.auth import AdminUser, VerifierUser
from reduc.settings import Settings


def add_role_probes(app: FastAPI) -> None:
    @app.get("/v1/admin/_probe/admin")
    def admin_only(user: AdminUser) -> dict[str, str]:
        return {"role": user.role}

    @app.get("/v1/admin/_probe/verifier")
    def verifier_only(user: VerifierUser) -> dict[str, str]:
        return {"role": user.role}


def test_login_returns_tokens_and_me_reads_the_user(shared_engine: Engine) -> None:
    with temporary_user(shared_engine, "verifier") as (email, user_id), admin_client(shared_engine) as client:
        tokens = login(client, email.upper())

        me = client.get("/v1/admin/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})

        assert tokens["token_type"] == "bearer"
        assert tokens["expires_in"] == 15 * 60
        assert me.status_code == 200
        assert me.json() == {"id": str(user_id), "email": email, "role": "verifier"}


def test_wrong_password_unknown_and_inactive_users_look_the_same(shared_engine: Engine) -> None:
    with (
        temporary_user(shared_engine) as (email, _),
        temporary_user(shared_engine, active=False) as (inactive, _),
        admin_client(shared_engine) as client,
    ):
        responses = [
            client.post("/v1/admin/auth/login", json={"email": email, "password": "equivocada"}),
            client.post("/v1/admin/auth/login", json={"email": "nadie@example.org", "password": PASSWORD}),
            client.post("/v1/admin/auth/login", json={"email": inactive, "password": PASSWORD}),
        ]

    assert [response.status_code for response in responses] == [401, 401, 401]
    assert len({response.text for response in responses}) == 1
    assert responses[0].json()["type"] == "unauthorized"


def test_refresh_rotates_tokens_and_rejects_access_tokens(shared_engine: Engine) -> None:
    with temporary_user(shared_engine) as (email, user_id), admin_client(shared_engine) as client:
        tokens = login(client, email)

        refreshed = client.post("/v1/admin/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
        misuse = client.post("/v1/admin/auth/refresh", json={"refresh_token": tokens["access_token"]})
        as_access = client.get("/v1/admin/auth/me", headers={"Authorization": f"Bearer {tokens['refresh_token']}"})
        # A deactivated user can neither refresh nor keep using a token issued earlier.
        with Session(shared_engine) as session:
            session.execute(text("UPDATE app_user SET is_active = false WHERE id = :id"), {"id": user_id})
            session.commit()
        after_deactivation = client.post("/v1/admin/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
        stale = client.get("/v1/admin/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})

    assert refreshed.status_code == 200
    assert refreshed.json()["access_token"] != tokens["access_token"]
    assert (misuse.status_code, as_access.status_code) == (401, 401)
    assert (after_deactivation.status_code, stale.status_code) == (401, 401)


def test_roles_admin_includes_verifier_but_not_the_reverse(shared_engine: Engine) -> None:
    with (
        temporary_user(shared_engine, "admin") as (admin, _),
        temporary_user(shared_engine, "verifier") as (verifier, _),
        admin_client(shared_engine, configure=add_role_probes) as client,
    ):
        admin_headers, verifier_headers = bearer(client, admin), bearer(client, verifier)

        assert client.get("/v1/admin/_probe/admin", headers=admin_headers).status_code == 200
        assert client.get("/v1/admin/_probe/verifier", headers=admin_headers).status_code == 200
        assert client.get("/v1/admin/_probe/verifier", headers=verifier_headers).status_code == 200
        forbidden = client.get("/v1/admin/_probe/admin", headers=verifier_headers)
        anonymous = client.get("/v1/admin/_probe/admin")
        garbage = client.get("/v1/admin/_probe/admin", headers={"Authorization": "Bearer nope"})

    assert (forbidden.status_code, forbidden.json()["type"]) == (403, "forbidden")
    assert (anonymous.status_code, anonymous.json()["type"]) == (401, "unauthorized")
    assert garbage.status_code == 401


def test_login_attempts_are_rate_limited(shared_engine: Engine) -> None:
    with admin_client(shared_engine, login_limiter=CountingLimiter(limit=3)) as client:
        codes = [
            client.post("/v1/admin/auth/login", json={"email": "nadie@example.org", "password": "x"}).status_code
            for _ in range(4)
        ]

    assert codes == [401, 401, 401, 429]


def test_without_a_strong_secret_no_token_is_issued_or_accepted(shared_engine: Engine) -> None:
    weak = Settings(cors_origins="http://localhost:5173", jwt_secret="")
    with temporary_user(shared_engine) as (email, _), admin_client(shared_engine, settings=weak) as client:
        response = client.post("/v1/admin/auth/login", json={"email": email, "password": PASSWORD})
        me = client.get("/v1/admin/auth/me", headers={"Authorization": "Bearer anything"})

    assert (response.status_code, me.status_code) == (503, 503)
    assert JWT_SECRET not in response.text


def test_changing_the_password_revokes_existing_sessions(shared_engine: Engine) -> None:
    with temporary_user(shared_engine) as (email, _), admin_client(shared_engine) as client:
        old = login(client, email)
        with Session(shared_engine) as session:
            upsert_user(session, email, "otra-clave-larga-distinta", "admin")
            session.commit()

        stale_access = client.get("/v1/admin/auth/me", headers={"Authorization": f"Bearer {old['access_token']}"})
        stale_refresh = client.post("/v1/admin/auth/refresh", json={"refresh_token": old["refresh_token"]})
        fresh = login(client, email, "otra-clave-larga-distinta")
        current = client.get("/v1/admin/auth/me", headers={"Authorization": f"Bearer {fresh['access_token']}"})

    assert (stale_access.status_code, stale_refresh.status_code) == (401, 401)
    assert current.status_code == 200
