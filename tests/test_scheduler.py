"""One plan, one run, one PR per task: the plan scheduler."""

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
  non_goals: []
  acceptance: ["Third thing done"]
  verification: ["true"]
  risk: low
"""
IDS = ["demo-t01", "demo-t02", "demo-t03"]


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
        pr = self.status == "pr_open"
        self.db.update(self.tid, status=self.status, cost_usd=self.cost, candidate_sha=f"sha-{self.tid}" if pr else None,
                       pr_url=f"https://github.test/{self.tid}" if pr else None)
        self.returncode = 0
        return 0


@pytest.fixture
def db(tmp_path):
    d = open_db(tmp_path)
    d.sync({t.id: t for t in parse_text(plan_text(THREE), "docs/plans/demo/demo.md")})
    return d


def _run(db, plan, outcomes=None, ticks=2, cost=0.5, max_loops=60, on_loop=lambda n: None):
    launched, peak = [], [0]
    loops = [0]

    def launch(tid, args):
        launched.append((tid, args))
        return FakeProc(db, tid, (outcomes or {}).get(tid, "pr_open"), ticks, cost)

    def sleep(_):
        loops[0] += 1
        on_loop(loops[0])
        peak[0] = max(peak[0], sum(1 for r in db.tasks() if r["status"] == "building"))
        if loops[0] > max_loops:
            raise KeyboardInterrupt

    results = scheduler.run(db, plan, launch, clock=lambda: loops[0] * 10.0, sleep=sleep)
    return results, launched, peak[0]


def test_one_run_gives_a_pr_per_task_with_dependents_stacked(db, capsys):
    results, launched, peak = _run(db, scheduler.Plan(name="demo", tasks=IDS, parallel=1))
    assert [t for t, _ in launched] == ["demo-t01", "demo-t02", "demo-t03"]   # t02 starts on t01's open PR
    assert peak == 1
    assert results == {t: "pr_open" for t in IDS}
    out = capsys.readouterr().out
    assert "start  demo-t02" in out and "stacked on demo-t01" in out and "https://github.test/demo-t03" in out
    summary = scheduler.summary(db, scheduler.Plan(name="demo", tasks=IDS))
    assert summary.splitlines()[0] == "plan demo  ◆◆◆  0/3 merged · 3 PR open · $1.50"
    assert summary.index("https://github.test/demo-t01\n") < summary.index("https://github.test/demo-t02\n")


def test_independent_tasks_run_in_parallel(db):
    _, launched, peak = _run(db, scheduler.Plan(name="demo", tasks=IDS, parallel=3))
    assert [t for t, _ in launched][:2] == ["demo-t01", "demo-t03"] and peak == 2


def test_a_failure_blocks_only_its_dependents(db):
    results, launched, _ = _run(db, scheduler.Plan(name="demo", tasks=IDS, parallel=2), outcomes={"demo-t01": "failed"})
    assert results == {"demo-t01": "failed", "demo-t03": "pr_open"}
    summary = scheduler.summary(db, scheduler.Plan(name="demo", tasks=IDS))
    assert "demo-t02" in summary and "waits for demo-t01 (failed)" in summary


def test_rerun_keeps_prs_and_holds_and_retries_failures_once(db):
    db.update("demo-t03", status="pr_open", candidate_sha="x", pr_url="u")
    db.update("demo-t02", status="abandoned", note="hold")
    db.update("demo-t01", status="failed", note="earlier run")
    results, launched, _ = _run(db, scheduler.Plan(name="demo", tasks=IDS), outcomes={"demo-t01": "failed"})
    assert [t for t, _ in launched] == ["demo-t01"] and results == {"demo-t01": "failed"}   # not looped


def test_manual_tasks_are_reported_not_run(db):
    plan = scheduler.Plan(name="demo", tasks=IDS, manual={"demo-t03": "no e2e path; run it by hand"})
    _, launched, _ = _run(db, plan)
    assert "demo-t03" not in [t for t, _ in launched]
    assert "manual: no e2e path; run it by hand" in scheduler.summary(db, plan)


def test_dependents_wait_for_a_dependency_running_elsewhere(db):
    db.update("demo-t01", status="building")
    db.claim("demo-t01", os.getpid())                 # live, started by another `factory run`

    def finish(n):
        if n == 3:
            db.update("demo-t01", status="pr_open", candidate_sha="sha", pr_url="u")
    _, launched, _ = _run(db, scheduler.Plan(name="demo", tasks=IDS, parallel=3), on_loop=finish)
    assert [t for t, _ in launched] == ["demo-t03", "demo-t02"]


def test_network_and_flags_pass_through_to_children(db):
    plan = scheduler.Plan(name="demo", tasks=IDS, parallel=2, network_for=("demo-t03",),
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


def test_a_pr_with_conflicts_runs_again_to_resolve_them(db):
    db.update("demo-t03", status="conflict", candidate_sha="x", pr_url="u", note="its PR conflicts with main")
    db.update("demo-t01", status="pr_open", candidate_sha="y", pr_url="v")
    results, launched, _ = _run(db, scheduler.Plan(name="demo", tasks=IDS))
    assert [t for t, _ in launched] == ["demo-t02", "demo-t03"] and results["demo-t03"] == "pr_open"
