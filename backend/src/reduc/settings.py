"""Environment-based application settings."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration shared by the API and worker."""

    model_config = SettingsConfigDict(env_prefix="REDUC_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://reduc:reduc@localhost:5432/reduc"
    redis_url: str = "redis://localhost:6379/0"
    cors_origins: str = "http://localhost:5173,http://localhost:8081"
    rate_limit_routes_per_minute: int = 60
    s3_endpoint: str = ""
    s3_public_endpoint: str = ""
    s3_bucket: str = "reduc"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    jwt_secret: str = ""
    jwt_access_minutes: int = 15
    jwt_refresh_days: int = 7
    login_attempts_per_minute: int = 10
    mapillary_token: str = ""
    streetview_api_key: str = ""
    model_detector_version: str = "det-v0.1.0"
    model_surface_version: str = "surf-v0.1.0"
    detector_backend: str = "fake"

    @property
    def cors_origin_list(self) -> list[str]:
        """Return configured CORS origins without empty entries."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Load settings once per process."""
    return Settings()
