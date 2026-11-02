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


FMT = {"__typename": "CheckRun", "workflowName": "factory", "name": "rust fmt", "status": "COMPLETED",
       "conclusion": "FAILURE", "detailsUrl": "https://github.test/o/r/actions/runs/11/job/22"}
FMT_LOG = ("2026-10-31T10:00:00.0000000Z assertion failed: the greeting is `hello, world`\n"
           "2026-10-31T10:00:01.0000000Z ##[error]Process completed with exit code 101.")


def _ci_says(fake_gh, branch, head, *checks, logs=None):
    """GitHub's checks on the PR's head commit."""
    state = json.loads(fake_gh.read_text())
    state["prs"][branch].update(commits=[{"oid": "0" * 40}, {"oid": head}], statusCheckRollup=list(checks))
    state.setdefault("logs", {}).update(logs or {})
    fake_gh.write_text(json.dumps(state))


def _review(id, login, state, body=""):
    return {"id": id, "user": {"login": login}, "state": state, "body": body, "commit_id": "a" * 40}


def _reviews_say(fake_gh, branch, head, *reviews, permissions=None):
    """GitHub's reviews on the PR at `head`, checks green."""
    state = json.loads(fake_gh.read_text())
    state["prs"][branch].update(commits=[{"oid": "0" * 40}, {"oid": head}],
                                 statusCheckRollup=[], reviews=list(reviews))
    if permissions is not None:
        state["permissions"] = permissions
    fake_gh.write_text(json.dumps(state))


def _inline(review_id, path, line, body):
    return {"id": line, "pull_request_review_id": review_id, "path": path, "line": line,
            "original_line": None, "body": body, "user": {"login": "alice"}, "in_reply_to_id": None}


def _inline_comments(fake_gh, branch, *comments):
    state = json.loads(fake_gh.read_text())
    state["prs"][branch]["comments"] = list(comments)
    fake_gh.write_text(json.dumps(state))


def test_failing_ci_is_fixed_on_the_pr_branch_then_reviewed_and_gated(factory_repo, home, fake_gh, monkeypatch, capsys):
    _use_model(monkeypatch, scripts(review_verdicts=["APPROVE"]))
    assert main(["run", "demo-t01", "--skip-gates", SKIP, *SANDBOX]) == 0
    row = open_db(home).task("demo-t01")
    old, base = row["candidate_sha"], row["base_sha"]

    # CI checks something the gates don't, and it fails on the PR's head.
    _ci_says(fake_gh, "factory/demo-t01", old, FMT, logs={"22": FMT_LOG})
    capsys.readouterr()
    assert main(["status", "--refresh"]) == 0
    captured = capsys.readouterr()
    assert "demo-t01: CI fails (factory / rust fmt) (`factory run demo-t01` fixes it)" in captured.err
    assert "!" in captured.out and "1 CI failing" in captured.out
    assert open_db(home).task("demo-t01")["status"] == "ci_failed"

    plays = scripts(review_verdicts=["APPROVE"])
    plays["BUILDER"] = [call("write_file", path="src/greet.txt", content="hello, world\n"),
                        AIMessage("Fixed the greeting CI expects.\nRESULT: DONE")]
    calls = _use_model(monkeypatch, plays)
    assert main(["run", "demo-t01", "--skip-gates", SKIP, *SANDBOX]) == 0

    db = open_db(home)
    row = db.task("demo-t01")
    assert row["status"] == "pr_open" and row["pr_url"] == "https://github.test/pr/1" and row["base_sha"] == base
    runs = [(r["role"], r["outcome"]) for r in db.runs("demo-t01")]
    assert runs[runs.index(("pr", "opened")) + 1:] == [("ci", "failing"), ("build", "committed"), ("review", "APPROVE"),
                                                       ("verify", "pass"), ("verify", "report"), ("pr", "opened")]
    assert "PLANNER" not in {r for r, _ in calls}                      # the plan is reused, not redone
    new = row["candidate_sha"]
    assert git(factory_repo, "rev-parse", f"{new}^") == old             # built on the PR's head, not from scratch
    assert git(factory_repo, "show", f"{new}:src/greet.txt") == "hello, world"
    assert git(factory_repo, "show", f"{new}:crates/e2e/tests/greet.rs")  # the task's change is all still there
    assert git(factory_repo, "ls-remote", "origin", "refs/heads/factory/demo-t01").split()[0] == new
    assert "(fix CI, attempt 1)" in git(factory_repo, "log", "-1", "--format=%s", new)

    sent = open([r for r in db.runs("demo-t01") if r["role"] == "build"][-1]["transcript"]).read()
    assert "# Fix failing CI" in sent and "the greeting is `hello, world`" in sent and "# Plan" in sent
    log = (home / "logs/demo-t01.log").read_text()
    assert f"fixing CI (factory / rust fmt) on {old[:12]}" in log

    gh = json.loads(fake_gh.read_text())
    assert sum(c[:2] == ["pr", "create"] for c in gh["calls"]) == 1
    assert "**CI fixed**: `factory / rust fmt` failed on the previous candidate" in gh["prs"]["factory/demo-t01"]["body"]
    comment = [c for c in gh["calls"] if c[0] == "api" and c[1].endswith("/issues/1/comments")][-1]
    assert f"CI failed on {old[:12]} (`factory / rust fmt`)" in comment[-1] and f"{old[:12]} → {new[:12]}" in comment[-1]

    # CI runs again on the new head: the old failure no longer counts.
    _ci_says(fake_gh, "factory/demo-t01", new, {**FMT, "status": "IN_PROGRESS", "conclusion": ""})
    assert main(["status", "--refresh"]) == 0 and open_db(home).task("demo-t01")["status"] == "pr_open"


def test_ci_is_judged_only_on_the_factorys_candidate(factory_repo, home, fake_gh, monkeypatch, capsys):
    _use_model(monkeypatch, scripts(review_verdicts=["APPROVE"]))
    assert main(["run", "demo-t01", "--skip-gates", SKIP, *SANDBOX]) == 0
    sha = open_db(home).task("demo-t01")["candidate_sha"]

    def refreshed():
        assert main(["status", "--refresh"]) == 0
        return open_db(home).task("demo-t01")["status"]

    _ci_says(fake_gh, "factory/demo-t01", "f" * 40, FMT)                # someone else pushed to the branch
    assert refreshed() == "pr_open"
    _ci_says(fake_gh, "factory/demo-t01", sha, {**FMT, "conclusion": "CANCELLED"},
             {**FMT, "name": "rust e2e", "status": "IN_PROGRESS", "conclusion": ""})
    assert refreshed() == "pr_open"
    _ci_says(fake_gh, "factory/demo-t01", sha, FMT)
    assert refreshed() == "ci_failed"

    # The job is re-run and passes (a flake): the run finds nothing to fix, and no agent starts.
    _ci_says(fake_gh, "factory/demo-t01", sha, {**FMT, "conclusion": "SUCCESS"})
    calls = _use_model(monkeypatch, scripts(review_verdicts=[]))
    capsys.readouterr()
    assert main(["run", "demo-t01", "--skip-gates", SKIP, *SANDBOX]) == 0
    assert "CI no longer fails on https://github.test/pr/1; nothing to fix" in capsys.readouterr().out
    assert calls == [] and open_db(home).task("demo-t01")["status"] == "pr_open"

    _ci_says(fake_gh, "factory/demo-t01", sha, FMT)
    assert refreshed() == "ci_failed"
    _ci_says(fake_gh, "factory/demo-t01", sha, {**FMT, "conclusion": "SUCCESS"})
    capsys.readouterr()
    assert refreshed() == "pr_open" and "demo-t01: CI no longer fails" in capsys.readouterr().err

    # Red again, then a human pushes a fix of their own: the PR is theirs to finish, and stays off the queue.
    _ci_says(fake_gh, "factory/demo-t01", sha, FMT)
    assert refreshed() == "ci_failed"
    _ci_says(fake_gh, "factory/demo-t01", "e" * 40, FMT)
    assert refreshed() == "pr_open" and "isn't the factory's candidate" in open_db(home).task("demo-t01")["note"]


def test_failed_ci_fix_leaves_the_pr_alone(factory_repo, home, fake_gh, monkeypatch):
    _use_model(monkeypatch, scripts(review_verdicts=["APPROVE"]))
    assert main(["run", "demo-t01", "--skip-gates", SKIP, *SANDBOX]) == 0
    old = open_db(home).task("demo-t01")["candidate_sha"]
    _ci_says(fake_gh, "factory/demo-t01", old, FMT, logs={"22": FMT_LOG})
    assert main(["status", "--refresh"]) == 0

    plays = scripts(review_verdicts=["APPROVE"])
    plays["BUILDER"] = [AIMessage("Could not reproduce it.\nRESULT: BLOCKED")]      # changes nothing
    calls = _use_model(monkeypatch, plays)
    assert main(["run", "demo-t01", "--skip-gates", SKIP, "--max-attempts", "1", *SANDBOX]) == 1
    row = open_db(home).task("demo-t01")
    assert row["status"] == "failed" and row["pr_url"] == "https://github.test/pr/1"
    assert "produced no changes, so CI still fails" in row["note"]
    assert f"The PR still holds {old[:12]}, whose CI fails (factory / rust fmt)" in row["note"]
    assert "REVIEWER" not in {r for r, _ in calls}                     # nothing new to review
    assert git(factory_repo, "ls-remote", "origin", "refs/heads/factory/demo-t01").split()[0] == old


def test_ci_failure_of_a_stacked_pr_whose_dependency_merged_is_restacked_not_fixed(factory_repo, home, fake_gh,
                                                                                  monkeypatch, capsys):
    _use_model(monkeypatch, scripts(review_verdicts=["APPROVE"]))
    assert main(["run", "demo-t01", "--skip-gates", SKIP, *SANDBOX]) == 0
    plays = scripts(review_verdicts=["APPROVE"])
    plays["BUILDER"] = [call("write_file", path="crates/e2e/tests/second.rs", content=SECOND),
                        call("write_file", path="docs/sessions/2026-10-09.md",
                             content="## [12:00] demo-t01\n## [12:05] demo-t02\n"),
                        AIMessage("Second thing.\nRESULT: DONE")]
    _use_model(monkeypatch, plays)
    assert main(["run", "demo-t02", "--skip-gates", SKIP, *SANDBOX]) == 0
    old = open_db(home).task("demo-t02")["candidate_sha"]
    _ci_says(fake_gh, "factory/demo-t02", old, FMT)
    assert main(["status", "--refresh"]) == 0
    assert open_db(home).task("demo-t02")["status"] == "ci_failed"

    # demo-t01 is squash-merged before anyone refreshes: CI must judge demo-t02 again on the trunk first.
    git(factory_repo, "merge", "-q", "--squash", open_db(home).task("demo-t01")["candidate_sha"])
    git(factory_repo, "commit", "-q", "-m", "demo-t01 (#1)")
    git(factory_repo, "push", "-q", "origin", "main")
    open_db(home).update("demo-t01", status="merged")
    calls = _use_model(monkeypatch, scripts(review_verdicts=[]))
    capsys.readouterr()
    assert main(["run", "demo-t02", "--skip-gates", SKIP, *SANDBOX]) == 0
    assert "demo-t02: rebased onto main, PR retargeted; nothing to fix until CI runs on the new head" in \
        capsys.readouterr().out
    row = open_db(home).task("demo-t02")
    assert calls == [] and row["status"] == "pr_open" and row["base_ref"] == "main" and row["candidate_sha"] != old


def test_a_review_requesting_changes_marks_the_task_on_refresh(factory_repo, home, fake_gh, monkeypatch, capsys):
    _use_model(monkeypatch, scripts(review_verdicts=["APPROVE"]))
    assert main(["run", "demo-t01", "--skip-gates", SKIP, *SANDBOX]) == 0
    db = open_db(home)
    head = db.task("demo-t01")["candidate_sha"]

    capsys.readouterr()
    _reviews_say(fake_gh, "factory/demo-t01", head, _review(1, "alice", "CHANGES_REQUESTED"))
    assert main(["status", "--refresh"]) == 0
    captured = capsys.readouterr()
    assert "demo-t01: changes requested by @alice (`factory run demo-t01` addresses them)" in captured.err
    assert "↺" in captured.out and "1 changes requested" in captured.out
    row = db.task("demo-t01")
    assert row["status"] == "changes_requested"
    assert "@alice" in row["note"] and "`factory run demo-t01`" in row["note"]

    # top shows the glyph, counter, URL and note.
    assert main(["top", "--once"]) == 0
    top = capsys.readouterr().out
    assert "↺" in top and "1 changes requested" in top and "https://github.test/pr/1" in top and "@alice" in top

    # a read-only reviewer's request does not count.
    _reviews_say(fake_gh, "factory/demo-t01", head, _review(1, "alice", "CHANGES_REQUESTED"),
                 _review(2, "carol", "CHANGES_REQUESTED"), permissions={"carol": "read"})
    capsys.readouterr()
    assert main(["status", "--refresh"]) == 0
    assert db.task("demo-t01")["status"] == "changes_requested"

    # alice approves after her request -> back to pr_open.
    _reviews_say(fake_gh, "factory/demo-t01", head, _review(1, "alice", "CHANGES_REQUESTED"),
                 _review(2, "alice", "APPROVED"))
    assert main(["status", "--refresh"]) == 0
    assert "demo-t01: no review requests changes now" in capsys.readouterr().err
    assert db.task("demo-t01")["status"] == "pr_open"

    # the author's own COMMENTED review counts as a request.
    _reviews_say(fake_gh, "factory/demo-t01", head, _review(1, "you", "COMMENTED"))
    assert main(["status", "--refresh"]) == 0
    assert db.task("demo-t01")["status"] == "changes_requested"

    # refresh never GETs conversation comments, and the factory's own comment never changes the status.
    state = json.loads(fake_gh.read_text())
    state["calls"] = [c for c in state["calls"] if not (c[0] == "api" and "/issues/" in c[1] and "/comments" in c[1])]
    fake_gh.write_text(json.dumps(state))
    capsys.readouterr()
    assert main(["status", "--refresh"]) == 0
    calls = json.loads(fake_gh.read_text())["calls"]
    assert not any(c[0] == "api" and "/issues/1/comments" in c[1] for c in calls)
    assert db.task("demo-t01")["status"] == "changes_requested"


def test_conflicts_come_before_requested_changes_and_requested_changes_before_ci(factory_repo, home, fake_gh,
                                                                                monkeypatch, capsys):
    _use_model(monkeypatch, scripts(review_verdicts=["APPROVE"]))
    assert main(["run", "demo-t01", "--skip-gates", SKIP, *SANDBOX]) == 0
    db = open_db(home)
    sha = db.task("demo-t01")["candidate_sha"]

    # (1) request + conflict -> conflict wins, no "changes requested" line.
    _reviews_say(fake_gh, "factory/demo-t01", sha, _review(1, "alice", "CHANGES_REQUESTED"))
    _github_says(fake_gh, "factory/demo-t01", mergeable="CONFLICTING")
    capsys.readouterr()
    assert main(["status", "--refresh"]) == 0
    captured = capsys.readouterr()
    assert db.task("demo-t01")["status"] == "conflict"
    assert "changes requested" not in captured.err

    # (2) mergeable back to MERGEABLE -> changes_requested.
    db.update("demo-t01", status="pr_open")
    _github_says(fake_gh, "factory/demo-t01", mergeable="MERGEABLE")
    capsys.readouterr()
    assert main(["status", "--refresh"]) == 0
    assert "changes requested by @alice" in capsys.readouterr().err
    assert db.task("demo-t01")["status"] == "changes_requested"

    # (3) alice's approval clears it (green CI) -> pr_open.
    _reviews_say(fake_gh, "factory/demo-t01", sha, _review(1, "alice", "CHANGES_REQUESTED"),
                 _review(2, "alice", "APPROVED"))
    capsys.readouterr()
    assert main(["status", "--refresh"]) == 0
    assert db.task("demo-t01")["status"] == "pr_open"

    # (4) red CI -> ci_failed.
    _ci_says(fake_gh, "factory/demo-t01", sha, FMT)
    capsys.readouterr()
    assert main(["status", "--refresh"]) == 0
    assert db.task("demo-t01")["status"] == "ci_failed"

    # (5) a requesting review outranks red CI -> changes_requested.
    _reviews_say(fake_gh, "factory/demo-t01", sha, _review(1, "bob", "CHANGES_REQUESTED"))
    _ci_says(fake_gh, "factory/demo-t01", sha, FMT)
    capsys.readouterr()
    assert main(["status", "--refresh"]) == 0
    assert "changes requested by @bob" in capsys.readouterr().err
    assert db.task("demo-t01")["status"] == "changes_requested"


def test_reviews_on_a_head_someone_else_pushed_are_left_to_them(factory_repo, home, fake_gh, monkeypatch, capsys):
    _use_model(monkeypatch, scripts(review_verdicts=["APPROVE"]))
    assert main(["run", "demo-t01", "--skip-gates", SKIP, *SANDBOX]) == 0
    db = open_db(home)
    db.update("demo-t01", status="changes_requested",
              note="a review requests changes (@alice): `factory run demo-t01` addresses them")

    _ci_says(fake_gh, "factory/demo-t01", "f" * 40, FMT)      # head != candidate
    capsys.readouterr()
    assert main(["status", "--refresh"]) == 0
    captured = capsys.readouterr()
    assert db.task("demo-t01")["status"] == "pr_open"
    assert "isn't the factory's candidate; its reviews are left to whoever pushed" in db.task("demo-t01")["note"]
    assert "its reviews are theirs now" in captured.err

    # re-mark and break the reviews endpoint: gh failure changes nothing.
    db.update("demo-t01", status="changes_requested",
              note="a review requests changes (@alice): `factory run demo-t01` addresses them")
    _reviews_say(fake_gh, "factory/demo-t01", db.task("demo-t01")["candidate_sha"],
                 _review(1, "alice", "CHANGES_REQUESTED"))   # head is the candidate again
    state = json.loads(fake_gh.read_text())
    state["broken"] = ["pulls/1/reviews"]
    fake_gh.write_text(json.dumps(state))
    capsys.readouterr()
    assert main(["status", "--refresh"]) == 0
    assert db.task("demo-t01")["status"] == "changes_requested"


def test_a_stacked_pr_keeps_its_requested_changes_when_restacked(factory_repo, home, fake_gh, monkeypatch, capsys):
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
    t02 = db.task("demo-t02")["candidate_sha"]

    _reviews_say(fake_gh, "factory/demo-t02", t02, _review(1, "alice", "CHANGES_REQUESTED"))
    capsys.readouterr()
    assert main(["status", "--refresh"]) == 0
    assert db.task("demo-t02")["status"] == "changes_requested"
    note = db.task("demo-t02")["note"]

    # demo-t01 merges: the refresh moves demo-t02 onto main and keeps the changes_requested status.
    t01 = db.task("demo-t01")["candidate_sha"]
    git(factory_repo, "merge", "-q", "--squash", t01)
    git(factory_repo, "commit", "-q", "-m", "demo-t01 (#1)")
    git(factory_repo, "push", "-q", "origin", "main")
    _github_says(fake_gh, "factory/demo-t01", state="MERGED")
    capsys.readouterr()
    assert main(["status", "--refresh"]) == 0
    assert "demo-t02: rebased onto main, PR retargeted" in capsys.readouterr().err
    row = db.task("demo-t02")
    assert row["status"] == "changes_requested"
    assert note == row["note"] and "@alice" in row["note"]
    assert row["base_ref"] == "main"
    assert json.loads(fake_gh.read_text())["prs"]["factory/demo-t02"]["base"] == "main"
    assert row["candidate_sha"] != t02

    # sync the head to the new candidate and refresh again: idempotent, still changes_requested.
    _reviews_say(fake_gh, "factory/demo-t02", row["candidate_sha"], _review(1, "alice", "CHANGES_REQUESTED"))
    capsys.readouterr()
    assert main(["status", "--refresh"]) == 0
    assert db.task("demo-t02")["status"] == "changes_requested"


def test_a_taken_up_pr_treats_earlier_reviews_as_addressed(factory_repo, home, fake_gh, monkeypatch, capsys, tmp_path):
    _use_model(monkeypatch, scripts(review_verdicts=["APPROVE"]))
    assert main(["run", "demo-t01", "--skip-gates", SKIP, *SANDBOX]) == 0
    a = open_db(home).task("demo-t01")["candidate_sha"]
    _reviews_say(fake_gh, "factory/demo-t01", a,
                 _review(5, "alice", "CHANGES_REQUESTED"), _review(6, "bob", "CHANGES_REQUESTED"),
                 _review(7, "alice", "APPROVED"))

    # Board B takes the PR up; the watermark is the latest review id (7), so bob's request no longer counts.
    board_b = tmp_path / "board-b"
    monkeypatch.setenv("FACTORY_HOME", str(board_b))
    assert main(["sync"]) == 0
    capsys.readouterr()
    assert main(["status", "--refresh"]) == 0
    row = open_db(board_b).task("demo-t01")
    assert row["status"] == "pr_open"
    assert row["reviews_addressed"] == 7
    assert "changes requested" not in capsys.readouterr().err

    # a review after the watermark requests changes again.
    _reviews_say(fake_gh, "factory/demo-t01", a,
                 _review(5, "alice", "CHANGES_REQUESTED"), _review(6, "bob", "CHANGES_REQUESTED"),
                 _review(7, "alice", "APPROVED"), _review(9, "bob", "CHANGES_REQUESTED"))
    capsys.readouterr()
    assert main(["status", "--refresh"]) == 0
    assert open_db(board_b).task("demo-t01")["status"] == "changes_requested"


def test_requested_changes_are_addressed_on_the_pr_branch_then_reviewed_and_gated(factory_repo, home, fake_gh,
                                                                                 monkeypatch, capsys):
    _use_model(monkeypatch, scripts(review_verdicts=["APPROVE"]))
    assert main(["run", "demo-t01", "--skip-gates", SKIP, *SANDBOX]) == 0
    db = open_db(home)
    old, base = db.task("demo-t01")["candidate_sha"], db.task("demo-t01")["base_sha"]

    _reviews_say(fake_gh, "factory/demo-t01", old, _review(1, "alice", "CHANGES_REQUESTED", "Please be careful here."))
    _inline_comments(fake_gh, "factory/demo-t01", _inline(1, "src/greet.txt", 1, "capitalize the greeting and add a note"))
    capsys.readouterr()
    assert main(["status", "--refresh"]) == 0
    assert db.task("demo-t01")["status"] == "changes_requested"

    plays = scripts(review_verdicts=["APPROVE"])
    plays["BUILDER"] = [call("write_file", path="src/greet.txt", content="hello, world\n"),
                        AIMessage("Addressed the greeting as requested\nRESULT: DONE")]
    calls = _use_model(monkeypatch, plays)
    assert main(["run", "demo-t01", "--skip-gates", SKIP, *SANDBOX]) == 0

    db = open_db(home)
    row = db.task("demo-t01")
    assert row["status"] == "pr_open" and row["pr_url"] == "https://github.test/pr/1" and row["base_sha"] == base
    runs = [(r["role"], r["outcome"]) for r in db.runs("demo-t01")]
    assert runs[runs.index(("pr", "opened")) + 1:] == [("human_review", "changes_requested"), ("build", "committed"),
                                                       ("review", "APPROVE"), ("verify", "pass"), ("verify", "report"),
                                                       ("pr", "opened")]
    assert "PLANNER" not in {r for r, _ in calls}
    new = row["candidate_sha"]
    assert git(factory_repo, "rev-parse", f"{new}^") == old
    assert git(factory_repo, "show", f"{new}:src/greet.txt") == "hello, world"
    assert git(factory_repo, "ls-remote", "origin", "refs/heads/factory/demo-t01").split()[0] == new
    assert "(address review, attempt 1)" in git(factory_repo, "log", "-1", "--format=%s", new)

    # The brief and the inline comment reach the builder; the reviewer is told the requests are in scope.
    build_t = [r for r in db.runs("demo-t01") if r["role"] == "build"][-1]["transcript"]
    sent = open(build_t).read()
    assert "# Address review" in sent and "src/greet.txt:1" in sent and "Please be careful here." in sent
    review_t = [r for r in db.runs("demo-t01") if r["role"] == "review"][-1]["transcript"]
    assert "in scope" in open(review_t).read() and "# Address review" in open(review_t).read()
    assert "addressing review by @alice on " + old[:12] in (home / "logs/demo-t01.log").read_text()

    gh = json.loads(fake_gh.read_text())
    assert sum(c[:2] == ["pr", "create"] for c in gh["calls"]) == 1
    assert "**Review addressed** by @alice" in gh["prs"]["factory/demo-t01"]["body"]
    comment = [c for c in gh["calls"] if c[0] == "api" and c[1].endswith("/issues/1/comments")][-1]
    expected = (f"Addressed review by @alice on {old[:12]}: Addressed the greeting as requested. "
                f"Candidate {old[:12]} → {new[:12]}; review and gates ran on {new[:12]}.")
    assert comment[-1] == "body=" + expected
    assert db.task("demo-t01")["reviews_addressed"] == 1

    # `factory show --role human_review` lists the run; a refresh with the same reviews leaves it pr_open.
    capsys.readouterr()
    assert main(["show", "demo-t01", "--role", "human_review"]) == 0
    assert "changes_requested" in capsys.readouterr().out
    _reviews_say(fake_gh, "factory/demo-t01", new, _review(1, "alice", "CHANGES_REQUESTED", "Please be careful here."))
    assert main(["status", "--refresh"]) == 0
    assert open_db(home).task("demo-t01")["status"] == "pr_open"


def test_a_review_that_needs_no_change_is_answered_and_the_pr_left_as_is(factory_repo, home, fake_gh, monkeypatch, capsys):
    _use_model(monkeypatch, scripts(review_verdicts=["APPROVE"]))
    assert main(["run", "demo-t01", "--skip-gates", SKIP, *SANDBOX]) == 0
    db = open_db(home)
    old = db.task("demo-t01")["candidate_sha"]

    _reviews_say(fake_gh, "factory/demo-t01", old, _review(1, "alice", "CHANGES_REQUESTED", "Is this really needed?"))
    capsys.readouterr()
    assert main(["status", "--refresh"]) == 0
    assert db.task("demo-t01")["status"] == "changes_requested"

    plays = scripts(review_verdicts=["APPROVE"])
    plays["BUILDER"] = [AIMessage("No change needed: the greeting is already correct as shipped.\nRESULT: DONE")]
    _use_model(monkeypatch, plays)
    assert main(["run", "demo-t01", "--skip-gates", SKIP, *SANDBOX]) == 0

    db = open_db(home)
    row = db.task("demo-t01")
    assert row["status"] == "pr_open" and row["pr_url"] == "https://github.test/pr/1"
    assert row["reviews_addressed"] == 1
    runs = [(r["role"], r["outcome"]) for r in db.runs("demo-t01")]
    assert runs[runs.index(("pr", "opened")) + 1:] == [("human_review", "changes_requested"), ("build", "no-changes")]
    assert git(factory_repo, "ls-remote", "origin", "refs/heads/factory/demo-t01").split()[0] == old

    # The builder's answer (RESULT line stripped) is the PR comment; nothing was pushed or re-reviewed.
    gh = json.loads(fake_gh.read_text())
    comment = [c for c in gh["calls"] if c[0] == "api" and c[1].endswith("/issues/1/comments")][-1]
    assert comment[-1] == "body=No change needed: the greeting is already correct as shipped."
    assert sum(c[:2] == ["pr", "create"] for c in gh["calls"]) == 1

    # A refresh with the same (now-addressed) review does not re-mark it.
    _reviews_say(fake_gh, "factory/demo-t01", old, _review(1, "alice", "CHANGES_REQUESTED", "Is this really needed?"),
                 _review(2, "alice", "APPROVED"))
    capsys.readouterr()
    assert main(["status", "--refresh"]) == 0
    assert open_db(home).task("demo-t01")["status"] == "pr_open"


def test_review_rework_needs_an_outstanding_request_on_the_factorys_candidate(factory_repo, home, fake_gh, monkeypatch, capsys):
    _use_model(monkeypatch, scripts(review_verdicts=["APPROVE"]))
    assert main(["run", "demo-t01", "--skip-gates", SKIP, *SANDBOX]) == 0
    db = open_db(home)
    head = db.task("demo-t01")["candidate_sha"]

    # (a) the request is approved between refresh and run -> pr_open, no agent runs.
    _reviews_say(fake_gh, "factory/demo-t01", head, _review(1, "alice", "CHANGES_REQUESTED"))
    assert main(["status", "--refresh"]) == 0
    assert db.task("demo-t01")["status"] == "changes_requested"
    _reviews_say(fake_gh, "factory/demo-t01", head, _review(1, "alice", "CHANGES_REQUESTED"),
                 _review(2, "alice", "APPROVED"))
    calls = _use_model(monkeypatch, scripts(review_verdicts=[]))
    capsys.readouterr()
    assert main(["run", "demo-t01", "--skip-gates", SKIP, *SANDBOX]) == 0
    assert "demo-t01: no review requests changes on https://github.test/pr/1; nothing to address" in capsys.readouterr().out
    assert calls == [] and open_db(home).task("demo-t01")["status"] == "pr_open"

    # (b) head != candidate -> refused with the someone-pushed message, status stays changes_requested.
    db.update("demo-t01", status="changes_requested",
              note="a review requests changes (@alice): `factory run demo-t01` addresses them")
    _ci_says(fake_gh, "factory/demo-t01", "f" * 40, FMT)
    capsys.readouterr()
    assert main(["run", "demo-t01", "--skip-gates", SKIP, *SANDBOX]) == 1
    assert "someone pushed to it. Address the reviews there, or --force to rebuild" in capsys.readouterr().err
    assert open_db(home).task("demo-t01")["status"] == "changes_requested"

    # (c) --force rebuilds from scratch: the planner runs, the new head is off the trunk, the same PR is reused.
    trunk = git(factory_repo, "rev-parse", "origin/main")
    calls = _use_model(monkeypatch, scripts(review_verdicts=["APPROVE"]))
    assert main(["run", "demo-t01", "--skip-gates", SKIP, "--force", *SANDBOX]) == 0
    row = open_db(home).task("demo-t01")
    assert "PLANNER" in {r for r, _ in calls}
    assert git(factory_repo, "rev-parse", f"{row['candidate_sha']}^") == trunk
    assert row["pr_url"] == "https://github.test/pr/1"
    assert sum(c[:2] == ["pr", "create"] for c in json.loads(fake_gh.read_text())["calls"]) == 1


def test_failed_review_rework_leaves_the_pr_alone(factory_repo, home, fake_gh, monkeypatch):
    _use_model(monkeypatch, scripts(review_verdicts=["APPROVE"]))
    assert main(["run", "demo-t01", "--skip-gates", SKIP, *SANDBOX]) == 0
    db = open_db(home)
    old = db.task("demo-t01")["candidate_sha"]

    _reviews_say(fake_gh, "factory/demo-t01", old, _review(1, "alice", "CHANGES_REQUESTED"))
    assert main(["status", "--refresh"]) == 0
    assert db.task("demo-t01")["status"] == "changes_requested"

    plays = scripts(review_verdicts=["CHANGES"])
    plays["BUILDER"] = [call("write_file", path="src/greet.txt", content="Hello\n"),
                        AIMessage("Did what I could.\nRESULT: DONE")]
    _use_model(monkeypatch, plays)
    assert main(["run", "demo-t01", "--skip-gates", SKIP, "--max-attempts", "1", *SANDBOX]) == 1
    row = open_db(home).task("demo-t01")
    assert row["status"] == "failed" and row["pr_url"] == "https://github.test/pr/1"
    assert "whose reviews are still unaddressed" in row["note"]
    assert "Running the task again rebuilds it from scratch" in row["note"]
    assert git(factory_repo, "ls-remote", "origin", "refs/heads/factory/demo-t01").split()[0] == old


def test_requested_changes_on_a_stacked_pr_are_addressed_after_the_restack(factory_repo, home, fake_gh,
                                                                          monkeypatch, capsys):
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
    t02 = db.task("demo-t02")["candidate_sha"]

    _reviews_say(fake_gh, "factory/demo-t02", t02, _review(1, "alice", "CHANGES_REQUESTED"))
    capsys.readouterr()
    assert main(["status", "--refresh"]) == 0
    assert db.task("demo-t02")["status"] == "changes_requested"

    # demo-t01 merges; the refresh moves demo-t02 onto main and keeps changes_requested.
    t01 = db.task("demo-t01")["candidate_sha"]
    git(factory_repo, "merge", "-q", "--squash", t01)
    git(factory_repo, "commit", "-q", "-m", "demo-t01 (#1)")
    git(factory_repo, "push", "-q", "origin", "main")
    _github_says(fake_gh, "factory/demo-t01", state="MERGED")
    capsys.readouterr()
    assert main(["status", "--refresh"]) == 0
    assert "demo-t02: rebased onto main, PR retargeted" in capsys.readouterr().err
    row = db.task("demo-t02")
    assert row["status"] == "changes_requested" and row["base_ref"] == "main"
    restacked = row["candidate_sha"]
    assert restacked != t02

    # Sync the head to the restacked candidate, then run: the rework builds on the restacked head.
    _reviews_say(fake_gh, "factory/demo-t02", restacked, _review(1, "alice", "CHANGES_REQUESTED"))
    plays = scripts(review_verdicts=["APPROVE"])
    plays["BUILDER"] = [call("write_file", path="docs/sessions/2026-10-09.md",
                             content="## [12:00] demo-t01\n## [12:05] demo-t02\n## [12:10] addressed review\n"),
                        AIMessage("Addressed the review.\nRESULT: DONE")]
    _use_model(monkeypatch, plays)
    assert main(["run", "demo-t02", "--skip-gates", SKIP, *SANDBOX]) == 0
    row = open_db(home).task("demo-t02")
    assert row["status"] == "pr_open" and row["base_ref"] == "main" and row["reviews_addressed"] == 1
    assert git(factory_repo, "rev-parse", f"{row['candidate_sha']}^") == restacked
    assert json.loads(fake_gh.read_text())["prs"]["factory/demo-t02"]["base"] == "main"
