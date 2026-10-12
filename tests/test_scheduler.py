"""One factory, many agent loops: the scheduler that runs tasks in parallel."""

import os

import pytest

from factory import scheduler
from factory.contracts import parse_text
from factory.db import open_db
from conftest import TASK, plan_text

THREE = TASK + """- id: demo-t03
  goal: "An independent third thing"
  spec_refs: []
  depends_on: []
  allowed_paths: ["crates/e2e/tests/t3.rs"]
  non_goals: []
  acceptance: ["Third thing done"]
  verification: ["true"]
  risk: low
"""


class FakeProc:
    """A child run that finishes after `ticks` polls and leaves `status` (and cost) in the db."""
    def __init__(self, db, tid, status, ticks, cost):
        self.db, self.tid, self.status, self.ticks, self.cost = db, tid, status, ticks, cost
        self.returncode = None
        self.stderr = None
        db.update(tid, status="building")

    def poll(self):
        self.ticks -= 1
        if self.ticks > 0:
            return None
        self.db.update(self.tid, status=self.status, cost_usd=self.cost,
                       pr_url=f"https://github.test/{self.tid}" if self.status == "pr_open" else None)
        self.returncode = 0
        return 0


@pytest.fixture
def db(tmp_path):
    d = open_db(tmp_path)
    d.sync({t.id: t for t in parse_text(plan_text(THREE), "docs/plans/demo/demo.md")})
    return d


def _run(db, plan, outcomes=None, ticks=2, cost=0.5, max_loops=60, refresh=lambda db: None):
    launched, peak = [], [0]
    loops = [0]

    def launch(tid, args):
        launched.append((tid, args))
        return FakeProc(db, tid, (outcomes or {}).get(tid, "pr_open"), ticks, cost)

    def sleep(_):
        loops[0] += 1
        peak[0] = max(peak[0], sum(1 for r in db.tasks() if r["status"] == "building"))
        if loops[0] > max_loops:
            raise KeyboardInterrupt

    results = scheduler.run(db, plan, launch, refresh, clock=lambda: loops[0] * 10.0, sleep=sleep)
    return results, launched, peak[0]


def test_ready_runs_every_ready_task_within_the_parallel_cap(db, capsys):
    results, launched, peak = _run(db, scheduler.Plan(tasks=[], ready=True, parallel=1))
    assert [t for t, _ in launched] == ["demo-t01", "demo-t03"]       # demo-t02 waits for demo-t01's merge
    assert peak == 1
    assert results == {"demo-t01": "pr_open", "demo-t03": "pr_open"}
    out = capsys.readouterr().out
    assert "start  demo-t01" in out and "done   demo-t03" in out and "https://github.test/demo-t03" in out


def test_watch_starts_dependents_when_their_dependency_merges(db, capsys):
    def refresh(d):
        if d.task("demo-t01")["status"] == "pr_open":
            d.update("demo-t01", status="merged")         # a human merged the PR
    results, launched, _ = _run(db, scheduler.Plan(tasks=[], ready=True, parallel=3, watch=True, refresh_every=10),
                                refresh=refresh)
    assert [t for t, _ in launched] == ["demo-t01", "demo-t03", "demo-t02"]
    assert results["demo-t02"] == "pr_open"
    assert "merged demo-t01" in capsys.readouterr().out


def test_explicit_tasks_without_watch_report_unmerged_dependencies(db, capsys):
    results, launched, _ = _run(db, scheduler.Plan(tasks=["demo-t01", "demo-t02"], ready=False, parallel=2))
    assert [t for t, _ in launched] == ["demo-t01"]
    assert "waiting on unmerged dependencies: demo-t02" in capsys.readouterr().out


def test_budget_stops_new_launches(db, capsys):
    results, launched, _ = _run(db, scheduler.Plan(tasks=[], ready=True, parallel=1, budget=0.4), cost=0.5)
    assert [t for t, _ in launched] == ["demo-t01"]
    assert "budget reached ($0.50 of $0.40)" in capsys.readouterr().out


def test_failures_are_reported_and_do_not_stop_others(db, capsys):
    results, _, _ = _run(db, scheduler.Plan(tasks=[], ready=True, parallel=2), outcomes={"demo-t01": "failed"})
    assert results == {"demo-t01": "failed", "demo-t03": "pr_open"}


def test_a_requeued_task_runs_again_but_a_refused_one_does_not(db):
    requeues = []

    def refresh(d):          # `factory retry demo-t01` while the scheduler watches
        if d.task("demo-t01")["status"] == "failed" and not requeues:
            requeues.append(1)
            d.update("demo-t01", status="queued")
    _, launched, _ = _run(db, scheduler.Plan(tasks=[], ready=True, parallel=3, watch=True, refresh_every=10),
                          outcomes={"demo-t01": "failed", "demo-t03": "queued"}, refresh=refresh, max_loops=30)
    assert [t for t, _ in launched].count("demo-t01") == 2       # failed, requeued, started again
    assert [t for t, _ in launched].count("demo-t03") == 1       # ended still queued (refused): never looped


def test_runs_started_elsewhere_count_toward_parallel(db, capsys):
    db.update("demo-t03", status="building")
    db.claim("demo-t03", os.getpid())                 # live, but not started by this scheduler
    launched, loops = [], [0]

    def launch(tid, args):
        launched.append((tid, loops[0]))
        return FakeProc(db, tid, "pr_open", 1, 0.1)

    def sleep(_):
        loops[0] += 1
        if loops[0] == 3:
            db.update("demo-t03", status="pr_open")   # the other run finishes, freeing the only slot
        if loops[0] > 20:
            raise KeyboardInterrupt

    results = scheduler.run(db, scheduler.Plan(tasks=[], ready=True, parallel=1), launch, lambda d: None,
                            clock=lambda: loops[0] * 10.0, sleep=sleep)
    assert launched == [("demo-t01", 3)] and results == {"demo-t01": "pr_open"}
    assert "1 run(s) already in progress count toward --parallel: demo-t03" in capsys.readouterr().out


def test_network_and_flags_pass_through_to_children(db):
    plan = scheduler.Plan(tasks=[], ready=True, parallel=2, network_for=("demo-t03",),
                          child_args=["--max-attempts", "2", "--max-cost", "3.0"])
    _, launched, _ = _run(db, plan)
    args = dict(launched)
    assert args["demo-t01"] == ["--max-attempts", "2", "--max-cost", "3.0"]
    assert args["demo-t03"] == ["--max-attempts", "2", "--max-cost", "3.0", "--network"]


def test_default_launch_runs_quiet_child_factory(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(scheduler.subprocess, "Popen", lambda argv, **kw: seen.update(argv=argv, kw=kw))
    scheduler.default_launch(tmp_path)("demo-t01", ["--network"])
    assert seen["argv"][1:] == ["-m", "factory.cli", "run", "demo-t01", "--quiet", "--network"]
    assert seen["kw"]["cwd"] == tmp_path and seen["kw"]["start_new_session"] is True
