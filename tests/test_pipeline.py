"""End to end: `factory run` -> worktree -> plan/build/review/verify agents -> gates -> push -> PR -> db.

Everything is real (CLI, LangGraph, LangChain agents and tools, git, bwrap when present)
except the LLM (ScriptedModel) and GitHub (fake `gh` + a bare `origin`).
"""

import json
import shutil

import pytest

from factory import agents
from factory.cli import main
from factory.db import open_db
from fake_model import ScriptedModel, scripts
from conftest import git

SKIP = "unit_tests,e2e_tests"   # the toy repo has no Cargo workspace
SANDBOX = [] if shutil.which("bwrap") else ["--no-sandbox"]


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


def _use_model(monkeypatch, plays):
    monkeypatch.setattr(agents, "build_model", lambda spec: ScriptedModel(plays=plays))
    return plays["_calls"]


def test_run_ends_in_a_working_pr(factory_repo, home, fake_gh, monkeypatch, capsys):
    calls = _use_model(monkeypatch, scripts(review_verdicts=["CHANGES", "APPROVE"]))
    assert main(["run", "demo-t01", "--skip-gates", SKIP, *SANDBOX]) == 0

    db = open_db(home)
    row = db.task("demo-t01")
    assert row["status"] == "pr_open" and row["attempts"] == 2      # review sent it back once
    assert row["pr_url"] == "https://github.test/pr/1"
    roles = [(r["role"], r["outcome"]) for r in db.runs("demo-t01")]
    assert roles == [("plan", "done"), ("build", "committed"), ("review", "CHANGES"),
                     ("build", "no-changes"), ("review", "APPROVE"), ("verify", "pass"),
                     ("verify", "report"), ("pr", "opened")]
    assert {r for r, _ in calls} == {"PLANNER", "BUILDER", "REVIEWER", "VERIFIER"}

    # The branch on origin is exactly the verified candidate, and it stayed in scope.
    candidate = row["candidate_sha"]
    assert git(factory_repo, "ls-remote", "origin", "refs/heads/factory/demo-t01").split()[0] == candidate
    changed = git(factory_repo, "diff", "--name-only", f"{row['base_sha']}..{candidate}").split()
    assert sorted(changed) == ["crates/e2e/tests/greet.rs", "docs/sessions/2026-10-09.md", "src/greet.txt"]

    pr = json.loads(fake_gh.read_text())["prs"]["factory/demo-t01"]
    assert pr["base"] == "main" and pr["title"].startswith("demo-t01:")
    assert "| verification | PASS |" in pr["body"] and candidate in pr["body"] and "VERDICT: APPROVE" in pr["body"]

    # Merging the PR is the human gate; the board picks it up.
    state = json.loads(fake_gh.read_text())
    state["prs"]["factory/demo-t01"]["state"] = "MERGED"
    fake_gh.write_text(json.dumps(state))
    assert main(["status", "--refresh"]) == 0
    assert open_db(home).task("demo-t01")["status"] == "merged"
    assert "demo-t01" in capsys.readouterr().out


def test_rerun_after_closed_pr_opens_a_new_one(factory_repo, home, fake_gh, monkeypatch):
    # A previous run left a branch on origin and a PR that was since closed.
    git(factory_repo, "push", "-q", "origin", "main:refs/heads/factory/demo-t01")
    git(factory_repo, "fetch", "-q", "origin")
    fake_gh.write_text(json.dumps({"calls": [], "prs": {"factory/demo-t01": {
        "url": "https://github.test/pr/9", "state": "CLOSED", "base": "main", "title": "old", "body": "old"}}}))

    _use_model(monkeypatch, scripts(review_verdicts=["APPROVE"]))
    assert main(["run", "demo-t01", "--skip-gates", SKIP, *SANDBOX]) == 0
    row = open_db(home).task("demo-t01")
    assert row["status"] == "pr_open" and row["pr_url"] != "https://github.test/pr/9"
    assert git(factory_repo, "ls-remote", "origin", "refs/heads/factory/demo-t01").split()[0] == row["candidate_sha"]
    calls = json.loads(fake_gh.read_text())["calls"]
    assert any(c[:2] == ["pr", "create"] for c in calls) and not any(c[:2] == ["pr", "edit"] for c in calls)


def test_gate_failures_never_open_a_pr(factory_repo, home, fake_gh, monkeypatch):
    _use_model(monkeypatch, scripts(review_verdicts=[], greeting="bye"))   # verification grep fails every time
    assert main(["run", "demo-t01", "--skip-gates", SKIP, "--max-attempts", "2", *SANDBOX]) == 1
    row = open_db(home).task("demo-t01")
    assert row["status"] == "failed" and row["pr_url"] is None and "verification" in row["note"]
    assert not fake_gh.exists() or "factory/demo-t01" not in json.loads(fake_gh.read_text())["prs"]
    assert git(factory_repo, "ls-remote", "origin", "refs/heads/factory/demo-t01") == ""


def test_rerun_requires_clean_and_respects_dependencies(factory_repo, home, monkeypatch, capsys):
    _use_model(monkeypatch, scripts(review_verdicts=[], greeting="bye"))
    assert main(["run", "demo-t02", *SANDBOX]) == 1
    assert "depends on unmerged tasks: demo-t01" in capsys.readouterr().err
    assert main(["run", "demo-t01", "--skip-gates", SKIP, "--max-attempts", "1", "--no-pr", *SANDBOX]) == 1
    assert main(["run", "demo-t01", "--no-pr", *SANDBOX]) == 1
    assert "factory clean demo-t01" in capsys.readouterr().err
    assert main(["clean", "demo-t01"]) == 0
    assert not (home / "worktrees/demo-t01").exists()


def test_show_prints_reports(factory_repo, home, fake_gh, monkeypatch, capsys):
    _use_model(monkeypatch, scripts(review_verdicts=["APPROVE"]))
    assert main(["run", "demo-t01", "--skip-gates", SKIP, *SANDBOX]) == 0
    capsys.readouterr()
    assert main(["show", "demo-t01", "--role", "review"]) == 0
    out = capsys.readouterr().out
    assert "## review #1 — APPROVE" in out and "VERDICT: APPROVE" in out


def test_run_refuses_without_provider_key(factory_repo, home, monkeypatch, capsys):
    monkeypatch.delenv("FAKE_API_KEY")
    assert main(["run", "demo-t01", *SANDBOX]) == 1
    assert "set FAKE_API_KEY first" in capsys.readouterr().err
    assert not (home / "worktrees/demo-t01").exists()


def test_live_log_and_progress(factory_repo, home, fake_gh, monkeypatch, capsys):
    _use_model(monkeypatch, scripts(review_verdicts=["APPROVE"]))
    assert main(["run", "demo-t01", "--skip-gates", SKIP, *SANDBOX]) == 0
    echoed = capsys.readouterr().out
    log = (home / "logs/demo-t01.log").read_text()
    assert log.splitlines()[0].split("] ", 1)[1].startswith("=== demo-t01: worktree")
    for expected in ("[stage] planning (plan #0)", "[build#1] → write_file(path=src/greet.txt)",
                     "[build#1] ← ⚠ write_file: refused: write to README.md is outside allowed_paths",
                     "[build#1] ← run: exit 0", "[review#1] says:", "VERDICT: APPROVE",
                     "[gate] PASS verification", "[gate] skip unit_tests", "[stage] pr_open: https://github.test/pr/1"):
        assert expected in log, expected
    assert "[build#1] → write_file" in echoed            # echoed live to the run's terminal

    assert main(["logs", "demo-t01", "-n", "1"]) == 0
    assert capsys.readouterr().out.strip().endswith("pr_open: https://github.test/pr/1")
    assert main(["logs", "demo-t01", "-f"]) == 0          # run is over: prints everything, then stops
    assert "stopped following" in capsys.readouterr().out

    db = open_db(home)
    build = next(r for r in db.runs("demo-t01") if r["role"] == "build")
    assert build["steps"] == 6                             # 5 tool calls + final message
    assert db.task("demo-t01")["progress"] is None         # cleared when the run ends


def test_status_shows_live_progress_while_running(factory_repo, home, fake_gh, monkeypatch):
    seen = []
    from factory import pipeline
    real = pipeline.Pipeline._progress

    def spy(self, *args):
        real(self, *args)
        seen.append(self.db.task("demo-t01")["progress"])
    monkeypatch.setattr(pipeline.Pipeline, "_progress", spy)
    _use_model(monkeypatch, scripts(review_verdicts=["APPROVE"]))
    assert main(["run", "demo-t01", "--skip-gates", SKIP, *SANDBOX]) == 0
    assert "plan#0 step 1/20 · 0k in / 0k out" in seen
    assert any(p.startswith("build#1 step 6/20") for p in seen)


def test_sync_loads_backlog_with_readiness(factory_repo, home, capsys):
    assert main(["sync"]) == 0
    out = capsys.readouterr().out
    assert "synced 2 tasks from the plans: 2 added, 0 updated" in out and "ready to run: demo-t01" in out
    assert main(["status"]) == 0
    status = capsys.readouterr().out
    assert "demo-t01" in status and "queued" in status and "ready" in status
    assert "waits for demo-t01 (queued)" in status
    assert main(["sync"]) == 0                             # idempotent
    assert "0 added, 0 updated" in capsys.readouterr().out
    db = open_db(home)
    db.update("demo-t01", status="merged")
    assert db.readiness("demo-t02") == "ready"


def test_transcript_records_every_message(factory_repo, home, fake_gh, monkeypatch, capsys):
    _use_model(monkeypatch, scripts(review_verdicts=["APPROVE"]))
    assert main(["run", "demo-t01", "--skip-gates", SKIP, *SANDBOX]) == 0
    capsys.readouterr()
    assert main(["transcript", "demo-t01", "--role", "build"]) == 0
    out = capsys.readouterr().out
    assert "=== build #1 — committed" in out and "1 refused" in out
    assert '"content": "hello\\n"' in out                    # full tool arguments, not clipped
    assert "[⚠ tool write_file]" in out and "outside allowed_paths" in out
    assert "[task message]" in out and "# Plan" in out
    assert main(["transcript", "demo-t01", "--all"]) == 0
    assert out.count("===") < capsys.readouterr().out.count("===")
    build = next(r for r in open_db(home).runs("demo-t01") if r["role"] == "build")
    assert build["refused"] == 1 and build["transcript"].endswith("-build-1.jsonl")


def test_no_progress_stops_before_max_attempts(factory_repo, home, fake_gh, monkeypatch):
    _use_model(monkeypatch, scripts(review_verdicts=[], greeting="bye"))   # identical gate failure every time
    assert main(["run", "demo-t01", "--skip-gates", SKIP, "--max-attempts", "5", *SANDBOX]) == 1
    row = open_db(home).task("demo-t01")
    assert row["attempts"] == 2 and row["note"].startswith("no progress (same failure twice): Verification gates failed: verification")
    assert "no progress" in (home / "logs/demo-t01.log").read_text()


def test_run_refuses_contract_without_e2e_path(factory_repo, home, monkeypatch, capsys):
    plan = factory_repo / "docs/plans/demo/demo.md"
    plan.write_text(plan.read_text().replace('allowed_paths: ["src/**", "crates/e2e/tests/**"]', 'allowed_paths: ["src/**"]'))
    _use_model(monkeypatch, scripts(review_verdicts=["APPROVE"]))
    assert main(["run", "demo-t01", *SANDBOX]) == 1
    assert "cannot pass the e2e_written gate" in capsys.readouterr().err
    assert not (home / "worktrees/demo-t01").exists()
    assert main(["validate-plan", "docs/plans/demo/demo.md"]) == 0
    assert "warn: demo-t01 is not factory-runnable" in capsys.readouterr().out


def test_max_cost_aborts_a_run(factory_repo, home, fake_gh, monkeypatch):
    from factory import prices
    monkeypatch.setattr(prices, "cost", lambda spec, tin, tout, cache_read=0: 0.40)   # every model call costs $0.40
    _use_model(monkeypatch, scripts(review_verdicts=["APPROVE"]))
    with pytest.raises(Exception, match="cost limit exceeded"):
        main(["run", "demo-t01", "--skip-gates", SKIP, "--max-cost", "1.0", *SANDBOX])
    row = open_db(home).task("demo-t01")
    assert row["status"] == "failed" and "cost limit exceeded" in row["note"] and row["pr_url"] is None


def test_cli_scheduler_mode_requires_keys_and_known_tasks(factory_repo, home, monkeypatch, capsys):
    assert main(["run", "demo-t01", "nope-t99"]) == 1
    assert "unknown task(s): nope-t99" in capsys.readouterr().err
    monkeypatch.delenv("FAKE_API_KEY")
    assert main(["run", "--ready"]) == 1
    assert "set FAKE_API_KEY first" in capsys.readouterr().err


def test_retry_requeues_failed_tasks(factory_repo, home, monkeypatch, capsys):
    _use_model(monkeypatch, scripts(review_verdicts=[], greeting="bye"))
    assert main(["run", "demo-t01", "--skip-gates", SKIP, "--max-attempts", "1", "--no-pr", *SANDBOX]) == 1
    assert open_db(home).task("demo-t01")["status"] == "failed" and (home / "worktrees/demo-t01").exists()
    capsys.readouterr()

    monkeypatch.setattr("factory.scheduler.run", lambda *a, **k: {})
    assert main(["run", "demo-t01", "demo-t02"]) == 0
    assert "skipping demo-t01 (failed): only queued tasks start (`factory retry`" in capsys.readouterr().err

    assert main(["retry"]) == 0
    assert "requeued 1: demo-t01" in capsys.readouterr().out
    row = open_db(home).task("demo-t01")
    assert row["status"] == "queued" and row["note"] is None and not (home / "worktrees/demo-t01").exists()
    assert main(["retry"]) == 0 and "nothing to retry" in capsys.readouterr().out
    assert main(["retry", "demo-t01"]) == 1 and "demo-t01 is queued" in capsys.readouterr().err
