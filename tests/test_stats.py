"""factory stats: board-only task, gate and per-step measurements."""

import json

import pytest

from factory import gates as G
from factory import stats
from factory.cli import main
from factory.db import open_db

PLAN = "docs/plans/demo/demo.md"
AT = "2026-11-02T12:00:00+00:00"
UNSET = object()


@pytest.fixture
def db(tmp_path):
    d = open_db(tmp_path)
    yield d
    d.close()


def _task(db, tid, status="queued", plan=PLAN):
    db.conn.execute(
        "INSERT INTO tasks (id, plan, contract, status, updated_at) VALUES (?, ?, ?, ?, ?)",
        (tid, plan, "{}", status, "2026-01-01T00:00:00+00:00"))
    db.conn.commit()


def _run(db, tid, role, attempt, outcome, at=AT, *, model=None, flow=None, step=None,
         version=None, cost=UNSET, steps=0, refused=0, report=""):
    run_id = db.start_run(tid, role, attempt, model, flow, step)
    if cost is not UNSET or steps or refused:
        db.progress(tid, run_id, role, steps, 0, 0,
                    cost_usd=None if cost is UNSET else cost, refused=refused)
    db.finish_run(run_id, outcome, report)
    db.conn.execute("UPDATE runs SET started_at=?, prompt_version=? WHERE id=?", (at, version, run_id))
    db.conn.commit()
    return run_id


def test_first_attempt_pass_rate_and_attempts_per_pr(db):
    for tid in ("a", "b", "c", "d"):
        _task(db, tid)
    _run(db, "a", "build", 1, "committed")
    _run(db, "a", "pr", 1, "opened")

    _run(db, "b", "build", 1, "committed")
    _run(db, "b", "build", 2, "committed")
    _run(db, "b", "pr", 2, "opened")
    _run(db, "b", "pr", 1, "opened")       # a later rework is not the task's first opened PR

    _run(db, "c", "build", 1, "committed")
    _run(db, "d", "pr", 1, "closed")       # no build: outside the pass-rate denominator

    summary = stats.collect(db)["summary"]
    assert summary["first_attempt_pass_rate"] == {"rate": 1 / 3, "numerator": 1, "denominator": 3}
    assert summary["attempts_per_pr"] == {"mean": 1.5, "prs": 2}


def test_cost_per_merged_pr_counts_every_run_of_merged_tasks(db):
    _task(db, "m1", status="merged")
    _run(db, "m1", "plan", 0, "planned", model="m", cost=0.10)
    _run(db, "m1", "build", 1, "committed", model="m", cost=0.50)
    _run(db, "m1", "review", 1, "APPROVE", model="m", cost=0.05)
    _run(db, "m1", "verify", 1, "pass", model="m", cost=0.25)
    _run(db, "m1", "verify", 1, "fail")                 # the non-agent gates run is never priced
    _run(db, "m1", "pr", 1, "opened")
    _run(db, "m1", "merge", 0, "as_built")

    _task(db, "m2", status="merged")
    _run(db, "m2", "build", 1, "committed", model="m", cost=0.30)
    _run(db, "m2", "review", 1, "APPROVE", model="m", cost=None)

    _task(db, "f1", status="failed")
    _run(db, "f1", "build", 1, "failed", model="m", cost=5.0)

    summary = stats.collect(db)["summary"]
    assert summary["merged"] == 2
    assert summary["cost_per_merged_pr"] == {
        "mean_usd": pytest.approx(0.90), "priced_merged": 1, "unpriced_merged": 1,
    }


def test_gate_failures_are_counted_by_gate(db):
    _task(db, "task")
    report = G.table([G.Gate("session_log", False, "missing"), G.Gate("verification", True, "ok")])
    _run(db, "task", "verify", 1, "fail", "2026-11-02T00:00:00+00:00", report=report)
    handwritten = """| Gate | Result | Detail |
|---|---|---|
| session_log | FAIL | no entry |
| unit_tests | FAIL | 2 failed |
"""
    _run(db, "task", "verify", 2, "fail", "2026-11-03T00:00:00+00:00", report=handwritten)
    _run(db, "task", "verify", 3, "pass", "2026-11-04T00:00:00+00:00",
         report="| ignored | FAIL | a passing run is not counted |")
    _run(db, "task", "verify", 4, "fail", "2026-11-05T00:00:00+00:00", report="not a gate table")
    _run(db, "task", "verify", 5, "fail", "2026-10-05T00:00:00+00:00",
         report="| session_log | FAIL | outside the window |")

    assert stats.collect(db, since="2026-11-01")["gates"] == [
        {"gate": "session_log", "failures": 2},
        {"gate": "unit_tests", "failures": 1},
    ]


def test_step_rows_split_by_flow_model_and_prompt_version(db):
    _task(db, "task")
    _run(db, "task", "build", 1, "committed (step limit)", "2026-11-02T00:00:00+00:00",
         model="a/one", flow="default", step="build", version="v1", steps=10, cost=1.0)
    _run(db, "task", "build", 2, "committed", "2026-11-03T00:00:00+00:00",
         model="a/one", flow="default", step="build", version="v1", steps=30, cost=2.0, refused=2)
    _run(db, "task", "build", 1, "committed", "2026-11-04T00:00:00+00:00",
         model="a/one", flow="default", step="build", version="v2", steps=5, cost=0.0)
    _run(db, "task", "build", 1, "committed", "2026-11-05T00:00:00+00:00",
         model="b/two", flow="default", step="build", version="v1", steps=5, cost=0.0)
    _run(db, "task", "build", 1, "committed", "2026-11-06T00:00:00+00:00",
         model="a/one", flow="other", step="build", version="v1", steps=5, cost=0.0)
    _run(db, "task", "build", 1, "committed", "2026-11-07T00:00:00+00:00",
         model="old", steps=5, cost=0.0)
    _run(db, "task", "build", 1, "committed", "2026-11-08T00:00:00+00:00",
         model="a/one", flow="default", step="build", steps=5, cost=0.0)
    _run(db, "task", "verify", 1, "fail", "2026-11-09T00:00:00+00:00", flow="default", step="gates")
    _run(db, "task", "build", 1, "committed", "2026-10-05T00:00:00+00:00",
         model="a/one", flow="default", step="build", version="v1", steps=99, cost=20.0)

    data = stats.collect(db, since="2026-11-01")
    keys = [(row["flow"], row["step"], row["model"], row["version"]) for row in data["steps"]]
    assert keys == [
        ("-", "build", "old", "-"),
        ("default", "build", "a/one", "v1"),
        ("default", "build", "a/one", "v2"),
        ("default", "build", "a/one", "-"),
        ("default", "build", "b/two", "v1"),
        ("other", "build", "a/one", "v1"),
    ]
    v1 = next(row for row in data["steps"] if row["version"] == "v1" and row["flow"] == "default"
              and row["model"] == "a/one")
    assert v1 == {
        "flow": "default", "step": "build", "model": "a/one", "version": "v1",
        "runs": 2, "calls": 20.0, "stops": 1, "refused": 2, "cost_usd": pytest.approx(3.0),
        "outcomes": {"committed": 1, "committed (step limit)": 1}, "first_seen": "2026-10-05",
    }
    assert data["summary"]["step_limit_stops"] == {"build": 1}


def test_reworks_and_human_edits_are_rates_over_prs(db):
    _task(db, "p1", status="merged")
    _run(db, "p1", "pr", 1, "opened", "2026-11-01T00:00:00+00:00")
    _run(db, "p1", "resolve", 1, "committed", "2026-11-02T00:00:00+00:00")
    _run(db, "p1", "ci", 1, "committed", "2026-11-02T01:00:00+00:00")
    _run(db, "p1", "human_review", 1, "committed", "2026-11-02T02:00:00+00:00")
    _run(db, "p1", "merge", 0, "edited", "2026-11-03T00:00:00+00:00")

    _task(db, "p2", status="merged")
    _run(db, "p2", "pr", 1, "opened", "2026-11-02T00:00:00+00:00")
    _run(db, "p2", "merge", 0, "as_built", "2026-11-10T00:00:00+00:00")

    _task(db, "p3", status="failed")
    _run(db, "p3", "resolve", 1, "failed", "2026-11-02T00:00:00+00:00")

    summary = stats.collect(db, until="2026-11-05")["summary"]
    assert summary["prs_opened"] == 2
    for kind in ("conflict", "ci", "review"):
        assert summary["reworks"][kind] == {"rate": 0.5, "numerator": 1, "denominator": 2}
    assert summary["human_edits"] == {"rate": 1.0, "numerator": 1, "denominator": 1}
    assert stats.collect(db)["summary"]["human_edits"] == {"rate": 0.5, "numerator": 1, "denominator": 2}


def test_the_window_and_plan_filters_select_runs(db):
    _task(db, "a")
    _run(db, "a", "build", 1, "committed", "2026-11-01T00:00:00+00:00")
    _run(db, "a", "review", 1, "APPROVE", "2026-11-05T00:00:00+00:00")
    _task(db, "b")
    _run(db, "b", "build", 1, "committed", "2026-10-15T00:00:00+00:00")
    _task(db, "c", plan="docs/plans/other/other.md")
    _run(db, "c", "build", 1, "committed", "2026-11-03T23:59:59+00:00")
    _task(db, "d")

    assert stats.collect(db)["summary"]["tasks"] == 3
    assert stats.collect(db, since="2026-11-01")["summary"]["tasks"] == 2
    assert stats.collect(db, until="2026-11-01")["summary"]["tasks"] == 1
    assert stats.collect(db, since="2026-11-01", until="2026-11-04")["summary"]["tasks"] == 2
    assert stats.collect(db, plan="demo")["summary"]["tasks"] == 2
    assert stats.collect(db, plan=PLAN)["summary"]["tasks"] == 2
    assert stats.collect(db, plan="other")["summary"]["tasks"] == 1


def test_stats_command_prints_tables_and_json(home, capsys):
    db = open_db(home)
    _task(db, "t1", status="merged")
    _run(db, "t1", "build", 1, "committed", "2026-11-01T01:00:00+00:00",
         model="m", flow="default", step="build", version="v1", steps=4, cost=0.5)
    _run(db, "t1", "pr", 1, "opened", "2026-11-01T02:00:00+00:00")
    _run(db, "t1", "verify", 1, "fail", "2026-11-01T03:00:00+00:00",
         report="| session_log | FAIL | no log |")
    _task(db, "t2", status="failed")
    _run(db, "t2", "build", 1, "committed", "2026-11-02T01:00:00+00:00",
         model="m", flow="default", step="build", version="v1", steps=6, cost=0.0)
    db.close()

    assert main(["stats"]) == 0
    out = capsys.readouterr().out
    for text in ("window:", "2 tasks", "1 PR", "1 merged", "1 failed", "first-attempt pass rate",
                 "50% (1/2)", "attempts per PR", "cost per merged PR", "$0.50",
                 "reviewer CHANGES rate", "step-limit stops", "reworks", "human edits",
                 "session_log", "gate", "failures", "flow", "version", "outcomes", "first seen"):
        assert text in out
    assert "-" in out

    assert main(["stats", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert set(data) == {"window", "summary", "gates", "steps"}
    assert data["summary"]["reviewer_changes_rate"]["rate"] is None
    assert data["summary"]["human_edits"]["rate"] is None
    assert data["summary"]["first_attempt_pass_rate"]["rate"] == 0.5
    assert data["gates"] == [{"gate": "session_log", "failures": 1}]
    assert [(row["flow"], row["step"], row["model"], row["version"]) for row in data["steps"]] == [
        ("default", "build", "m", "v1"),
    ]
    assert data["steps"][0]["runs"] == 2
    assert data["steps"][0]["calls"] == 5.0
    assert data["steps"][0]["cost_usd"] == pytest.approx(0.5)
    assert data["steps"][0]["first_seen"] == "2026-11-01"

    assert main(["stats", "--since", "2030-01-01"]) == 0
    assert "no runs in the window" in capsys.readouterr().out
    assert main(["stats", "--since", "2030-01-01", "--json"]) == 0
    assert "no runs in the window" in capsys.readouterr().out
    assert main(["stats", "--since", "nope"]) == 2
    assert "FAIL --since: not an ISO date: 'nope'" in capsys.readouterr().err
