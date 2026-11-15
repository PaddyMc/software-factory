"""Server-rendered pages for the local factory web interface."""

from __future__ import annotations

import datetime as dt
import html
import importlib.metadata
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from .. import observe
from ..db import ACTIVE, DB, pid_alive, seconds_since
from ..log import log_path
from . import jobs

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
LOG_LINE = re.compile(r"(\d\d:\d\d:\d\d) (\[[^]]*\])? ?(.*)")
GOOD_OUTCOMES = {"done", "committed", "APPROVE", "pass", "verified", "opened"}
BAD_OUTCOMES = {"error", "fail", "CHANGES", "stopped"}


def esc(value) -> str:
    """Escape every value that comes from the board, config, request or filesystem."""
    return html.escape(str(value), quote=True)


def safe_url(url: str | None) -> str | None:
    """Only web URLs may become links; everything else is inert text or omitted."""
    return url if url and url.startswith(("https://", "http://")) else None


def action_form(action: str, token: str, next_: str, label: str, title: str,
                target: str | None = None, btn: str = "btn") -> str:
    target_field = (f'<input type="hidden" name="target" value="{esc(target)}">'
                    if target is not None else "")
    return f"""<form class="inline" method="post" action="/actions/{esc(action)}">
  <input type="hidden" name="token" value="{esc(token)}">{target_field}<input type="hidden" name="next" value="{esc(next_)}">
  <button class="{esc(btn)}" title="{esc(title)}">{esc(label)}</button>
</form>"""


def confirm_link(action: str, target: str, label: str, title: str, btn: str = "btn-danger") -> str:
    href = f"/confirm?action={quote(action, safe='')}&target={quote(target, safe='')}"
    return (f'<a class="btn {esc(btn)}" title="{esc(title)}" href="{esc(href)}">'
            f'{esc(label)}</a>')


def notice(job: jobs.Job | None) -> str:
    if job is None:
        return ""
    outcome = job.outcome
    if outcome == "done":
        wording, class_ = f"Done: {job.command}", "notice-ok"
    elif outcome == "running":
        wording, class_ = f"Still running: {job.command}", "notice-ok"
    else:
        wording, class_ = f"Failed: {job.command}", "notice-bad"
    output = job.output(1)
    last_line = output[-1] if output else ""
    return f"""<div class="notice {class_}" role="status">
  <span>{esc(wording)}</span>
  <span class="mono">{esc(last_line)}</span>
  <a href="/activity#job-{esc(job.id)}">View job</a>
</div>
"""


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


def _needs_row(db: DB, row, info: Status, token: str) -> str:
    next_step, why = _needs_next(db, row, info)
    actions = []
    if info.kind == "gone":
        actions.append(action_form("status", token, "/", "Check GitHub", "factory status --refresh"))
    elif info.kind == "failed":
        command = f'factory abandon {row["id"]} --note "put on hold from factory web"'
        actions.append(action_form("abandon", token, "/", "Put on hold", command, row["id"]))
    url = safe_url(row["pr_url"])
    if url:
        actions.append(f'<a class="btn" href="{esc(url)}">Open pull request</a>')
    action = "".join(actions)
    return f"""<li class="row">
  {status_html(info)}
  <a class="id" href="/tasks/{quote(row['id'], safe='')}">{esc(row['id'])}</a>
  <div class="what">
    <div class="next">{esc(next_step)}</div>
    <div class="why">{esc(why)}</div>
  </div>
  <div class="end"><div class="acts">{action}</div></div>
</li>"""


def _running_row(db: DB, row, info: Status) -> str:
    goal = _goal(db, row)
    stop = ""
    if pid_alive(row["pid"]):
        stop = confirm_link("stop", row["id"], "Stop", f'factory stop {row["id"]}')
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
  <a class="id" href="/tasks/{quote(row['id'], safe='')}">{esc(row['id'])}</a>
  <div class="what"><div class="goal" title="{esc(goal)}">{esc(goal)}</div></div>
  <div class="end">
    <span class="num quiet">{esc(elapsed)}</span>
    <span class="num cost">{esc(_cost(row))}</span>
    <div class="acts">{stop}</div>
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
  <a class="id" href="/tasks/{quote(row['id'], safe='')}">{esc(row['id'])}</a>
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
          refresh: int | None = None, current: str | None = None, top_end: str = "") -> str:
    address = f"127.0.0.1:{port}" if port is not None else "127.0.0.1"
    refresh_attr = f' data-refresh="{esc(refresh)}"' if refresh is not None else ""
    board_current = ' aria-current="page"' if current == "board" else ""
    activity_current = ' aria-current="page"' if current == "activity" else ""
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
    <nav class="nav" aria-label="Pages"><a href="/"{board_current}>Board</a><a href="/activity"{activity_current}>Activity</a></nav>
    <div class="top-end"><span class="live-dot" data-state="live">Live</span>{top_end}</div>
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


def board(db: DB, home: Path, project: str, port: int | None, token: str = "",
          job: jobs.Job | None = None) -> str:
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
{notice(job)}"""
    if not rows:
        content += ('<p class="fine">Load your plans with factory sync.</p>\n'
                    + action_form("sync", token, "/", "Load plans", "factory sync") + "\n")

    needs_html = "".join(_needs_row(db, row, infos[row["id"]], token) for row in needs_rows)
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
    top_end = (action_form("sync", token, "/", "Load plans", "factory sync")
               + action_form("status", token, "/", "Check GitHub", "factory status --refresh"))
    return _page("Board", project, home, port, content, refresh=2, current="board", top_end=top_end)


def _next_step(db: DB, row, info: Status, contract, actions: str = "") -> str:
    kind = info.kind
    note = ""
    if kind in NEEDS_ORDER:
        heading, detail = _needs_next(db, row, info)
        explanations = {
            "failed": ("Running it again starts a fresh build; putting it on hold keeps plan runs from picking it up."),
            "conflict": "Running it again starts a fresh build that resolves the conflict with its base.",
            "ci_failed": "Running it again starts a fresh build to fix the failing checks.",
            "changes_requested": "Running it again starts a fresh build to address the review.",
        }
        paragraph = esc(explanations.get(kind, detail))
        if kind in ("failed", "conflict", "ci_failed", "changes_requested"):
            note = f"<pre>{esc(row['note'] or '')}</pre>"
    elif kind == "running":
        progress = row["progress"] or ""
        match = STEP.search(progress)
        if match:
            label, attempt, used, limit = match.groups()
            heading = f"Running: {label} {attempt}, step {used} of {limit}."
        else:
            heading = f"Running: {progress}" if progress else "Running."
        activity = row["activity"] or ""
        quiet = observe.human_secs(seconds_since(row["heartbeat_at"]))
        paragraph = esc(f"{activity} · quiet {quiet}" if activity else f"quiet {quiet}")
    elif kind == "ready":
        heading = "Ready."
        paragraph = "The next run of its plan starts it."
    elif kind == "waiting":
        _, unmet = db.deps(contract)
        heading = f"Waits for {', '.join(unmet)}."
        paragraph = esc("A plan run starts it once those dependencies have merged or have open pull requests.")
    elif kind == "merged":
        heading = "Merged."
        url = safe_url(row["pr_url"])
        paragraph = (f'<a href="{esc(url)}">Open pull request</a>' if url else
                     "Its changes are merged.")
    elif kind == "abandoned":
        heading = "On hold."
        paragraph = "Plan runs skip it until you take it off hold."
    else:
        heading = info.word
        paragraph = esc(observe.detail(db, row))
    actions_html = f'<div class="acts">{actions}</div>' if actions else ""
    return f"""<section class="next-step" aria-labelledby="h-next">
  <div>
    <h2 id="h-next">{esc(heading)}</h2>
    <p>{paragraph}</p>
  </div>
  {actions_html}
  {note}
</section>"""


def _points(items, mono: bool = False) -> str:
    class_ = ' class="mono"' if mono else ""
    points = "".join(f"<li{class_}>{esc(item)}</li>" for item in items)
    return f'<ul class="points">{points}</ul>'


def _dependency(db: DB, task_id: str) -> str:
    row = db.task(task_id)
    if row is None:
        return f'<li><span class="mono">{esc(task_id)}</span></li>'
    href = quote(task_id, safe="")
    return (f'<li>{status_html(status(db, row))}<a class="mono" href="/tasks/{href}">'
            f'{esc(task_id)}</a></li>')


def _contract_block(db: DB, contract, needed_by: list[str]) -> str:
    commands = "".join(
        f'<div class="cmd"><code>{esc(command)}</code>'
        '<button class="copy" type="button" hidden>Copy</button></div>'
        for command in contract.verification)
    waits_for = "".join(_dependency(db, task_id) for task_id in contract.depends_on)
    dependents = "".join(_dependency(db, task_id) for task_id in needed_by)
    return f"""<section class="block contract" aria-labelledby="h-contract">
  <h2 id="h-contract">Contract</h2>
  <h3>Done when</h3>
  {_points(contract.acceptance)}
  <h3>Not part of it</h3>
  {_points(contract.non_goals)}
  <h3>Checked with</h3>
  {commands}
  <h3>Waits for</h3>
  <ul class="deps">{waits_for}</ul>
  <h3>Needed by</h3>
  <ul class="deps">{dependents}</ul>
  <h3>Reads</h3>
  {_points(contract.spec_refs, mono=True)}
</section>"""


def _relative(seconds: float | None) -> str:
    seconds = max(0, int(seconds or 0))
    if seconds < 60:
        count, unit = seconds, "second"
    elif seconds < 3600:
        count, unit = seconds // 60, "minute"
    elif seconds < 86400:
        count, unit = seconds // 3600, "hour"
    else:
        count, unit = seconds // 86400, "day"
    return f"{count} {unit}{'' if count == 1 else 's'}"


def _run_name(run) -> str:
    if run["role"] == "build":
        return f"build {run['attempt']}"
    name = run["step"] or run["role"]
    return f"{name}, build {run['attempt']}" if run["attempt"] else name


def _run_facts(run) -> str:
    facts = []
    if run["model"]:
        model = str(run["model"])
        facts.append(f'<span title="{esc(model)}">{esc(model.rsplit("/", 1)[-1])}</span>')
    if run["steps"]:
        facts.append(f"{run['steps']} steps")
    if run["tokens_in"]:
        facts.append(f"{run['tokens_in'] / 1000:,.0f}k in")
    if run["tokens_out"]:
        facts.append(f"{run['tokens_out'] / 1000:,.0f}k out")
    if run["cost_usd"] is not None:
        facts.append(_cost(run))
    return f'<div class="run-facts">{", ".join(facts)}</div>' if facts else ""


def _outcome_span(run) -> str:
    ended_at = run["ended_at"]
    outcome = run["outcome"] or ("running" if not ended_at else "finished")
    first = outcome.split(maxsplit=1)[0] if outcome else ""
    outcome_class = ("o-live" if not ended_at else "o-good" if first in GOOD_OUTCOMES else
                     "o-bad" if first in BAD_OUTCOMES else "")
    class_ = f" {outcome_class}" if outcome_class else ""
    return f'<span class="outcome{class_}">{esc(outcome)}</span>'


def _run_html(run, newest: bool, task_id: str) -> str:
    ended_at = run["ended_at"]
    started = dt.datetime.fromisoformat(run["started_at"])
    ended = dt.datetime.fromisoformat(ended_at) if ended_at else None
    duration = (ended - started).total_seconds() if ended else seconds_since(run["started_at"])
    relative = _relative(seconds_since(run["started_at"]))
    live = " is-live" if not ended_at else ""
    open_attr = " open" if newest else ""
    report = f'<pre class="report">{esc(run["report"])}</pre>' if run["report"] else ""
    transcript_link = ""
    if run["transcript"] and Path(run["transcript"]).is_file():
        href = f"/tasks/{quote(task_id, safe='')}/runs/{run['id']}"
        transcript_link = f'\n  <a class="run-link" href="{href}">Read the transcript</a>'
    return f"""<li class="run{live}">
  <div class="run-head"><span class="run-name">{esc(_run_name(run))}</span>{_outcome_span(run)}<span class="quiet"><time datetime="{esc(run['started_at'])}" title="{esc(run['started_at'])}">{esc(relative)}</time> ago, took {esc(observe.human_secs(duration))}</span></div>
  {_run_facts(run)}
  <details id="run-{run['id']}-report"{open_attr}><summary>Report</summary>{report}</details>{transcript_link}
</li>"""


def _runs_block(runs, task_id: str) -> str:
    items = "".join(_run_html(run, index == 0, task_id) for index, run in enumerate(runs))
    return f"""<section class="block" aria-labelledby="h-runs">
  <h2 id="h-runs">Runs <span class="count">{esc(len(runs))}</span> <span class="aside">Newest first</span></h2>
  <p class="runs-head">Each line is one agent, or one pass of the gates.</p>
  <ol class="runs">{items}</ol>
</section>"""


ROLE_WORDS = {"plan": "planner", "build": "builder", "review": "reviewer", "verify": "verifier"}


def _role_word(run) -> str:
    return ROLE_WORDS.get(run["role"]) or run["step"] or run["role"]


def run_of(db: DB, task_id: str, run_text: str):
    """Find a run only within its task; a run id from another task is not a match."""
    try:
        run_id = int(run_text)
    except (TypeError, ValueError):
        return None
    return next((run for run in db.runs(task_id) if run["id"] == run_id), None)


def _tokens(count: int) -> str:
    return f"{count:,}" if count < 1000 else f"{count / 1000:,.0f}k"


def _events(path: Path) -> list[dict]:
    events = []
    for line in path.read_text(errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get("type"):
            events.append(event)
    return events


def _step_groups(events: list[dict]) -> list[tuple[dict, list[dict]]]:
    groups = []
    for index, event in enumerate(events):
        if event.get("type") != "ai":
            continue
        results = []
        for following in events[index + 1:]:
            if following.get("type") != "tool":
                break
            results.append(following)
        groups.append((event, results))
    return groups


def _result(content: str, step: int, index: int | None) -> str:
    content = str(content)
    refused = " refused" if content.startswith("refused") else ""
    result = f'<pre class="result{refused}">{esc(content)}</pre>'
    if index is None or len(content) <= 2000:
        return result
    fold_id = esc(f"t-{step}-{index}")
    return (f'<details class="fold" id="{fold_id}"><summary>Result, {len(content):,} characters</summary>'
            f'{result}</details>')


def _step(ai: dict, results: list[dict], row: dict) -> str:
    timing = ""
    if row["model_s"] is not None:
        timing = f"{row['model_s']:.1f}s thinking"
    if row["tools_s"] >= 1.0:
        tools = f"{observe.human_secs(row['tools_s'])} in tools"
        timing = f"{timing}, {tools}" if timing else tools
    facts = []
    if timing:
        facts.append(timing)
    facts.append(f"{_tokens(row['ctx_in'])} in, {_tokens(row['out'])} out")
    if row["cost"] is not None:
        facts.append(f"${row['cost']:.3f}")
    facts_html = "<br>".join(esc(fact) for fact in facts)

    says = f'<p class="says">{esc(ai["text"])}</p>' if ai.get("text") else ""
    calls = []
    call_events = ai.get("tool_calls", []) or []
    for index, call in enumerate(call_events):
        args = ", ".join(f"{key}={value}" for key, value in (call.get("args", {}) or {}).items()
                         if key != "content")
        result = ""
        if index < len(results):
            result = _result(results[index].get("content", ""), row["step"], index)
        calls.append(f"""<div class="call">
  <div class="call-name"><b>{esc(call.get('name', ''))}</b>({esc(args)})</div>
  {result}
</div>""")
    surplus = "".join(_result(result.get("content", ""), row["step"], None)
                      for result in results[len(call_events):])
    return f"""<div class="step">
  <div>
    <div class="step-n">Step {esc(row['step'])}</div>
    <div class="step-facts">{facts_html}</div>
  </div>
  <div>{says}{''.join(calls)}{surplus}</div>
</div>"""


def transcript(db: DB, home: Path, project: str, port: int | None, task_id: str, run) -> str:
    label = _run_name(run)
    title = f"What the {_role_word(run)} did, step by step."
    task_row = db.task(task_id)
    plan_name = observe.plan_name(task_row["plan"])
    task_href = f"/tasks/{quote(task_id, safe='')}"

    events = None
    if run["transcript"]:
        path = Path(run["transcript"])
        if path.is_file():
            try:
                events = _events(path)
            except FileNotFoundError:
                pass

    rows = observe.trace_rows(events) if events is not None else []
    facts = []
    if events is not None:
        system = next((event for event in events if event.get("type") == "system"), {})
        model = system.get("model") or run["model"]
        if model:
            facts.append(("model", str(model)))
        facts.append(("steps", str(len(rows))))
        if rows:
            tokens_in = sum(row["ctx_in"] for row in rows)
            tokens_out = sum(row["out"] for row in rows)
            facts.append(("tokens", f"{_tokens(tokens_in)} in, {_tokens(tokens_out)} out"))
        costs = [row["cost"] for row in rows if row["cost"] is not None]
        if costs:
            facts.append(("cost", f"${sum(costs):.2f}"))
        if rows:
            model_s = sum(row["model_s"] or 0 for row in rows)
            tools_s = sum(row["tools_s"] for row in rows)
            facts.append(("time", f"{observe.human_secs(model_s)} thinking, "
                                  f"{observe.human_secs(tools_s)} in tools"))
        mix = Counter()
        for row in rows:
            for call in row["calls"]:
                name = call.split("(")[0]
                if name:
                    mix[name] += 1
        if mix:
            facts.append(("tools", ", ".join(f"{name} {count}" for name, count in mix.most_common())))
    facts_html = "".join(f"<div><dt>{esc(name)}</dt><dd>{esc(value)}</dd></div>" for name, value in facts)
    facts_block = f'<dl class="facts">{facts_html}</dl>' if facts_html else ""

    content = f"""<div class="page-head">
  <ol class="crumbs">
    <li><a href="/">Board</a></li>
    <li><a href="/#plan-{esc(plan_name)}">{esc(plan_name)}</a></li>
    <li><a href="{task_href}">{esc(task_id)}</a></li>
    <li>{esc(label)}</li>
  </ol>
  <div class="task-id"><span>{esc(label)}</span>{_outcome_span(run)}</div>
  <h1 class="task-goal">{esc(title)}</h1>
  {facts_block}
</div>
"""
    refresh = 2 if not run["ended_at"] else None
    if events is None:
        content += (f'<p class="fine">No transcript was recorded for this run. '
                    f'<a href="{task_href}">Back to {esc(task_id)}</a>.</p>\n')
        return _page(f"{task_id}, {label}", project, home, port, content, refresh=refresh)

    system = next((event for event in events if event.get("type") == "system"), None)
    human = next((event for event in events if event.get("type") == "human"), None)
    folds = []
    if system is not None:
        prompt = str(system.get("content", ""))
        folds.append(f'<details class="fold" id="t-system"><summary>What the agent was told '
                     f'({len(prompt):,} characters)</summary><pre class="result">{esc(prompt)}</pre></details>')
    if human is not None:
        message = str(human.get("content", ""))
        folds.append(f'<details class="fold" id="t-task"><summary>The task it was given '
                     f'({len(message):,} characters)</summary><pre class="result">{esc(message)}</pre></details>')
    groups = _step_groups(events)
    steps = "".join(_step(ai, results, row) for (ai, results), row in zip(groups, rows))
    stopped = next((event for event in events if event.get("type") == "stopped"), None)
    stopped_html = f'<p class="stopped">Stopped: {esc(stopped.get("reason", ""))}</p>' if stopped else ""
    content += f"""<section class="block" aria-labelledby="h-steps">
  <h2 id="h-steps">Steps <span class="count">{len(rows)}</span></h2>
  {''.join(folds)}
  {steps}
  {stopped_html}
</section>
"""
    return _page(f"{task_id}, {label}", project, home, port, content, refresh=refresh)


def _log_block(home: Path, task_id: str) -> str:
    try:
        lines = log_path(home, task_id).read_text(errors="replace").splitlines()[-200:]
    except FileNotFoundError:
        lines = []
    rendered = []
    for line in lines:
        match = LOG_LINE.match(line)
        if not match:
            rendered.append(esc(line))
            continue
        time, tag, text = match.groups()
        parts = [f'<span class="t">{esc(time)}</span>']
        if tag:
            parts.append(f'<span class="tag">{esc(tag)}</span>')
        parts.append(esc(text))
        rendered.append(" ".join(parts))
    log = "\n".join(rendered) if rendered else "No log yet."
    return f"""<section class="block" aria-labelledby="h-log">
  <h2 id="h-log">Log <span class="aside">Last 200 lines, follows the run</span></h2>
  <pre class="log" data-follow>{log}</pre>
</section>"""


def task(db: DB, home: Path, project: str, port: int | None, task_id: str, token: str = "",
         job: jobs.Job | None = None) -> str:
    row = db.task(task_id)
    info = status(db, row)
    contract = db.contract(task_id)
    task_href = f"/tasks/{quote(task_id, safe='')}"
    running = row["status"] in ACTIVE and pid_alive(row["pid"])
    actions = []
    if row["status"] in ("queued", "failed") and not running:
        command = f'factory abandon {task_id} --note "put on hold from factory web"'
        actions.append(action_form("abandon", token, task_href, "Put on hold", command, task_id))
    if row["status"] == "abandoned":
        actions.append(action_form("requeue", token, task_href, "Take off hold",
                                   f"factory requeue {task_id}", task_id))
    if running:
        actions.append(confirm_link("stop", task_id, "Stop", f"factory stop {task_id}"))
    if (home / "worktrees" / task_id).exists() and not running:
        actions.append(confirm_link("clean", task_id, "Remove worktree", f"factory clean {task_id}", "btn-quiet"))
    plan_name = observe.plan_name(row["plan"])
    runs = list(reversed(db.runs(task_id)))
    needed_by = [r["id"] for r in db.tasks() if task_id in db.contract(r["id"]).depends_on]

    facts = []
    if contract.risk:
        facts.append(("risk", esc(contract.risk)))
    if row["attempts"]:
        facts.append(("builds", esc(row["attempts"])))
    if _cost(row):
        facts.append(("cost", esc(_cost(row))))
    if row["branch"]:
        facts.append(("branch", esc(row["branch"])))
    if row["base_ref"] and row["base_sha"]:
        facts.append(("built on", esc(f"{row['base_ref']} at {row['base_sha'][:7]}")))
    url = safe_url(row["pr_url"])
    if url:
        facts.append(("pull request", f'<a href="{esc(url)}">pull request</a>'))
    facts_html = "".join(f"<div><dt>{esc(label)}</dt><dd>{value}</dd></div>" for label, value in facts)

    content = f"""<div class="page-head">
  <ol class="crumbs">
    <li><a href="/">Board</a></li>
    <li><a href="/#plan-{esc(plan_name)}">{esc(plan_name)}</a></li>
    <li>{esc(task_id)}</li>
  </ol>
  <div class="task-id"><span>{esc(task_id)}</span>{status_html(info)}</div>
  <h1 class="task-goal">{esc(contract.goal)}</h1>
  <dl class="facts">{facts_html}</dl>
</div>
{notice(job)}{_next_step(db, row, info, contract, "".join(actions))}
<div class="cols">
  {_contract_block(db, contract, needed_by)}
  {_runs_block(runs, task_id)}
</div>
{_log_block(home, task_id)}
"""
    return _page(contract.goal, project, home, port, content, refresh=2)


def _job_item(job: jobs.Job) -> str:
    outcome = job.outcome
    outcome_class = "o-live" if outcome == "running" else "o-good" if outcome == "done" else "o-bad"
    live = " is-live" if outcome == "running" else ""
    try:
        started = dt.datetime.fromisoformat(job.started_at)
        if started.tzinfo is None:
            started = started.replace(tzinfo=dt.timezone.utc)
        elapsed = max(0, (dt.datetime.now(dt.timezone.utc) - started).total_seconds())
        relative = _relative(elapsed)
    except (TypeError, ValueError):
        started = None
        relative = "unknown time"
    time_html = (f'<time datetime="{esc(job.started_at)}" title="{esc(job.started_at)}">'
                 if started is not None else "<span>")
    close_time = "</time>" if started is not None else "</span>"
    ended = None
    if job.result and job.result.get("ended_at"):
        try:
            ended = dt.datetime.fromisoformat(str(job.result["ended_at"]))
            if ended.tzinfo is None:
                ended = ended.replace(tzinfo=dt.timezone.utc)
        except (TypeError, ValueError):
            ended = None
    if started is not None and ended is not None:
        duration = observe.human_secs(max(0, (ended - started).total_seconds()))
        timing = f"{time_html}{esc(relative)}{close_time} ago, took {esc(duration)}"
    elif started is not None:
        duration = observe.human_secs(elapsed)
        suffix = f"running for {duration}" if outcome == "running" else f"{duration} since start"
        timing = f"{time_html}started {esc(relative)}{close_time} ago, {esc(suffix)}"
    else:
        timing = f"{time_html}{esc(relative)}{close_time} ago"
    output = job.output(200)
    report = f'<pre class="report">{esc(chr(10).join(output))}</pre>' if output else ""
    open_attr = " open" if outcome != "done" else ""
    stop = ""
    if outcome == "running" and job.kind == "run" and job.target:
        stop = confirm_link("stop", job.target, "Stop this run", f"factory stop {job.target}")
    return f"""<li class="run{live}">
  <div class="run-head"><span class="run-name">{esc(job.command)}</span><span class="outcome {outcome_class}">{esc(outcome)}</span><span class="quiet">{timing}</span></div>
  <details id="job-{esc(job.id)}"{open_attr}><summary>Output</summary>{report}</details>
  {stop}
</li>"""


def _all_task_logs(home: Path) -> str:
    logs = home / "logs"
    task_ids = sorted(path.stem for path in logs.glob("*.log")) if logs.is_dir() else []
    rendered = []
    for time, task_id, line in observe.recent_lines(home, task_ids, 200):
        rest = line[8:].lstrip()
        rendered.append(f'<span class="t">{esc(time)}</span> <span class="tag">{esc(task_id)}</span> {esc(rest)}')
    return "\n".join(rendered) if rendered else "No log yet."


def activity(home: Path, project: str, port: int | None, job: jobs.Job | None = None) -> str:
    all_jobs = jobs.load(home)
    running = sum(item.outcome == "running" for item in all_jobs)
    if running == 1:
        sentence = "1 command is running."
    elif running:
        sentence = f"{running} commands are running."
    else:
        sentence = "Nothing is running from this page."
    shown = all_jobs[:50]
    items = "".join(_job_item(item) for item in shown)
    content = f"""<div class="page-head">
  <h1 class="lede">{esc(sentence)}</h1>
</div>
{notice(job)}<section class="block" aria-labelledby="h-cmds">
  <h2 id="h-cmds">Commands from this page <span class="count">{len(shown)}</span> <span class="aside">Newest first</span></h2>
  <ol class="runs">{items}</ol>
</section>
<section class="block" aria-labelledby="h-events">
  <h2 id="h-events">Latest from every task <span class="aside">Last 200 lines</span></h2>
  <pre class="log" data-follow>{_all_task_logs(home)}</pre>
</section>
"""
    return _page("Activity", project, home, port, content, refresh=2, current="activity")


def confirm(project: str, home: Path, port: int | None, token: str, action: str, target: str,
            applies: bool, why: str = "", back=("Back to the board", "/")) -> str:
    stopping = action == "stop"
    title = f"Stop {target}?" if stopping else f"Remove {target}'s worktree?"
    command = f"factory {action} {target}"
    if stopping:
        explanation = (f"{command} terminates the running task, or the plan run and every task it started. "
                       "It waits briefly, then kills a process that does not exit.")
        next_ = "/activity"
        label = "Stop"
        return_to = ("Back to the board", "/")
    else:
        explanation = (f"{command} removes this task's worktree. Its board entry, branches and pull request "
                       "are left alone.")
        next_ = f"/tasks/{quote(target, safe='')}"
        label = "Remove worktree"
        return_to = (f"Back to {target}", next_)
    if applies:
        detail = (f'<p class="fine">{esc(explanation)}</p>'
                  + action_form(action, token, next_, label, command, target, "btn btn-danger")
                  + f' <a class="btn" href="{esc(return_to[1])}">{esc(return_to[0])}</a>')
    else:
        detail = (f'<p class="fine">{esc(why)}</p>'
                  f'<a class="btn" href="{esc(back[1])}">{esc(back[0])}</a>')
    content = f"""<div class="page-head">
  <h1 class="lede">{esc(title)}</h1>
</div>
{detail}
"""
    return _page(title, project, home, port, content)


def error_page(project: str, home: Path, port: int | None, title: str, message: str,
               back=("Back to the board", "/")) -> str:
    content = f"""<div class="page-head">
  <h1 class="lede">{esc(title)}</h1>
</div>
<p class="fine">{esc(message)} <a href="{esc(back[1])}">{esc(back[0])}</a>.</p>
"""
    return _page(title, project, home, port, content)
