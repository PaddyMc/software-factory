"""Path globs for the plan settings (`plans`, `exclude`)."""

from __future__ import annotations

import re


def glob_to_regex(pattern: str) -> re.Pattern:
    """Path glob: `**` spans directories, `*` stays within one; a plain path also covers its subtree."""
    pattern = pattern.rstrip("/")
    if not any(ch in pattern for ch in "*?["):
        return re.compile("^" + re.escape(pattern) + r"(/.*)?$")
    out, i = [], 0
    while i < len(pattern):
        if pattern.startswith("**", i):
            out.append(".*")
            i += 2
            if i < len(pattern) and pattern[i] == "/":
                i += 1
            continue
        out.append({"*": "[^/]*", "?": "."}.get(pattern[i], re.escape(pattern[i])))
        i += 1
    return re.compile("^" + "".join(out) + "$")


def matches_any(path: str, patterns) -> bool:
    return any(glob_to_regex(p).match(path) for p in patterns)
