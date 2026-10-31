"""Run a whole plan: `factory run <plan> [--parallel N]`.

Every task of the plan without a PR yet runs as its own child `factory run <task> --quiet` process
(own worktree, sandbox, log, transcript, pid liveness), so one crash never takes the others down and
`factory top` shows them all. A task starts once each dependency is merged or has an open PR; the
child then builds it on top of those PRs (stacked, see stack.py). Independent tasks run in parallel,
up to --parallel. The run ends when nothing more can start, leaving one PR per finished task.

Rerunning the plan picks up where it stopped: tasks with a PR are kept, failed ones run again, and PRs
that conflict with their base (`conflict`, found by the refresh the plan run starts with) get their
conflicts resolved.
"""

from __future__ import annotations

import datetime as dt
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .db import ACTIVE, DB, pid_alive
from .observe import counts, human_secs, strip


@dataclass
class Plan:
    name: str
    tasks: list[str]                       # the plan's task ids, in dependency order
    parallel: int = 3
    poll: float = 5.0
    network_for: tuple[str, ...] = ()      # task ids that get --network
    child_args: list[str] = field(default_factory=list)   # flags passed through to every child run
    manual: dict[str, str] = field(default_factory=dict)  # task id -> why the factory cannot run it


def say(msg: str) -> None:
    print(f"{dt.datetime.now():%H:%M:%S} {msg}", flush=True)


def default_launch(repo: Path) -> Callable[[str, list[str]], subprocess.Popen]:
    def launch(task_id: str, args: list[str]) -> subprocess.Popen:
        return subprocess.Popen([sys.executable, "-m", "factory.cli", "run", task_id, "--quiet", *args],
                                cwd=repo, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.PIPE, start_new_session=True, text=True)
    return launch


def startable(db: DB, plan: Plan, tid: str, started: set[str]) -> bool:
    """No PR yet (or one that conflicts), not running, not started by this run, and every dependency merged
    or with an open PR. A task that failed in an earlier run starts again; one that fails in this run does not."""
    row = db.task(tid)
    return (row is not None and tid not in started and tid not in plan.manual
            and row["status"] in ("queued", "failed", "conflict") and db.ready(tid))


def elsewhere(db: DB, plan: Plan, running: dict) -> list[str]:
    """Tasks of the plan being run by another `factory run`; their dependents wait for them."""
    return [t for t in plan.tasks if t not in running
            and (r := db.task(t)) is not None and r["status"] in ACTIVE and pid_alive(r["pid"])]


def run(db: DB, plan: Plan, launch: Callable[[str, list[str]], subprocess.Popen],
        clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep) -> dict[str, str]:
    """Supervise until nothing is running and nothing more can start.
    Returns {task_id: final status} for every task this run started."""
    running: dict[str, tuple[subprocess.Popen, float]] = {}
    results: dict[str, str] = {}
    say(f"plan {plan.name}: {len(plan.tasks)} tasks, up to {plan.parallel} at once — follow with `factory top`")
    try:
        while True:
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

            free = max(0, plan.parallel - len(running))
            for tid in [t for t in plan.tasks if startable(db, plan, t, set(running) | set(results))][:free]:
                args = list(plan.child_args) + (["--network"] if tid in plan.network_for else [])
                running[tid] = (launch(tid, args), clock())
                stacks = db.deps(db.contract(tid))[0]
                say(f"start  {tid:<32} ({len(running)}/{plan.parallel} running)"
                    + (f" stacked on {', '.join(stacks)}" if stacks else ""))

            if not running and not elsewhere(db, plan, running):
                break
            sleep(plan.poll)
    except KeyboardInterrupt:
        if running:
            say(f"stopped; {len(running)} run(s) continue in the background: " + ", ".join(running))
    return results


def summary(db: DB, plan: Plan) -> str:
    """Where every task of the plan ended up, and the PRs to review in merge order."""
    rows = [db.task(t) for t in plan.tasks]
    total = sum(r["cost_usd"] or 0 for r in rows)
    lines = [f"plan {plan.name}  {strip(db, rows)}  {counts(db, rows)} · ${total:.2f}"]
    for r in rows:
        st = r["status"]
        if r["id"] in plan.manual and st not in ("pr_open", "merged"):
            what = f"manual: {plan.manual[r['id']]}"
        elif st == "pr_open":
            what = r["pr_url"] + (f"  stacked on {r['stacked_on']}" if r["stacked_on"] else "")
        elif st == "conflict":
            what = f"{r['pr_url']}  {(r['note'] or '').splitlines()[0][:140] if r['note'] else ''}"
        elif st in ("queued", "failed"):
            what = db.readiness(r["id"]) if st == "queued" else (r["note"] or "").splitlines()[0][:140] if r["note"] else ""
        else:
            what = (r["note"] or "").splitlines()[0][:140] if st == "abandoned" and r["note"] else ""
        cost = f"${r['cost_usd']:.2f}" if r["cost_usd"] is not None else "-"
        lines.append(f"  {r['id']:<34} {st:<9} {cost:>7}  {what}")
    prs = [r["pr_url"] for r in rows if r["status"] == "pr_open"]
    if prs:
        lines += ["", "review and merge in this order (a stacked PR targets the one before it; after each merge, "
                      "`factory status --refresh` moves the next onto the trunk):"]
        lines += [f"  {u}" for u in prs]
    return "\n".join(lines)
