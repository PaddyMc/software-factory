"""Text normalization helpers."""

import re
import unicodedata


def normalize(text: str) -> str:
    """Collapse whitespace runs and trim surrounding whitespace."""
    return re.sub(r"\s+", " ", text).strip()


def slugify(title: str, max_length: int = 64) -> str:
    """Return an ASCII URL slug, cut at a word boundary when necessary."""
    folded = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", folded.lower()).strip("-")
    if max_length <= 0:
        return ""
    if len(slug) <= max_length:
        return slug
    cut = slug[:max_length]
    if not cut.endswith("-") and slug[max_length] != "-" and "-" in cut:
        cut = cut.rsplit("-", 1)[0]
    return cut.rstrip("-")
