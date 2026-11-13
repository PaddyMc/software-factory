"""Text normalization helpers."""

import re


def normalize(text: str) -> str:
    """Collapse whitespace runs and trim surrounding whitespace."""
    return re.sub(r"\s+", " ", text).strip()
