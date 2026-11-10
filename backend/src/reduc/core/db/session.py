"""Database base metadata and session factory."""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from reduc.settings import get_settings


class Base(DeclarativeBase):
    """Base class for all ORM models."""


engine = create_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_session() -> Generator[Session]:
    """Provide a scoped request session."""
    with SessionLocal() as session:
        yield session
