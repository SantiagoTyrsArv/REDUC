"""Tests for configuration parsing."""

from reduc.settings import Settings


def test_cors_origins_are_trimmed() -> None:
    """Comma-separated environment configuration becomes an origin list."""
    settings = Settings(cors_origins="http://localhost:5173, https://admin.example.com,")

    assert settings.cors_origin_list == ["http://localhost:5173", "https://admin.example.com"]
