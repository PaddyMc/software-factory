"""Application settings."""


def load_settings(text):
    """Load application settings from key = value lines."""
    settings = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"expected key = value, got {line!r}")
        key, value = line.split("=", 1)
        settings[key.strip()] = value.strip()
    return settings
