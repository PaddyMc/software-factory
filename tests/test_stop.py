"""`factory stop`: graceful task runs, stuck processes, and whole plan runs."""

import os
import re
import signal
import subprocess
import sys
import threading
import time

import pytest

from factory import scheduler
from factory.cli import main
from factory.contracts import parse_text
from factory.db import open_db, pid_alive
from factory.pipeline import Stopped
from conftest import TASK, git, plan_text

NOTE = r"stopped by factory stop at \d\d:\d\d UTC; run it again to start over"
PLAN = "docs/plans/demo/demo.md"
SLEEPER = "import time\ntime.sleep(300)\n"
IGNORING_SLEEPER = """\
import signal, sys, time
signal.signal(signal.SIGTERM, signal.SIG_IGN)
open(sys.argv[1], "w").close()
time.sleep(300)
"""
BLOCKING_RUN = """\
import sys, time
from factory import agents
agents.PROVIDER_KEYS["fake"] = "FAKE_API_KEY"
from langchain_core.language_models.chat_models import BaseChatModel

class BlockingModel(BaseChatModel):
    @property
    def _llm_type(self):
        return "blocking"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        time.sleep(300)
        raise AssertionError("the blocking model returned")

agents.build_model = lambda spec: BlockingModel()
from factory.cli import main
sys.exit(main(["run", "demo-t01", "--no-sandbox"]))
"""

THREE = TASK + """- id: demo-t03
  goal: "An independent third thing"
  spec_refs: []
  depends_on: []
  non_goals: []
  acceptance: ["Third thing done"]
  verification: ["true"]
  risk: low
"""


def _board(home, body=TASK):
    db = open_db(home)
    db.sync({t.id: t for t in parse_text(plan_text(body), PLAN)})
    return db


def _spawn(script, *args):
    proc = subprocess.Popen([sys.executable, "-c", script, *args], stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    # A reaped child stops looking alive immediately; otherwise `stop` can wait out --wait on a zombie.
    threading.Thread(target=proc.wait, daemon=True).start()
    return proc


def _reap(proc):
    if proc.poll() is None:
        proc.kill()
    proc.wait()


def test_stop_ends_a_running_task_as_failed_and_records_the_run_as_stopped(
        repo, home, tmp_path, monkeypatch, capsys):
    agents_dir = repo / ".factory/agents"
    agents_dir.mkdir(parents=True)
    for role in ("planner", "builder", "reviewer", "verifier"):
        (agents_dir / f"{role}.md").write_text(
            f"---\nmodel: fake:{role}\nmax_steps: 20\n---\nYou are the {role.upper()} for one task.\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "agents")
    git(repo, "push", "-q", "origin", "main")
    monkeypatch.setenv("FAKE_API_KEY", "x")
    monkeypatch.chdir(repo)

    child_log = tmp_path / "stopped-task.log"
    with child_log.open("w") as output:
        child = subprocess.Popen([sys.executable, "-c", BLOCKING_RUN], cwd=repo, stdin=subprocess.DEVNULL,
                                 stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
        threading.Thread(target=child.wait, daemon=True).start()
        try:
            ready = False
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline and child.poll() is None:
                db = open_db(home)
                row = db.task("demo-t01")
                open_run = db.conn.execute(
                    "SELECT 1 FROM runs WHERE task_id='demo-t01' AND ended_at IS NULL").fetchone()
                db.close()
                if row is not None and row["status"] == "planning" and row["pid"] == child.pid and open_run:
                    ready = True
                    break
                time.sleep(0.1)
            assert ready, child_log.read_text()

            assert main(["stop", "demo-t01"]) == 0
            assert child.wait(timeout=5) == 1, child_log.read_text()
            db = open_db(home)
            row = db.task("demo-t01")
            assert row["status"] == "failed"
            assert re.fullmatch(NOTE, row["note"])
            assert db.runs("demo-t01")[-1]["outcome"] == "stopped"
            assert "[stage] stopped" in (home / "logs/demo-t01.log").read_text()
            assert (home / "worktrees/demo-t01").exists()
            assert git(repo, "branch", "--list", "factory/demo-t01")
            assert "stopped demo-t01" in capsys.readouterr().out
        finally:
            _reap(child)


def test_stop_kills_a_task_that_ignores_sigterm(repo, home, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(repo)
    ready = tmp_path / "ignoring-sigterm"
    child = _spawn(IGNORING_SLEEPER, str(ready))
    try:
        deadline = time.monotonic() + 5
        while not ready.exists() and child.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        assert ready.exists()
        db = _board(home)
        db.update("demo-t01", status="building")
        db.claim("demo-t01", child.pid)

        started = time.monotonic()
        assert main(["stop", "demo-t01", "--wait", "1"]) == 0
        assert time.monotonic() - started >= 0.8
        assert child.wait(timeout=5) == -signal.SIGKILL
        row = open_db(home).task("demo-t01")
        assert row["status"] == "failed" and re.fullmatch(NOTE, row["note"])
        assert "stopped demo-t01" in capsys.readouterr().out
    finally:
        _reap(child)


def test_a_plan_run_records_its_pid_and_stops_its_tasks_on_sigterm(home):
    db = _board(home, THREE)
    plan = scheduler.Plan(name="demo", tasks=["demo-t01", "demo-t02", "demo-t03"], parallel=3)
    launched, procs, sleeps = [], {}, []

    class HungProc:
        def __init__(self, tid):
            self.tid = tid
            self.terminated = 0
            self.waited = 0

        def poll(self):
            return None

        def terminate(self):
            self.terminated += 1

        def wait(self):
            self.waited += 1

    def launch(tid, args):
        launched.append(tid)
        procs[tid] = HungProc(tid)
        return procs[tid]

    def stop_now(_):
        assert not sleeps, "the plan kept supervising after SIGTERM"
        sleeps.append(1)
        pid_file = home / "plan-runs/demo.pid"
        assert pid_file.read_text() == str(os.getpid())
        os.kill(os.getpid(), signal.SIGTERM)

    with pytest.raises(Stopped):
        scheduler.run(db, plan, launch, clock=lambda: 0.0, sleep=stop_now)

    assert launched == ["demo-t01", "demo-t03"]
    assert all(p.terminated == 1 and p.waited == 1 for p in procs.values())
    assert not (home / "plan-runs/demo.pid").exists()


def test_stop_plan_stops_the_plan_run_and_its_running_tasks(repo, home, monkeypatch, capsys):
    monkeypatch.chdir(repo)
    db = _board(home)
    plan_proc, task_proc = _spawn(SLEEPER), _spawn(SLEEPER)
    try:
        pid_file = home / "plan-runs/demo.pid"
        pid_file.parent.mkdir(parents=True)
        pid_file.write_text(str(plan_proc.pid))
        db.update("demo-t01", status="building")
        db.claim("demo-t01", task_proc.pid)

        assert main(["stop", "demo"]) == 0
        out = capsys.readouterr().out
        assert "stopped plan run demo" in out and "stopped demo-t01" in out
        assert plan_proc.wait(timeout=5) is not None
        assert task_proc.wait(timeout=5) is not None
        assert not pid_file.exists()
        rows = open_db(home)
        assert rows.task("demo-t01")["status"] == "failed"
        assert re.fullmatch(NOTE, rows.task("demo-t01")["note"])
        assert rows.task("demo-t02")["status"] == "queued"
    finally:
        _reap(plan_proc)
        _reap(task_proc)


def test_stop_refuses_unknown_targets_and_idle_tasks(repo, home, monkeypatch, capsys):
    monkeypatch.chdir(repo)
    _board(home)

    assert main(["stop", "nope-t99"]) == 1
    assert "nope-t99 is neither a task on the board nor a plan" in capsys.readouterr().err
    assert main(["stop", "demo-t01"]) == 1
    assert "demo-t01 is queued; nothing to stop" in capsys.readouterr().err
    assert main(["stop", "demo"]) == 0
    assert "nothing to stop: demo has no running plan run or task" in capsys.readouterr().out


def test_a_stale_plan_pid_file_is_removed(repo, home, monkeypatch, capsys):
    monkeypatch.chdir(repo)
    _board(home)
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    assert not pid_alive(dead.pid)
    pid_file = home / "plan-runs/demo.pid"
    pid_file.parent.mkdir(parents=True)
    pid_file.write_text(str(dead.pid))

    assert main(["stop", "demo"]) == 0
    assert not pid_file.exists()
    assert "nothing to stop: demo has no running plan run or task" in capsys.readouterr().out
