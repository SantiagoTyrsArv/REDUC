"""Create or update a panel user.

    uv run python scripts/create_admin.py --email ana@example.org --role admin

The password is read from `REDUC_ADMIN_PASSWORD` or asked for interactively; it is never
accepted as a command-line argument so it does not end up in the shell history.
"""

import argparse
import getpass
import os
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session
from structlog import get_logger

from reduc.core.db.models import AppUser
from reduc.core.db.session import SessionLocal
from reduc.core.security import ROLES, hash_password


def upsert_user(session: Session, email: str, password: str, role: str = "admin") -> tuple[AppUser, bool]:
    """Create the user or reset its password and role. Returns the user and whether it is new."""
    if role not in ROLES:
        raise ValueError(f"Rol no válido: {role}")
    normalized = email.strip().lower()
    if "@" not in normalized:
        raise ValueError("Correo no válido")
    password_hash = hash_password(password)
    user = session.scalar(select(AppUser).where(AppUser.email == normalized))
    created = user is None
    if user is None:
        user = AppUser(email=normalized, password_hash=password_hash, role=role, is_active=True)
        session.add(user)
    else:
        user.password_hash = password_hash
        user.role = role
        user.is_active = True
    session.flush()
    return user, created


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Crea o actualiza un usuario del panel.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--role", choices=ROLES, default="admin")
    args = parser.parse_args(argv)
    password = os.environ.get("REDUC_ADMIN_PASSWORD") or getpass.getpass("Contraseña: ")
    try:
        with SessionLocal() as session:
            user, created = upsert_user(session, args.email, password, args.role)
            session.commit()
    except ValueError as error:
        sys.stderr.write(f"{error}\n")
        return 2
    get_logger("reduc.scripts").info("user_saved", user_id=str(user.id), role=user.role, created=created)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
