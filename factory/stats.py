"""Factory statistics read from the board, never written back to it.

The window selects runs. A task with at least one selected run is in the window:
task-level metrics then use all of that task's runs, while run-level metrics use
only the selected runs. Step first-seen dates are the exception: they span the
whole database so an older prompt version keeps its actual first-seen date.
"""

from __future__ import annotations

import datetime as dt
import re
from collections import Counter

from . import observe
from .db import DB

UTC = dt.timezone.utc
STOP_SUFFIXES = ("(step limit)", "(graph recursion limit)")
GATE_FAIL = re.compile(r"^\|\s*([^|]+?)\s*\|\s*FAIL\s*\|", re.MULTILINE)


def _utc(value: dt.datetime) -> dt.datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def parse_when(text: str, flag: str) -> dt.datetime:
    """An ISO date at midnight UTC, or an ISO datetime (naive means UTC)."""
    try:
        return _utc(dt.datetime.fromisoformat(text))
    except (TypeError, ValueError):
        raise ValueError(f"{flag}: not an ISO date: {text!r}") from None


def _started(run) -> dt.datetime:
    return _utc(dt.datetime.fromisoformat(run["started_at"]))


def _display_step(run) -> str:
    return run["step"] or run["role"]


def _group_key(run) -> tuple:
    # Pre-flow runs have no step; their role is the step they are reported under.
    return (run["flow"], _display_step(run), run["model"], run["prompt_version"])


def _is_stop(run) -> bool:
    return (run["outcome"] or "").endswith(STOP_SUFFIXES)


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _rate_data(numerator: int, denominator: int) -> dict:
    return {"rate": _rate(numerator, denominator), "numerator": numerator, "denominator": denominator}


def _sorted_counts(counts: Counter) -> dict:
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def collect(db: DB, since: str | None = None, until: str | None = None,
            plan: str | None = None) -> dict | None:
    """Collect every stats metric, or return None when the window selects no tasks."""
    since_at = parse_when(since, "--since") if since is not None else None
    until_at = parse_when(until, "--until") if until is not None else None
    tasks = observe.in_plan(db.tasks(), plan)
    by_id = {task["id"]: task for task in tasks}
    runs = db.conn.execute("SELECT * FROM runs ORDER BY id").fetchall()

    def in_window(run) -> bool:
        if run["task_id"] not in by_id:
            return False
        started = _started(run)
        return (since_at is None or started >= since_at) and (until_at is None or started < until_at)

    window_runs = [run for run in runs if in_window(run)]
    selected_ids = {run["task_id"] for run in window_runs}
    if not selected_ids:
        return None
    selected_tasks = [task for task in tasks if task["id"] in selected_ids]
    task_runs = {task_id: [] for task_id in selected_ids}
    for run in runs:
        if run["task_id"] in selected_ids:
            task_runs[run["task_id"]].append(run)

    build_ids = {task_id for task_id, rs in task_runs.items() if any(r["role"] == "build" for r in rs)}
    pr_ids = {task_id for task_id, rs in task_runs.items() if any(r["role"] == "pr" for r in rs)}
    first_opened = {}
    for task_id, rs in task_runs.items():
        opened = next((r for r in rs if r["role"] == "pr" and r["outcome"] == "opened"), None)
        if opened is not None:
            first_opened[task_id] = opened
    passed_first = {task_id for task_id, run in first_opened.items()
                    if task_id in build_ids and run["attempt"] == 1}
    attempts = [run["attempt"] for run in first_opened.values()]

    merged_ids = {task["id"] for task in selected_tasks if task["status"] == "merged"}
    priced_cost = 0.0
    priced_merged = unpriced_merged = 0
    for task_id in merged_ids:
        rs = task_runs[task_id]
        if any(r["model"] is not None and r["cost_usd"] is None for r in rs):
            unpriced_merged += 1
        else:
            priced_merged += 1
            priced_cost += sum(r["cost_usd"] or 0 for r in rs)

    review_runs = [r for r in window_runs if r["role"] == "review"]
    changes = sum((r["outcome"] or "").startswith("CHANGES") for r in review_runs)
    stops = Counter(_display_step(r) for r in window_runs if _is_stop(r))
    merge_runs = [r for r in window_runs if r["role"] == "merge"]
    edited = sum(r["outcome"] == "edited" for r in merge_runs)

    reworks = {}
    for kind, role in (("conflict", "resolve"), ("ci", "ci"), ("review", "human_review")):
        numerator = sum(any(r["role"] == role for r in task_runs[task_id]) for task_id in pr_ids)
        reworks[kind] = _rate_data(numerator, len(pr_ids))

    gate_failures = Counter()
    for run in window_runs:
        if run["role"] == "verify" and run["outcome"] == "fail":
            gate_failures.update(match.group(1).strip() for match in GATE_FAIL.finditer(run["report"] or ""))
    gates = [{"gate": gate, "failures": failures}
             for gate, failures in sorted(gate_failures.items(), key=lambda item: (-item[1], item[0]))]

    # First seen is deliberately independent of both the window and the plan filter.
    first_seen = {}
    for run in runs:
        if run["model"] is None:
            continue
        key = _group_key(run)
        started = _started(run)
        if key not in first_seen or started < first_seen[key]:
            first_seen[key] = started

    groups = {}
    for run in window_runs:
        if run["model"] is not None:
            groups.setdefault(_group_key(run), []).append(run)
    steps = []
    for key, rs in groups.items():
        flow, step, model, version = key
        outcomes = Counter((r["outcome"] or "running") for r in rs)
        steps.append({
            "flow": flow or "-",
            "step": step,
            "model": model,
            "version": version or "-",
            "runs": len(rs),
            "calls": round(sum(r["steps"] or 0 for r in rs) / len(rs), 1),
            "stops": sum(_is_stop(r) for r in rs),
            "refused": sum(r["refused"] or 0 for r in rs),
            "cost_usd": round(sum(r["cost_usd"] or 0 for r in rs), 2),
            "outcomes": _sorted_counts(outcomes),
            "first_seen": first_seen[key].date().isoformat(),
        })
    steps.sort(key=lambda row: (row["flow"], row["step"], row["model"], row["first_seen"], row["version"]))

    summary = {
        "tasks": len(selected_tasks),
        "prs_opened": len(pr_ids),
        "merged": len(merged_ids),
        "failed": sum(task["status"] == "failed" for task in selected_tasks),
        "first_attempt_pass_rate": _rate_data(len(passed_first), len(build_ids)),
        "attempts_per_pr": {
            "mean": round(sum(attempts) / len(attempts), 1) if attempts else None,
            "prs": len(attempts),
        },
        "cost_per_merged_pr": {
            "mean_usd": round(priced_cost / priced_merged, 2) if priced_merged else None,
            "priced_merged": priced_merged,
            "unpriced_merged": unpriced_merged,
        },
        "reviewer_changes_rate": _rate_data(changes, len(review_runs)),
        "step_limit_stops": _sorted_counts(stops),
        "reworks": reworks,
        "human_edits": _rate_data(edited, len(merge_runs)),
    }
    return {
        "window": {"since": since, "until": until, "plan": plan},
        "summary": summary,
        "gates": gates,
        "steps": steps,
    }


def _rate_text(data: dict) -> str:
    if data["rate"] is None:
        return "-"
    return f"{100 * data['numerator'] / data['denominator']:.0f}% ({data['numerator']}/{data['denominator']})"


def _percent(data: dict) -> str:
    if data["rate"] is None:
        return "-"
    return f"{100 * data['numerator'] / data['denominator']:.0f}%"


def render(data: dict) -> str:
    """Render the same summary, gates and steps returned by collect as plain tables."""
    window = data["window"]
    summary = data["summary"]
    heading = f"window: {window['since'] or 'beginning'} → {window['until'] or 'now'}"
    if window["plan"] is not None:
        heading += f" · plan {window['plan']}"
    heading += (f" · {summary['tasks']} tasks · {summary['prs_opened']} PRs · {summary['merged']} merged"
                f" · {summary['failed']} failed")

    attempts = summary["attempts_per_pr"]
    attempts_text = f"{attempts['mean']:.1f}" if attempts["mean"] is not None else "-"
    cost_data = summary["cost_per_merged_pr"]
    cost_text = f"${cost_data['mean_usd']:.2f}" if cost_data["mean_usd"] is not None else "-"
    if cost_data["unpriced_merged"]:
        cost_text += f" · {cost_data['unpriced_merged']} merged with unpriced runs"
    reworks = " · ".join(f"{kind} {_percent(summary['reworks'][kind])}"
                          for kind in ("conflict", "ci", "review"))
    stops = summary["step_limit_stops"]
    stops_text = " · ".join(f"{step} {count}" for step, count in
                             sorted(stops.items(), key=lambda item: (-item[1], item[0]))) or "-"
    out = [
        heading,
        "",
        f"{'first-attempt pass rate':<26}{_rate_text(summary['first_attempt_pass_rate']):<16}"
        f"{'reviewer CHANGES rate':<24}{_rate_text(summary['reviewer_changes_rate'])}",
        f"{'attempts per PR':<26}{attempts_text:<16}{'human edits':<24}{_rate_text(summary['human_edits'])}",
        f"{'cost per merged PR':<26}{cost_text:<16}{'reworks':<24}{reworks}",
        f"{'step-limit stops':<26}{stops_text}",
        "",
        f"{'gate':<14}failures",
    ]
    if data["gates"]:
        out += [f"{row['gate']:<14}{row['failures']}" for row in data["gates"]]
    else:
        out.append("no failed gates")

    out += [
        "",
        f"{'flow':<9}{'step':<8}{'model':<25}{'version':<14}{'runs':<6}{'calls':<7}{'stops':<7}"
        f"{'refused':<9}{'cost':<7}{'outcomes':<24}first seen",
    ]
    if not data["steps"]:
        out.append("no agent runs in the window")
    for row in data["steps"]:
        outcomes = " · ".join(f"{outcome} {count}" for outcome, count in row["outcomes"].items())
        out.append(
            f"{row['flow']:<9}{row['step']:<8}{row['model']:<25}{row['version']:<14}{row['runs']:<6}"
            f"{row['calls']:<7.1f}{row['stops']:<7}{row['refused']:<9}{('$%.2f' % row['cost_usd']):<7}"
            f"{outcomes:<24}{row['first_seen']}"
        )
    return "\n".join(out)
