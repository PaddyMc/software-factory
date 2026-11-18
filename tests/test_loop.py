"""Opt-in agent loop behaviours: flow parsing, trimming, repository maps and nudges."""

from dataclasses import replace

import pytest
import yaml
from langchain.agents.middleware import ModelCallLimitMiddleware, ModelRetryMiddleware, ToolErrorMiddleware
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.messages.utils import count_tokens_approximately

from factory import agents
from factory import config as C
from factory import flows as F
from factory.agents import Ctx, LangChainRoles
from factory.cli import main
from factory.contracts import parse_text
from factory.sandbox import Unsandboxed
from factory.tools import READ_CAP, PathGuard, read_tools
from conftest import git, plan_text
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


def _builder_roles(tmp_path, max_steps=20):
    d = tmp_path / ".factory/agents"
    d.mkdir(parents=True)
    (d / "builder.md").write_text(
        f"---\nmodel: fake:x\nmax_steps: {max_steps}\n---\nYou are the BUILDER.\n")
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
    assert F.LOOP == ("trim", "map", "nudge")
    step = F.parse_step("careful", {"name": "reading", "kind": "build", "loop": ["trim"]})
    assert step.loop == ("trim",)
    assert F.parse_step("careful", "build").loop == ()
    assert F.parse_step("careful", {"kind": "build", "loop": []}).loop == ()
    for kind in ("plan", "build", "review", "verify"):
        for loop in (["map"], ["nudge"], ["trim", "map", "nudge"]):
            assert F.parse_step("careful", {"kind": kind, "loop": loop}).loop == tuple(loop)

    for loop, message in (("trim", "loop must be a list"),
                          (["sleep"], "unknown loop behaviour"),
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


def test_map_lists_the_tree_and_the_spec_references(tmp_path, monkeypatch):
    (tmp_path / "README.md").write_text("read me\n")
    (tmp_path / "ROOT.txt").write_text("root\n")
    (tmp_path / "factory/prompts").mkdir(parents=True)
    (tmp_path / "factory/x.py").write_text("one\ntwo\n")
    (tmp_path / "factory/prompts/y.md").write_text("prompt\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/a.py").write_text("test\n")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/spec.md").write_text("first\nsecond\nthird\n")
    git(tmp_path, "init", "-q")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "init")

    plays = {"PLANNER": [AIMessage("the plan")], "_calls": [], "_verdicts": [], "_seen": []}
    monkeypatch.setattr(agents, "build_model", lambda spec: SeenModel(plays=plays))
    events = []
    ctx = _ctx(tmp_path, events)
    ctx.task = replace(ctx.task, spec_refs=(
        "factory/x.py", "docs/spec.md#map", "https://example.org/spec", "missing.md"))
    out = _roles(tmp_path).step(F.Step("plan", "plan", loop=("map",)), ctx)

    human = next(e["content"] for e in events if e["type"] == "human")
    assert human == (
        "Plan task demo-t01.\n\n"
        "# Repository map\n"
        "README.md  ROOT.txt\n"
        "docs/ 1 files\n"
        "factory/ 2 files\n"
        "factory/prompts/ 1 files\n"
        "tests/ 1 files\n\n"
        "# Spec references\n"
        "- factory/x.py (2 lines)\n"
        "- docs/spec.md#map (docs/spec.md, 3 lines)\n"
        "- https://example.org/spec (not a file)\n"
        "- missing.md (not a file)"
    )
    assert out.steps == 1 and out.text == "the plan"

    monkeypatch.setattr(agents, "MAP_LINES", 4)
    capped = agents.repository_map(tmp_path, ctx.task.spec_refs)
    repository_lines = capped.split("\n\n# Spec references", 1)[0].splitlines()
    assert repository_lines == [
        "# Repository map", "README.md  ROOT.txt", "docs/ 1 files", "… (3 more directories)"]
    assert len(repository_lines) <= agents.MAP_LINES
    assert capped.endswith("- missing.md (not a file)")


def test_map_is_left_out_outside_a_git_work_tree(tmp_path, monkeypatch):
    plays = {"PLANNER": [AIMessage("the plan")], "_calls": [], "_verdicts": [], "_seen": []}
    monkeypatch.setattr(agents, "build_model", lambda spec: SeenModel(plays=plays))
    events = []
    out = _roles(tmp_path).step(F.Step("plan", "plan", loop=("map",)), _ctx(tmp_path, events))

    human = next(e["content"] for e in events if e["type"] == "human")
    assert human == "Plan task demo-t01."
    assert "# Repository map" not in human and "# Spec references" not in human
    assert out.steps == 1


def test_nudge_warns_once_near_the_step_limit(tmp_path, monkeypatch):
    plays = {"BUILDER": [call("list_dir", path=".") for _ in range(3)] + [AIMessage("done")],
             "_calls": [], "_verdicts": [], "_seen": []}
    monkeypatch.setattr(agents, "build_model", lambda spec: SeenModel(plays=plays))
    events = []
    ctx = _ctx(tmp_path, events)
    ctx.attempt = 1
    out = _builder_roles(tmp_path, max_steps=4).step(F.Step("build", "build", loop=("nudge",)), ctx)

    def budget_messages(messages):
        return [m for m in messages if isinstance(m, HumanMessage) and "allowed model calls" in str(m.content)]

    assert [len(budget_messages(messages)) for messages in plays["_seen"]] == [0, 0, 0, 1]
    nudge = budget_messages(plays["_seen"][3])[0]
    assert plays["_seen"][3][-1] is nudge
    assert "3 of 4" in nudge.text
    assert "Finish" in nudge.text and "run your checks" in nudge.text and "final report" in nudge.text
    recorded = [e for e in events if e["type"] == "nudge"]
    assert len(recorded) == 1 and recorded[0]["kind"] == "budget" and recorded[0]["text"] == nudge.text
    logs = [e for e in events if e["type"] == "log" and e["msg"].startswith("nudge: budget:")]
    assert len(logs) == 1 and logs[0]["tag"] == "build#1"
    assert len([e for e in events if e["type"] == "human"]) == 1
    assert out.steps == 4 and out.stopped is None and out.text == "done"


def test_nudge_names_a_file_edited_again_and_again(tmp_path, monkeypatch):
    path = "src/loop.py"
    writes = [
        call("write_file", path=path, content="value = 0\n"),
        call("edit_file", path=path, old="value = 0", new="value = 1"),
        call("write_file", path=path, content="value = 2\n"),
        call("edit_file", path=path, old="value = 2", new="value = 3"),
        call("write_file", path=path, content="value = 4\n"),
        call("edit_file", path=path, old="value = 4", new="value = 5"),
        call("write_file", path=path, content="value = 6\n"),
        call("edit_file", path=path, old="value = 6", new="value = 7"),
    ]
    plays = {"BUILDER": writes + [AIMessage("done")], "_calls": [], "_verdicts": [], "_seen": []}
    monkeypatch.setattr(agents, "build_model", lambda spec: SeenModel(plays=plays))
    monkeypatch.setattr(agents, "TRIM_AT", 1)                 # cleared results must not erase nudge history
    monkeypatch.setattr(agents, "TRIM_KEEP", 0)
    events = []
    ctx = _ctx(tmp_path, events)
    ctx.attempt = 1
    out = _builder_roles(tmp_path).step(F.Step("build", "build", loop=("trim", "nudge")), ctx)

    def edit_nudges(messages):
        return [m for m in messages if isinstance(m, HumanMessage) and "has been written" in str(m.content)]

    assert [len(edit_nudges(messages)) for messages in plays["_seen"]] == [0] * 6 + [1, 0, 0]
    nudge = edit_nudges(plays["_seen"][6])[0]
    assert plays["_seen"][6][-1] is nudge
    assert path in nudge.text and f"{agents.NUDGE_EDITS} times" in nudge.text
    assert "Re-read the failing output and the contract" in nudge.text
    recorded = [e for e in events if e["type"] == "nudge"]
    assert len(recorded) == 1 and recorded[0]["kind"] == "edits" and recorded[0]["text"] == nudge.text
    assert any(e["type"] == "trim" for e in events)
    logs = [e for e in events if e["type"] == "log" and e["msg"].startswith("nudge: edits:")]
    assert len(logs) == 1 and logs[0]["tag"] == "build#1"
    assert (tmp_path / path).read_text() == "value = 7\n"
    assert out.steps == 9 and out.stopped is None


def test_nudge_names_a_command_that_keeps_failing(tmp_path, monkeypatch):
    command = "test -f pass"
    script = [call("run", command=command) for _ in range(3)]
    script += [call("run", command="touch pass"), call("run", command=command),
               call("run", command="rm pass")]
    script += [call("run", command=command) for _ in range(2)]
    script += [call("run", command="git push") for _ in range(3)] + [AIMessage("done")]
    plays = {"BUILDER": script, "_calls": [], "_verdicts": [], "_seen": []}
    monkeypatch.setattr(agents, "build_model", lambda spec: SeenModel(plays=plays))
    events = []
    ctx = _ctx(tmp_path, events)
    ctx.attempt = 1
    ctx.sandbox = Unsandboxed(tmp_path)
    out = _builder_roles(tmp_path).step(F.Step("build", "build", loop=("nudge",)), ctx)

    def failing_nudges(messages):
        return [m for m in messages if isinstance(m, HumanMessage) and "has exited non-zero" in str(m.content)]

    assert [len(failing_nudges(messages)) for messages in plays["_seen"]] == [0, 0, 0, 1] + [0] * 8
    nudge = failing_nudges(plays["_seen"][3])[0]
    assert plays["_seen"][3][-1] is nudge
    assert command in nudge.text and f"{agents.NUDGE_FAILS} times in a row" in nudge.text
    assert "approach isn't working" in nudge.text
    recorded = [e for e in events if e["type"] == "nudge"]
    assert len(recorded) == 1 and recorded[0]["kind"] == "failing" and recorded[0]["text"] == nudge.text
    assert "git push" not in recorded[0]["text"]
    logs = [e for e in events if e["type"] == "log" and e["msg"].startswith("nudge: failing:")]
    assert len(logs) == 1 and logs[0]["tag"] == "build#1"
    assert out.steps == 12 and out.stopped is None and out.refused == 3
