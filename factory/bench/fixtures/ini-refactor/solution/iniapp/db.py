"""Database settings."""

from .ini import parse_pairs


def load_db_config(text):
    """Load database settings from key = value lines."""
    return parse_pairs(text)
