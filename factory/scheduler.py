"""Run many tasks from one command: `factory run --ready --parallel N [--watch]`.

The scheduler is a small supervisor loop. Each task runs in its own child
`factory run <task> --quiet` process (own sandbox, log, transcript, pid
liveness), so one crash never takes the others down and `factory top` shows
them all. With --watch it also polls GitHub for merged PRs and starts the
tasks whose dependencies just merged.

Failed tasks are never retried on their own; `factory retry` puts them back
to queued and a running scheduler starts them again. Live runs it did not
start (an earlier scheduler, a single `factory run`) count toward --parallel,
so restarting the scheduler never doubles the load.
"""

from __future__ import annotations

import datetime as dt
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .db import ACTIVE, DB, pid_alive, seconds_since
from .observe import human_secs


@dataclass
class Plan:
    tasks: list[str]                       # explicit task ids ([] = every ready task with --ready)
    ready: bool
    parallel: int = 3
    watch: bool = False
    budget: float | None = None            # stop launching once this much USD was spent by this scheduler
    poll: float = 5.0
    refresh_every: float = 60.0
    network_for: tuple[str, ...] = ()      # task ids that get --network
    child_args: list[str] = field(default_factory=list)   # flags passed through to every child run


def say(msg: str) -> None:
    print(f"{dt.datetime.now():%H:%M:%S} {msg}", flush=True)


def default_launch(repo: Path) -> Callable[[str, list[str]], subprocess.Popen]:
    def launch(task_id: str, args: list[str]) -> subprocess.Popen:
        return subprocess.Popen([sys.executable, "-m", "factory.cli", "run", task_id, "--quiet", *args],
                                cwd=repo, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.PIPE, start_new_session=True, text=True)
    return launch


def blocked(running: dict, results: dict[str, str]) -> set[str]:
    """Not to be launched: running now, or ended still `queued` (refused before it started, e.g. an invalid
    contract; launching it again would loop). A task that ended failed and is queued again was requeued
    by `factory retry`, so it may start again."""
    return set(running) | {t for t, status in results.items() if status == "queued"}


def candidates(db: DB, plan: Plan, skip: set[str]) -> list[str]:
    """Tasks that may start now: queued, dependencies merged, not in `skip`."""
    pool = plan.tasks or ([r["id"] for r in db.tasks()] if plan.ready else [])
    out = []
    for tid in pool:
        row = db.task(tid)
        if row is None or tid in skip or row["status"] != "queued":
            continue
        if db.readiness(tid) == "ready":
            out.append(tid)
    return out


def pending(db: DB, plan: Plan, skip: set[str]) -> list[str]:
    """Explicit tasks not started yet (still waiting for dependencies)."""
    return [t for t in plan.tasks if t not in skip and (db.task(t) or {"status": None})["status"] == "queued"]


def elsewhere(db: DB, running: dict) -> list[str]:
    """Live runs this scheduler did not start; they count toward --parallel."""
    return [r["id"] for r in db.tasks() if r["status"] in ACTIVE and r["id"] not in running and pid_alive(r["pid"])]


def run(db: DB, plan: Plan, launch: Callable[[str, list[str]], subprocess.Popen],
        refresh: Callable[[DB], None], clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep) -> dict[str, str]:
    """Supervise until nothing is running and nothing more can start (or forever with --watch).
    Returns {task_id: final status} for every task this scheduler started."""
    running: dict[str, tuple[subprocess.Popen, float]] = {}
    results: dict[str, str] = {}
    spent_at_start = sum(r["cost_usd"] or 0 for r in db.tasks())
    last_refresh = clock() - plan.refresh_every
    stopped_for_budget = False
    say(f"scheduler: parallel {plan.parallel}" + (", watching for merges" if plan.watch else "")
        + (f", budget ${plan.budget:.2f}" if plan.budget is not None else "")
        + " — follow with `factory top`")
    others = elsewhere(db, running)
    if others:
        say(f"{len(others)} run(s) already in progress count toward --parallel: " + ", ".join(others))
    try:
        while True:
            # Reap finished children.
            for tid, (proc, t0) in list(running.items()):
                if proc.poll() is None:
                    continue
                del running[tid]
                row = db.task(tid)
                results[tid] = row["status"]
                extra = row["pr_url"] if row["status"] == "pr_open" else (row["note"] or "").splitlines()[0][:140] if row["note"] else ""
                if proc.returncode not in (0, 1) and not extra:
                    extra = (proc.stderr.read() if proc.stderr else "")[-300:].strip()
                cost = f" ${row['cost_usd']:.2f}" if row["cost_usd"] is not None else ""
                say(f"done   {tid:<32} {row['status']:<9} {human_secs(clock() - t0)}{cost}  {extra}")

            # Pick up merges so dependents become ready.
            if plan.watch and clock() - last_refresh >= plan.refresh_every:
                before = {r["id"]: r["status"] for r in db.tasks()}
                refresh(db)
                last_refresh = clock()
                for r in db.tasks():
                    if before.get(r["id"]) != r["status"] and r["status"] in ("merged", "abandoned"):
                        say(f"{r['status']:<6} {r['id']}")

            # Budget: stop launching (running tasks continue; per-task --max-cost still applies).
            spent = sum(r["cost_usd"] or 0 for r in db.tasks()) - spent_at_start
            if plan.budget is not None and spent >= plan.budget and not stopped_for_budget:
                stopped_for_budget = True
                say(f"budget reached (${spent:.2f} of ${plan.budget:.2f}); not starting more tasks")

            # Launch.
            if not stopped_for_budget:
                others = elsewhere(db, running)
                free = max(0, plan.parallel - len(running) - len(others))
                for tid in candidates(db, plan, blocked(running, results))[:free]:
                    args = list(plan.child_args) + (["--network"] if tid in plan.network_for else [])
                    running[tid] = (launch(tid, args), clock())
                    say(f"start  {tid:<32} ({len(running) + len(others)}/{plan.parallel} running)")

            if not running and not plan.watch:
                skip = blocked(running, results)
                ready_now = [] if stopped_for_budget else candidates(db, plan, skip)
                if not (ready_now and elsewhere(db, running)):    # else: runs started elsewhere hold every slot
                    waiting = pending(db, plan, skip)
                    if waiting and stopped_for_budget:
                        say("not started (budget reached): " + ", ".join(waiting))
                    elif waiting:
                        say("waiting on unmerged dependencies: " + ", ".join(waiting) + " (use --watch to keep going)")
                    break
            sleep(plan.poll)
    except KeyboardInterrupt:
        if running:
            say(f"scheduler stopped; {len(running)} run(s) continue in the background: " + ", ".join(running))
    return results


def summary(db: DB, results: dict[str, str]) -> str:
    if not results:
        return "nothing was started (no ready tasks — `factory sync`, then `factory status`)"
    lines = []
    for tid, status in sorted(results.items()):
        row = db.task(tid)
        cost = f"${row['cost_usd']:.2f}" if row["cost_usd"] is not None else "-"
        lines.append(f"  {tid:<32} {status:<9} {cost:>7}  {row['pr_url'] or ''}")
    total = sum(db.task(t)["cost_usd"] or 0 for t in results)
    return "\n".join([f"{len(results)} task(s), ${total:.2f}:"] + lines)
