"""Database settings."""


def load_db_config(text):
    """Load database settings from key = value lines."""
    config = {}
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            raise ValueError(f"expected key = value, got {stripped!r}")
        name, setting = stripped.split("=", 1)
        config[name.strip()] = setting.strip()
    return config
