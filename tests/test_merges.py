"""End to end: refresh records what a human changed on a PR before merging it.

Everything is real (CLI, LangGraph, LangChain agents and tools, git, bwrap when present)
except the LLM (ScriptedModel) and GitHub (fake `gh` + a bare `origin`).
"""

import json
import shutil

import pytest

from factory import agents, merges
from factory.cli import main
from factory.db import open_db

from fake_model import ScriptedModel, scripts
from conftest import git

SKIP = "unit_tests,e2e_tests"   # the toy repo has no Cargo workspace
SANDBOX = [] if shutil.which("bwrap") else ["--no-sandbox"]
BRANCH = "factory/demo-t01"


@pytest.fixture
def factory_repo(repo, home, fake_gh, monkeypatch):
    agents_dir = repo / ".factory/agents"
    agents_dir.mkdir(parents=True)
    for role in ("planner", "builder", "reviewer", "verifier"):
        (agents_dir / f"{role}.md").write_text(f"---\nmodel: fake:{role}\nmax_steps: 20\n---\nYou are the {role.upper()} for one task.\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "agents")
    git(repo, "push", "-q", "origin", "main")
    monkeypatch.setenv("FAKE_API_KEY", "x")
    monkeypatch.setitem(agents.PROVIDER_KEYS, "fake", "FAKE_API_KEY")
    monkeypatch.chdir(repo)
    return repo


def _open_pr(factory_repo, home, fake_gh, monkeypatch):
    monkeypatch.setattr(agents, "build_model", lambda spec: ScriptedModel(plays=scripts(review_verdicts=["APPROVE"])))
    assert main(["run", "demo-t01", "--skip-gates", SKIP, *SANDBOX]) == 0
    return open_db(home).task("demo-t01")


def _pr(fake_gh, branch, **fields):
    state = json.loads(fake_gh.read_text())
    state["prs"][branch].update(fields)
    fake_gh.write_text(json.dumps(state))


def _human_clone(tmp_path):
    work = tmp_path / "human"
    git(tmp_path, "clone", "-q", str(tmp_path / "origin.git"), str(work))
    return work


def _checkout_pr(work):
    git(work, "checkout", "-q", "-B", BRANCH, f"origin/{BRANCH}")


def _merge_runs(db):
    return [r for r in db.runs("demo-t01") if r["role"] == "merge"]


def test_a_pr_merged_as_built_is_recorded_as_built(factory_repo, home, fake_gh, monkeypatch, capsys):
    row = _open_pr(factory_repo, home, fake_gh, monkeypatch)
    candidate = row["candidate_sha"]
    _pr(fake_gh, BRANCH, state="MERGED", commits=[{"oid": candidate}])

    assert main(["status", "--refresh"]) == 0
    db = open_db(home)
    assert db.task("demo-t01")["status"] == "merged"
    runs = _merge_runs(db)
    assert len(runs) == 1
    run = runs[0]
    assert run["attempt"] == 0 and run["outcome"] == "as_built" and run["sha"] == candidate
    assert all(run[k] is None for k in ("model", "prompt_version", "flow", "step"))

    assert main(["status", "--refresh"]) == 0
    assert len(_merge_runs(db)) == 1
    capsys.readouterr()
    assert main(["show", "demo-t01", "--role", "merge"]) == 0
    assert "## merge #0 — as_built" in capsys.readouterr().out


def test_commits_pushed_to_a_pr_before_merge_are_recorded_as_human_edits(
        factory_repo, home, fake_gh, monkeypatch, tmp_path):
    row = _open_pr(factory_repo, home, fake_gh, monkeypatch)
    candidate = row["candidate_sha"]
    work = _human_clone(tmp_path)
    _checkout_pr(work)
    (work / "src/greet.txt").write_text("hello there\n")
    git(work, "add", "src/greet.txt")
    git(work, "commit", "-q", "-m", "human: tweak the greeting")
    git(work, "push", "-q", "origin", f"HEAD:{BRANCH}")
    head = git(work, "rev-parse", "HEAD")
    assert head != candidate
    _pr(fake_gh, BRANCH, state="MERGED", commits=[{"oid": head}])

    assert main(["status", "--refresh"]) == 0
    runs = _merge_runs(open_db(home))
    assert len(runs) == 1
    assert runs[0]["outcome"] == "edited" and runs[0]["sha"] == head
    assert "human: tweak the greeting" in runs[0]["report"]
    assert "+hello there" in runs[0]["report"]


def test_updating_a_pr_from_its_base_is_not_a_human_edit(
        factory_repo, home, fake_gh, monkeypatch, tmp_path):
    row = _open_pr(factory_repo, home, fake_gh, monkeypatch)
    candidate = row["candidate_sha"]
    work = _human_clone(tmp_path)
    (work / "base.txt").write_text("new work on main\n")
    git(work, "add", "base.txt")
    git(work, "commit", "-q", "-m", "other work on main")
    git(work, "push", "-q", "origin", "main")
    git(work, "fetch", "-q", "origin", "main")
    _checkout_pr(work)
    git(work, "merge", "-q", "--no-edit", "origin/main")
    git(work, "push", "-q", "origin", f"HEAD:{BRANCH}")
    head = git(work, "rev-parse", "HEAD")
    assert head != candidate and len(git(work, "rev-list", "--parents", "-n", "1", head).split()) == 3
    _pr(fake_gh, BRANCH, state="MERGED", commits=[{"oid": head}])

    assert main(["status", "--refresh"]) == 0
    runs = _merge_runs(open_db(home))
    assert len(runs) == 1
    assert runs[0]["outcome"] == "as_built" and runs[0]["sha"] == head


def test_a_rewritten_pr_head_is_recorded_as_edited_with_its_diff(
        factory_repo, home, fake_gh, monkeypatch, tmp_path):
    row = _open_pr(factory_repo, home, fake_gh, monkeypatch)
    candidate = row["candidate_sha"]
    work = _human_clone(tmp_path)
    _checkout_pr(work)
    (work / "src/greet.txt").write_text("a rewritten greeting\n")
    git(work, "add", "src/greet.txt")
    git(work, "commit", "-q", "--amend", "--no-edit")
    git(work, "push", "-q", "--force", "origin", f"HEAD:{BRANCH}")
    head = git(work, "rev-parse", "HEAD")
    assert head != candidate
    git(work, "push", "-q", "origin", "--delete", BRANCH)
    number = row["pr_url"].rsplit("/", 1)[1]
    git(tmp_path / "origin.git", "update-ref", f"refs/pull/{number}/head", head)
    _pr(fake_gh, BRANCH, state="MERGED", commits=[{"oid": head}])

    assert main(["status", "--refresh"]) == 0
    runs = _merge_runs(open_db(home))
    assert len(runs) == 1
    assert runs[0]["outcome"] == "edited" and runs[0]["sha"] == head
    assert "head was rewritten" in runs[0]["report"]
    assert "src/greet.txt" in runs[0]["report"]


def test_a_merge_whose_final_head_cant_be_read_records_nothing(
        factory_repo, home, fake_gh, monkeypatch, tmp_path, capsys):
    _open_pr(factory_repo, home, fake_gh, monkeypatch)
    work = _human_clone(tmp_path)
    _checkout_pr(work)
    (work / "human.txt").write_text("a human edit\n")
    git(work, "add", "human.txt")
    git(work, "commit", "-q", "-m", "human: edit before merging")
    git(work, "push", "-q", "origin", f"HEAD:{BRANCH}")
    head = git(work, "rev-parse", "HEAD")
    git(work, "push", "-q", "origin", "--delete", BRANCH)
    _pr(fake_gh, BRANCH, state="MERGED", commits=[{"oid": head}])
    capsys.readouterr()

    assert main(["status", "--refresh"]) == 0
    captured = capsys.readouterr()
    assert "demo-t01: merged; can't tell whether it was changed before merging" in captured.err
    assert "couldn't fetch factory/demo-t01 or refs/pull/1/head" in captured.err
    db = open_db(home)
    assert db.task("demo-t01")["status"] == "merged"
    assert _merge_runs(db) == []

    merges.record(db, factory_repo, db.task("demo-t01"), None)
    assert "demo-t01: merged; can't tell whether it was changed before merging (gh gave no head" \
        in capsys.readouterr().err
    assert _merge_runs(db) == []
