"""Text helpers for a factory PR body.

These functions only shape text: the complete agent reports remain in the run
records, and the pointers in a capped body name the commands that print them.
"""

from __future__ import annotations

import re

BODY_LIMIT = 60_000
BLOCK_LIMIT = 12_000


def clean_report(text: str, first: str | None = None) -> str:
    """Drop an agent's preamble, keeping only its last draft when `first` repeats."""
    lines = text.splitlines(keepends=True)
    if first is not None:
        marker = first.strip()
        drafts = [i for i, line in enumerate(lines) if line.strip() == marker]
        if len(drafts) > 1:
            return "".join(lines[drafts[-1]:]).strip()
    for i, line in enumerate(lines):
        if re.match(r"#{1,6}(\s|$)", line):
            return "".join(lines[i:]).strip()
    return text.strip()


def cap(text: str, limit: int, pointer: str) -> str:
    """Cap text at a line where possible, closing a fence and pointing to the full report."""
    if len(text) <= limit:
        return text

    def assemble(at: int) -> str:
        prefix = text[:at]
        open_fence = sum(line.startswith("```") for line in prefix.splitlines()) % 2
        note = f"… kept {len(prefix)} of {len(text)} characters: {pointer}"
        return prefix + ("\n```" if open_fence else "") + "\n\n" + note

    breaks = [i for i, char in enumerate(text) if char == "\n"]
    for at in reversed(breaks):
        if at > limit:
            continue
        result = assemble(at)
        if len(result) <= limit:
            return result

    # A long line has no suitable break: make the largest hard cut that fits.
    for at in range(min(limit, len(text)), -1, -1):
        result = assemble(at)
        if len(result) <= limit:
            return result
    return assemble(0)[:max(0, limit)]
