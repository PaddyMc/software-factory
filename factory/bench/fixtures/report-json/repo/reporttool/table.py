"""Table formatting for reports."""


def format_table(title, rows):
    """Format a title and key-value rows as an aligned plain-text table."""
    width = max((len(key) for key, _ in rows), default=0)
    lines = [title, "-" * len(title)]
    lines.extend(key.ljust(width) + " " + value for key, value in rows)
    return "\n".join(lines)
