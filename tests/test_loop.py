"""Opt-in agent loop behaviours: flow parsing, capped reads and batched context trimming."""

import pytest
import yaml
from langchain.agents.middleware import ModelCallLimitMiddleware, ModelRetryMiddleware, ToolErrorMiddleware
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_core.messages.utils import count_tokens_approximately

from factory import agents
from factory import config as C
from factory import flows as F
from factory.agents import Ctx, LangChainRoles
from factory.cli import main
from factory.contracts import parse_text
from factory.tools import READ_CAP, PathGuard, read_tools
from conftest import plan_text
from fake_model import ScriptedModel, call


class SeenModel(ScriptedModel):
    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.plays["_seen"].append(list(messages))
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


def _roles(tmp_path, max_steps=20):
    d = tmp_path / ".factory/agents"
    d.mkdir(parents=True)
    (d / "planner.md").write_text(
        f"---\nmodel: fake:x\nmax_steps: {max_steps}\n---\nYou are the PLANNER.\n")
    return LangChainRoles(tmp_path)


def _ctx(tmp_path, events):
    task = parse_text(plan_text(), "p.md")[0]
    return Ctx(task=task, worktree=tmp_path, base_sha="0" * 40, attempt=0, sandbox=None,
               record=events.append,
               log=lambda tag, msg: events.append({"type": "log", "tag": tag, "msg": msg}))


def _tools(messages):
    return [m for m in messages if isinstance(m, ToolMessage)]


def _conversation_tokens(messages):
    return count_tokens_approximately(m for m in messages if not isinstance(m, SystemMessage))


def _trim_run(tmp_path, monkeypatch):
    """Two batches: four old results at call 7, then two more at call 9, keeping the latest two."""
    monkeypatch.setattr(agents, "TRIM_AT", 540)
    monkeypatch.setattr(agents, "TRIM_KEEP", 2)
    for i in range(8):
        (tmp_path / f"{i}.txt").write_text(f"MARKER-{i}-" + "x" * 200 + "\n")
    plays = {"PLANNER": [call("read_file", path=f"{i}.txt") for i in range(8)] + [AIMessage("done")],
             "_calls": [], "_verdicts": [], "_seen": []}
    monkeypatch.setattr(agents, "build_model", lambda spec: SeenModel(plays=plays))
    events = []
    out = _roles(tmp_path).step(F.Step("plan", "plan", loop=("trim",)), _ctx(tmp_path, events))
    return out, events, plays


def test_loop_is_a_list_of_known_behaviours(repo, monkeypatch, capsys):
    assert F.LOOP == ("trim",)
    step = F.parse_step("careful", {"name": "reading", "kind": "build", "loop": ["trim"]})
    assert step.loop == ("trim",)
    assert F.parse_step("careful", "build").loop == ()
    assert F.parse_step("careful", {"kind": "build", "loop": []}).loop == ()

    for loop, message in (("trim", "loop must be a list"),
                          (["map"], "unknown loop behaviour"),
                          (["trim", "trim"], "appears more than once")):
        with pytest.raises(C.ConfigError, match=message) as error:
            F.parse_step("careful", {"name": "reading", "kind": "build", "loop": loop})
        assert "careful" in str(error.value) and "reading" in str(error.value)
    with pytest.raises(C.ConfigError, match="gates step") as error:
        F.parse_step("careful", {"kind": "gates", "loop": ["trim"]})
    assert "careful" in str(error.value) and "gates" in str(error.value)

    (repo / ".factory/config.yaml").write_text(
        "flows:\n"
        "  careful:\n"
        "    - {kind: build, loop: [trim]}\n"
        "    - review\n")
    monkeypatch.chdir(repo)
    assert main(["config"]) == 0
    out = capsys.readouterr().out
    printed = yaml.safe_load(out)
    steps = printed["flows"]["careful"]["steps"]
    assert [s["loop"] for s in steps] == [["trim"], [], []]
    assert "loop: []" in out


def test_trim_caps_a_read_and_says_how_to_read_on(tmp_path, monkeypatch):
    text = "".join(f"line-{i:03}\n" for i in range(1, 451))
    (tmp_path / "big.txt").write_text(text)
    guard = PathGuard(tmp_path)
    capped = {t.name: t for t in read_tools(tmp_path, guard, cap=READ_CAP)}["read_file"]

    result = capped.invoke({"path": "big.txt"})
    lines = result.splitlines()
    assert len(lines) == READ_CAP + 1
    assert lines[0] == "1\tline-001" and lines[READ_CAP - 1] == "400\tline-400"
    assert lines[-1] == "… 50 more of 450 lines; read on from start 401"
    rest = capped.invoke({"path": "big.txt", "start": 401}).splitlines()
    assert len(rest) == 50 and rest[0] == "401\tline-401" and rest[-1] == "450\tline-450"

    fits = capped.invoke({"path": "big.txt", "start": 20, "end": 100}).splitlines()
    assert len(fits) == 81 and fits[0].startswith("20\t") and fits[-1].startswith("100\t")
    cut = capped.invoke({"path": "big.txt", "start": 25, "end": 999}).splitlines()
    assert len(cut) == READ_CAP + 1 and cut[READ_CAP - 1] == "424\tline-424"
    assert cut[-1] == "… 26 more of 450 lines; read on from start 425"

    uncapped = {t.name: t for t in read_tools(tmp_path, guard)}["read_file"]
    expected = "\n".join(f"{i}\tline-{i:03}" for i in range(1, 451))
    assert uncapped.invoke({"path": "big.txt"}) == expected

    plays = {"PLANNER": [call("read_file", path="big.txt"), AIMessage("the plan")],
             "_calls": [], "_verdicts": []}
    monkeypatch.setattr(agents, "build_model", lambda spec: ScriptedModel(plays=plays))
    events = []
    out = _roles(tmp_path, max_steps=2).step(
        F.Step("plan", "plan", loop=("trim",)), _ctx(tmp_path, events))
    tool = next(e for e in events if e["type"] == "tool")
    assert tool["content"] == result
    assert out.steps == 2 and out.stopped is None
    assert not [e for e in events if e["type"] == "trim"]


def test_trim_clears_old_results_in_batches_and_keeps_the_latest(tmp_path, monkeypatch):
    out, events, plays = _trim_run(tmp_path, monkeypatch)
    trims = [e for e in events if e["type"] == "trim"]
    assert len(trims) == 2 and [e["cleared"] for e in trims] == [4, 2]
    for event in trims:
        assert event["tokens_before"] > agents.TRIM_AT
        assert event["tokens_after"] < event["tokens_before"]

    cleared_counts = [sum(str(m.content).startswith(agents.CLEARED_MARK) for m in _tools(messages))
                      for messages in plays["_seen"]]
    assert cleared_counts == [0, 0, 0, 0, 0, 0, 4, 4, 6]
    assert _conversation_tokens(plays["_seen"][7]) <= agents.TRIM_AT

    results = _tools(plays["_seen"][6])
    assert [m.content for m in results[:-2]] == [
        f"[cleared: read_file(path={i}.txt): call it again if you need it]" for i in range(4)]
    assert all("\n" not in m.content for m in results[:-2])
    assert results[-2].content == "1\tMARKER-4-" + "x" * 200
    assert results[-1].content == "1\tMARKER-5-" + "x" * 200
    assert out.text == "done" and out.steps == 9 and out.stopped is None


def test_cleared_results_stay_cleared_and_the_transcript_keeps_them(tmp_path, monkeypatch):
    out, events, plays = _trim_run(tmp_path, monkeypatch)
    first_batch = _tools(plays["_seen"][6])
    placeholders = [m.content for m in first_batch[:4]]
    for messages in plays["_seen"][7:]:
        assert [m.content for m in _tools(messages)[:4]] == placeholders

    tools = [e for e in events if e["type"] == "tool"]
    assert len(tools) == 8
    assert [e["content"] for e in tools] == [f"1\tMARKER-{i}-" + "x" * 200 for i in range(8)]
    assert all(not e["content"].startswith(agents.CLEARED_MARK) for e in tools)
    trims = [e for e in events if e["type"] == "trim"]
    assert len(trims) == 2
    assert all({"cleared", "tokens_before", "tokens_after"} <= set(e) for e in trims)
    logs = [e for e in events if e["type"] == "log" and e["msg"].startswith("trim: cleared")]
    assert len(logs) == 2 and all(e["tag"] == "plan" for e in logs)
    assert [f"cleared {n} tool results" in e["msg"] for e, n in zip(logs, (4, 2))] == [True, True]
    assert out.text == "done"


def test_without_loop_the_agent_is_built_as_today(tmp_path, monkeypatch):
    plays = {"PLANNER": [AIMessage("the plan")], "_calls": [], "_verdicts": []}
    monkeypatch.setattr(agents, "build_model", lambda spec: ScriptedModel(plays=plays))
    created, real_create_agent = [], agents.create_agent

    def capture(model, tools, **kw):
        agent = real_create_agent(model, tools, **kw)
        created.append((kw["middleware"], [t.name for t in tools], set(agent.get_graph().nodes)))
        return agent

    monkeypatch.setattr(agents, "create_agent", capture)
    roles = _roles(tmp_path)
    roles.step(F.Step("plan", "plan"), _ctx(tmp_path, []))
    roles.step(F.Step("plan", "plan", loop=("trim",)), _ctx(tmp_path, []))

    expected = [ModelCallLimitMiddleware, ModelRetryMiddleware, ToolErrorMiddleware]
    assert [type(m) for m in created[0][0]] == expected
    assert created[0][1] == ["read_file", "list_dir", "grep"]
    assert [type(m) for m in created[1][0]] == expected + [agents.TrimMiddleware]
    assert sum(isinstance(m, agents.TrimMiddleware) for m in created[1][0]) == 1
    assert created[1][1] == created[0][1]
    assert created[1][2] == created[0][2]
