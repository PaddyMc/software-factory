"""End to end: every agent run records the instructions it ran under, apart from the per-task parts.

Everything is real (CLI, LangGraph, LangChain agents and tools, git, bwrap when present)
except the LLM (ScriptedModel) and GitHub (fake `gh` + a bare `origin`).
"""

import hashlib
import json
import re
import shutil

import pytest

from factory import agents, config as C, flows
from factory.cli import main
from factory.db import open_db
from langchain_core.messages import AIMessage

from fake_model import ScriptedModel, call, scripts
from conftest import git

SKIP = "unit_tests,e2e_tests"   # the toy repo has no Cargo workspace
SANDBOX = [] if shutil.which("bwrap") else ["--no-sandbox"]
SECOND = "#[test]\nfn second_e2e() {\n    assert!(true);\n}\n"
AGENT_RUNS = (("plan", "plan"), ("build", "build"), ("review", "review"), ("verify", "verify"))


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


def test_each_agent_run_records_its_prompt_version(factory_repo, home, fake_gh, monkeypatch):
    _use_model(monkeypatch, scripts(review_verdicts=["APPROVE"]))
    assert main(["run", "demo-t01", "--skip-gates", SKIP, *SANDBOX]) == 0

    db = open_db(home)
    runs = db.runs("demo-t01")
    versions = {(r["role"], r["step"]): r["prompt_version"] for r in runs}
    for key in AGENT_RUNS:
        assert re.fullmatch(r"[0-9a-f]{12}", versions[key])
    assert versions[("verify", "gates")] is None
    assert versions[("pr", "pr")] is None

    build = next(r for r in runs if (r["role"], r["step"]) == ("build", "build"))
    events = [json.loads(line) for line in open(build["transcript"])]
    system = next(event["content"] for event in events if event["type"] == "system")
    assert "# Task `demo-t01`" in system and "Today:" in system
    prompt_body = agents.load_step(factory_repo, flows.Step("build", "build"))[1].strip()
    rules = agents.project_rules(C.load(factory_repo))
    guidance = "# Repository guidance (AGENTS.md)\n\n" + (home / "worktrees/demo-t01/AGENTS.md").read_text()
    expected = hashlib.sha256(
        "\n\n".join(x for x in (prompt_body, rules, guidance) if x).encode()).hexdigest()[:12]
    assert build["prompt_version"] == expected


def test_two_tasks_under_the_same_prompts_share_a_version(factory_repo, home, fake_gh, monkeypatch):
    _use_model(monkeypatch, scripts(review_verdicts=["APPROVE"]))
    assert main(["run", "demo-t01", "--skip-gates", SKIP, *SANDBOX]) == 0
    db = open_db(home)
    first = {(r["role"], r["step"]): r["prompt_version"] for r in db.runs("demo-t01")}

    plays = scripts(review_verdicts=["APPROVE"])
    plays["BUILDER"] = [call("write_file", path="crates/e2e/tests/second.rs", content=SECOND),
                        call("write_file", path="docs/sessions/2026-10-09.md",
                             content="## [12:00] demo-t01\n## [12:05] demo-t02\n"),
                        AIMessage("Second thing.\nRESULT: DONE")]
    _use_model(monkeypatch, plays)
    assert main(["run", "demo-t02", "--skip-gates", SKIP, *SANDBOX]) == 0
    second = {(r["role"], r["step"]): r["prompt_version"] for r in db.runs("demo-t02")}

    for key in AGENT_RUNS:
        assert re.fullmatch(r"[0-9a-f]{12}", first[key])
        assert re.fullmatch(r"[0-9a-f]{12}", second[key])
        assert second[key] == first[key]


def test_editing_a_role_prompt_changes_only_that_roles_version(factory_repo, home, fake_gh, monkeypatch):
    _use_model(monkeypatch, scripts(review_verdicts=["APPROVE"]))
    assert main(["run", "demo-t01", "--skip-gates", SKIP, *SANDBOX]) == 0
    db = open_db(home)
    before_rows = db.runs("demo-t01")
    before = {(r["role"], r["step"]): r["prompt_version"] for r in before_rows}
    old_ids = {r["id"] for r in before_rows}

    builder = factory_repo / ".factory/agents/builder.md"
    builder.write_text(builder.read_text() + "Measure this instruction change.\n")
    git(factory_repo, "add", ".factory/agents/builder.md")
    git(factory_repo, "commit", "-q", "-m", "change builder instructions")
    git(factory_repo, "push", "-q", "origin", "main")
    _use_model(monkeypatch, scripts(review_verdicts=["APPROVE"]))
    assert main(["run", "demo-t01", "--skip-gates", SKIP, "--force", *SANDBOX]) == 0

    after = {(r["role"], r["step"]): r["prompt_version"]
             for r in db.runs("demo-t01") if r["id"] not in old_ids}
    assert after[("build", "build")] != before[("build", "build")]
    for key in (("plan", "plan"), ("review", "review"), ("verify", "verify")):
        assert after[key] == before[key]


def test_editing_the_repository_guidance_changes_every_roles_version(factory_repo, home, fake_gh, monkeypatch):
    _use_model(monkeypatch, scripts(review_verdicts=["APPROVE"]))
    assert main(["run", "demo-t01", "--skip-gates", SKIP, *SANDBOX]) == 0
    db = open_db(home)
    before_rows = db.runs("demo-t01")
    before = {(r["role"], r["step"]): r["prompt_version"] for r in before_rows}
    old_ids = {r["id"] for r in before_rows}

    (factory_repo / "AGENTS.md").write_text("# Demo repo\nAlways run the tests before answering.\n")
    git(factory_repo, "add", "AGENTS.md")
    git(factory_repo, "commit", "-q", "-m", "change repository guidance")
    git(factory_repo, "push", "-q", "origin", "main")
    _use_model(monkeypatch, scripts(review_verdicts=["APPROVE"]))
    assert main(["run", "demo-t01", "--skip-gates", SKIP, "--force", *SANDBOX]) == 0

    after = {(r["role"], r["step"]): r["prompt_version"]
             for r in db.runs("demo-t01") if r["id"] not in old_ids}
    for key in AGENT_RUNS:
        assert re.fullmatch(r"[0-9a-f]{12}", after[key])
        assert after[key] != before[key]


def test_show_prints_each_runs_prompt_version(factory_repo, home, fake_gh, monkeypatch, capsys):
    _use_model(monkeypatch, scripts(review_verdicts=["APPROVE"]))
    assert main(["run", "demo-t01", "--skip-gates", SKIP, *SANDBOX]) == 0
    capsys.readouterr()

    assert main(["show", "demo-t01"]) == 0
    lines = capsys.readouterr().out.splitlines()
    for run in open_db(home).runs("demo-t01"):
        header = next(line for line in lines
                      if line.startswith(f"## {run['role']} #{run['attempt']} — {run['outcome']}"))
        assert f"{run['model'] or '-'}, prompt {run['prompt_version'] or '-'}," in header
