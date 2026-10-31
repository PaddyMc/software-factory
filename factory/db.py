"""Local task database (SQLite). The only place task state lives.

tasks: one row per contract that has entered the factory.
runs:  one row per role invocation (plan/build/review/verify/pr, and resolve/ci), with its report.
"""

from __future__ import annotations

import datetime as dt
import os
import sqlite3
from pathlib import Path

from .contracts import Task

STATUSES = ("queued", "planning", "building", "reviewing", "verifying", "pr_open", "conflict", "ci_failed", "merged",
            "failed", "abandoned")
ROLES = ("plan", "build", "resolve", "ci", "review", "verify", "pr")
ACTIVE = ("planning", "building", "reviewing", "verifying")

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id            TEXT PRIMARY KEY,
    plan          TEXT NOT NULL,
    contract      TEXT NOT NULL,
    status        TEXT NOT NULL,
    branch        TEXT,
    base_ref      TEXT,
    base_sha      TEXT,
    candidate_sha TEXT,
    pr_url        TEXT,
    attempts      INTEGER NOT NULL DEFAULT 0,
    note          TEXT,
    progress      TEXT,
    updated_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id    TEXT NOT NULL REFERENCES tasks(id),
    role       TEXT NOT NULL,
    attempt    INTEGER NOT NULL,
    model      TEXT,
    started_at TEXT NOT NULL,
    ended_at   TEXT,
    outcome    TEXT,
    sha        TEXT,
    report     TEXT,
    steps      INTEGER NOT NULL DEFAULT 0,
    tokens_in  INTEGER NOT NULL DEFAULT 0,
    tokens_out INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS runs_task ON runs(task_id, id);
"""
# Columns added after the first release; ALTERed into older databases on open.
MIGRATIONS = {
    "tasks": [("progress", "TEXT"), ("pid", "INTEGER"), ("started_at", "TEXT"), ("heartbeat_at", "TEXT"),
              ("activity", "TEXT"), ("cost_usd", "REAL"), ("trunk", "TEXT"), ("stacked_on", "TEXT")],
    "runs": [("steps", "INTEGER NOT NULL DEFAULT 0"), ("tokens_in", "INTEGER NOT NULL DEFAULT 0"),
             ("tokens_out", "INTEGER NOT NULL DEFAULT 0"), ("cost_usd", "REAL"),
             ("refused", "INTEGER NOT NULL DEFAULT 0"), ("transcript", "TEXT")],
}


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


class DB:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        for table, cols in MIGRATIONS.items():
            have = {r["name"] for r in self.conn.execute(f"PRAGMA table_info({table})")}
            for name, decl in cols:
                if name not in have:
                    self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # ------------------------------------------------------------ tasks

    def upsert_task(self, task: Task) -> None:
        """Insert a task as queued, or refresh its contract (status untouched)."""
        self.conn.execute(
            "INSERT INTO tasks (id, plan, contract, status, updated_at) VALUES (?, ?, ?, 'queued', ?) "
            "ON CONFLICT(id) DO UPDATE SET plan=excluded.plan, contract=excluded.contract, updated_at=excluded.updated_at",
            (task.id, task.plan, task.to_json(), now()))
        self.conn.commit()

    def update(self, task_id: str, **fields) -> None:
        if "status" in fields and fields["status"] not in STATUSES:
            raise ValueError(f"unknown status {fields['status']!r}")
        cols = ", ".join(f"{k}=?" for k in fields)
        self.conn.execute(f"UPDATE tasks SET {cols}, updated_at=? WHERE id=?", (*fields.values(), now(), task_id))
        self.conn.commit()

    def task(self, task_id: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()

    def tasks(self) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM tasks ORDER BY id").fetchall()

    def contract(self, task_id: str) -> Task:
        row = self.task(task_id)
        if row is None:
            raise KeyError(task_id)
        return Task.from_json(row["contract"])

    def deps(self, task: Task) -> tuple[list[str], list[str]]:
        """(open, unmet): dependencies with an open PR, which a dependent is built on top of (stacked),
        and dependencies with neither a merged nor an open PR, annotated with their status."""
        open_, unmet = [], []
        for d in task.depends_on:
            row = self.task(d)
            if row is not None and row["status"] == "merged":
                continue
            if row is not None and row["status"] == "pr_open" and row["candidate_sha"]:
                open_.append(d)
            else:
                unmet.append(f"{d} ({row['status'] if row else 'not in factory'})")
        return open_, unmet

    def ready(self, task_id: str) -> bool:
        """Every dependency is merged or has an open PR to build on."""
        return not self.deps(self.contract(task_id))[1]

    # ------------------------------------------------------------ runs

    def start_run(self, task_id: str, role: str, attempt: int, model: str | None = None) -> int:
        if role not in ROLES:
            raise ValueError(f"unknown role {role!r}")
        cur = self.conn.execute(
            "INSERT INTO runs (task_id, role, attempt, model, started_at) VALUES (?, ?, ?, ?, ?)",
            (task_id, role, attempt, model, now()))
        self.conn.commit()
        return cur.lastrowid

    def finish_run(self, run_id: int, outcome: str, report: str = "", sha: str | None = None) -> None:
        self.conn.execute("UPDATE runs SET ended_at=?, outcome=?, report=?, sha=? WHERE id=?",
                          (now(), outcome, report, sha, run_id))
        self.conn.commit()

    def progress(self, task_id: str, run_id: int, text: str, steps: int, tokens_in: int, tokens_out: int,
                 cost_usd: float | None = None, refused: int = 0) -> None:
        """Live progress of the running role: shown by `factory status` and `factory top`."""
        self.conn.execute("UPDATE runs SET steps=?, tokens_in=?, tokens_out=?, cost_usd=?, refused=? WHERE id=?",
                          (steps, tokens_in, tokens_out, cost_usd, refused, run_id))
        self.conn.execute(
            "UPDATE tasks SET progress=?, cost_usd=(SELECT SUM(cost_usd) FROM runs WHERE task_id=?), "
            "heartbeat_at=?, updated_at=? WHERE id=?", (text, task_id, now(), now(), task_id))
        self.conn.commit()

    def heartbeat(self, task_id: str, activity: str | None = None) -> None:
        """Last sign of life from the running `factory run` process (+ what it was doing)."""
        if activity is None:
            self.conn.execute("UPDATE tasks SET heartbeat_at=? WHERE id=?", (now(), task_id))
        else:
            self.conn.execute("UPDATE tasks SET heartbeat_at=?, activity=? WHERE id=?", (now(), activity[:500], task_id))
        self.conn.commit()

    def claim(self, task_id: str, pid: int) -> None:
        """Record the process that is running this task (liveness is checked against it)."""
        self.conn.execute("UPDATE tasks SET pid=?, started_at=?, heartbeat_at=?, activity=NULL WHERE id=?",
                          (pid, now(), now(), task_id))
        self.conn.commit()

    def sync(self, tasks: dict[str, Task]) -> tuple[list[str], list[str], list[str]]:
        """Load every contract: new ones become queued, known ones get their contract refreshed
        (status untouched). Returns (added, updated, orphaned) task ids; orphaned = in the db
        but no longer in any plan."""
        added, updated = [], []
        for t in tasks.values():
            row = self.task(t.id)
            if row is None:
                added.append(t.id)
            elif row["contract"] != t.to_json():
                updated.append(t.id)
            self.upsert_task(t)
        orphaned = [r["id"] for r in self.tasks() if r["id"] not in tasks]
        return added, updated, orphaned

    def readiness(self, task_id: str) -> str:
        """For a queued/failed task: 'ready', 'ready, stacks on <open PRs>', or what it waits for."""
        open_, unmet = self.deps(self.contract(task_id))
        if unmet:
            return "waits for " + ", ".join(unmet)
        return "ready" + (", stacks on " + ", ".join(open_) if open_ else "")

    def runs(self, task_id: str) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM runs WHERE task_id=? ORDER BY id", (task_id,)).fetchall()

    def last_report(self, task_id: str, role: str, outcome: str) -> str:
        """The newest report of `role` that ended with `outcome`, e.g. the plan a PR was built from."""
        row = self.conn.execute("SELECT report FROM runs WHERE task_id=? AND role=? AND outcome=? ORDER BY id DESC",
                                (task_id, role, outcome)).fetchone()
        return (row["report"] or "") if row else ""


def open_db(home: Path) -> DB:
    return DB(home / "factory.db")


def pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def seconds_since(ts: str | None) -> float | None:
    if not ts:
        return None
    return (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(ts)).total_seconds()
