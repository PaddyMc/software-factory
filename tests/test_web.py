"""The read-only board, its loopback HTTP server, and the `factory web` command."""

import datetime as dt
import hashlib
import html
import json
import os
import re
import socket
import socketserver
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote, urlencode
from html.parser import HTMLParser

import pytest

from factory import observe
from factory.cli import main
from factory.contracts import Task, parse_text
from factory.db import open_db
from factory.web import jobs, server as web_server
from factory.web.server import App, make_server
from conftest import plan_text

PLAN = "docs/plans/demo/demo.md"
HOST = {"Host": "127.0.0.1:8765"}


def _contract(task_id, goal=None, depends=()):
    return f"""- id: {task_id}
  goal: {json.dumps(goal or f'Goal for {task_id}')}
  spec_refs: []
  depends_on: {json.dumps(list(depends))}
  non_goals: []
  acceptance: ["Done"]
  verification: ["true"]
  risk: low
"""


def _add(db, contracts, plan=PLAN):
    tasks = parse_text(plan_text("".join(contracts)), plan)
    db.sync({task.id: task for task in tasks})
    return tasks


def _board(home, contracts=(), plan=PLAN):
    db = open_db(home)
    if contracts:
        _add(db, contracts, plan)
    return db


def _at(seconds):
    base = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
    return (base + dt.timedelta(seconds=seconds)).isoformat(timespec="milliseconds")


def _system(at, content, model="test/model"):
    return {"type": "system", "at": _at(at), "model": model, "max_steps": 20, "content": content}


def _human(at, content):
    return {"type": "human", "at": _at(at), "content": content}


def _ai(step, at, text="", calls=(), tokens=(100, 10), cost=0.001, reasoning=None, think=None):
    event = {
        "type": "ai", "at": _at(at), "step": step, "text": text,
        "usage": {"in": tokens[0], "out": tokens[1], "cache_read": 0}, "cost_usd": cost,
        "tool_calls": [{"name": name, "args": args} for name, args in calls],
    }
    if reasoning is not None:
        event["reasoning"] = reasoning
    if think is not None:
        event["usage"]["reasoning"] = think
    return event


def _tool(at, name, content):
    return {"type": "tool", "at": _at(at), "name": name, "content": content}


def _write_transcript(db, home, task_id, run_id, events):
    path = home / "transcripts" / task_id / f"{run_id:05d}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(event) + "\n" for event in events))
    db.conn.execute("UPDATE runs SET transcript=? WHERE id=?", (str(path), run_id))
    db.conn.commit()
    return path


def _dead_pid():
    process = subprocess.Popen([sys.executable, "-c", "pass"])
    process.wait()
    return process.pid


def _get(app, path="/", headers=HOST, method="GET"):
    status, response_headers, body = app.handle(method, path, headers, b"")
    return status, dict(response_headers), body.decode()


def _post(app, action, fields=None, headers=None, body=None):
    fields = dict(fields or {})
    fields.setdefault("token", app.token)
    if body is None:
        body = urlencode(fields).encode()
    request_headers = {**HOST, "Content-Type": "application/x-www-form-urlencoded"}
    for name, value in (headers or {}).items():
        if value is None:
            request_headers = {key: existing for key, existing in request_headers.items()
                               if key.lower() != name.lower()}
        else:
            request_headers[name] = value
    status, response_headers, response_body = app.handle("POST", f"/actions/{action}", request_headers, body)
    return status, dict(response_headers), response_body.decode()


class Recording:
    """A launch double; optionally finish the command before the server starts waiting."""
    def __init__(self, exit_code=None, output="", pid=None):
        self.exit_code = exit_code
        self.output = output
        self.pid = pid
        self.calls = []

    def __call__(self, argv, cwd):
        self.calls.append((argv, cwd))
        directory = Path(argv[-1])
        if self.exit_code is not None:
            (directory / "output.log").write_text(self.output)
            (directory / "result.json").write_text(json.dumps({
                "exit": self.exit_code,
                "ended_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            }))
        return SimpleNamespace(pid=self.pid)


def _job_dir(home, number, command=None, kind="quick", target="", minutes=1, pid=None,
             exit_code=None, output=""):
    directory = home / "web" / "jobs" / f"{number:06d}"
    directory.mkdir(parents=True)
    started = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=minutes)
    (directory / "job.json").write_text(json.dumps({
        "argv": [sys.executable, "-m", "factory.cli", "sync"],
        "command": command or "factory sync", "kind": kind, "target": target,
        "started_at": started.isoformat(timespec="seconds"), "pid": pid, "root": "/repo",
    }))
    (directory / "output.log").write_text(output)
    if exit_code is not None:
        ended = started + dt.timedelta(seconds=9)
        (directory / "result.json").write_text(json.dumps({
            "exit": exit_code, "ended_at": ended.isoformat(timespec="seconds"),
        }))
    return directory


def test_board_sentence_and_counts_match_factory_top(home, repo):
    contracts = [_contract(f"many-t{i:02d}") for i in range(1, 14)]
    contracts[-1] = _contract("many-t13", depends=["many-t10"])
    db = _board(home, contracts)
    statuses = ["planning", "building", "reviewing", "verifying", "pr_open", "conflict", "ci_failed",
                "changes_requested", "merged", "failed", "abandoned", "queued", "queued"]
    for index, status in enumerate(statuses, 1):
        db.update(f"many-t{index:02d}", status=status, cost_usd=index / 100,
                  pr_url=f"https://github.test/pr/{index}" if status == "pr_open" else None)
    expected = observe.render_top(db, home, width=200).splitlines()[0]
    db.close()

    status, _, body = _get(App(home, repo))
    assert status == 200
    numbers = {name: int(re.search(rf"(\d+) {name}", expected).group(1))
               for name in ("running", "ready", "waiting")}
    spent = re.search(r"spent \$(\d+\.\d\d)", expected).group(1)
    assert '<h1 class="lede">5 tasks need you. 4 are running.</h1>' in body
    for name, number in numbers.items():
        assert f"<dt>{name}</dt><dd>{number}</dd>" in body
    assert f"<dt>spent</dt><dd>${spent}</dd>" in body
    assert "<dt>need you</dt><dd>5</dd>" in body
    assert "<dt>merged</dt><dd>1</dd>" in body
    assert "<dt>on hold</dt><dd>1</dd>" in body


def test_needs_you_lists_each_task_waiting_on_you_with_its_next_step(home, repo):
    db = _board(home, [_contract(f"needs-t{i:02d}") for i in range(1, 12)])
    db.update("needs-t01", status="building", progress="build#1 step 2/20")
    db.claim("needs-t01", _dead_pid())
    db.update("needs-t02", status="failed", note="unit tests failed\nmore detail")
    db.update("needs-t03", status="conflict", note="conflicts with main",
              pr_url="https://github.test/pr/39")
    db.update("needs-t04", status="ci_failed", note="tests failed on the PR",
              pr_url="https://github.test/pr/40")
    db.update("needs-t05", status="changes_requested", note="review asks for a test",
              pr_url="https://github.test/pr/41")
    db.update("needs-t06", status="pr_open", pr_url="https://github.test/pr/42")
    db.update("needs-t07", status="pr_open", pr_url="https://github.test/pr/43", stacked_on="needs-t10")
    db.update("needs-t08", status="building")
    db.claim("needs-t08", os.getpid())
    db.update("needs-t09", status="queued")
    db.update("needs-t10", status="merged")
    db.update("needs-t11", status="abandoned")
    db.close()

    _, _, body = _get(App(home, repo))
    section = re.search(r'<section class="block" aria-labelledby="h-you">(.*?)</section>', body, re.S).group(1)
    ids = re.findall(r'<a class="id" href="/tasks/[^"]+">([^<]+)</a>', section)
    assert ids == [f"needs-t{i:02d}" for i in range(1, 8)]
    for expected in (
            "Its process is gone. Check GitHub to mark it failed.",
            "Read why it failed, then run it again.",
            "Run it again to resolve the conflict with its base.",
            "Run it again to fix the failing checks on its pull request.",
            "Run it again to address the review.",
            "Review and merge pull request #42.",
            "Review pull request #43; merge it after needs-t10.",
            "Every gate passed. Merging is your approval.",
            "unit tests failed", "conflicts with main", "tests failed on the PR", "review asks for a test"):
        assert expected in section
    assert section.count("Open pull request") == 5
    for task_id in ("needs-t08", "needs-t09", "needs-t10", "needs-t11"):
        assert f'<a class="id" href="/tasks/{task_id}">{task_id}</a>' not in section


def test_running_tasks_show_their_step_activity_and_quiet_time(home, repo):
    db = _board(home, [_contract("run-t01", "Build the whole feature"), _contract("run-t02")])
    db.update("run-t01", status="building", attempts=1)
    db.claim("run-t01", os.getpid())
    run = db.start_run("run-t01", "build", 1)
    db.progress("run-t01", run, "build#1 step 14/120 · 12k in / 1k out", 14, 12000, 1000, 0.25)
    db.heartbeat("run-t01", "run(command=uv run pytest -q)")
    at = dt.datetime.now(dt.timezone.utc)
    db.update("run-t01", started_at=(at - dt.timedelta(seconds=123)).isoformat(timespec="seconds"),
              heartbeat_at=(at - dt.timedelta(seconds=8)).isoformat(timespec="seconds"))
    db.update("run-t02", status="reviewing", progress="collecting review context")
    db.claim("run-t02", os.getpid())
    db.close()

    _, _, body = _get(App(home, repo))
    running = re.search(r'<section class="block" aria-labelledby="h-run">(.*?)</section>', body, re.S).group(1)
    assert "build 1, step 14 of 120" in running
    assert '<progress class="meter" value="14" max="120" aria-label="14 of 120 steps"></progress>' in running
    assert "run(command=uv run pytest -q)" in running
    assert re.search(r"quiet (8s|9s)", running)
    assert "2m03s" in running and "$0.25" in running
    assert 'title="Build the whole feature"' in running
    assert "collecting review context" in running
    assert running.count("<progress") == 1


def test_plans_show_one_square_per_task_and_finished_plans_collapse(home, repo):
    db = _board(home, [
        _contract("mix-t01"), _contract("mix-t02", depends=["mix-t01"]),
        _contract("mix-t03", depends=["mix-t02"]), _contract("mix-t04", depends=["mix-t03"]),
    ], "docs/plans/mix/mix.md")
    db.update("mix-t01", status="merged", attempts=1, cost_usd=1.0)
    db.update("mix-t02", status="ci_failed", attempts=1, cost_usd=2.0)
    db.update("mix-t03", status="failed", attempts=3, cost_usd=0.5)
    _add(db, [_contract("done-t01"), _contract("done-t02", depends=["done-t01"])], "docs/plans/done/done.md")
    db.update("done-t01", status="merged")
    db.update("done-t02", status="merged")
    db.close()

    _, _, body = _get(App(home, repo))
    assert '<details class="plan" id="plan-mix" open>' in body
    mix = re.search(r'<details class="plan" id="plan-mix" open>(.*?)</summary>', body, re.S).group(1)
    strip = re.search(r'<span class="strip"[^>]*>(.*?)</span>', mix, re.S).group(1)
    assert re.findall(r'<i class="([^"]+)"></i>', strip) == ["s-merged", "s-attn", "s-failed", "s-waiting"]
    assert 'aria-label="1 merged, 1 CI failing, 1 failed, 1 waiting"' in mix
    assert '<span class="plan-counts">1 of 4 merged, 1 CI failing, 1 failed, 1 waiting</span>' in mix
    assert ('<span class="plan-end"><span class="num">$3.50</span>'
            '<a class="btn" href="/run?plan=mix">Run plan</a></span>') in mix
    assert '<details class="finished" id="finished"><summary>1 finished plan</summary>' in body
    assert '<details class="finished" id="finished" open>' not in body
    assert '<details class="plan" id="plan-done">' in body
    assert body.index('id="finished"') < body.index('id="plan-done"')


def test_empty_board_says_how_to_load_plans(home, repo):
    _board(home).close()
    status, _, body = _get(App(home, repo))
    assert status == 200
    assert '<h1 class="lede">No tasks yet.</h1>' in body
    assert '<p class="fine">Load your plans with factory sync.</p>' in body
    assert "Nothing needs you right now." in body


def test_board_escapes_text_from_tasks_and_agents(home, repo):
    payload = "<script>alert(1)</script>"
    db = _board(home, [_contract("safe-t01", payload), _contract("safe-t02"), _contract("safe-t03")])
    db.update("safe-t01", status="failed", note=payload)
    db.update("safe-t02", status="building")
    db.claim("safe-t02", os.getpid())
    db.heartbeat("safe-t02", payload)
    db.update("safe-t03", status="pr_open", pr_url="javascript:alert(1)")
    db.close()

    _, _, body = _get(App(home, repo))
    assert payload not in body
    assert body.count("&lt;script&gt;alert(1)&lt;/script&gt;") >= 3
    assert 'href="javascript:' not in body
    assert "javascript:alert(1)" not in body


def test_only_get_requests_for_localhost_are_answered(home, repo):
    _board(home).close()
    app = App(home, repo)
    responses = []
    status, headers, _ = _get(app, method="POST")
    assert status == 405 and headers["Allow"] == "GET, HEAD"
    responses.append((status, headers))
    status, headers, _ = _get(app, headers={"Host": "evil.example:8765"})
    assert status == 403
    responses.append((status, headers))
    status, headers, _ = _get(app, headers={})
    assert status == 403
    responses.append((status, headers))
    for host in ("localhost:9000", "127.0.0.1:8765"):
        status, headers, _ = _get(app, headers={"hOsT": host})
        assert status == 200
        responses.append((status, headers))
    status, headers, _ = _get(app, method="HEAD")
    assert status == 200
    responses.append((status, headers))
    for path in ("/static/../db.py", "/static/fonts/OFL-dmmono.txt", "/factory.db"):
        status, headers, _ = _get(app, path)
        assert status == 404 and 'href="/"' in _
        responses.append((status, headers))

    for _, headers in responses:
        assert headers["Content-Security-Policy"] == web_server.CSP
        assert headers["X-Content-Type-Options"] == "nosniff"
        assert headers["Referrer-Policy"] == "no-referrer"
        assert headers["Cache-Control"] == "no-store"
        assert "Access-Control-Allow-Origin" not in headers


def test_the_web_reads_the_board_read_only(home, repo, monkeypatch):
    db = _board(home, [_contract("read-t01")])
    db.close()
    path = home / "factory.db"
    before = path.read_bytes()
    captured = []
    real_open = web_server.open_db

    class Capture:
        def __init__(self, db):
            self.db = db
            self.closed = False

        def __getattr__(self, name):
            return getattr(self.db, name)

        def close(self):
            self.closed = True       # keep the actual connection open so the test can try a write

    def capture(home, readonly=False):
        db = real_open(home, readonly=readonly)
        wrapped = Capture(db)
        captured.append((wrapped, readonly))
        return wrapped

    monkeypatch.setattr(web_server, "open_db", capture)
    status, _, _ = _get(App(home, repo))
    assert status == 200 and len(captured) == 1
    request, readonly = captured[0]
    try:
        assert readonly is True and request.closed
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            request.db.update("read-t01", note="not allowed")
        assert path.read_bytes() == before
        assert hashlib.sha256(path.read_bytes()).digest() == hashlib.sha256(before).digest()
    finally:
        request.db.close()


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.references = []
        self.scripts = []
        self.mains = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        for name in ("href", "src"):
            if name in values:
                self.references.append((tag, name, values[name]))
        if tag == "script":
            self.scripts.append(values)
        if tag == "main":
            self.mains.append(values)


def test_pages_and_static_files_load_nothing_from_the_network(home, repo):
    db = _board(home, [_contract("local-t01")])
    db.update("local-t01", status="pr_open", pr_url="https://github.test/pr/9")
    db.close()
    app = App(home, repo)
    _, _, body = _get(app)
    parser = _Links()
    parser.feed(body)
    for _, _, reference in parser.references:
        assert reference.startswith("/") or reference == "https://github.test/pr/9"
    assert parser.scripts == [{"src": "/static/app.js", "defer": None}]
    assert parser.mains[0]["data-refresh"] == "2"
    for path in ("/static/app.css", "/static/app.js"):
        status, _, content = _get(app, path)
        assert status == 200
        assert "http://" not in content and "https://" not in content
    forms = re.findall(r'<form\b[^>]*action="([^"]+)"', body)
    assert forms and all(action.startswith("/actions/") for action in forms)


def test_task_page_shows_the_contract_with_what_it_waits_for_and_what_needs_it(home, repo):
    contract = """- id: page-t02
  goal: "Show the whole contract"
  spec_refs: ["docs/plans/webui.md#task-page", "docs/design/webui/task.html"]
  depends_on: ["page-t01"]
  non_goals: ["Editing the contract", "Adding action forms"]
  acceptance: ["Every contract item is visible", "Dependencies link to their pages"]
  verification: ["uv run pytest -q tests/test_web.py", "git diff --check"]
  risk: medium
"""
    db = _board(home, [
        _contract("page-t01"), contract, _contract("page-t03", depends=["page-t02"]),
    ])
    db.update("page-t01", status="ci_failed")
    db.update("page-t02", status="failed", attempts=3, cost_usd=0.42, branch="factory/page-t02",
              base_ref="factory/page-t01", base_sha="55d7f91abcdef", pr_url="https://github.test/pr/42")
    db.close()

    app = App(home, repo)
    status_code, _, body = _get(app, "/tasks/page-t02")
    assert status_code == 200
    assert "<title>Show the whole contract · demo</title>" in body
    assert '<li><a href="/">Board</a></li>' in body
    assert '<li><a href="/#plan-demo">demo</a></li>' in body
    assert "<li>page-t02</li>" in body
    assert '<div class="task-id"><span>page-t02</span><span class="status s-failed">' in body
    assert '<h1 class="task-goal">Show the whole contract</h1>' in body
    facts = re.search(r'<dl class="facts">(.*?)</dl>', body, re.S).group(1)
    for fact in (
            "<dt>risk</dt><dd>medium</dd>", "<dt>builds</dt><dd>3</dd>", "<dt>cost</dt><dd>$0.42</dd>",
            "<dt>branch</dt><dd>factory/page-t02</dd>",
            "<dt>built on</dt><dd>factory/page-t01 at 55d7f91</dd>",
            '<dt>pull request</dt><dd><a href="https://github.test/pr/42">pull request</a></dd>'):
        assert fact in facts

    section = re.search(r'<section class="block contract" aria-labelledby="h-contract">(.*?)</section>',
                        body, re.S).group(1)
    for heading in ("Done when", "Not part of it", "Checked with", "Waits for", "Needed by", "Reads"):
        assert f"<h3>{heading}</h3>" in section
    for text in ("Every contract item is visible", "Dependencies link to their pages",
                 "Editing the contract", "Adding action forms"):
        assert f"<li>{text}</li>" in section
    for command in ("uv run pytest -q tests/test_web.py", "git diff --check"):
        assert (f'<div class="cmd"><code>{command}</code>'
                '<button class="copy" type="button" hidden>Copy</button></div>') in section
    assert section.count('<div class="cmd">') == 2
    waits = re.search(r'<h3>Waits for</h3>\s*<ul class="deps">(.*?)</ul>', section, re.S).group(1)
    needed = re.search(r'<h3>Needed by</h3>\s*<ul class="deps">(.*?)</ul>', section, re.S).group(1)
    assert '<span class="status s-attn"><i class="mark"></i>CI failing</span>' in waits
    assert '<a class="mono" href="/tasks/page-t01">page-t01</a>' in waits
    assert '<span class="status s-waiting"><i class="mark"></i>Waiting</span>' in needed
    assert '<a class="mono" href="/tasks/page-t03">page-t03</a>' in needed
    assert '<li class="mono">docs/plans/webui.md#task-page</li>' in section
    assert '<li class="mono">docs/design/webui/task.html</li>' in section
    assert body.count("<button") == 3
    assert body.count("<form") == 1
    assert 'title="factory abandon page-t02 --note &quot;put on hold from factory web&quot;"' in body

    _, _, sparse = _get(app, "/tasks/page-t01")
    sparse_facts = re.search(r'<dl class="facts">(.*?)</dl>', sparse, re.S).group(1)
    assert "<dt>risk</dt><dd>low</dd>" in sparse_facts
    for label in ("builds", "cost", "branch", "built on", "pull request"):
        assert f"<dt>{label}</dt>" not in sparse_facts


def test_task_page_lists_runs_newest_first_with_labels_outcomes_and_reports(home, repo):
    db = _board(home, [_contract("runs-t01")])
    now = dt.datetime.now(dt.timezone.utc)

    def stamp(run_id, minutes_ago, duration=None):
        started = now - dt.timedelta(minutes=minutes_ago)
        ended = started + dt.timedelta(seconds=duration) if duration is not None else None
        db.conn.execute("UPDATE runs SET started_at=?, ended_at=? WHERE id=?",
                        (started.isoformat(timespec="seconds"),
                         ended.isoformat(timespec="seconds") if ended else None, run_id))
        db.conn.commit()
        return started.isoformat(timespec="seconds")

    plan = db.start_run("runs-t01", "plan", 0, "models/glm-5.3")
    db.progress("runs-t01", plan, "planning", 14, 211000, 3000, 0.02)
    db.finish_run(plan, "done", "the plan")
    build = db.start_run("runs-t01", "build", 3, "openrouter/kimi-k3.1-pro")
    db.progress("runs-t01", build, "building", 31, 1204113, 14020, 0.11)
    db.finish_run(build, "committed (step limit)", "built <ok>")
    review = db.start_run("runs-t01", "review", 3, "deepseek-v4-pro")
    db.progress("runs-t01", review, "reviewing", 16, 402000, 6000, 0.04)
    db.finish_run(review, "APPROVE")
    gates = db.start_run("runs-t01", "verify", 2, step="gates")
    db.finish_run(gates, "fail unit_tests", "FAIL unit_tests\nsecond line")
    live = db.start_run("runs-t01", "build", 4, "provider/live-model")
    db.progress("runs-t01", live, "build#4 step 2/20", 2, 1000, 100, 0.01)
    started = {
        plan: stamp(plan, 31, 116), build: stamp(build, 13, 220), review: stamp(review, 9, 134),
        gates: stamp(gates, 6, 62), live: stamp(live, 4),
    }
    db.close()

    _, _, body = _get(App(home, repo), "/tasks/runs-t01")
    section = re.search(r'<section class="block" aria-labelledby="h-runs">(.*?)</section>', body, re.S).group(1)
    assert "Runs <span class=\"count\">5</span> <span class=\"aside\">Newest first</span>" in section
    assert '<p class="runs-head">Each line is one agent, or one pass of the gates.</p>' in section
    assert re.findall(r'<span class="run-name">([^<]+)</span>', section) == [
        "build 4", "gates, build 2", "review, build 3", "build 3", "plan",
    ]
    assert re.findall(r'<span class="outcome([^"]*)">', section) == [
        " o-live", " o-bad", " o-good", " o-good", " o-good",
    ]
    reports = re.findall(r'<details id="run-(\d+)-report"( open)?><summary>Report</summary>', section)
    assert [int(run_id) for run_id, _ in reports] == [live, gates, review, build, plan]
    assert [int(run_id) for run_id, open_ in reports if open_] == [live]
    assert '<li class="run is-live">' in section
    assert "committed (step limit)" in section
    assert "built &lt;ok&gt;" in section and "FAIL unit_tests\nsecond line" in section
    assert ('<span title="openrouter/kimi-k3.1-pro">kimi-k3.1-pro</span>, 31 steps, '
            '1,204k in, 14k out, $0.11') in section
    assert '<span title="deepseek-v4-pro">deepseek-v4-pro</span>, 16 steps, 402k in, 6k out, $0.04' in section
    assert (f'<time datetime="{started[gates]}" title="{started[gates]}">6 minutes</time> ago, '
            "took 1m02s") in section
    assert "Read the transcript" not in body


def test_transcript_page_shows_each_step_with_its_calls_and_results(home, repo):
    db = _board(home, [_contract("trace-t01")])
    run = db.start_run("trace-t01", "build", 3, "run/model")
    prompt = "Follow the <rules> & build."
    message = "Implement <trace-t01> & test it."
    model = "openrouter:moonshotai/kimi-k3.1-pro"
    events = [
        _system(0, prompt, model),
        _human(1, message),
        _ai(1, 4.1, "I'll read the view first.", [
            ("read_file", {"path": "factory/web/views.py", "content": "SHOULD_NOT_APPEAR"}),
        ], (18000, 210), 0.004),
        _tool(6.1, "read_file", "file contents"),
        _ai(2, 10.0, "Now I'll test and inspect.", [
            ("run", {"command": "uv run pytest -q"}),
            ("read_file", {"path": "tests/test_web.py", "start": 1}),
        ], (24000, 412), 0.006),
        _tool(12.0, "run", "exit 0\n1 passed"),
        _tool(50.0, "read_file", "test source"),
        _ai(3, 53.2, "All done.", tokens=(25000, 388), cost=0.020),
    ]
    _write_transcript(db, home, "trace-t01", run, events)
    db.finish_run(run, "committed")
    db.close()

    status, _, body = _get(App(home, repo), f"/tasks/trace-t01/runs/{run}")
    assert status == 200
    assert "<title>trace-t01, build 3 · demo</title>" in body
    assert '<li><a href="/">Board</a></li>' in body
    assert '<li><a href="/#plan-demo">demo</a></li>' in body
    assert '<li><a href="/tasks/trace-t01">trace-t01</a></li>' in body
    assert "<li>build 3</li>" in body
    assert '<div class="task-id"><span>build 3</span><span class="outcome o-good">committed</span></div>' in body
    assert '<h1 class="task-goal">What the builder did, step by step.</h1>' in body

    rows = observe.trace_rows(events)

    def tokens(count):
        return f"{count:,}" if count < 1000 else f"{count / 1000:,.0f}k"

    costs = [row["cost"] for row in rows if row["cost"] is not None]
    mix = Counter()
    for row in rows:
        for call in row["calls"]:
            name = call.split("(")[0]
            if name:
                mix[name] += 1
    expected_facts = [
        ("model", model),
        ("steps", str(len(rows))),
        ("tokens", f"{tokens(sum(row['ctx_in'] for row in rows))} in, "
                   f"{tokens(sum(row['out'] for row in rows))} out"),
        ("cost", f"${sum(costs):.2f}"),
        ("time", f"{observe.human_secs(sum(row['model_s'] or 0 for row in rows))} in the model, "
                 f"{observe.human_secs(sum(row['tools_s'] for row in rows))} in tools"),
        ("tools", ", ".join(f"{name} {count}" for name, count in mix.most_common())),
    ]
    facts = re.search(r'<dl class="facts">(.*?)</dl>', body, re.S).group(1)
    assert re.findall(r"<dt>([^<]+)</dt>", facts) == [name for name, _ in expected_facts]
    for name, value in expected_facts:
        assert f"<div><dt>{name}</dt><dd>{html.escape(value, quote=True)}</dd></div>" in facts
    assert expected_facts[-1] == ("tools", "read_file 2, run 1")
    assert "final answer" not in body

    assert (f'<details class="fold" id="t-system"><summary>What the agent was told '
            f'({len(prompt):,} characters)</summary><pre class="result">'
            f'{html.escape(prompt, quote=True)}</pre></details>') in body
    assert (f'<details class="fold" id="t-task"><summary>The task it was given '
            f'({len(message):,} characters)</summary><pre class="result">'
            f'{html.escape(message, quote=True)}</pre></details>') in body
    assert re.findall(r'<div class="step-n">Step (\d+)</div>', body) == ["1", "2", "3"]
    for row in rows:
        model_time = "-" if row["model_s"] is None else f"{row['model_s']:.1f}s"
        timing = f"{model_time} in the model"
        if row["tools_s"] >= 1.0:
            timing += f", {observe.human_secs(row['tools_s'])} in tools"
        step_facts = [timing, f"{tokens(row['ctx_in'])} in, {tokens(row['out'])} out"]
        if row["cost"] is not None:
            step_facts.append(f"${row['cost']:.3f}")
        assert f'<div class="step-facts">{"<br>".join(step_facts)}</div>' in body
    for text in ("I'll read the view first.", "Now I'll test and inspect.", "All done."):
        assert f'<p class="says">{html.escape(text, quote=True)}</p>' in body

    ordered = [
        "<b>read_file</b>(path=factory/web/views.py)",
        '<pre class="result">file contents</pre>',
        "<b>run</b>(command=uv run pytest -q)",
        '<pre class="result">exit 0\n1 passed</pre>',
        "<b>read_file</b>(path=tests/test_web.py, start=1)",
        '<pre class="result">test source</pre>',
    ]
    positions = [body.index(fragment) for fragment in ordered]
    assert positions == sorted(positions)
    assert "SHOULD_NOT_APPEAR" not in body
    assert '<div class="thinks">' not in body and 'class="thinks-' not in body


def test_long_results_are_folded_and_refusals_flagged(home, repo):
    db = _board(home, [_contract("fold-t01")])
    run = db.start_run("fold-t01", "build", 1)
    long = "<script>alert(1)</script>" + "x" * 2000
    long_refused = "refused: " + "y" * 2000
    boundary = "b" * 2000
    events = [
        _ai(1, 0, calls=[
            ("run", {"command": "long"}), ("run", {"command": "short"}),
            ("run", {"command": "refused"}), ("run", {"command": "long-refused"}),
            ("run", {"command": "boundary"}),
        ], cost=None),
        _tool(1, "run", long),
        _tool(2, "run", "ok"),
        _tool(3, "run", "refused: denied"),
        _tool(4, "run", long_refused),
        _tool(5, "run", boundary),
        {"type": "stopped", "at": _at(6), "reason": "step limit", "steps": 1},
    ]
    _write_transcript(db, home, "fold-t01", run, events)
    db.finish_run(run, "committed (step limit)")
    db.close()

    status, _, body = _get(App(home, repo), f"/tasks/fold-t01/runs/{run}")
    assert status == 200
    fold = re.search(r'<details class="fold" id="t-1-0">(.*?)</details>', body, re.S).group(1)
    assert f"<summary>Result, {len(long):,} characters</summary>" in fold
    assert f'<pre class="result">{html.escape(long, quote=True)}</pre>' in fold
    assert '<pre class="result">ok</pre>' in body
    assert '<pre class="result refused">refused: denied</pre>' in body
    refused_fold = re.search(r'<details class="fold" id="t-1-3">(.*?)</details>', body, re.S).group(1)
    assert f"<summary>Result, {len(long_refused):,} characters</summary>" in refused_fold
    assert f'<pre class="result refused">{html.escape(long_refused, quote=True)}</pre>' in refused_fold
    assert 'id="t-1-1"' not in body and 'id="t-1-2"' not in body
    assert f'<pre class="result">{boundary}</pre>' in body
    assert "Result, 2,000 characters" not in body
    assert 'id="t-1-4"' not in body
    assert '<p class="stopped">Stopped: step limit</p>' in body
    assert '<span class="outcome o-good">committed (step limit)</span>' in body
    assert "<script>alert(1)</script>" not in body
    assert html.escape("<script>alert(1)</script>", quote=True) in body


def test_transcript_page_shows_thoughts_above_what_the_step_said(home, repo):
    db = _board(home, [_contract("web-thoughts-t01")])
    run = db.start_run("web-thoughts-t01", "build", 1)
    thought = "Compare <script> & the result."
    events = [
        _system(0, "prompt"),
        _human(0.5, "task"),
        _ai(1, 1, "I checked.", [("read_file", {"path": "factory/web/views.py"})],
            reasoning=thought, think=152),
        _tool(2, "read_file", "source"),
        _ai(2, 3, "Done.", reasoning="No token count was reported."),
    ]
    _write_transcript(db, home, "web-thoughts-t01", run, events)
    db.finish_run(run, "committed")
    db.close()

    status, _, body = _get(App(home, repo), f"/tasks/web-thoughts-t01/runs/{run}")
    assert status == 200
    escaped = html.escape(thought, quote=True)
    assert (f'<div class="thinks"><div class="thinks-head">Thought, 152 tokens</div>'
            f'<p>{escaped}</p></div>') in body
    assert '<div class="thinks-head">Thought</div>' in body
    assert "&lt;script&gt;" in body and "&amp;" in body
    assert "<script>" not in body

    step_one = body[body.index('<div class="step-n">Step 1</div>'):
                    body.index('<div class="step-n">Step 2</div>')]
    thought_at = step_one.index('<div class="thinks">')
    assert thought_at < step_one.index('<p class="says">I checked.</p>')
    assert thought_at < step_one.index("<b>read_file</b>")


def test_long_thoughts_fold_after_their_opening(home, repo):
    db = _board(home, [_contract("thought-fold-t01")])
    run = db.start_run("thought-fold-t01", "build", 1)
    boundary = "a" * 800
    long = "x" * 300 + " " + "x" * 293 + "\n" + "y" * 251
    events = [
        _system(0, "prompt"),
        _ai(1, 1, reasoning=boundary),
        _ai(2, 2, reasoning=long, think=318),
    ]
    _write_transcript(db, home, "thought-fold-t01", run, events)
    db.finish_run(run, "committed")
    db.close()

    status, _, body = _get(App(home, repo), f"/tasks/thought-fold-t01/runs/{run}")
    assert status == 200
    assert f"<p>{boundary}</p>" in body
    assert 'id="t-1-thought"' not in body
    opening = f"<p>{'x' * 300} {'x' * 293}…</p>"
    fold = (f'<details class="fold" id="t-2-thought"><summary>The rest of the thought, 251 characters</summary>'
            f'<p>{"y" * 251}</p></details>')
    assert opening in body
    assert fold in body
    assert body.index(opening) < body.index(fold)
    assert long not in body


def test_a_step_that_thought_without_sharing_says_so(home, repo):
    db = _board(home, [_contract("hidden-thought-t01")])
    run = db.start_run("hidden-thought-t01", "build", 1)
    events = [
        _system(0, "prompt"),
        _ai(1, 1, "I can still answer.", reasoning="", think=121),
    ]
    _write_transcript(db, home, "hidden-thought-t01", run, events)
    db.finish_run(run, "committed")
    db.close()

    status, _, body = _get(App(home, repo), f"/tasks/hidden-thought-t01/runs/{run}")
    assert status == 200
    thought = ('<div class="thinks"><div class="thinks-head">Thought, 121 tokens</div>'
               '<p class="thinks-none">The model didn&#x27;t share its reasoning.</p></div>')
    says = '<p class="says">I can still answer.</p>'
    assert thought in body
    assert body.index(thought) < body.index(says)


def test_transcript_page_labels_model_time_and_thinking_tokens(home, repo):
    db = _board(home, [_contract("thought-facts-t01")])
    run = db.start_run("thought-facts-t01", "build", 1)
    events = [
        _system(0, "prompt"),
        _human(1, "task"),
        _ai(1, 4.1, "First", [("run", {"command": "fast"})], (18000, 210), 0.004,
            reasoning="First thought", think=9500),
        _tool(5.0, "run", "fast result"),
        _ai(2, 10.0, "Second", [("run", {"command": "slow"})], (24000, 412), 0.005,
            reasoning="Second thought", think=312),
        _tool(55.0, "run", "slow result"),
    ]
    _write_transcript(db, home, "thought-facts-t01", run, events)
    db.finish_run(run, "committed")
    old_run = db.start_run("thought-facts-t01", "build", 2)
    old_events = [_system(0, "prompt"), _ai(1, 2, "done")]
    _write_transcript(db, home, "thought-facts-t01", old_run, old_events)
    db.finish_run(old_run, "committed")
    db.close()

    status, _, body = _get(App(home, repo), f"/tasks/thought-facts-t01/runs/{run}")
    assert status == 200
    facts = re.search(r'<dl class="facts">(.*?)</dl>', body, re.S).group(1)
    assert '<div><dt>time</dt><dd>9s in the model, 45s in tools</dd></div>' in facts
    assert '<div><dt>tokens</dt><dd>42k in, 622 out (9,812 thinking)</dd></div>' in facts
    assert ('<div class="step-facts">4.1s in the model<br>18k in, 210 out<br>'
            '9500 thinking<br>$0.004</div>') in body
    assert ('<div class="step-facts">5.0s in the model, 45s in tools<br>24k in, 412 out<br>'
            '312 thinking<br>$0.005</div>') in body

    status, _, old_body = _get(App(home, repo), f"/tasks/thought-facts-t01/runs/{old_run}")
    assert status == 200
    assert "thinking" not in old_body
    old_facts = re.search(r'<dl class="facts">(.*?)</dl>', old_body, re.S).group(1)
    assert '<div><dt>time</dt><dd>2s in the model, 0s in tools</dd></div>' in old_facts


def test_transcript_page_refreshes_only_while_its_run_is_running(home, repo):
    db = _board(home, [_contract("live-t01")])
    run = db.start_run("live-t01", "build", 2)
    events = [_system(0, "prompt"), _ai(1, 2, "working")]
    _write_transcript(db, home, "live-t01", run, events)
    app = App(home, repo)

    status, _, body = _get(app, f"/tasks/live-t01/runs/{run}")
    assert status == 200
    assert '<main class="wrap" data-refresh="2">' in body
    assert '<span class="outcome o-live">running</span>' in body

    db.finish_run(run, "committed")
    db.close()
    status, _, body = _get(app, f"/tasks/live-t01/runs/{run}")
    assert status == 200
    assert '<main class="wrap">' in body
    assert "data-refresh" not in body
    assert '<span class="outcome o-good">committed</span>' in body


def test_a_half_written_transcript_line_is_skipped(home, repo):
    db = _board(home, [_contract("partial-t01")])
    run = db.start_run("partial-t01", "build", 1)
    result = "z" * 2001
    events = [
        _system(0, "prompt"),
        _human(0.5, "task"),
        "not an event object",
        {"at": _at(0.6)},
        _ai(1, 2, "Still working", [("run", {"command": "first"}), ("run", {"command": "second"})]),
        _tool(3, "run", result),
    ]
    path = _write_transcript(db, home, "partial-t01", run, events)
    filler = "half-written filler " * 110
    with path.open("a") as transcript:
        transcript.write('{"type": "tool", "name": "run", "content": "' + filler)
    db.close()

    status, _, body = _get(App(home, repo), f"/tasks/partial-t01/runs/{run}")
    assert status == 200
    assert '<p class="says">Still working</p>' in body
    assert "<b>run</b>(command=first)" in body and "<b>run</b>(command=second)" in body
    assert body.count('<div class="call">') == 2
    assert f'<summary>Result, {len(result):,} characters</summary>' in body
    assert result in body
    assert filler not in body
    assert body.count('id="t-1-') == 1


def test_a_run_of_another_task_or_without_a_transcript(home, repo):
    db = _board(home, [_contract("owner-t01"), _contract("owner-t02")])
    without_path = db.start_run("owner-t01", "build", 1)
    missing_file = db.start_run("owner-t01", "build", 2)
    foreign = db.start_run("owner-t02", "build", 1)
    db.conn.execute("UPDATE runs SET transcript=? WHERE id=?",
                    (str(home / "transcripts" / "owner-t01" / "missing.jsonl"), missing_file))
    db.conn.commit()
    for run in (without_path, missing_file, foreign):
        db.finish_run(run, "committed")
    db.close()
    app = App(home, repo)

    for requested in (str(foreign), "999999", "not-a-number"):
        status, _, body = _get(app, f"/tasks/owner-t01/runs/{requested}")
        assert status == 404
        message = html.escape(f"Run {requested} isn't one of owner-t01's runs", quote=True)
        assert message in body
        assert '<a href="/tasks/owner-t01">Back to owner-t01</a>' in body

    for run in (without_path, missing_file):
        status, _, body = _get(app, f"/tasks/owner-t01/runs/{run}")
        assert status == 200
        assert "No transcript was recorded for this run." in body
        assert '<a href="/tasks/owner-t01">Back to owner-t01</a>' in body
        assert '<dl class="facts">' not in body
        assert "<dt>steps</dt>" not in body

    status, _, body = _get(app, "/tasks/missing-t01/runs/1")
    assert status == 404
    assert "missing-t01 isn&#x27;t on this board" in body
    assert '<a href="/">Back to the board</a>' in body


def test_task_page_links_runs_to_their_transcripts(home, repo):
    db = _board(home, [_contract("links-t01")])
    recorded = db.start_run("links-t01", "build", 1)
    gates = db.start_run("links-t01", "verify", 1, step="gates")
    without_path = db.start_run("links-t01", "review", 1)
    _write_transcript(db, home, "links-t01", recorded, [_system(0, "prompt"), _ai(1, 1, "done")])
    db.conn.execute("UPDATE runs SET transcript=? WHERE id=?",
                    (str(home / "transcripts" / "links-t01" / "gates.jsonl"), gates))
    db.conn.commit()
    db.finish_run(recorded, "committed")
    db.finish_run(gates, "pass")
    db.finish_run(without_path, "APPROVE")
    db.close()

    status, _, body = _get(App(home, repo), "/tasks/links-t01")
    assert status == 200
    href = f"/tasks/links-t01/runs/{recorded}"
    assert re.findall(r'<a class="run-link" href="([^"]+)">Read the transcript</a>', body) == [href]
    items = re.findall(r'<li class="run">(.*?)</li>', body, re.S)
    recorded_item = next(item for item in items if f'id="run-{recorded}-report"' in item)
    gates_item = next(item for item in items if f'id="run-{gates}-report"' in item)
    without_item = next(item for item in items if f'id="run-{without_path}-report"' in item)
    assert f'<a class="run-link" href="{href}">Read the transcript</a>' in recorded_item
    assert recorded_item.index(f'id="run-{recorded}-report"') < recorded_item.index("Read the transcript")
    assert "Read the transcript" not in gates_item
    assert "Read the transcript" not in without_item


def test_task_page_next_step_follows_the_status(home, repo):
    contracts = [_contract(f"state-t{index:02d}") for index in range(1, 13)]
    contracts[7] = _contract("state-t08", depends=["state-t07"])
    db = _board(home, contracts)
    notes = {
        "state-t01": "gates failed: unit_tests\n\nFAIL first\n  second <tag>",
        "state-t02": "conflict with main\nresolve both files",
        "state-t03": "CI failed\nunit_tests: 2 failed",
        "state-t04": "changes requested\nadd the missing test",
    }
    for task_id, note in notes.items():
        status = {"state-t01": "failed", "state-t02": "conflict",
                  "state-t03": "ci_failed", "state-t04": "changes_requested"}[task_id]
        db.update(task_id, status=status, note=note)
    db.update("state-t05", status="building")
    db.claim("state-t05", _dead_pid())
    db.update("state-t06", status="building")
    db.claim("state-t06", os.getpid())
    db.update("state-t06", progress="build#2 step 14/120", activity="run(command=uv run pytest -q)")
    db.update("state-t09", status="merged", pr_url="https://github.test/pr/66")
    db.update("state-t10", status="abandoned")
    db.update("state-t11", status="pr_open", pr_url="https://github.test/pr/77")
    db.update("state-t12", status="reviewing", progress="collecting review context")
    db.claim("state-t12", os.getpid())
    db.close()

    app = App(home, repo)
    headings = {
        "state-t01": "Read why it failed, then run it again.",
        "state-t02": "Run it again to resolve the conflict with its base.",
        "state-t03": "Run it again to fix the failing checks on its pull request.",
        "state-t04": "Run it again to address the review.",
        "state-t05": "Its process is gone. Check GitHub to mark it failed.",
        "state-t06": "Running: build 2, step 14 of 120.",
        "state-t07": "Ready.",
        "state-t08": "Waits for state-t07 (queued).",
        "state-t09": "Merged.",
        "state-t10": "On hold.",
        "state-t11": "Review and merge pull request #77.",
        "state-t12": "Running: collecting review context",
    }
    panels = {}
    for task_id, heading in headings.items():
        status_code, _, body = _get(app, f"/tasks/{task_id}")
        assert status_code == 200
        assert '<main class="wrap" data-refresh="2">' in body
        panel = re.search(r'<section class="next-step" aria-labelledby="h-next">(.*?)</section>', body, re.S).group(1)
        panels[task_id] = panel
        assert f'<h2 id="h-next">{heading}</h2>' in panel
    for task_id in ("state-t01", "state-t07", "state-t08"):
        assert 'action="/actions/abandon"' in panels[task_id] and "Put on hold" in panels[task_id]
    assert 'action="/actions/requeue"' in panels["state-t10"] and "Take off hold" in panels["state-t10"]
    for task_id in ("state-t06", "state-t12"):
        assert f'href="/confirm?action=stop&amp;target={task_id}"' in panels[task_id]
    for task_id in ("state-t02", "state-t03", "state-t04"):
        link = f'<a class="btn btn-primary" href="/run?task={task_id}">Run again</a>'
        assert f'<div class="acts">{link}</div>' in panels[task_id]
        assert "<form" not in panels[task_id]
    for task_id in ("state-t05", "state-t09", "state-t11"):
        assert '<div class="acts">' not in panels[task_id] and "<form" not in panels[task_id]
    for task_id, note in notes.items():
        assert f"<pre>{html.escape(note, quote=True)}</pre>" in panels[task_id]
    assert "FAIL first\n  second &lt;tag&gt;" in panels["state-t01"]
    assert "DEAD: process" in panels["state-t05"] and "<pre>" not in panels["state-t05"]
    assert "run(command=uv run pytest -q)" in panels["state-t06"]
    assert re.search(r"quiet \d+s", panels["state-t06"])
    assert "The next run of its plan starts it." in panels["state-t07"]
    assert '<a href="https://github.test/pr/66">Open pull request</a>' in panels["state-t09"]
    assert "Plan runs skip it until you take it off hold." in panels["state-t10"]
    assert "Every gate passed. Merging is your approval." in panels["state-t11"]


def test_task_page_tails_the_task_log(home, repo):
    db = _board(home, [_contract("log-t01"), _contract("log-t02")])
    db.close()
    (home / "logs").mkdir()
    lines = [f"12:34:{index % 60:02d} [build#1] message {index:03d}" for index in range(250)]
    lines[-1] += " <unsafe>"
    (home / "logs/log-t01.log").write_text("\n".join(lines) + "\n")

    app = App(home, repo)
    _, _, body = _get(app, "/tasks/log-t01")
    log = re.search(r'<pre class="log" data-follow>(.*?)</pre>', body, re.S).group(1)
    assert log.count('<span class="t">') == 200
    assert log.count('<span class="tag">[build#1]</span>') == 200
    assert "message 049" not in log
    assert "message 050" in log and "message 249" in log
    assert log.index("message 050") < log.index("message 249")
    assert '<span class="t">12:34:50</span> <span class="tag">[build#1]</span> message 050' in log
    assert "message 249 &lt;unsafe&gt;" in log and "<unsafe>" not in log

    _, _, missing = _get(app, "/tasks/log-t02")
    assert '<pre class="log" data-follow>No log yet.</pre>' in missing


def test_unknown_task_is_a_404_that_links_back_to_the_board(home, repo):
    _board(home).close()
    status, _, body = _get(App(home, repo), "/tasks/nope-t01")
    assert status == 404
    assert "nope-t01 isn&#x27;t on this board" in body
    assert '<a href="/">Back to the board</a>' in body


def test_board_links_every_task_to_its_page(home, repo):
    db = _board(home, [_contract("link-t01"), _contract("link-t02"), _contract("link-t03")])
    special = Task(id="link t04+%", goal="A quoted task id", spec_refs=(), depends_on=(), non_goals=(),
                   acceptance=("Done",), verification=("true",), risk="low", plan=PLAN)
    db.upsert_task(special)
    db.update("link-t01", status="failed")
    db.update("link-t02", status="building")
    db.claim("link-t02", os.getpid())
    db.update("link-t03", status="merged")
    db.close()

    app = App(home, repo)
    _, _, body = _get(app)
    needs = re.search(r'<section class="block" aria-labelledby="h-you">(.*?)</section>', body, re.S).group(1)
    running = re.search(r'<section class="block" aria-labelledby="h-run">(.*?)</section>', body, re.S).group(1)
    plans = re.search(r'<section class="block" aria-labelledby="h-plans">(.*?)</section>', body, re.S).group(1)
    assert re.findall(r'<a class="id" href="([^"]+)">([^<]+)</a>', needs) == [("/tasks/link-t01", "link-t01")]
    assert re.findall(r'<a class="id" href="([^"]+)">([^<]+)</a>', running) == [("/tasks/link-t02", "link-t02")]
    links = {text: href for href, text in re.findall(r'<a class="id" href="([^"]+)">([^<]+)</a>', plans)}
    quoted = quote(special.id, safe="")
    assert links == {
        "link-t01": "/tasks/link-t01", "link-t02": "/tasks/link-t02", "link-t03": "/tasks/link-t03",
        special.id: f"/tasks/{quoted}",
    }
    assert quoted == "link%20t04%2B%25"
    assert '<span class="id">' not in body
    status, _, page = _get(app, f"/tasks/{quoted}")
    assert status == 200 and '<h1 class="task-goal">A quoted task id</h1>' in page


def test_web_serves_the_board_and_its_assets_over_http(home, repo):
    _board(home, [_contract("http-t01")]).close()
    app = App(home, repo)
    httpd = make_server(app, 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        assert httpd.server_address[0] == "127.0.0.1" and app.port == httpd.server_address[1]
        for path, content_type in (
                ("/", "text/html"), ("/static/app.css", "text/css"),
                ("/static/app.js", "text/javascript"), ("/static/favicon.svg", "image/svg+xml"),
                ("/static/fonts/dm-mono-400.woff2", "font/woff2")):
            with urllib.request.urlopen(base + path, timeout=5) as response:
                assert response.status == 200
                assert response.headers.get_content_type() == content_type
                assert response.read()
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
    assert not thread.is_alive()


def test_http_oversized_posts_are_capped_before_the_application_reads_them(home, repo):
    app = App(home, repo)
    body_sizes = []
    handle = app.handle

    def record_body_size(method, path, headers, body):
        body_sizes.append(len(body))
        return handle(method, path, headers, body)

    app.handle = record_body_size
    httpd = make_server(app, 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    client = socket.create_connection(httpd.server_address, timeout=5)
    try:
        client.settimeout(5)
        port = httpd.server_address[1]
        client.sendall((
            "POST /actions/sync HTTP/1.1\r\n"
            f"Host: 127.0.0.1:{port}\r\n"
            "Content-Type: application/x-www-form-urlencoded\r\n"
            "Content-Length: 1048576\r\n"
            "Connection: keep-alive\r\n\r\n"
        ).encode() + b"x" * (web_server.MAX_FORM_BODY + 1))
        response = b""
        while chunk := client.recv(65536):
            response += chunk
        assert response.startswith(b"HTTP/1.0 413 ")
        assert body_sizes == [web_server.MAX_FORM_BODY + 1]
    finally:
        client.close()
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
    assert not thread.is_alive()


def test_web_command_falls_back_to_a_free_port_and_refuses_a_busy_explicit_one(
        home, repo, monkeypatch, capsys):
    held = socket.socket()
    try:
        held.bind(("127.0.0.1", 8765))
    except OSError as error:
        held.close()
        pytest.skip(f"the test needs to hold the default port: {error}")
    held.listen()
    opened = []
    monkeypatch.chdir(repo)
    monkeypatch.setattr(socketserver.BaseServer, "serve_forever", lambda self: None)
    monkeypatch.setattr(webbrowser, "open", lambda url: opened.append(url))
    try:
        assert main(["web"]) == 0
        output = capsys.readouterr()
        match = re.search(r"factory web: http://127\.0\.0\.1:(\d+)/ \(Ctrl-C to stop\)", output.out)
        assert match and int(match.group(1)) != 8765
        assert opened == [f"http://127.0.0.1:{match.group(1)}/"]
        assert output.err == ""

        assert main(["web", "--no-open"]) == 0
        assert len(opened) == 1
        capsys.readouterr()

        assert main(["web", "--port", "8765", "--no-open"]) == 1
        output = capsys.readouterr()
        assert output.out == ""
        assert "port 8765 is in use; pick another with --port" in output.err
        assert len(opened) == 1
    finally:
        held.close()


def test_each_action_runs_its_factory_command_as_a_job(home, repo):
    db = _board(home, [
        _contract("act-t01"), _contract("act-t02"), _contract("act-t03"), _contract("act-t04"),
    ])
    db.update("act-t01", status="failed")
    db.update("act-t02", status="abandoned")
    db.update("act-t04", status="building")
    db.claim("act-t04", os.getpid())
    db.close()
    (home / "worktrees" / "act-t03").mkdir(parents=True)
    recording = Recording()
    app = App(home, repo, launch=recording)

    posts = [
        ("sync", "", ["sync"], "factory sync", "quick", ""),
        ("status", "", ["status", "--refresh"], "factory status --refresh", "quick", ""),
        ("abandon", "act-t01", ["abandon", "act-t01", "--note", "put on hold from factory web"],
         'factory abandon act-t01 --note "put on hold from factory web"', "quick", "act-t01"),
        ("requeue", "act-t02", ["requeue", "act-t02"], "factory requeue act-t02", "quick", "act-t02"),
        ("clean", "act-t03", ["clean", "act-t03"], "factory clean act-t03", "quick", "act-t03"),
        ("stop", "act-t04", ["stop", "act-t04"], "factory stop act-t04", "stop", "act-t04"),
        ("stop", "demo", ["stop", "demo"], "factory stop demo", "stop", "demo"),
    ]
    for index, (action, target, args, command, kind, job_target) in enumerate(posts, 1):
        status, headers, _ = _post(app, action, {"target": target, "next": "/"})
        assert status == 303
        expected_location = f"/activity?job={index:06d}" if kind == "stop" else f"/?job={index:06d}"
        assert headers["Location"] == expected_location
        directory = home / "web" / "jobs" / f"{index:06d}"
        record = json.loads((directory / "job.json").read_text())
        assert record["argv"] == [sys.executable, "-m", "factory.cli", *args]
        assert record["command"] == command
        assert record["kind"] == kind and record["target"] == job_target
        assert record["started_at"] and "pid" in record
        assert record["root"] == str(repo)
        assert recording.calls[index - 1] == (
            [sys.executable, "-m", "factory.web.jobs", str(directory)], repo)


def test_actions_are_refused_for_tasks_they_dont_apply_to(home, repo):
    db = _board(home, [_contract("bad-t01"), _contract("bad-t02"), _contract("bad-t03")])
    db.update("bad-t01", status="merged")
    db.update("bad-t02", status="building")
    db.claim("bad-t02", os.getpid())
    _add(db, [_contract("idle-t01")], "docs/plans/idle/idle.md")
    db.close()
    (home / "worktrees" / "bad-t02").mkdir(parents=True)
    pid_file = home / "plan-runs" / "idle.pid"
    pid_file.parent.mkdir()
    pid_file.write_text("-1")
    app = App(home, repo, launch=Recording())

    refused = [
        ("abandon", "bad-t01", "bad-t01 is merged; only a queued or failed task can be put on hold"),
        ("abandon", "bad-t02", "bad-t02 is building; only a queued or failed task can be put on hold"),
        ("requeue", "bad-t03", "bad-t03 is queued; only a task on hold can be taken off hold"),
        ("clean", "bad-t03", "bad-t03 has no worktree to remove"),
        ("clean", "bad-t02", "bad-t02 is running; stop it first"),
        ("stop", "bad-t03", "bad-t03 is queued; nothing to stop"),
        ("stop", "missing", "missing is neither a task on the board nor a plan"),
        ("stop", "idle", "nothing to stop: idle has no running plan run or task"),
    ]
    for action, target, reason in refused:
        status, _, body = _post(app, action, {"target": target})
        assert status == 409
        assert html.escape(reason, quote=True) in body
        assert 'class="nav"' in body and ">Board</a>" in body
    assert not (home / "web" / "jobs").exists()


def test_posts_without_this_servers_token_or_from_another_origin_are_refused(home, repo):
    db = _board(home, [_contract("secure-t01")])
    db.close()
    (home / "worktrees" / "secure-t01").mkdir(parents=True)
    app = App(home, repo, launch=Recording())

    assert _post(app, "sync", {"token": "wrong"})[0] == 403
    assert _post(app, "sync", {"token": None}, body=b"next=%2F")[0] == 403
    assert _post(app, "sync", headers={"Origin": "http://evil.example"})[0] == 403
    app.port = 8765
    for origin in ("http://127.0.0.1:8765", "http://localhost:8765"):
        assert _post(app, "sync", headers={"Origin": origin})[0] == 303
    assert _post(app, "sync", headers={"Sec-Fetch-Site": "cross-site"})[0] == 403
    assert _post(app, "sync", headers={"Sec-Fetch-Site": "same-origin"})[0] == 303
    assert _post(app, "sync", headers={"Content-Type": "text/plain"})[0] == 415
    assert _post(app, "sync", headers={"Content-Type": None})[0] == 415
    oversized = urlencode({"token": app.token, "padding": "x" * (17 * 1024)}).encode()
    assert _post(app, "sync", body=oversized)[0] == 413
    assert _post(app, "sync", headers={"Host": "evil.example:8765"})[0] == 403
    status, headers, _ = _get(app, method="POST")
    assert status == 405 and headers["Allow"] == "GET, HEAD"

    for path in ("/", "/tasks/secure-t01", "/confirm?action=clean&target=secure-t01"):
        _, _, body = _get(app, path)
        forms = [form for form in re.findall(r"<form\b.*?</form>", body, re.S) if 'method="post"' in form]
        assert forms
        for form in forms:
            assert f'<input type="hidden" name="token" value="{app.token}">' in form


def test_stop_and_remove_worktree_ask_for_confirmation(home, repo):
    db = _board(home, [_contract("confirm-t01"), _contract("confirm-t02"), _contract("confirm-t03")])
    db.update("confirm-t01", status="building")
    db.claim("confirm-t01", os.getpid())
    db.update("confirm-t02", status="failed")
    db.close()
    (home / "worktrees" / "confirm-t02").mkdir(parents=True)
    app = App(home, repo, launch=Recording())

    _, _, board = _get(app)
    assert '<a class="btn btn-danger" title="factory stop confirm-t01" href="/confirm?action=stop&amp;target=confirm-t01">Stop</a>' in board
    _, _, task = _get(app, "/tasks/confirm-t02")
    assert '<a class="btn btn-quiet" title="factory clean confirm-t02" href="/confirm?action=clean&amp;target=confirm-t02">Remove worktree</a>' in task
    for body in (board, task):
        forms = re.findall(r"<form\b.*?</form>", body, re.S)
        assert not any('action="/actions/stop"' in form or 'action="/actions/clean"' in form for form in forms)

    for action, target, command, next_ in (
            ("stop", "confirm-t01", "factory stop confirm-t01", "/activity"),
            ("clean", "confirm-t02", "factory clean confirm-t02", "/tasks/confirm-t02")):
        status, _, body = _get(app, f"/confirm?action={action}&target={target}")
        assert status == 200 and command in body
        assert ("terminates" in body if action == "stop" else "removes this task" in body)
        form = re.search(r"<form\b.*?</form>", body, re.S).group(0)
        assert f'action="/actions/{action}"' in form
        assert f'name="token" value="{app.token}"' in form
        assert f'name="target" value="{target}"' in form
        assert f'name="next" value="{next_}"' in form
        assert f'title="{command}"' in form

    status, _, body = _get(app, "/confirm?action=stop&target=confirm-t03")
    assert status == 200 and "confirm-t03 is queued; nothing to stop" in body
    assert "<form" not in body
    status, _, body = _get(app, "/confirm?action=clean&target=missing")
    assert status == 200 and "missing isn&#x27;t on this board" in body
    assert '<a class="btn" href="/">Back to the board</a>' in body
    assert 'href="/tasks/missing"' not in body and "<form" not in body
    assert _get(app, "/confirm?action=nonsense&target=confirm-t03")[0] == 404


def test_quick_actions_return_to_their_page_with_a_notice(home, repo):
    db = _board(home, [_contract("quick-t01"), _contract("quick-t02")])
    db.update("quick-t01", status="failed")
    db.update("quick-t02", status="building")
    db.claim("quick-t02", os.getpid())
    db.close()
    recording = Recording(exit_code=0, output="first line\nsynced 2 tasks\n")
    app = App(home, repo, launch=recording)

    status, headers, _ = _post(app, "sync")
    assert status == 303 and headers["Location"] == "/?job=000001"
    _, _, board = _get(app, headers["Location"])
    assert '<div class="notice notice-ok" role="status">' in board
    assert "Done: factory sync" in board and "synced 2 tasks" in board
    assert "first line" not in board
    assert '<a href="/activity#job-000001">View job</a>' in board

    status, headers, _ = _post(app, "abandon", {"target": "quick-t01", "next": "/tasks/quick-t01"})
    assert status == 303 and headers["Location"] == "/tasks/quick-t01?job=000002"
    _, _, task = _get(app, headers["Location"])
    assert "Done: factory abandon quick-t01" in task
    assert '<a href="/activity#job-000002">View job</a>' in task

    recording.exit_code = 1
    recording.output = "sync failed\n"
    for next_ in ("https://evil.example/", "//evil.example/", "///evil.example/", "tasks/quick-t01",
                  "/\\evil.example/", "/tasks/quick-t01#fragment"):
        status, headers, _ = _post(app, "sync", {"next": next_})
        assert status == 303
        assert re.fullmatch(r"/\?job=\d{6}", headers["Location"])
    _, _, failed = _get(app, headers["Location"])
    assert '<div class="notice notice-bad" role="status">' in failed
    assert "Failed: factory sync" in failed and "sync failed" in failed
    status, headers, _ = _post(app, "sync", {"next": "/?view=all"})
    assert status == 303 and re.fullmatch(r"/\?view=all&job=\d{6}", headers["Location"])

    recording.exit_code = None
    recording.pid = os.getpid()
    status, headers, _ = _post(app, "stop", {"target": "quick-t02", "next": "/tasks/quick-t02"})
    assert status == 303 and re.fullmatch(r"/activity\?job=\d{6}", headers["Location"])
    _, _, activity = _get(app, headers["Location"])
    assert "Still running: factory stop quick-t02" in activity
    assert '<div class="notice notice-ok" role="status">' in activity
    _, _, missing = _get(app, "/?job=999999")
    assert '<div class="notice' not in missing


def _wait_for_result(home, job_id, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = jobs.get(home, job_id)
        if job is not None and job.result is not None:
            return job
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} did not finish")


def test_a_job_records_its_output_and_exit_code_and_outlives_the_server(home, repo):
    _board(home).close()
    app = App(home, repo)
    status, headers, _ = _post(app, "sync")
    assert status == 303 and headers["Location"] == "/?job=000001"
    first = _wait_for_result(home, "000001")
    assert first.result["exit"] == 0 and first.result["ended_at"]
    assert isinstance(json.loads((first.directory / "job.json").read_text())["pid"], int)
    output = (first.directory / "output.log").read_text()
    assert "synced 2 tasks" in output and "ready to run:" in output

    sleeper = jobs.start(home, repo,
                         [sys.executable, "-c", "import time; time.sleep(1.5); print('slept through')"],
                         "sleep 1.5", "quick", "")
    running = jobs.get(home, sleeper)
    assert os.getpgid(running.pid) == running.pid
    finished = _wait_for_result(home, sleeper)
    assert finished.result["exit"] == 0
    assert "slept through" in (finished.directory / "output.log").read_text()
    for job in (first, finished):
        try:
            os.waitpid(job.pid, 0)
        except (ChildProcessError, ProcessLookupError):
            pass

    fresh = App(home, repo)
    status, _, body = _get(fresh, "/activity")
    assert status == 200
    assert "factory sync" in body and "sleep 1.5" in body
    assert body.index("sleep 1.5") < body.index("factory sync")


def test_activity_lists_jobs_newest_first_with_their_output(home, repo):
    _board(home).close()
    _job_dir(home, 1, "factory sync", minutes=120, exit_code=0)
    _job_dir(home, 2, "factory requeue wiki-t01", target="wiki-t01", minutes=18,
             exit_code=1, output="".join(f"line {index:03d}\n" for index in range(250)))
    _job_dir(home, 3, "factory status --refresh", minutes=6, pid=os.getpid())
    _job_dir(home, 4, "factory clean wiki-t01", target="wiki-t01", minutes=4, pid=_dead_pid())
    _job_dir(home, 5, "factory run demo --max-cost 5.00", kind="run", target="demo",
             minutes=2, pid=os.getpid(), output="run started\n")
    logs = home / "logs"
    logs.mkdir()
    (logs / "alpha.log").write_text("12:00:00 [build] alpha zero\n12:00:02 [build] alpha two\n")
    (logs / "beta.log").write_text("12:00:01 [review] beta one\n12:00:03 [verify] beta three\n")

    status, _, body = _get(App(home, repo), "/activity")
    assert status == 200
    assert '<h1 class="lede">2 commands are running.</h1>' in body
    assert "Commands from this page <span class=\"count\">5</span>" in body
    commands = re.findall(r'<span class="run-name">([^<]+)</span>', body)
    assert commands == [
        "factory run demo --max-cost 5.00", "factory clean wiki-t01", "factory status --refresh",
        "factory requeue wiki-t01", "factory sync",
    ]
    outcomes = re.findall(r'<span class="outcome ([^"]+)">([^<]+)</span>', body)
    assert outcomes == [("o-live", "running"), ("o-bad", "lost"), ("o-live", "running"),
                        ("o-bad", "exit 1"), ("o-good", "done")]
    opened = {job_id for job_id, open_ in re.findall(r'<details id="job-(\d+)"( open)?>', body) if open_}
    assert opened == {"000002", "000003", "000004", "000005"}
    failed = re.search(r'<details id="job-000002" open>(.*?)</details>', body, re.S).group(1)
    assert failed.count("line ") == 200
    assert "line 049" not in failed and "line 050" in failed and "line 249" in failed
    assert "took 9s" in body
    assert re.search(r"started \d+ minutes</time> ago, running for \d+m\d\ds", body)
    assert re.search(r"started \d+ minutes</time> ago, \d+m\d\ds since start", body)
    assert body.count("Stop this run") == 1
    assert 'title="factory stop demo" href="/confirm?action=stop&amp;target=demo"' in body
    assert '<main class="wrap" data-refresh="2">' in body
    assert '<a href="/">Board</a><a href="/activity" aria-current="page">Activity</a>' in body
    for text in (
            '<span class="t">12:00:00</span> <span class="tag">alpha</span> [build] alpha zero',
            '<span class="t">12:00:01</span> <span class="tag">beta</span> [review] beta one',
            '<span class="t">12:00:02</span> <span class="tag">alpha</span> [build] alpha two',
            '<span class="t">12:00:03</span> <span class="tag">beta</span> [verify] beta three'):
        assert text in body
    positions = [body.index(f"12:00:0{index}") for index in range(4)]
    assert positions == sorted(positions)


def test_old_jobs_are_pruned(home, repo):
    for number in range(1, 201):
        _job_dir(home, number, f"factory sync {number}", exit_code=0)
    recording = Recording()
    job_id = jobs.start(home, repo, [sys.executable, "-m", "factory.cli", "sync"],
                        "factory sync", "quick", "", recording)
    assert job_id == "000201"
    remaining = sorted(path.name for path in (home / "web" / "jobs").iterdir())
    assert len(remaining) == 200
    assert remaining[0] == "000002" and remaining[-1] == "000201"
    assert not (home / "web" / "jobs" / "000001").exists()


def test_run_form_lists_what_will_run_and_previews_the_command(home, repo, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "x")
    db = _board(home, [
        _contract("form-t01"), _contract("form-t02"), _contract("form-t03"), _contract("form-t04"),
        _contract("form-t05", depends=["form-t04"]), _contract("form-t06", depends=["form-t05"]),
        _contract("form-t07"), _contract("form-t08"), _contract("form-t09"), _contract("form-t10"),
    ], "docs/plans/form/form.md")
    for task_id, state in (("form-t01", "ci_failed"), ("form-t02", "failed"),
                           ("form-t03", "conflict"), ("form-t04", "changes_requested"),
                           ("form-t07", "building"), ("form-t08", "merged"),
                           ("form-t09", "pr_open"), ("form-t10", "abandoned")):
        db.update(task_id, status=state)
    db.claim("form-t07", os.getpid())
    _add(db, [_contract("empty-t01"), _contract("empty-t02")], "docs/plans/empty/empty.md")
    db.update("empty-t01", status="merged")
    db.update("empty-t02", status="pr_open")
    db.close()
    app = App(home, repo)

    status, _, body = _get(app, "/run?plan=form")
    assert status == 200
    assert "<title>Run form · demo</title>" in body
    assert '<h1 class="lede">Run the form plan.</h1>' in body
    assert '<li><a href="/">Board</a></li>' in body
    assert '<li><a href="/#plan-form">form</a></li>' in body
    assert '<h2 id="h-what">What will run <span class="count">4 now, 2 later</span></h2>' in body
    what = re.search(r'<section class="block" aria-labelledby="h-what">(.*?)</section>', body, re.S).group(1)
    rows = re.findall(r'<li class="row">(.*?)</li>', what, re.S)
    assert len(rows) == 7
    expected = {
        "form-t01": "Starts now, to fix the failing checks on its pull request.",
        "form-t02": "Starts now, with a fresh build.",
        "form-t03": "Starts now, to resolve the conflict with its base.",
        "form-t04": "Starts now, to address the review.",
        "form-t05": "Starts when form-t04 has a pull request.",
        "form-t06": "Starts when form-t05 has a pull request.",
        "form-t07": "Running already; this run leaves it alone.",
    }
    for task_id, sentence in expected.items():
        row = next(row for row in rows if f'>{task_id}</a>' in row)
        assert sentence in row
    for task_id in ("form-t08", "form-t09", "form-t10"):
        assert task_id not in what

    for field in (
            '<label for="max-cost">Cost cap per task, in USD</label>',
            '<input id="max-cost" name="max_cost" inputmode="decimal" value="5.00" required>',
            '<span class="hint">A task stops once it has spent this much.</span>',
            '<label for="parallel">Tasks at once</label>',
            '<input id="parallel" name="parallel" inputmode="numeric" value="3">',
            '<span class="hint">Independent tasks run side by side.</span>',
            '<label for="attempts">Builds per task</label>',
            '<input id="attempts" name="max_attempts" inputmode="numeric" value="3">',
            '<span class="hint">How often review or the gates may send it back.</span>',
            '<label for="flow">Agent flow</label>',
            '<select id="flow" name="flow"><option selected>default</option></select>',
            '<span class="hint">From .factory/config.yaml.</span>'):
        assert field in body
    assert ('<div class="cmd" data-preview><code>factory run form --max-cost 5.00 --parallel 3 '
            '--max-attempts 3</code><button class="copy" type="button" hidden>Copy</button></div>') in body
    assert ("Agents call your model provider, which costs money: at most $5.00 for each of 6 tasks, "
            "$30.00 in all. The run keeps going if you close this page. Stop it from the board.") in body
    assert '<button class="btn btn-primary">Start run</button>' in body
    assert '<a class="btn btn-quiet" href="/">Cancel</a>' in body
    assert f'<input type="hidden" name="token" value="{app.token}">' in body
    assert '<input type="hidden" name="target" value="form">' in body
    assert '<main class="wrap">' in body and "data-refresh" not in body

    status, _, task = _get(app, "/run?task=form-t02")
    assert status == 200
    assert '<h1 class="lede">Run form-t02.</h1>' in task
    assert '<li><a href="/tasks/form-t02">form-t02</a></li>' in task
    assert '<h2 id="h-what">What will run</h2>' in task
    assert 'name="parallel"' not in task
    assert '<input type="checkbox" name="quiet" checked hidden>' in task
    assert ("factory run form-t02 --max-cost 5.00 --max-attempts 3 --quiet"
            in task)
    assert "at most $5.00 for each of 1 tasks, $5.00 in all." in task
    assert '<a class="btn btn-quiet" href="/tasks/form-t02">Cancel</a>' in task

    status, _, empty = _get(app, "/run?plan=empty")
    assert status == 200
    assert "Every task of empty is merged, on hold or has a pull request." in empty
    assert "<form" not in empty
    for path in ("/run?plan=nope", "/run?task=nope", "/run"):
        assert _get(app, path)[0] == 404


def test_a_run_needs_a_valid_cost_cap_and_limits(home, repo):
    db = _board(home, [_contract("limits-t01")], "docs/plans/limits/limits.md")
    db.update("limits-t01", status="failed")
    db.close()
    recording = Recording()
    app = App(home, repo, launch=recording)

    base = {"target": "limits-t01", "max_attempts": "3", "flow": "default"}
    status, _, body = _post(app, "run", base)
    assert status == 400 and "The cost cap is required." in body
    for cap in ("0", "-1", "abc", "1000.01"):
        status, _, body = _post(app, "run", {**base, "max_cost": cap})
        assert status == 400
        assert "Enter a number above 0 and at most 1000." in body
        assert f'value="{cap}"' in body
    for parallel in ("0", "9", "2.5", "x"):
        status, _, body = _post(app, "run", {
            "target": "limits", "max_cost": "5.00", "parallel": parallel,
            "max_attempts": "3", "flow": "default",
        })
        assert status == 400 and "Enter a whole number from 1 to 8." in body
        assert f'value="{parallel}"' in body
    for attempts in ("0", "6", "x"):
        status, _, body = _post(app, "run", {
            "target": "limits", "max_cost": "5.00", "parallel": "3",
            "max_attempts": attempts, "flow": "default",
        })
        assert status == 400 and "Enter a whole number from 1 to 5." in body
        assert f'value="{attempts}"' in body
    status, _, body = _post(app, "run", {**base, "max_cost": "5.00", "flow": "nonsense"})
    assert status == 400 and "Pick a flow from the list." in body
    status, _, body = _post(app, "run", {**base, "max_cost": "0", "max_attempts": "6"})
    assert status == 400
    assert body.count('<span class="error">') == 2
    assert '<input id="max-cost" name="max_cost" inputmode="decimal" value="0" required>' in body
    assert '<input id="attempts" name="max_attempts" inputmode="numeric" value="6">' in body
    assert recording.calls == [] and not (home / "web" / "jobs").exists()

    valid = [
        {"target": "limits-t01", "max_cost": "0.01"},
        {"target": "limits-t01", "max_cost": "1000"},
        {"target": "limits", "max_cost": "5.00", "parallel": "1"},
        {"target": "limits", "max_cost": "5.00", "parallel": "8"},
        {"target": "limits", "max_cost": "5.00", "max_attempts": "1"},
        {"target": "limits", "max_cost": "5.00", "max_attempts": "5"},
        {"target": "limits-t01", "max_cost": "5.00", "parallel": "99"},
    ]
    for fields in valid:
        status, _, _ = _post(app, "run", fields)
        assert status == 303
    assert len(recording.calls) == len(valid)


def test_starting_a_run_launches_factory_run_with_the_forms_flags(home, repo):
    config_path = repo / ".factory/config.yaml"
    config_path.write_text(config_path.read_text()
                           + "\nflows:\n  strict: [plan, build, review, gates, verify]\n")
    db = _board(home, [_contract("go-t01")], "docs/plans/go/go.md")
    db.update("go-t01", status="failed")
    db.close()
    recording = Recording()
    app = App(home, repo, launch=recording)

    status, plan_headers, _ = _post(app, "run", {
        "target": "go", "max_cost": "5.00", "parallel": "2", "max_attempts": "3",
    })
    assert status == 303 and plan_headers["Location"] == "/activity?job=000001"
    status, _, _ = _post(app, "run", {
        "target": "go", "max_cost": "5.00", "parallel": "2", "max_attempts": "3", "flow": "strict",
    })
    assert status == 303
    status, task_headers, _ = _post(app, "run", {
        "target": "go-t01", "max_cost": "2.5", "max_attempts": "4", "flow": "strict",
    })
    assert status == 303 and task_headers["Location"] == "/activity?job=000003"

    expected = [
        ("go", "factory run go --max-cost 5.00 --parallel 2 --max-attempts 3", "Started the go plan."),
        ("go", "factory run go --max-cost 5.00 --parallel 2 --max-attempts 3 --flow strict",
         "Started the go plan."),
        ("go-t01", "factory run go-t01 --max-cost 2.5 --max-attempts 4 --flow strict --quiet",
         "Started go-t01."),
    ]
    for number, (target, command, notice) in enumerate(expected, 1):
        directory = home / "web" / "jobs" / f"{number:06d}"
        record = json.loads((directory / "job.json").read_text())
        assert record["command"] == command
        assert record["argv"] == [sys.executable, "-m", "factory.cli", *command.split()[1:]]
        assert record["kind"] == "run" and record["target"] == target
        assert record["notice"] == notice
        assert recording.calls[number - 1] == (
            [sys.executable, "-m", "factory.web.jobs", str(directory)], repo)

    _, _, activity = _get(app, plan_headers["Location"])
    assert '<div class="notice notice-ok" role="status">' in activity
    assert "Started the go plan." in activity
    assert '<a href="/activity#job-000001">View job</a>' in activity
    _, _, activity = _get(app, task_headers["Location"])
    assert "Started go-t01." in activity
    assert '<a href="/activity#job-000003">View job</a>' in activity

    for path, preview in (
            ("/run?plan=go", "factory run go --max-cost 2.5 --parallel 3 --max-attempts 3"),
            ("/run?task=go-t01", "factory run go-t01 --max-cost 2.5 --max-attempts 3 --quiet")):
        _, _, form = _get(app, path)
        assert 'value="2.5"' in form
        assert preview in form


def test_a_run_cannot_be_started_without_the_form(home, repo):
    db = _board(home, [
        _contract("gate-t01"), _contract("gate-t02"), _contract("gate-t03"), _contract("gate-t04"),
        _contract("gate-t05"), _contract("gate-t06", depends=["gate-t07"]), _contract("gate-t07"),
        _contract("gate-t08"),
    ], "docs/plans/gate/gate.md")
    for task_id, state in (("gate-t01", "failed"), ("gate-t02", "building"), ("gate-t03", "merged"),
                           ("gate-t04", "pr_open"), ("gate-t05", "abandoned"), ("gate-t08", "building")):
        db.update(task_id, status=state)
    db.claim("gate-t02", os.getpid())
    db.claim("gate-t08", _dead_pid())
    _add(db, [_contract("shut-t01")], "docs/plans/shut/shut.md")
    db.update("shut-t01", status="merged")
    db.close()
    recording = Recording()
    app = App(home, repo, launch=recording)

    assert _post(app, "run", {"target": "gate-t01"})[0] == 400
    refused = [
        ("gate-t02", "gate-t02 is building; it is already running"),
        ("gate-t08", "gate-t08 is building but its process is gone; check GitHub first, then run it again"),
        ("gate-t03", "gate-t03 is merged; nothing to run"),
        ("gate-t04", "gate-t04 has an open pull request; nothing to run"),
        ("gate-t05", "gate-t05 is on hold; take it off hold first, then run it"),
        ("gate-t06", "gate-t06 waits for gate-t07 (queued): each dependency needs a merged or an open PR"),
        ("shut", "Every task of shut is merged, on hold or has a pull request."),
        ("missing", "missing is neither a task on the board nor a plan"),
    ]
    for target, reason in refused:
        status, _, body = _post(app, "run", {"target": target, "max_cost": "5.00"})
        assert status == 409
        assert "Run refused." in body and html.escape(reason, quote=True) in body
    assert _post(app, "run", {"target": "gate-t01", "max_cost": "5.00", "token": "wrong"})[0] == 403
    assert recording.calls == [] and not (home / "web" / "jobs").exists()

    status, _, running = _get(app, "/run?task=gate-t02")
    assert status == 200
    assert "gate-t02 is building; it is already running" in running
    assert "<form" not in running


def test_missing_provider_keys_disable_start_run(home, repo, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    db = _board(home, [_contract("keys-t01")], "docs/plans/keys/keys.md")
    db.update("keys-t01", status="failed")
    db.close()
    app = App(home, repo)

    _, _, body = _get(app, "/run?plan=keys")
    assert "Set OPENROUTER_API_KEY first: the default flow's models need it." in body
    assert '<button class="btn btn-primary" disabled>Start run</button>' in body
    assert "factory run keys --max-cost 5.00 --parallel 3 --max-attempts 3" in body
    assert "at most $5.00 for each of 1 tasks, $5.00 in all." in body

    monkeypatch.setenv("OPENROUTER_API_KEY", "x")
    _, _, enabled = _get(app, "/run?plan=keys")
    assert "Set OPENROUTER_API_KEY first" not in enabled
    assert '<button class="btn btn-primary" disabled>Start run</button>' not in enabled
    assert '<button class="btn btn-primary">Start run</button>' in enabled

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    config_path = repo / ".factory/config.yaml"
    config_path.write_text(config_path.read_text() + '\nmodels: {plan: "anthropic:claude-opus-5-5"}\n')
    _, _, anthropic = _get(App(home, repo), "/run?plan=keys")
    assert "Set ANTHROPIC_API_KEY first: the default flow's models need it." in anthropic
    assert "Set OPENROUTER_API_KEY first" not in anthropic


def test_run_buttons_appear_where_a_run_would_do_something(home, repo):
    db = _board(home, [
        _contract("btn-t01"), _contract("btn-t02"), _contract("btn-t03"), _contract("btn-t04"),
        _contract("btn-t05"), _contract("btn-t06", depends=["btn-t01"]),
        _contract("btn-t07"), _contract("btn-t08"),
    ], "docs/plans/btn/btn.md")
    for task_id, state in (("btn-t01", "failed"), ("btn-t02", "conflict"), ("btn-t03", "ci_failed"),
                           ("btn-t04", "changes_requested"), ("btn-t07", "pr_open"),
                           ("btn-t08", "merged")):
        db.update(task_id, status=state)
    for number in (2, 3, 4, 7):
        db.update(f"btn-t{number:02d}", pr_url=f"https://github.test/pr/{number}")
    _add(db, [_contract("onlywait-t01", depends=["btn-t06"])], "docs/plans/onlywait/onlywait.md")
    _add(db, [_contract("onlyrun-t01"), _contract("onlyrun-t02", depends=["onlyrun-t01"])],
         "docs/plans/onlyrun/onlyrun.md")
    db.update("onlyrun-t01", status="building")
    db.claim("onlyrun-t01", os.getpid())
    _add(db, [_contract("doneplan-t01")], "docs/plans/doneplan/doneplan.md")
    db.update("doneplan-t01", status="merged")
    db.close()
    app = App(home, repo)

    _, _, board = _get(app)
    needs = re.search(r'<section class="block" aria-labelledby="h-you">(.*?)</section>', board, re.S).group(1)
    rows = re.findall(r'<li class="row">(.*?)</li>', needs, re.S)
    for number in (1, 2, 3, 4):
        task_id = f"btn-t{number:02d}"
        row = next(row for row in rows if f'>{task_id}</a>' in row)
        link = f'<a class="btn btn-primary" href="/run?task={task_id}">Run again</a>'
        assert link in row
        following = "Put on hold" if number == 1 else "Open pull request"
        assert row.index("Run again") < row.index(following)
    pr_row = next(row for row in rows if ">btn-t07</a>" in row)
    assert "Run again" not in pr_row

    def summary(name):
        return re.search(rf'<details class="plan" id="plan-{name}"[^>]*>(.*?)</summary>', board, re.S).group(1)

    assert '<a class="btn" href="/run?plan=btn">Run plan</a>' in summary("btn")
    for name in ("onlywait", "onlyrun", "doneplan"):
        assert "Run plan" not in summary(name)

    _, _, conflict = _get(app, "/tasks/btn-t02")
    assert '<a class="btn btn-primary" href="/run?task=btn-t02">Run again</a>' in conflict
    _, _, pr_open = _get(app, "/tasks/btn-t07")
    assert "Run again" not in pr_open
    _, _, running = _get(app, "/tasks/onlyrun-t01")
    assert "Run again" not in running
