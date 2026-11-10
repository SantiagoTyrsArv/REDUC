"""Unit tests for the initial backend package."""

from reduc import __version__


def test_version_is_defined() -> None:
    """The package exposes its initial semantic version."""
    assert __version__ == "0.1.0"
