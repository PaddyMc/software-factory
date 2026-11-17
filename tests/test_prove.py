"""Opt-in proving reviews: flow parsing, reviewer tools, REPRO evidence and verdicts."""

import pytest
import yaml
from langchain_core.messages import AIMessage

from factory import agents
from factory import config as C
from factory import flows as F
from factory.agents import Ctx, LangChainRoles
from factory.cli import main
from factory.contracts import parse_text
from factory.sandbox import Result, Unsandboxed
from conftest import plan_text
from fake_model import ScriptedModel


def _ctx(tmp_path, events):
    task = parse_text(plan_text(), "p.md")[0]
    return Ctx(task=task, worktree=tmp_path, base_sha="0" * 40, attempt=1,
               sandbox=Unsandboxed(tmp_path), record=events.append,
               log=lambda tag, msg: events.append({"type": "log", "tag": tag, "msg": msg}))


def _report(command: str, verdict: str | None = "CHANGES") -> str:
    ending = f"\n\nVERDICT: {verdict}" if verdict else ""
    return ("## Findings\n"
            "1. [major] src/greet.txt:1 — the greeting is wrong\n"
            f"   REPRO: {command}{ending}")


class StubSandbox:
    def __init__(self, results=None):
        self.results = results or {}
        self.calls = []

    def run(self, command, timeout=1800):
        self.calls.append((command, timeout))
        return self.results[command]


def test_prove_is_a_review_step_option(repo, monkeypatch, capsys):
    step = F.parse_step("careful", {"name": "audit", "kind": "review", "prove": True})
    assert step.prove is True
    assert F.parse_step("careful", {"name": "audit", "kind": "review"}).prove is False

    for kind in ("plan", "test", "build", "verify", "gates"):
        with pytest.raises(C.ConfigError) as error:
            F.parse_step("careful", {"name": "audit", "kind": kind, "prove": True})
        assert "careful" in str(error.value) and "audit" in str(error.value)
    for value in ("yes", 1, None):
        with pytest.raises(C.ConfigError, match="prove must be a boolean") as error:
            F.parse_step("careful", {"name": "audit", "kind": "review", "prove": value})
        assert "flows.careful.audit" in str(error.value)

    (repo / ".factory/config.yaml").write_text(
        "flow: careful\n"
        "flows:\n"
        "  careful:\n"
        "    - build\n"
        "    - {name: audit, kind: review, prove: true}\n")
    monkeypatch.chdir(repo)
    assert main(["config"]) == 0
    out = capsys.readouterr().out
    printed = yaml.safe_load(out)
    steps = printed["flows"]["careful"]["steps"]
    assert next(s for s in steps if s["name"] == "audit")["prove"] is True
    assert all("prove" in step for step in steps)
    assert "prove: true" in out


def test_a_proving_reviewer_can_run_commands_and_gets_the_proof_rules(tmp_path, monkeypatch):
    d = tmp_path / ".factory/agents"
    d.mkdir(parents=True)
    (d / "reviewer.md").write_text(
        "---\nmodel: fake:x\nmax_steps: 5\n---\n"
        "You are the REVIEWER.\n\nEnd with VERDICT: APPROVE or CHANGES.\n")
    plays = {"REVIEWER": [AIMessage("looks good\n\nVERDICT: APPROVE")], "_calls": [], "_verdicts": []}
    monkeypatch.setattr(agents, "build_model", lambda spec: ScriptedModel(plays=plays))
    created, real_create_agent = [], agents.create_agent

    def capture(model, tools, **kw):
        created.append((tools, kw["system_prompt"]))
        return real_create_agent(model, tools, **kw)

    monkeypatch.setattr(agents, "create_agent", capture)
    cfg = C.parse({"denied_commands": [r"\bforbidden\b"]})
    roles = LangChainRoles(tmp_path, cfg=cfg)
    proving = roles.step(F.Step("review", "review", prove=True), _ctx(tmp_path, []))
    plain = roles.step(F.Step("review", "review"), _ctx(tmp_path, []))

    proving_tools, proving_prompt = created[0]
    plain_tools, plain_prompt = created[1]
    assert [t.name for t in proving_tools] == ["read_file", "list_dir", "grep", "git_diff", "run"]
    assert [t.name for t in plain_tools] == ["read_file", "list_dir", "grep", "git_diff"]
    assert proving_prompt.index("# Project rules") < proving_prompt.index("# Proof rules")
    assert proving_prompt.index("# Proof rules") < proving_prompt.index("Today:")
    assert "REPRO:" in proving_prompt and "[scope]" in proving_prompt
    assert "# Proof rules" not in plain_prompt
    assert proving.prompt_version != plain.prompt_version

    run = next(t for t in proving_tools if t.name == "run")
    assert run.invoke({"command": "printf reviewer-ran"}) == "exit 0\nreviewer-ran"
    assert run.invoke({"command": "git commit -m nope"}).startswith("refused:")
    assert run.invoke({"command": "echo forbidden"}).startswith("refused:")


def test_changes_stands_on_a_reproduced_failure(tmp_path):
    report, verdict, outcome = agents.apply_proof(
        _report("printf 'candidate broke\\n'; exit 7"), "CHANGES", Unsandboxed(tmp_path), ())

    assert verdict == outcome == "CHANGES"
    assert "## Proof" in report
    assert "printf 'candidate broke" in report and "reproduced" in report
    assert "candidate broke" in report


def test_changes_stands_on_a_scope_finding(tmp_path):
    for finding in ("[major] [scope] src/greet.txt:1", "[major]\n   [scope] src/greet.txt:1"):
        text = _report("true").replace("[major] src/greet.txt:1", finding)
        report, verdict, outcome = agents.apply_proof(text, "CHANGES", Unsandboxed(tmp_path), ())

        assert verdict == outcome == "CHANGES"
        assert "[scope] src/greet.txt:1" in report
        assert "## Proof" in report and "passed" in report

    assert not agents.has_scope_finding(
        "1. [major] src/a.py:1 — no tag\n2. [minor] [scope] src/b.py:2 — only this minor is scoped")


def test_unproven_changes_becomes_an_approval(tmp_path):
    original = _report("printf 'nothing failed\\n'")
    report, verdict, outcome = agents.apply_proof(original, "CHANGES", Unsandboxed(tmp_path), ())

    assert verdict == "APPROVE"
    assert outcome == "APPROVE (unproven)"
    assert "1. [major] src/greet.txt:1 — the greeting is wrong" in report
    assert "VERDICT: CHANGES" in report
    assert "## Proof" in report and "nothing failed" in report and "passed" in report


def test_a_passing_timed_out_or_denied_repro_is_unproven():
    cases = (
        ("passing", Result(0, "ok\n"), "passed"),
        ("slow", Result(-1, f"timeout after {agents.PROVE_TIMEOUT}s"), "timed out"),
        ("git push origin main", None, "denied"),
    )
    for command, result, word in cases:
        sandbox = StubSandbox({command: result} if result is not None else {})
        report, verdict, outcome = agents.apply_proof(_report(command), "CHANGES", sandbox, ())
        assert verdict == "APPROVE" and outcome == "APPROVE (unproven)"
        assert f"**{word}**" in report
        expected = [] if word == "denied" else [(command, agents.PROVE_TIMEOUT)]
        assert sandbox.calls == expected

    text = "\n".join(["REPRO: echo 0", "  REPRO: echo 0"]
                     + [f"REPRO: echo {i}" for i in range(1, agents.PROVE_MAX + 2)])
    assert agents.parse_repros(text) == [f"echo {i}" for i in range(agents.PROVE_MAX)]


def test_a_missing_verdict_is_still_changes(tmp_path):
    for command in ("false", "true"):
        text = _report(command, verdict=None)
        report, verdict, outcome = agents.apply_proof(
            text, agents.parse_verdict(text), Unsandboxed(tmp_path), ())
        assert verdict == outcome == "CHANGES"
        assert "VERDICT:" not in text
        assert "## Proof" in report
