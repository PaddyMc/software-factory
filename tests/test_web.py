"""The read-only board, its loopback HTTP server, and the `factory web` command."""

import datetime as dt
import hashlib
import json
import os
import re
import socket
import socketserver
import sqlite3
import subprocess
import sys
import threading
import urllib.request
import webbrowser
from html.parser import HTMLParser

import pytest

from factory import observe
from factory.cli import main
from factory.contracts import parse_text
from factory.db import open_db
from factory.web import server as web_server
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


def _dead_pid():
    process = subprocess.Popen([sys.executable, "-c", "pass"])
    process.wait()
    return process.pid


def _get(app, path="/", headers=HOST, method="GET"):
    status, response_headers, body = app.handle(method, path, headers, b"")
    return status, dict(response_headers), body.decode()


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
    ids = re.findall(r'<span class="id">([^<]+)</span>', section)
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
        assert f'<span class="id">{task_id}</span>' not in section


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
    assert '<span class="plan-end"><span class="num">$3.50</span></span>' in mix
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
    assert "<form" not in body and "<button" not in body


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
