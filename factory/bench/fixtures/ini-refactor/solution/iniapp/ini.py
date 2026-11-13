"""Shared parsing for key = value settings."""


def parse_pairs(text):
    """Parse key = value lines into a dictionary of strings."""
    pairs = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"expected key = value, got {line!r}")
        key, value = line.split("=", 1)
        pairs[key.strip()] = value.strip()
    return pairs
