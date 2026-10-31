"""Stacked PRs: building on several open PRs, and keeping a PR's base right as they merge."""

import json

import pytest

from factory import stack
from factory.contracts import parse_text
from factory.db import open_db
from factory.pipeline import PipelineError, create_worktree, replay_worktree
from conftest import TASK, git, plan_text


def _commit(repo, branch, path, text):
    git(repo, "checkout", "-q", "-b", branch, "main")
    (repo / path).write_text(text)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", branch)
    git(repo, "checkout", "-q", "main")
    return git(repo, "rev-parse", branch)


def test_stacking_on_two_open_prs_merges_them_into_the_base(repo, home):
    a = _commit(repo, "a", "a.txt", "a\n")
    b = _commit(repo, "b", "b.txt", "b\n")
    wt, base = create_worktree(repo, home, "demo-t03", a, (("demo-t02", b),))
    assert (wt / "a.txt").exists() and (wt / "b.txt").exists()
    assert git(wt, "rev-parse", "HEAD") == base and git(wt, "log", "-1", "--format=%s") == "factory: stack demo-t03 on demo-t02"


def test_conflicting_open_prs_cannot_be_stacked(repo, home):
    a = _commit(repo, "a", "same.txt", "a\n")
    b = _commit(repo, "b", "same.txt", "b\n")
    with pytest.raises(PipelineError, match="cannot stack demo-t03: its open dependencies conflict"):
        create_worktree(repo, home, "demo-t03", a, (("demo-t02", b),))
    assert not (home / "worktrees/demo-t03").exists()


def test_one_of_two_dependencies_merged_moves_the_pr_to_the_open_one(tmp_path, repo, fake_gh):
    db = open_db(tmp_path)
    three = TASK + TASK.replace("demo-t01", "demo-t03").replace("demo-t02", "demo-t04")
    for t in parse_text(plan_text(three.replace("depends_on: [demo-t03]", "depends_on: [demo-t01, demo-t03]")),
                        "docs/plans/demo/demo.md"):
        db.upsert_task(t)
    db.update("demo-t01", status="merged")
    db.update("demo-t03", status="pr_open", candidate_sha="c3", pr_url="https://github.test/pr/3")
    db.update("demo-t04", status="pr_open", candidate_sha="c4", pr_url="https://github.test/pr/4",
              base_ref="factory/demo-t01", stacked_on="demo-t01,demo-t03", trunk="main", base_sha="m")
    fake_gh.write_text(json.dumps({"calls": [], "prs": {"factory/demo-t04": {
        "url": "https://github.test/pr/4", "state": "OPEN", "base": "factory/demo-t01"}}}))
    assert stack.restack(db, repo, tmp_path, "demo-t04") == "demo-t04: PR now targets factory/demo-t03"
    assert db.task("demo-t04")["base_ref"] == "factory/demo-t03"
    assert json.loads(fake_gh.read_text())["prs"]["factory/demo-t04"]["base"] == "factory/demo-t03"
    assert stack.restack(db, repo, tmp_path, "demo-t04") is None


def _stacked_on_merged_dependency(tmp_path, repo, fake_gh, main_text):
    """demo-t01's PR edits shared.txt; demo-t02 is stacked on it and edits it again; then demo-t01 is
    squash-merged together with `main_text`, a further change to the same line."""
    git(repo, "checkout", "-q", "-b", "dep", "main")
    (repo / "shared.txt").write_text("dep\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "dep")
    dep = git(repo, "rev-parse", "HEAD")
    (repo / "shared.txt").write_text("dep + task\n")
    (repo / "task-only.txt").write_text("new\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "task")
    task = git(repo, "rev-parse", "HEAD")
    git(repo, "checkout", "-q", "main")
    (repo / "shared.txt").write_text(main_text)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "demo-t01 (#1) and more")
    git(repo, "push", "-q", "origin", "main")
    db = open_db(tmp_path)
    for t in parse_text(plan_text(TASK), "docs/plans/demo/demo.md"):
        db.upsert_task(t)
    db.update("demo-t01", status="merged", candidate_sha=dep)
    db.update("demo-t02", status="pr_open", candidate_sha=task, base_sha=dep, pr_url="https://github.test/pr/2",
              base_ref="factory/demo-t01", stacked_on="demo-t01", trunk="main")
    fake_gh.write_text(json.dumps({"calls": [], "prs": {"factory/demo-t02": {
        "url": "https://github.test/pr/2", "state": "OPEN", "base": "factory/demo-t01"}}}))
    return db, dep, task


def test_restack_conflict_marks_the_task_for_resolution(tmp_path, repo, fake_gh):
    db, dep, task = _stacked_on_merged_dependency(tmp_path, repo, fake_gh, "dep, then main\n")
    msg = stack.restack(db, repo, tmp_path, "demo-t02")
    assert msg == "demo-t02: retargeted to main; conflicts (`factory run demo-t02` resolves them)"
    row = db.task("demo-t02")
    assert row["status"] == "conflict" and row["base_ref"] == "main" and row["stacked_on"] is None
    assert row["candidate_sha"] == task and row["base_sha"] == dep          # what resolution replays
    state = json.loads(fake_gh.read_text())
    assert state["prs"]["factory/demo-t02"]["base"] == "main"
    assert any(c[0] == "api" and c[1].endswith("/issues/2/comments") for c in state["calls"])
    assert stack.restack(db, repo, tmp_path, "demo-t02") is None              # only pr_open rows restack


def test_replay_leaves_diff3_markers_and_a_brief(tmp_path, repo, fake_gh):
    db, dep, task = _stacked_on_merged_dependency(tmp_path, repo, fake_gh, "dep, then main\n")
    main = git(repo, "rev-parse", "main")
    wt, r = replay_worktree(repo, tmp_path, "demo-t02", dep, task, main, "main")
    assert r.conflicts == ("shared.txt",) and r.onto == "main" and r.old_candidate == task
    text = (wt / "shared.txt").read_text()
    assert text.startswith("<<<<<<< HEAD\ndep, then main\n||||||| ") and "=======\ndep + task\n>>>>>>> " in text
    assert (wt / "task-only.txt").read_text() == "new\n"                      # what merged cleanly is in place
    assert git(wt, "rev-parse", "HEAD") == main and git(wt, "diff", "--cached", "--name-only") == ""
    assert "- shared.txt" in r.brief and "+dep + task" in r.brief and "+dep, then main" in r.brief


def test_replay_without_conflicts_and_with_nothing_left(tmp_path, repo, fake_gh):
    db, dep, task = _stacked_on_merged_dependency(tmp_path, repo, fake_gh, "dep\n")    # plain squash merge
    main = git(repo, "rev-parse", "main")
    wt, r = replay_worktree(repo, tmp_path, "demo-t02", dep, task, main, "main")
    assert r.conflicts == () and r.brief == "" and (wt / "shared.txt").read_text() == "dep + task\n"
    git(repo, "worktree", "remove", "--force", str(wt))
    with pytest.raises(PipelineError, match="demo-t02's change is already on main"):
        replay_worktree(repo, tmp_path, "demo-t02", dep, dep, main, "main")
    assert not (tmp_path / "worktrees/demo-t02").exists()
