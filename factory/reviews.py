"""Reviews on open factory PRs.

A human reviews a factory PR on GitHub, and `factory status --refresh` reads those reviews to decide which
unaddressed ones request changes (docs/plans/pr-review-rework.md). The trigger is conservative so it fires on a
solo repository: any submitted review by the PR's author counts, and for everyone else only a reviewer with
write or admin permission whose *latest* decision is a request does. The `reviews_addressed` watermark excludes
reviews the factory has already answered, and `brief` turns the remainder into the builder's feedback.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .ci import BRIEF_LIMIT

# Copy of stack.PR_NUMBER; importing stack would pull in langgraph.
PR_NUMBER = re.compile(r"/(\d+)/?$")

WRITE = {"write", "admin"}
DECIDED = {"APPROVED", "CHANGES_REQUESTED", "DISMISSED"}


@dataclass(frozen=True)
class Snapshot:
    """What one `fetch` returns: the PR's author, its submitted reviews (raw GitHub dicts, in id order)
    and each reviewer's permission string."""
    author: str
    reviews: tuple[dict, ...]
    permissions: dict[str, str]


def _values(root: Path, path: str, paginate: bool = False) -> list | None:
    """The values `gh api` prints for `path`, flattened one level; None on any failure or invalid JSON.
    `--paginate` prints one JSON array per page, back to back, so the output is parsed as concatenated arrays."""
    p = subprocess.run(["gh", "api", *(["--paginate"] if paginate else []), path], cwd=root,
                       capture_output=True, text=True)
    if p.returncode != 0:
        return None
    dec = json.JSONDecoder()
    text = p.stdout.lstrip("\ufeff")
    out = []
    try:
        while text.lstrip():
            text = text.lstrip()
            value, end = dec.raw_decode(text)
            out.extend(value if isinstance(value, list) else [value])
            text = text[end:]
    except json.JSONDecodeError:
        return None
    return out


def _values_one(root: Path, path: str) -> dict | None:
    vals = _values(root, path)
    return vals[0] if vals and isinstance(vals[0], dict) else None


def _login(r: dict) -> str:
    return (r.get("user") or {}).get("login") or ""


def _commit(r: dict) -> str:
    return (r.get("commit_id") or "")[:12]


def _line(c: dict) -> str:
    """One inline comment as `path:line: body`; an outdated comment (`line` null) shows its original
    line, marked outdated."""
    line = c.get("line")
    mark = ""
    if line is None:
        line = c.get("original_line")
        mark = " (outdated)"
    return f"- {c.get('path')}:{line}{mark}: {c.get('body') or ''}"


def fetch(root: Path, pr_url: str) -> Snapshot | None:
    """The PR's author, its submitted reviews, and each reviewer's permission, read through `gh api`.
    None when any call fails or prints invalid JSON, or the author can't be determined."""
    m = PR_NUMBER.search(pr_url or "")
    if not m:
        return None
    num = m.group(1)
    pr = _values_one(root, f"repos/{{owner}}/{{repo}}/pulls/{num}")
    if not pr:
        return None
    author = (pr.get("user") or {}).get("login")
    if not author:
        return None
    revs = _values(root, f"repos/{{owner}}/{{repo}}/pulls/{num}/reviews?per_page=100", paginate=True)
    if revs is None:
        return None
    reviews = sorted((r for r in revs if isinstance(r, dict) and r.get("state") != "PENDING"),
                     key=lambda r: r.get("id", 0))
    permissions: dict[str, str] = {}
    for login in dict.fromkeys(_login(r) for r in reviews):
        if not login:
            continue
        perm = _values_one(root, f"repos/{{owner}}/{{repo}}/collaborators/{login}/permission")
        if perm is None:
            return None
        permissions[login] = perm.get("permission") or "none"
    return Snapshot(author, tuple(reviews), permissions)


def _unaddressed(snap: Snapshot, watermark: int | None) -> list[dict]:
    """The submitted (non-PENDING) reviews that come after the task's watermark (NULL = nothing
    addressed, so 0)."""
    floor = watermark or 0
    return [r for r in snap.reviews if r.get("state") != "PENDING" and (r.get("id") or 0) > floor]


def covered(snap: Snapshot, watermark: int | None = None) -> list[dict]:
    """The unaddressed reviews whose content reaches the brief: the author's, and anyone with write/admin
    access, whatever their state. `requests` is the subset of these that block the merge."""
    out = []
    for r in _unaddressed(snap, watermark):
        login = _login(r)
        if login == snap.author or snap.permissions.get(login) in WRITE:
            out.append(r)
    return out


def requests(snap: Snapshot, watermark: int | None = None) -> list[dict]:
    """The unaddressed reviews that request changes. Any submitted review by the PR's author counts; for
    anyone else with write/admin access, only their latest decided (APPROVED/CHANGES_REQUESTED/DISMISSED)
    review counts, and only when it is CHANGES_REQUESTED. COMMENTED from others neither requests nor clears,
    and read/triage/none access never counts."""
    out = []
    latest: dict[str, dict] = {}
    for r in covered(snap, watermark):
        login = _login(r)
        if login == snap.author:
            out.append(r)
        elif r.get("state") in DECIDED:
            latest[login] = r   # a COMMENTED review neither requests nor clears, so only decisions count
    for r in latest.values():
        if r.get("state") == "CHANGES_REQUESTED":
            out.append(r)
    out.sort(key=lambda r: r.get("id", 0))
    return out


def brief(root: Path, pr_url: str, snap: Snapshot, watermark: int | None = None) -> str:
    """The builder's feedback for addressing a review rework: the heading, the in-scope sentence, then each
    counted review with its inline comments as `path:line: body` (replies indented, outdated lines marked).
    Capped like ci.BRIEF_LIMIT."""
    revs = covered(snap, watermark)
    m = PR_NUMBER.search(pr_url or "")
    num = m.group(1) if m else ""
    comments: dict[int, list[dict]] = {}
    comments_failed = None
    if num:
        vals = _values(root, f"repos/{{owner}}/{{repo}}/pulls/{num}/comments?per_page=100", paginate=True)
        if vals is None:
            comments_failed = True
        else:
            ids = {r.get("id") for r in revs}
            for c in vals:
                if isinstance(c, dict) and c.get("pull_request_review_id") in ids:
                    comments.setdefault(c["pull_request_review_id"], []).append(c)
    for cl in comments.values():
        cl.sort(key=lambda c: c.get("id", 0))

    shas = ", ".join(dict.fromkeys(_commit(r) for r in revs if _commit(r)))
    parts = [
        f"# Address review\n\nThis task's PR ({pr_url}) is open, and its reviewer, who approves the merge, "
        f"asked for changes on {shas}. The worktree is the PR's branch at that commit. Do what each review "
        f"asks, even where it goes beyond the plan, the task's goal or its non-goals. Where a comment asks a "
        f"question, answer it in your final message, and change code only if the answer calls for it.",
    ]
    for r in revs:
        login = _login(r)
        state = r.get("state") or ""
        header = f"## Review by @{login} ({state}, on {_commit(r)})"
        block = [header]
        body = (r.get("body") or "").strip()
        if body:
            block.append(body)
        rev_comments = comments.get(r.get("id"), [])
        replies: dict[int, list[dict]] = {}
        for c in rev_comments:
            if c.get("in_reply_to_id") is not None:
                replies.setdefault(c["in_reply_to_id"], []).append(c)
        for c in rev_comments:
            if c.get("in_reply_to_id") is not None:
                continue
            block.append(_line(c))
            block.extend("  " + _line(rep) for rep in replies.get(c.get("id"), []))
        parts.append("\n".join(block))
    if comments_failed:
        parts.append("(the inline comments couldn't be read: gh failed or printed invalid JSON)")
    text = "\n\n".join(parts)
    return text if len(text) <= BRIEF_LIMIT else text[:BRIEF_LIMIT] + "\n… (truncated)"