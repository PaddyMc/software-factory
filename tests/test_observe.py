"""factory top, merged logs, liveness, cost."""

import json
import subprocess
import sys

from factory import observe, prices
from factory.cli import main
from factory.contracts import parse_text
from factory.db import open_db, pid_alive
from conftest import plan_text


def _db(home):
    db = open_db(home)
    for t in parse_text(plan_text(), "docs/plans/demo/demo.md"):
        db.upsert_task(t)
    return db


def _dead_pid():
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    return p.pid


def test_top_shows_running_task_activity_cost_and_failures(home):
    db = _db(home)
    import os
    db.update("demo-t01", status="building", attempts=1)
    db.claim("demo-t01", os.getpid())
    run = db.start_run("demo-t01", "build", 1)
    db.progress("demo-t01", run, "build#1 step 7/120 · 12k in / 1k out · $0.021", 7, 12000, 1000, 0.021)
    db.heartbeat("demo-t01", "[build#1] → run(command=cargo test -p demo-node)")
    (home / "logs").mkdir()
    (home / "logs/demo-t01.log").write_text("00:00:01 [stage] building (build #1)\n00:00:02 [build#1] → run(command=cargo test)\n")
    screen = observe.render_top(db, home, width=200)
    assert "1 running" in screen and "spent $0.02" in screen
    assert "demo-t01" in screen and "building" in screen and "build#1 step 7/120" in screen and "$0.02" in screen
    assert "↳ [build#1] → run(command=cargo test -p demo-node)" in screen
    assert "recent events" in screen and "demo-t01                       00:00:02 [build#1]" in screen


def test_dead_run_is_flagged_and_refresh_fails_it(home, monkeypatch, capsys):
    db = _db(home)
    db.update("demo-t01", status="building")
    db.claim("demo-t01", _dead_pid())
    assert not pid_alive(db.task("demo-t01")["pid"])
    assert "DEAD: process" in observe.detail(db, db.task("demo-t01"))
    assert main(["status"]) == 0
    assert "DEAD" in capsys.readouterr().out
    assert main(["status", "--refresh"]) == 0
    row = open_db(home).task("demo-t01")
    assert row["status"] == "failed" and "exited mid-run" in row["note"]


def test_logs_all_merges_tasks_in_time_order(home, capsys):
    (home / "logs").mkdir()
    (home / "logs/a-t01.log").write_text("10:00:01 [stage] one\n10:00:03 [stage] three\n")
    (home / "logs/b-t01.log").write_text("10:00:02 [stage] two\n")
    assert main(["logs", "--all"]) == 0
    lines = [l.split()[0] + " " + l.split()[-1] for l in capsys.readouterr().out.splitlines()]
    assert lines == ["a-t01 one", "b-t01 two", "a-t01 three"]


def test_cost_from_cached_openrouter_prices(home):
    prices._memo.clear()
    cache = prices.cache_path()
    cache.parent.mkdir(parents=True)
    cache.write_text(json.dumps({"z-ai/glm-5.3": {"prompt": 0.04e-6, "completion": 6e-6}}))
    assert abs(prices.cost("openrouter:z-ai/glm-5.3", 1_000_000, 1_000) - (0.04 + 0.006)) < 1e-9
    assert prices.cost("openrouter:unknown/model", 10, 10) is None
    assert prices.cost("anthropic:claude-opus-5-5", 10, 10) is None
    prices._memo.clear()
