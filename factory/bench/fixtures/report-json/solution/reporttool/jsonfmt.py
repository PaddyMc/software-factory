"""JSON formatting for reports."""

import json


def format_json(title, rows):
    """Format a title and key-value rows as a JSON object."""
    return json.dumps({"title": title, "rows": [list(row) for row in rows]})
