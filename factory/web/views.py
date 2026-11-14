"""Server-rendered pages for the local factory web interface."""

from __future__ import annotations

import html
import importlib.metadata
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .. import observe
from ..db import ACTIVE, DB, seconds_since

DONE = ("merged", "abandoned")
ATTENTION = ("pr_open", "conflict", "ci_failed", "changes_requested")


@dataclass(frozen=True)
class Status:
    word: str
    css: str
    kind: str


STATUSES = {
    "merged": Status("Merged", "s-merged", "merged"),
    "pr_open": Status("PR open", "s-pr", "pr_open"),
    "conflict": Status("Conflict", "s-attn", "conflict"),
    "ci_failed": Status("CI failing", "s-attn", "ci_failed"),
    "changes_requested": Status("Changes requested", "s-attn", "changes_requested"),
    "planning": Status("Planning", "s-live", "running"),
    "building": Status("Building", "s-live", "running"),
    "reviewing": Status("Reviewing", "s-live", "running"),
    "verifying": Status("Verifying", "s-live", "running"),
    "failed": Status("Failed", "s-failed", "failed"),
    "abandoned": Status("On hold", "s-held", "abandoned"),
}
GONE = Status("Process gone", "s-failed", "gone")
READY = Status("Ready", "s-ready", "ready")
WAITING = Status("Waiting", "s-waiting", "waiting")
COUNT_ORDER = ("pr_open", "conflict", "ci_failed", "changes_requested", "running", "failed", "gone",
               "ready", "waiting", "abandoned")
COUNT_WORDS = {
    "pr_open": "PR open",
    "conflict": "conflict",
    "ci_failed": "CI failing",
    "changes_requested": "changes requested",
    "running": "running",
    "failed": "failed",
    "gone": "process gone",
    "ready": "ready",
    "waiting": "waiting",
    "abandoned": "on hold",
}
NEEDS_ORDER = {"gone": 0, "failed": 1, "conflict": 2, "ci_failed": 3, "changes_requested": 4, "pr_open": 5}
STEP = re.compile(r"(\S+)#(\d+) step (\d+)/(\d+)")


def esc(value) -> str:
    """Escape every value that comes from the board, config, request or filesystem."""
    return html.escape(str(value), quote=True)


def safe_url(url: str | None) -> str | None:
    """Only web URLs may become links; everything else is inert text or omitted."""
    return url if url and url.startswith(("https://", "http://")) else None


def status(db: DB, row) -> Status:
    if observe.liveness(row) == "DEAD":
        return GONE
    if row["status"] == "queued":
        return READY if db.ready(row["id"]) else WAITING
    return STATUSES.get(row["status"], Status(str(row["status"]), "s-waiting", str(row["status"])))


def status_html(info: Status) -> str:
    return f'<span class="status {info.css}"><i class="mark"></i>{esc(info.word)}</span>'


def _cost(row) -> str:
    return f"${row['cost_usd']:.2f}" if row["cost_usd"] is not None else ""


def _plan_cost(rows) -> str:
    if not any(row["cost_usd"] is not None for row in rows):
        return ""
    return f"${sum(row['cost_usd'] or 0 for row in rows):.2f}"


def _goal(db: DB, row) -> str:
    return db.contract(row["id"]).goal


def _pr_number(url: str | None) -> str | None:
    match = re.search(r"(\d+)/?$", url or "")
    return match.group(1) if match else None


def _needs_next(db: DB, row, info: Status) -> tuple[str, str]:
    kind = info.kind
    if kind == "gone":
        return "Its process is gone. Check GitHub to mark it failed.", observe.detail(db, row)
    if kind == "failed":
        return "Read why it failed, then run it again.", observe.failing_summary(row["note"])
    if kind == "conflict":
        return "Run it again to resolve the conflict with its base.", observe.failing_summary(row["note"])
    if kind == "ci_failed":
        return ("Run it again to fix the failing checks on its pull request.",
                observe.failing_summary(row["note"]))
    if kind == "changes_requested":
        return "Run it again to address the review.", observe.failing_summary(row["note"])
    number = _pr_number(row["pr_url"])
    if row["stacked_on"]:
        first = (f"Review pull request #{number}; merge it after {row['stacked_on']}." if number else
                 f"Review the pull request; merge it after {row['stacked_on']}.")
    else:
        first = f"Review and merge pull request #{number}." if number else "Review and merge the pull request."
    return first, "Every gate passed. Merging is your approval."


def _needs_row(db: DB, row, info: Status) -> str:
    next_step, why = _needs_next(db, row, info)
    action = ""
    url = safe_url(row["pr_url"])
    if url:
        action = f'<a class="btn" href="{esc(url)}">Open pull request</a>'
    return f"""<li class="row">
  {status_html(info)}
  <span class="id">{esc(row['id'])}</span>
  <div class="what">
    <div class="next">{esc(next_step)}</div>
    <div class="why">{esc(why)}</div>
  </div>
  <div class="end"><div class="acts">{action}</div></div>
</li>"""


def _running_row(db: DB, row, info: Status) -> str:
    goal = _goal(db, row)
    progress = row["progress"] or ""
    match = STEP.search(progress)
    if match:
        label, attempt, used, limit = match.groups()
        step = f"{label} {attempt}, step {used} of {limit}"
        meter = (f'<progress class="meter" value="{esc(used)}" max="{esc(limit)}" '
                 f'aria-label="{esc(used)} of {esc(limit)} steps"></progress>')
    else:
        step = progress
        meter = ""
    elapsed = observe.human_secs(seconds_since(row["started_at"]))
    quiet = observe.human_secs(seconds_since(row["heartbeat_at"]))
    return f"""<li class="row">
  {status_html(info)}
  <span class="id">{esc(row['id'])}</span>
  <div class="what"><div class="goal" title="{esc(goal)}">{esc(goal)}</div></div>
  <div class="end">
    <span class="num quiet">{esc(elapsed)}</span>
    <span class="num cost">{esc(_cost(row))}</span>
  </div>
  <div class="now">
    <span>{esc(step)}</span>
    {meter}
    <span class="doing">{esc(row['activity'] or '')}</span>
    <span>quiet {esc(quiet)}</span>
  </div>
</li>"""


def _plan_task_row(db: DB, row, info: Status) -> str:
    goal = _goal(db, row)
    why = ""
    if info.kind == "waiting":
        why = f'<div class="why">{esc(db.readiness(row["id"]))}</div>'
    attempts = row["attempts"] or 0
    builds = f"{attempts} build" if attempts == 1 else f"{attempts} builds" if attempts else ""
    return f"""<li class="row">
  {status_html(info)}
  <span class="id">{esc(row['id'])}</span>
  <div class="what"><div class="goal" title="{esc(goal)}">{esc(goal)}</div>{why}</div>
  <div class="end"><span class="num quiet builds">{esc(builds)}</span><span class="num cost">{esc(_cost(row))}</span></div>
</li>"""


def _counts(rows, infos) -> tuple[str, str]:
    counts = Counter(info.kind for info in infos)
    rest = [f"{counts[kind]} {COUNT_WORDS[kind]}" for kind in COUNT_ORDER if counts[kind]]
    text = ", ".join([f"{counts['merged']} of {len(rows)} merged", *rest])
    aria_counts = ([f"{counts['merged']} merged"] if counts["merged"] else []) + rest
    return text, ", ".join(aria_counts)


def _plan(db: DB, name: str, rows, open_: bool) -> str:
    infos = [status(db, row) for row in rows]
    counts, aria = _counts(rows, infos)
    squares = "".join(f'<i class="{info.css}"></i>' for info in infos)
    tasks = "".join(_plan_task_row(db, row, info) for row, info in zip(rows, infos))
    open_attr = " open" if open_ else ""
    return f"""<details class="plan" id="plan-{esc(name)}"{open_attr}>
  <summary>
    <span class="plan-name">{esc(name)}</span>
    <span class="strip" role="img" aria-label="{esc(aria)}">{squares}</span>
    <span class="plan-counts">{esc(counts)}</span>
    <span class="plan-end"><span class="num">{esc(_plan_cost(rows))}</span></span>
  </summary>
  <ul class="rows">{tasks}</ul>
</details>"""


def _tally(running: int, needs: int, ready: int, waiting: int, merged: int, held: int, spent: float) -> str:
    entries = [("running", str(running)), ("need you", str(needs)), ("ready", str(ready)),
               ("waiting", str(waiting)), ("merged", str(merged))]
    if held:
        entries.append(("on hold", str(held)))
    entries.append(("spent", f"${spent:.2f}"))
    body = "".join(f'<div><dt>{esc(label)}</dt><dd>{esc(value)}</dd></div>' for label, value in entries)
    return f'<dl class="tally">{body}</dl>'


def _sentence(rows, running: int, needs: int, ready: int, waiting: int) -> str:
    if not rows:
        return "No tasks yet."
    if needs:
        sentence = "1 task needs you." if needs == 1 else f"{needs} tasks need you."
    else:
        sentence = "Nothing needs you."
    if running:
        return sentence + (" 1 is running." if running == 1 else f" {running} are running.")
    if not needs:
        if ready:
            return sentence + f" {ready} tasks are ready to run."
        if all(row["status"] in DONE for row in rows):
            return sentence + " Every plan is finished."
        if waiting:
            return sentence + f" {waiting} tasks are waiting."
    return sentence


def _version() -> str:
    try:
        return importlib.metadata.version("software-factory")
    except importlib.metadata.PackageNotFoundError:
        return "0.1.0"


def _page(title: str, project: str, home: Path, port: int | None, content: str,
          refresh: int | None = None) -> str:
    address = f"127.0.0.1:{port}" if port is not None else "127.0.0.1"
    refresh_attr = f' data-refresh="{esc(refresh)}"' if refresh is not None else ""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} · {esc(project)}</title>
<link rel="icon" href="/static/favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="/static/app.css">
<script src="/static/app.js" defer></script>
</head>
<body>
<header class="top">
  <div class="wrap">
    <a class="brand" href="/">factory <span>/ {esc(project)}</span></a>
    <nav class="nav" aria-label="Pages"><a href="/" aria-current="page">Board</a></nav>
    <div class="top-end"><span class="live-dot" data-state="live">Live</span></div>
  </div>
</header>
<main class="wrap"{refresh_attr}>
{content}
<footer class="foot">
  <span>factory web {esc(_version())}</span>
  <span>{esc(address)}, this machine only</span>
  <span>state in {esc(home)}</span>
</footer>
</main>
<div class="banner" hidden>Can't reach factory web. Retrying.</div>
</body>
</html>
"""


def board(db: DB, home: Path, project: str, port: int | None) -> str:
    rows = db.tasks()
    infos = {row["id"]: status(db, row) for row in rows}
    running_rows = [row for row in rows if row["status"] in ACTIVE]
    needs_rows = [row for row in rows if infos[row["id"]].kind in NEEDS_ORDER]
    needs_rows.sort(key=lambda row: (NEEDS_ORDER[infos[row["id"]].kind], row["id"]))
    queued = [row for row in rows if row["status"] == "queued"]
    ready = sum(db.ready(row["id"]) for row in queued)
    waiting = len(queued) - ready
    merged = sum(row["status"] == "merged" for row in rows)
    held = sum(row["status"] == "abandoned" for row in rows)
    spent = sum(row["cost_usd"] or 0 for row in rows)
    running = len(running_rows)
    needs = len(needs_rows)

    content = f"""<div class="page-head">
  <h1 class="lede">{esc(_sentence(rows, running, needs, ready, waiting))}</h1>
  {_tally(running, needs, ready, waiting, merged, held, spent)}
</div>
"""
    if not rows:
        content += '<p class="fine">Load your plans with factory sync.</p>\n'

    needs_html = "".join(_needs_row(db, row, infos[row["id"]]) for row in needs_rows)
    if not needs_html:
        needs_html = '<p class="empty">Nothing needs you right now.</p>'
    else:
        needs_html = f'<ul class="rows">{needs_html}</ul>'
    content += f"""<section class="block" aria-labelledby="h-you">
  <h2 id="h-you">Needs you <span class="count">{esc(needs)}</span></h2>
  {needs_html}
</section>
"""

    if running_rows:
        running_html = "".join(_running_row(db, row, infos[row["id"]]) for row in running_rows)
        content += f"""<section class="block" aria-labelledby="h-run">
  <h2 id="h-run">Running <span class="count">{esc(running)}</span></h2>
  <ul class="rows">{running_html}</ul>
</section>
"""

    groups = observe.plan_groups(db, rows)
    live, remaining, finished = [], [], []
    for name, rs in groups:
        if any(row["status"] in ACTIVE + ATTENTION + ("failed",) for row in rs):
            live.append((name, rs))
        elif all(row["status"] in DONE for row in rs):
            finished.append((name, rs))
        else:
            remaining.append((name, rs))
    plans = "".join(_plan(db, name, rs, True) for name, rs in live)
    plans += "".join(_plan(db, name, rs, False) for name, rs in remaining)
    if finished:
        finished_plans = "".join(_plan(db, name, rs, False) for name, rs in finished)
        label = "1 finished plan" if len(finished) == 1 else f"{len(finished)} finished plans"
        plans += f'<details class="finished" id="finished"><summary>{esc(label)}</summary>{finished_plans}</details>'
    content += f"""<section class="block" aria-labelledby="h-plans">
  <h2 id="h-plans">Plans <span class="count">{esc(len(groups))}</span> <span class="aside">One square per task, in the order they run.</span></h2>
  {plans}
</section>
"""
    return _page("Board", project, home, port, content, refresh=2)


def error_page(project: str, home: Path, port: int | None, title: str, message: str) -> str:
    content = f"""<div class="page-head">
  <h1 class="lede">{esc(title)}</h1>
</div>
<p class="fine">{esc(message)} <a href="/">Back to the board</a>.</p>
"""
    return _page(title, project, home, port, content)
