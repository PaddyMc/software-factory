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
from langchain_core.messages import AIMessage

from fake_model import ScriptedModel, call, scripts
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


def test_rerun_replaces_a_finished_run_and_dependencies_need_a_pr(factory_repo, home, monkeypatch, capsys):
    _use_model(monkeypatch, scripts(review_verdicts=[], greeting="bye"))
    assert main(["run", "demo-t02", *SANDBOX]) == 1
    assert "demo-t02 waits for demo-t01 (not in factory): each dependency needs a merged or an open PR" in capsys.readouterr().err
    assert main(["run", "demo-t01", "--skip-gates", SKIP, "--max-attempts", "1", "--no-pr", *SANDBOX]) == 1
    assert open_db(home).task("demo-t01")["status"] == "failed" and (home / "worktrees/demo-t01").exists()
    first = open_db(home).runs("demo-t01")[-1]["id"]
    assert main(["run", "demo-t01", "--skip-gates", SKIP, "--max-attempts", "1", "--no-pr", *SANDBOX]) == 1
    assert open_db(home).runs("demo-t01")[-1]["id"] > first       # ran again in a fresh worktree
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
                     "[build#1] ← ⚠ write_file: refused: write to .git/config: git internals are off limits",
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
    assert "[⚠ tool write_file]" in out and "git internals are off limits" in out
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


def test_run_refuses_a_manual_contract(factory_repo, home, monkeypatch, capsys):
    plan = factory_repo / "docs/plans/demo/demo.md"
    plan.write_text(plan.read_text().replace('verification: ["grep -q hello src/greet.txt"]',
                                             'verification: ["terraform -chdir=infra apply -auto-approve"]'))
    _use_model(monkeypatch, scripts(review_verdicts=["APPROVE"]))
    assert main(["run", "demo-t01", *SANDBOX]) == 1
    assert "which the factory refuses; run it by hand" in capsys.readouterr().err
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


def test_run_target_is_a_task_or_a_plan(factory_repo, home, monkeypatch, capsys):
    assert main(["run", "nope-t99"]) == 2
    assert "nope-t99 is neither a task id nor a plan" in capsys.readouterr().err
    seen = {}
    monkeypatch.setattr("factory.scheduler.run", lambda db, plan, launch: seen.setdefault("plan", plan) and {})
    for target in ("demo", "docs/plans/demo/demo.md"):
        assert main(["run", target, "--parallel", "2", "--network-for", "demo-t02", "--max-cost", "4"]) == 0
        plan = seen.pop("plan")
        assert plan.name == "demo" and plan.tasks == ["demo-t01", "demo-t02"] and plan.parallel == 2
        assert plan.network_for == ("demo-t02",) and plan.child_args[:2] == ["--max-cost", "4.0"]
    assert "plan demo  ··  0/2 merged · 1 ready · 1 waiting" in capsys.readouterr().out
    monkeypatch.delenv("FAKE_API_KEY")
    assert main(["run", "demo"]) == 1
    assert "set FAKE_API_KEY first" in capsys.readouterr().err


SECOND = "#[test]\nfn second_e2e() {\n    assert!(true);\n}\n"


def test_dependent_stacks_on_an_open_pr_and_moves_to_main_after_merge(factory_repo, home, fake_gh, monkeypatch, capsys):
    _use_model(monkeypatch, scripts(review_verdicts=["APPROVE"]))
    assert main(["run", "demo-t01", "--skip-gates", SKIP, *SANDBOX]) == 0
    t01 = open_db(home).task("demo-t01")["candidate_sha"]

    plays = scripts(review_verdicts=["APPROVE"])
    plays["BUILDER"] = [call("write_file", path="crates/e2e/tests/second.rs", content=SECOND),
                        call("write_file", path="docs/sessions/2026-10-09.md",
                             content="## [12:00] demo-t01\n## [12:05] demo-t02\n"),
                        AIMessage("Second thing.\nRESULT: DONE")]
    _use_model(monkeypatch, plays)
    assert main(["run", "demo-t02", "--skip-gates", SKIP, *SANDBOX]) == 0

    db = open_db(home)
    row = db.task("demo-t02")
    assert row["status"] == "pr_open" and row["stacked_on"] == "demo-t01" and row["trunk"] == "main"
    assert row["base_ref"] == "factory/demo-t01" and row["base_sha"] == t01
    assert git(factory_repo, "show", f"{row['candidate_sha']}:src/greet.txt") == "hello"     # built on demo-t01
    assert sorted(git(factory_repo, "diff", "--name-only", f"{t01}..{row['candidate_sha']}").split()) == \
        ["crates/e2e/tests/second.rs", "docs/sessions/2026-10-09.md"]                       # its own changes only
    pr = json.loads(fake_gh.read_text())["prs"]["factory/demo-t02"]
    assert pr["base"] == "factory/demo-t01" and "**Stacked** on demo-t01 (https://github.test/pr/1)" in pr["body"]
    assert "| plan_untouched | PASS |" in pr["body"]

    # A human squash-merges demo-t01; the refresh moves demo-t02 onto main.
    git(factory_repo, "merge", "-q", "--squash", t01)
    git(factory_repo, "commit", "-q", "-m", "demo-t01 (#1)")
    git(factory_repo, "push", "-q", "origin", "main")
    state = json.loads(fake_gh.read_text())
    state["prs"]["factory/demo-t01"]["state"] = "MERGED"
    fake_gh.write_text(json.dumps(state))
    capsys.readouterr()
    assert main(["status", "--refresh"]) == 0
    assert "demo-t02: rebased onto main, PR retargeted" in capsys.readouterr().err

    row = open_db(home).task("demo-t02")
    main_sha = git(factory_repo, "rev-parse", "origin/main")
    assert row["base_ref"] == "main" and row["stacked_on"] is None and row["base_sha"] == main_sha
    assert git(factory_repo, "rev-parse", f"{row['candidate_sha']}^") == main_sha
    assert git(factory_repo, "ls-remote", "origin", "refs/heads/factory/demo-t02").split()[0] == row["candidate_sha"]
    assert sorted(git(factory_repo, "diff", "--name-only", f"{main_sha}..{row['candidate_sha']}").split()) == \
        ["crates/e2e/tests/second.rs", "docs/sessions/2026-10-09.md"]
    state = json.loads(fake_gh.read_text())
    assert state["prs"]["factory/demo-t02"]["base"] == "main"
    assert any(c[0] == "api" and c[1].endswith("/issues/2/comments") for c in state["calls"])
    assert main(["status", "--refresh"]) == 0 and "demo-t02:" not in capsys.readouterr().err    # idempotent


def _push_to_main(repo, path, text, message):
    (repo / path).parent.mkdir(parents=True, exist_ok=True)
    (repo / path).write_text(text)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)
    git(repo, "push", "-q", "origin", "main")
    return git(repo, "rev-parse", "HEAD")


def _github_says(fake_gh, branch, **fields):
    state = json.loads(fake_gh.read_text())
    state["prs"][branch].update(fields)
    fake_gh.write_text(json.dumps(state))


def test_conflicting_pr_is_resolved_by_the_builder_then_reviewed_and_gated(factory_repo, home, fake_gh, monkeypatch, capsys):
    _use_model(monkeypatch, scripts(review_verdicts=["APPROVE"]))
    assert main(["run", "demo-t01", "--skip-gates", SKIP, *SANDBOX]) == 0
    old = open_db(home).task("demo-t01")["candidate_sha"]

    # Another PR lands a different src/greet.txt on main; GitHub now reports the open PR as conflicting.
    new_main = _push_to_main(factory_repo, "src/greet.txt", "hi there\n", "other work (#7)")
    _github_says(fake_gh, "factory/demo-t01", mergeable="CONFLICTING")
    capsys.readouterr()
    assert main(["status", "--refresh"]) == 0
    captured = capsys.readouterr()
    assert "demo-t01: conflicts with main (`factory run demo-t01` resolves them)" in captured.err
    assert "≠" in captured.out and "1 conflict" in captured.out
    assert open_db(home).task("demo-t01")["status"] == "conflict"

    plays = scripts(review_verdicts=["APPROVE"])
    plays["BUILDER"] = [call("read_file", path="src/greet.txt"),
                        call("write_file", path="src/greet.txt", content="hi there\nhello\n"),
                        AIMessage("Kept main's line and re-applied the greeting.\nRESULT: DONE")]
    calls = _use_model(monkeypatch, plays)
    assert main(["run", "demo-t01", "--skip-gates", SKIP, *SANDBOX]) == 0

    db = open_db(home)
    row = db.task("demo-t01")
    assert row["status"] == "pr_open" and row["pr_url"] == "https://github.test/pr/1" and row["base_sha"] == new_main
    runs = [(r["role"], r["outcome"]) for r in db.runs("demo-t01")]
    assert runs[runs.index(("pr", "opened")) + 1:] == [("resolve", "committed"), ("review", "APPROVE"),
                                                       ("verify", "pass"), ("verify", "report"), ("pr", "opened")]
    assert "PLANNER" not in {r for r, _ in calls}                      # the plan is reused, not redone
    candidate = row["candidate_sha"]
    assert git(factory_repo, "rev-parse", f"{candidate}^") == new_main
    assert git(factory_repo, "show", f"{candidate}:src/greet.txt") == "hi there\nhello"
    assert git(factory_repo, "ls-remote", "origin", "refs/heads/factory/demo-t01").split()[0] == candidate

    task_message = next(r for r in db.runs("demo-t01") if r["role"] == "resolve")["transcript"]
    sent = open(task_message).read()
    assert "Resolve the merge conflicts of task demo-t01" in sent and "- src/greet.txt" in sent
    assert "1\\t<<<<<<< HEAD\\n2\\thi there\\n3\\t||||||| " in sent     # the builder read diff3 markers
    log = (home / "logs/demo-t01.log").read_text()
    assert "resolving conflicts in src/greet.txt" in log and "[gate] PASS conflict_markers" in log

    gh_calls = json.loads(fake_gh.read_text())["calls"]
    assert sum(c[:2] == ["pr", "create"] for c in gh_calls) == 1
    body = json.loads(fake_gh.read_text())["prs"]["factory/demo-t01"]["body"]
    assert f"Candidate `{candidate}`" in body and "**Conflicts resolved** on `main`: `src/greet.txt`" in body
    comment = next(c for c in gh_calls if c[0] == "api" and c[1].endswith("/issues/1/comments"))
    assert f"Candidate {old[:12]} → {candidate[:12]}" in comment[-1] and "resolved conflicts in `src/greet.txt`" in comment[-1]


def test_conflict_that_now_replays_cleanly_goes_straight_to_the_gates(factory_repo, home, fake_gh, monkeypatch):
    _use_model(monkeypatch, scripts(review_verdicts=["APPROVE"]))
    assert main(["run", "demo-t01", "--skip-gates", SKIP, *SANDBOX]) == 0
    new_main = _push_to_main(factory_repo, "unrelated.txt", "x\n", "unrelated (#8)")
    _github_says(fake_gh, "factory/demo-t01", mergeable="CONFLICTING")
    assert main(["status", "--refresh"]) == 0

    calls = _use_model(monkeypatch, scripts(review_verdicts=[]))
    assert main(["run", "demo-t01", "--skip-gates", SKIP, *SANDBOX]) == 0
    db = open_db(home)
    runs = [(r["role"], r["outcome"]) for r in db.runs("demo-t01")]
    assert runs[-4:] == [("resolve", "committed"), ("verify", "pass"), ("verify", "report"), ("pr", "opened")]
    assert {r for r, _ in calls} == {"VERIFIER"}                       # no builder, no reviewer: nothing to resolve
    assert git(factory_repo, "rev-parse", f"{db.task('demo-t01')['candidate_sha']}^") == new_main


def test_run_builds_on_origin_even_when_the_local_trunk_is_behind(factory_repo, home, fake_gh, monkeypatch, tmp_path):
    other = tmp_path / "other"
    git(tmp_path, "clone", "-q", str(tmp_path / "origin.git"), str(other))
    merged = _push_to_main(other, "merged-elsewhere.txt", "x\n", "a dependency merged on GitHub (#5)")
    assert git(factory_repo, "rev-parse", "main") != merged             # this checkout has not pulled it
    _use_model(monkeypatch, scripts(review_verdicts=["APPROVE"]))
    assert main(["run", "demo-t01", "--skip-gates", SKIP, *SANDBOX]) == 0
    assert open_db(home).task("demo-t01")["base_sha"] == merged


def test_failed_resolution_leaves_the_pr_alone(factory_repo, home, fake_gh, monkeypatch):
    _use_model(monkeypatch, scripts(review_verdicts=["APPROVE"]))
    assert main(["run", "demo-t01", "--skip-gates", SKIP, *SANDBOX]) == 0
    old = open_db(home).task("demo-t01")["candidate_sha"]
    _push_to_main(factory_repo, "src/greet.txt", "hi there\n", "other work (#7)")
    _github_says(fake_gh, "factory/demo-t01", mergeable="CONFLICTING")
    assert main(["status", "--refresh"]) == 0

    plays = scripts(review_verdicts=["CHANGES"])
    plays["BUILDER"] = [AIMessage("Could not reconcile them.\nRESULT: BLOCKED")]     # leaves the markers in
    _use_model(monkeypatch, plays)
    assert main(["run", "demo-t01", "--skip-gates", SKIP, "--max-attempts", "1", *SANDBOX]) == 1
    row = open_db(home).task("demo-t01")
    assert row["status"] == "failed" and row["pr_url"] == "https://github.test/pr/1"
    assert f"The PR still holds {old[:12]}, which conflicts with main" in row["note"]
    assert git(factory_repo, "ls-remote", "origin", "refs/heads/factory/demo-t01").split()[0] == old


def test_stacked_conflict_whose_dependency_merged_meanwhile_resolves_onto_the_trunk(factory_repo, home, fake_gh, monkeypatch):
    _use_model(monkeypatch, scripts(review_verdicts=["APPROVE"]))
    assert main(["run", "demo-t01", "--skip-gates", SKIP, *SANDBOX]) == 0
    plays = scripts(review_verdicts=["APPROVE"])
    plays["BUILDER"] = [call("write_file", path="crates/e2e/tests/second.rs", content=SECOND),
                        call("write_file", path="docs/sessions/2026-10-09.md",
                             content="## [12:00] demo-t01\n## [12:05] demo-t02\n"),
                        AIMessage("Second thing.\nRESULT: DONE")]
    _use_model(monkeypatch, plays)
    assert main(["run", "demo-t02", "--skip-gates", SKIP, *SANDBOX]) == 0
    db = open_db(home)
    db.update("demo-t02", status="conflict", note="demo-t01 moved and this PR's commits conflict with it")

    # demo-t01 is squash-merged, with a different session log on main by then.
    t01 = db.task("demo-t01")["candidate_sha"]
    git(factory_repo, "merge", "-q", "--squash", t01)
    git(factory_repo, "commit", "-q", "-m", "demo-t01 (#1)")
    new_main = _push_to_main(factory_repo, "docs/sessions/2026-10-09.md", "## [12:00] demo-t01\n## [12:01] other\n",
                             "other log (#3)")
    _github_says(fake_gh, "factory/demo-t01", state="MERGED")
    assert main(["status", "--refresh"]) == 0
    assert open_db(home).task("demo-t02")["status"] == "conflict"          # refresh leaves it for the run

    plays = scripts(review_verdicts=["APPROVE"])
    plays["BUILDER"] = [call("write_file", path="docs/sessions/2026-10-09.md",
                             content="## [12:00] demo-t01\n## [12:01] other\n## [12:05] demo-t02\n"),
                        AIMessage("Kept both entries.\nRESULT: DONE")]
    _use_model(monkeypatch, plays)
    assert main(["run", "demo-t02", "--skip-gates", SKIP, *SANDBOX]) == 0
    row = open_db(home).task("demo-t02")
    assert row["status"] == "pr_open" and row["base_ref"] == "main" and row["stacked_on"] is None
    assert git(factory_repo, "rev-parse", f"{row['candidate_sha']}^") == new_main
    assert json.loads(fake_gh.read_text())["prs"]["factory/demo-t02"]["base"] == "main"


def test_another_board_takes_up_the_prs_and_moves_the_stack(factory_repo, home, fake_gh, monkeypatch, tmp_path, capsys):
    # Board A opens demo-t01's PR, then demo-t02's stacked on it.
    _use_model(monkeypatch, scripts(review_verdicts=["APPROVE"]))
    assert main(["run", "demo-t01", "--skip-gates", SKIP, *SANDBOX]) == 0
    plays = scripts(review_verdicts=["APPROVE"])
    plays["BUILDER"] = [call("write_file", path="crates/e2e/tests/second.rs", content=SECOND),
                        call("write_file", path="docs/sessions/2026-10-09.md",
                             content="## [12:00] demo-t01\n## [12:05] demo-t02\n"),
                        AIMessage("Second thing.\nRESULT: DONE")]
    _use_model(monkeypatch, plays)
    assert main(["run", "demo-t02", "--skip-gates", SKIP, *SANDBOX]) == 0
    a = {t: open_db(home).task(t) for t in ("demo-t01", "demo-t02")}

    # Board B, another maintainer's, starts from the contracts alone; its refresh takes both PRs up from GitHub.
    board_b = tmp_path / "board-b"
    monkeypatch.setenv("FACTORY_HOME", str(board_b))
    assert main(["sync"]) == 0
    capsys.readouterr()
    assert main(["status", "--refresh"]) == 0
    err = capsys.readouterr().err
    assert "demo-t01: PR open at https://github.test/pr/1 (taken up from GitHub)" in err
    assert "demo-t02: PR open at https://github.test/pr/2, stacked on demo-t01 (taken up from GitHub)" in err
    for t, row_a in a.items():
        row = open_db(board_b).task(t)
        assert row["status"] == "pr_open"
        assert {k: row[k] for k in ("pr_url", "branch", "base_ref", "base_sha", "candidate_sha", "trunk", "stacked_on")} \
            == {k: row_a[k] for k in ("pr_url", "branch", "base_ref", "base_sha", "candidate_sha", "trunk", "stacked_on")}
    assert main(["status", "--refresh"]) == 0 and "taken up" not in capsys.readouterr().err     # idempotent

    # demo-t01 merges; board B moves demo-t02 onto main as board A would.
    git(factory_repo, "merge", "-q", "--squash", a["demo-t01"]["candidate_sha"])
    git(factory_repo, "commit", "-q", "-m", "demo-t01 (#1)")
    git(factory_repo, "push", "-q", "origin", "main")
    _github_says(fake_gh, "factory/demo-t01", state="MERGED")
    assert main(["status", "--refresh"]) == 0
    assert "demo-t02: rebased onto main, PR retargeted" in capsys.readouterr().err
    row = open_db(board_b).task("demo-t02")
    assert row["base_ref"] == "main" and row["stacked_on"] is None
    assert git(factory_repo, "rev-parse", f"{row['candidate_sha']}^") == git(factory_repo, "rev-parse", "origin/main")


def test_refresh_takes_up_merged_prs_but_not_closed_ones_or_holds(factory_repo, home, fake_gh, capsys):
    fake_gh.write_text(json.dumps({"calls": [], "prs": {
        "factory/demo-t01": {"url": "https://github.test/pr/5", "state": "MERGED", "base": "main"},
        "factory/demo-t02": {"url": "https://github.test/pr/6", "state": "CLOSED", "base": "main"}}}))
    assert main(["sync"]) == 0
    assert main(["status", "--refresh"]) == 0
    db = open_db(home)
    assert db.task("demo-t01")["status"] == "merged" and db.task("demo-t01")["pr_url"] == "https://github.test/pr/5"
    assert db.task("demo-t02")["status"] == "queued" and db.task("demo-t02")["pr_url"] is None    # a closed PR is history

    _github_says(fake_gh, "factory/demo-t02", state="OPEN")     # open, but its branch isn't on origin
    capsys.readouterr()
    assert main(["status", "--refresh"]) == 0
    assert "demo-t02: can't take up https://github.test/pr/6" in capsys.readouterr().err
    assert open_db(home).task("demo-t02")["status"] == "queued"

    git(factory_repo, "push", "-q", "origin", "main:refs/heads/factory/demo-t02")
    assert main(["abandon", "demo-t02", "--note", "hold: not now"]) == 0
    assert main(["status", "--refresh"]) == 0
    assert open_db(home).task("demo-t02")["status"] == "abandoned"     # a hold outranks GitHub


def test_an_initialised_repo_runs_its_starter_plan_with_the_shipped_prompts(tmp_path, home, fake_gh, monkeypatch):
    """`factory init` in an empty repository is all it takes: the example task goes to a PR, with the prompts
    and the session-log rule that ship with the factory (no .factory/agents overrides)."""
    import datetime as dt

    origin, r = tmp_path / "starter.git", tmp_path / "starter"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    r.mkdir()
    git(r, "init", "-q", "-b", "main")
    monkeypatch.chdir(r)
    assert main(["init"]) == 0 and not (r / ".factory/agents").exists()
    git(r, "add", "-A")
    git(r, "commit", "-q", "-m", "factory init")
    git(r, "remote", "add", "origin", str(origin))
    git(r, "push", "-q", "-u", "origin", "main")

    doc = "# The factory here\n\nPlan with /plan-workstream, check with factory validate-plan, review with /review-task.\n"
    today = dt.date.today().isoformat()
    plays = {"PLANNER": [AIMessage("**Files**: docs/factory.md\n**Steps**: write it")],
             "BUILDER": [call("write_file", path="docs/factory.md", content=doc),
                         call("write_file", path=f"docs/sessions/{today}.md", content="## [12:00] example-t01\n"),
                         AIMessage("RESULT: DONE")],
             "REVIEWER": ["VERDICT"], "VERIFIER": [AIMessage("**Summary**\n- documents the factory\n")],
             "_verdicts": [], "_calls": []}
    _use_model(monkeypatch, plays)
    monkeypatch.setenv("OPENROUTER_API_KEY", "x")          # the shipped prompts name OpenRouter models
    assert main(["run", "example-t01", *SANDBOX]) == 0
    row = open_db(home).task("example-t01")
    assert row["status"] == "pr_open" and row["pr_url"].startswith("https://github.test/pr/")
    runs = {r["role"]: r for r in open_db(home).runs("example-t01")}
    assert {role for role, _ in plays["_calls"]} == {"PLANNER", "BUILDER", "REVIEWER", "VERIFIER"}
    assert runs["pr"]["outcome"] == "opened"
