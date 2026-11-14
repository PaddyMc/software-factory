import multiprocessing as mp
import os
import sqlite3
import time
from pathlib import Path

import pytest

from factory import observe, pipeline
from factory.contracts import parse_text
from factory.db import DB, open_db
from factory.log import RunLog
from conftest import plan_text


@pytest.fixture
def db(tmp_path):
    d = open_db(tmp_path)
    yield d
    d.close()


def _tasks():
    return {t.id: t for t in parse_text(plan_text(), "docs/plans/demo/demo.md")}


def test_upsert_keeps_status_and_refreshes_contract(db):
    t1 = _tasks()["demo-t01"]
    db.upsert_task(t1)
    db.update(t1.id, status="pr_open", pr_url="u")
    db.upsert_task(t1)
    row = db.task(t1.id)
    assert row["status"] == "pr_open" and row["pr_url"] == "u"
    assert db.contract(t1.id) == t1


def test_dependencies_are_stacked_on_open_prs_or_merged(db):
    ts = _tasks()
    db.upsert_task(ts["demo-t02"])
    assert db.deps(ts["demo-t02"]) == ([], ["demo-t01 (not in factory)"])
    db.upsert_task(ts["demo-t01"])
    assert db.readiness("demo-t02") == "waits for demo-t01 (queued)" and not db.ready("demo-t02")
    db.update("demo-t01", status="pr_open", candidate_sha="abc")
    assert db.deps(ts["demo-t02"]) == (["demo-t01"], [])
    assert db.readiness("demo-t02") == "ready, stacks on demo-t01" and db.ready("demo-t02")
    db.update("demo-t01", status="merged")
    assert db.deps(ts["demo-t02"]) == ([], []) and db.readiness("demo-t02") == "ready"


def test_runs_are_recorded_in_order(db):
    db.upsert_task(_tasks()["demo-t01"])
    a = db.start_run("demo-t01", "plan", 0, "m")
    db.finish_run(a, "done", "the plan")
    b = db.start_run("demo-t01", "build", 1)
    db.finish_run(b, "committed", "built", sha="abc")
    runs = db.runs("demo-t01")
    assert [(r["role"], r["outcome"], r["sha"]) for r in runs] == [("plan", "done", None), ("build", "committed", "abc")]
    assert runs[0]["report"] == "the plan" and runs[0]["ended_at"]


def test_unknown_status_and_role_rejected(db):
    db.upsert_task(_tasks()["demo-t01"])
    with pytest.raises(ValueError):
        db.update("demo-t01", status="ready")
    with pytest.raises(ValueError):
        db.start_run("demo-t01", "deploy", 0)


def test_old_database_is_migrated(tmp_path):
    import sqlite3
    old = sqlite3.connect(tmp_path / "factory.db")
    old.executescript("""
        CREATE TABLE tasks (id TEXT PRIMARY KEY, plan TEXT NOT NULL, contract TEXT NOT NULL, status TEXT NOT NULL,
            branch TEXT, base_ref TEXT, base_sha TEXT, candidate_sha TEXT, pr_url TEXT,
            attempts INTEGER NOT NULL DEFAULT 0, note TEXT, updated_at TEXT NOT NULL);
        CREATE TABLE runs (id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL, role TEXT NOT NULL,
            attempt INTEGER NOT NULL, model TEXT, started_at TEXT NOT NULL, ended_at TEXT, outcome TEXT,
            sha TEXT, report TEXT);""")
    old.close()
    db = open_db(tmp_path)
    db.upsert_task(_tasks()["demo-t01"])
    run = db.start_run("demo-t01", "build", 1)
    db.progress("demo-t01", run, "build#1 step 3/120", 3, 1000, 200)
    assert db.task("demo-t01")["progress"] == "build#1 step 3/120"
    assert db.runs("demo-t01")[0]["tokens_in"] == 1000
    assert db.task("demo-t01")["reviews_addressed"] is None
    db.update("demo-t01", status="changes_requested", reviews_addressed=7)
    assert db.task("demo-t01")["reviews_addressed"] == 7


def _hammer_writer(path, task_id, run_id, number, seconds, results):
    who = f"writer-{number}"
    count = 0
    try:
        db = DB(Path(path))
        try:
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                db.heartbeat(task_id, f"[{who}] working")
                db.progress(task_id, run_id, f"{who} step {count}", count, count, count)
                count += 1
        finally:
            db.close()
    except Exception as e:
        results.put(("error", who, repr(e)))
    else:
        results.put(("done", who, count))


def _hammer_reader(home, seconds, results):
    count = 0
    try:
        root = Path(home)
        db = open_db(root)
        try:
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                observe.render_top(db, root, width=200)
                count += 1
        finally:
            db.close()
    except Exception as e:
        results.put(("error", "reader", repr(e)))
    else:
        results.put(("done", "reader", count))


def _hammer_opener(home, seconds, results):
    count = 0
    try:
        root = Path(home)
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            db = open_db(root)
            db.close()
            count += 1
    except Exception as e:
        results.put(("error", "opener", repr(e)))
    else:
        results.put(("done", "opener", count))


def test_the_board_opens_in_wal_mode_with_a_long_busy_timeout(tmp_path):
    path = tmp_path / "factory.db"
    db = DB(path)
    try:
        assert db.conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert db.conn.execute("PRAGMA busy_timeout").fetchone()[0] == 30000
        assert db.conn.execute("PRAGMA synchronous").fetchone()[0] == 1
    finally:
        db.close()

    plain = sqlite3.connect(path)
    try:
        assert plain.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    finally:
        plain.close()


def test_a_rollback_journal_board_is_switched_to_wal_on_open(tmp_path):
    path = tmp_path / "rollback.db"
    plain = sqlite3.connect(path)
    assert plain.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    plain.close()
    DB(path).close()
    plain = sqlite3.connect(path)
    try:
        assert plain.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    finally:
        plain.close()

    path = tmp_path / "locked.db"
    seed = DB(path)
    seed.upsert_task(_tasks()["demo-t01"])
    seed.start_run("demo-t01", "build", 1)
    seed.close()
    locked = sqlite3.connect(path)
    try:
        assert locked.execute("PRAGMA journal_mode=DELETE").fetchone()[0] == "delete"
        locked.execute("BEGIN IMMEDIATE")
        db = DB(path, timeout=0.2)
        try:
            assert db.conn.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
            assert db.task("demo-t01") is not None
        finally:
            db.close()
    finally:
        locked.rollback()
        locked.close()

    db = DB(path)
    try:
        assert db.conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    finally:
        db.close()


def test_parallel_writers_and_readers_never_see_a_locked_board(tmp_path):
    db = open_db(tmp_path)
    task = _tasks()["demo-t01"]
    db.upsert_task(task)
    db.update(task.id, status="building", attempts=1)
    db.claim(task.id, os.getpid())
    run = db.start_run(task.id, "build", 1)
    db.progress(task.id, run, "build#1 step 1/10", 1, 100, 10)
    db.heartbeat(task.id, "ready")
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs/demo-t01.log").write_text("00:00:01 [stage] building (build #1)\n")
    db.close()

    seconds = 3.0
    ctx = mp.get_context()
    results = ctx.Queue()
    processes = [
        ctx.Process(target=_hammer_writer,
                    args=(str(tmp_path / "factory.db"), task.id, run, number, seconds, results))
        for number in range(8)
    ]
    processes.extend([
        ctx.Process(target=_hammer_reader, args=(str(tmp_path), seconds, results)),
        ctx.Process(target=_hammer_opener, args=(str(tmp_path), seconds, results)),
    ])
    for process in processes:
        process.start()
    try:
        for process in processes:
            process.join(timeout=seconds + 30)
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
        for process in processes:
            process.join(timeout=5)

    assert [process.exitcode for process in processes] == [0] * len(processes)
    reports = [results.get(timeout=5) for _ in processes]
    results.close()
    results.join_thread()
    errors = [report for report in reports if report[0] == "error"]
    assert not errors, errors
    assert sum(report[2] for report in reports if report[1].startswith("writer-")) > 0

    db = open_db(tmp_path)
    try:
        activity = db.task(task.id)["activity"]
        assert activity is not None and activity.startswith("[writer-")
    finally:
        db.close()


def test_a_locked_heartbeat_is_skipped_and_the_run_carries_on(tmp_path):
    path = tmp_path / "factory.db"
    seed = DB(path)
    task = _tasks()["demo-t01"]
    seed.upsert_task(task)
    run = seed.start_run(task.id, "build", 1)
    seed.close()

    locked = sqlite3.connect(path)
    locked.execute("BEGIN EXCLUSIVE")
    db = DB(path, timeout=0.2)
    log = RunLog(tmp_path / "run.log", echo=False)
    try:
        assert db.heartbeat(task.id, "working") is False
        assert not db.conn.in_transaction
        assert db.progress(task.id, run, "build#1 step 3/20", 3, 100, 50) is False
        assert not db.conn.in_transaction
        assert db.task(task.id)["heartbeat_at"] is None
        with pytest.raises(sqlite3.OperationalError, match="database is locked"):
            db.update(task.id, note="x")
        db.conn.rollback()

        p = pipeline.Pipeline(db, roles=None, task=task, worktree=tmp_path, base_sha="a" * 40,
                              sandbox=None, opts=pipeline.Options(base_ref="main"), log=log)
        p.run_id = run
        p._event("stage", "building (build #1)")
        p._progress(3, 20, 100, 50)

        locked.rollback()
        locked.close()
        p._event("stage", "still here")
        assert db.heartbeat(task.id) is True
        assert db.progress(task.id, run, "build#1 step 4/20", 4, 120, 60) is True
        heartbeat_at = db.task(task.id)["heartbeat_at"]
    finally:
        locked.close()
        log.close()
        db.close()

    text = (tmp_path / "run.log").read_text()
    for expected in ("[stage] building (build #1)", "board busy: skipped a heartbeat",
                     "board busy: skipped a progress update", "[stage] still here"):
        assert expected in text
    assert heartbeat_at is not None
