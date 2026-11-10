"""Infrastructure dependencies used by API endpoints."""

from functools import lru_cache

import psycopg

from reduc.core.storage import ObjectStorage, S3Storage
from reduc.settings import get_settings


def check_database(database_url: str) -> bool:
    """Check database availability without retaining server-side location data."""
    connection_url = database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    try:
        with psycopg.connect(connection_url, connect_timeout=2) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            return cursor.fetchone() == (1,)
    except psycopg.Error:
        return False


@lru_cache
def _storage() -> ObjectStorage | None:
    settings = get_settings()
    if not settings.s3_endpoint:
        return None
    return S3Storage(
        settings.s3_endpoint,
        settings.s3_public_endpoint,
        settings.s3_bucket,
        settings.s3_access_key,
        settings.s3_secret_key,
    )


def get_storage() -> ObjectStorage | None:
    """Object storage, or None when S3 is not configured (photos are then omitted)."""
    return _storage()
