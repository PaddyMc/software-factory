"""Application settings."""

from .ini import parse_pairs


def load_settings(text):
    """Load application settings from key = value lines."""
    return parse_pairs(text)
