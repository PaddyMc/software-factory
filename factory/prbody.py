"""Text helpers for a factory PR body.

These functions only shape text: the complete agent reports remain in the run
records, and the pointers in a capped body name the commands that print them.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass

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


def shorten(text: str, limit: int) -> str:
    """The first line, cut at a word boundary (with an ellipsis) to fit `limit`."""
    lines = text.splitlines()
    line = lines[0].strip() if lines else ""
    if len(line) <= limit:
        return line
    if limit <= 0:
        return ""
    if limit == 1:
        return "…"

    room = limit - 1                       # the ellipsis takes the last character
    words = [m for m in re.finditer(r"\S+", line) if m.end() <= room]
    kept = line[:words[-1].end()] if words else line[:room].rstrip()
    return kept + "…"


@dataclass
class Summary:
    title: str
    changed: list[str]
    check: list[str]


_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*$")
_BULLET = re.compile(r"^\s*(?:[-*]|\d+[.)])\s+(.+?)\s*$")


def _section(line: str) -> str | None:
    """The summary section named by a markdown heading or a whole bold line."""
    text = line.strip()
    match = _HEADING.match(text)
    if match:
        text = match.group(1).strip()
    else:
        if text.endswith(":"):             # also accept **What changed**:
            text = text[:-1].rstrip()
        if len(text) >= 4 and text[:2] == text[-2:] and text[:2] in ("**", "__"):
            text = text[2:-2].strip()
        else:
            return None
    text = text.rstrip(":").strip().casefold()
    return {"what changed": "changed", "what to check": "check"}.get(text)


def parse_summary(text: str) -> Summary | None:
    """Read the verifier's fixed-shape summary, tolerating headings and bullet styles."""
    title = ""
    title_seen = False
    sections: dict[str, list[str]] = {"changed": [], "check": []}
    seen: set[str] = set()
    current: str | None = None
    open_bullet: int | None = None

    for line in text.splitlines():
        section = _section(line)
        if section is not None:
            current = section if section not in seen else None   # the first draft of a section wins
            seen.add(section)
            open_bullet = None
            continue
        if _HEADING.match(line):           # an unrelated heading ends the current section
            current = None
            open_bullet = None
            continue
        if not title_seen and line.startswith("TITLE:"):
            title = line[len("TITLE:"):].strip()
            title_seen = True
            open_bullet = None
            continue

        bullet = _BULLET.match(line)
        if bullet:
            open_bullet = None
            if current is not None:
                sections[current].append(bullet.group(1).strip())
                open_bullet = len(sections[current]) - 1
            continue
        if current is not None and open_bullet is not None and line[:1].isspace() and line.strip():
            sections[current][open_bullet] += " " + line.strip()
        elif line.strip():
            open_bullet = None             # an unindented paragraph is not a continuation

    return Summary(title, sections["changed"], sections["check"]) if sections["changed"] else None


def _bound_bullets(items: list[str], limit: int, pointer: str) -> list[str]:
    """Bound content and replace everything that does not fit with one pointer bullet."""
    bounded = [shorten(item, 400) for item in items]
    if len(bounded) <= limit:
        return bounded
    if limit <= 0:
        return []
    kept = bounded[:limit - 1]             # the pointer itself stays within the section's limit
    more = len(bounded) - len(kept)
    return kept + [shorten(f"{more} more bullets: {pointer}", 400)]


def bound_summary(summary: Summary, task_id: str, step: str) -> Summary:
    """Apply the PR's title and bullet limits, pointing to the verify run for the rest."""
    pointer = f"factory show {task_id} --step {step}"
    return Summary(
        title=shorten(summary.title, 72),
        changed=_bound_bullets(summary.changed, 5, pointer),
        check=_bound_bullets(summary.check, 8, pointer),
    )


def _findings(report: str) -> list[str]:
    """Bullets under the last markdown heading whose text contains `Findings`."""
    lines = clean_report(report, "## Acceptance criteria").splitlines()
    headings = [(i, _HEADING.match(line)) for i, line in enumerate(lines)]
    matches = [(i, m) for i, m in headings if m and "findings" in m.group(1).casefold()]
    if not matches:
        return []
    start = matches[-1][0]
    found = []
    for line in lines[start + 1:]:
        if _HEADING.match(line):
            break
        if _BULLET.match(line):
            found.append(line.strip())
    return found


def fallback_summary(task, files, reviews: dict[str, str]) -> Summary:
    """A bounded summary built from the contract, changed paths and reviewer findings."""
    paths = list(files)
    count = f"{len(paths)} file" + ("" if len(paths) == 1 else "s") + " changed"
    listed = ", ".join(paths[:10]) + (", …" if len(paths) > 10 else "")
    files_bullet = count + (f": {listed}" if listed else "")
    changed = [shorten(task.goal, 400), files_bullet]

    checks: list[str] = []
    contributing: list[str] = []
    for step, report in reviews.items():
        found = _findings(report)
        if found:
            contributing.append(step)
        checks.extend(f"{step}: {finding}" for finding in found)
    pointers = "; ".join(f"factory show {task.id} --step {step}" for step in contributing)
    return Summary(
        title=shorten(task.goal, 72),
        changed=_bound_bullets(changed, 5, f"factory show {task.id}"),
        check=_bound_bullets(checks, 8, pointers),
    )


@dataclass
class Check:
    name: str
    ok: bool | None
    commands: int | None = None
    tests: int | None = None


def checks_paragraph(checks: list[Check], reviews: list[tuple[str, str | None]], sha: str, attempts: int) -> str:
    """One paragraph counting the candidate's gates, commands, tests and review outcomes."""
    failed = any(check.ok is False for check in checks)
    passed = sum(check.ok is not False for check in checks)
    count = f"{passed} of {len(checks)}" if failed else f"All {len(checks)}"
    sentences = [f"{count} gates passed on {sha[:12]} after {attempts} build "
                 f"attempt{'' if attempts == 1 else 's'}."]
    for check in checks:
        if check.commands is None:
            continue
        commands = f"{check.commands} command{'' if check.commands == 1 else 's'}"
        tests = "" if check.tests is None else (
            f", {check.tests} test{'' if check.tests == 1 else 's'}")
        sentences.append(f"{check.name}: {commands}{tests}.")
    skipped = [check.name for check in checks if check.ok is None]
    if skipped:
        sentences.append(f"Skipped: {', '.join(skipped)}.")
    sentences.extend(f"Reviewed by {name}: {outcome}." for name, outcome in reviews if outcome)
    return " ".join(sentences)


def demote(text: str) -> str:
    """Move markdown headings down two levels, without touching fenced code."""
    result = []
    fenced = False
    for line in text.splitlines(keepends=True):
        if line.startswith("```"):
            fenced = not fenced
            result.append(line)
            continue
        match = re.match(r"^(\s{0,3})(#{1,6})(?=\s)", line) if not fenced else None
        if match and _HEADING.match(line):
            level = len(match.group(2))
            at = match.start(2)
            line = line[:at] + "#" * min(2, 6 - level) + line[at:]
        result.append(line)
    return "".join(result)


def task_text(task) -> str:
    """The task contract, with its list-valued fields rendered as markdown lists."""
    def bullets(items: tuple[str, ...], code: bool = False) -> str:
        if not items:
            return "None."
        return "\n".join(f"- `{item}`" if code else f"- {item}" for item in items)

    return "\n\n".join([
        f"**Goal**\n\n{task.goal}",
        f"**Non-goals**\n\n{bullets(task.non_goals)}",
        f"**Acceptance criteria**\n\n{bullets(task.acceptance)}",
        f"**Verification commands**\n\n{bullets(task.verification, code=True)}",
    ])


def footer(task, flow, sha: str, base_ref: str, base_sha: str, cost: float | None = None) -> str:
    """The PR's task, flow, candidate and optional recorded cost on one line."""
    parts = [
        f"Factory task `{task.id}` from `{task.plan}`",
        f"**Flow** `{flow.name}`: " + ", ".join(step.name for step in flow.steps),
        f"Candidate `{sha}` on base `{base_ref}` (`{base_sha[:12]}`)",
    ]
    if cost:
        parts.append(f"${cost:.2f}")
    return " · ".join(parts)


def fit(assemble: Callable[[], str], steps: Iterable[Callable[[], None]], limit: int,
        last_resort: Callable[[], str]) -> str:
    """Assemble after each shrink in order, stopping as soon as the body fits."""
    body = assemble()
    for shrink in steps:
        if len(body) <= limit:
            return body
        shrink()
        body = assemble()
    return body if len(body) <= limit else last_resort()
