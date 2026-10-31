import pytest

from factory.contracts import parse_text
from factory.db import open_db
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
