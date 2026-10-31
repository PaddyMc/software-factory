"""`factory requeue`: failed or held tasks go back to queued; live, open and merged ones stay put."""

import os

from factory.cli import main
from factory.db import open_db


def test_requeue_moves_only_failed_and_abandoned_tasks(repo, home, monkeypatch, capsys):
    monkeypatch.chdir(repo)
    assert main(["sync"]) == 0
    db = open_db(home)
    db.update("demo-t01", status="failed", note="gates failed")
    db.update("demo-t02", status="abandoned", note="hold")
    assert main(["requeue", "demo-t01", "demo-t02"]) == 0
    assert [db.task(t)["status"] for t in ("demo-t01", "demo-t02")] == ["queued", "queued"]
    assert db.task("demo-t01")["note"] is None

    db.update("demo-t01", status="pr_open", pr_url="https://github.test/pr/1")
    db.update("demo-t02", status="building", pid=os.getpid())
    capsys.readouterr()
    assert main(["requeue", "demo-t01", "demo-t02", "nope-t01"]) == 1
    out = capsys.readouterr().out
    assert "demo-t01: pr_open; nothing to requeue" in out and "demo-t02: running (building" in out
    assert "nope-t01: not on the board" in out
    assert [db.task(t)["status"] for t in ("demo-t01", "demo-t02")] == ["pr_open", "building"]
