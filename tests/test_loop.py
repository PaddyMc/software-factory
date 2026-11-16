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
    assert F.LOOP == ("trim", "map", "nudge", "resume")
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


def test_resume_is_for_build_steps_only():
    assert "resume" in F.LOOP
    step = F.parse_step("careful", {"name": "fix", "kind": "build", "loop": ["trim", "resume"]})
    assert step.loop == ("trim", "resume")

    for kind in ("plan", "review", "verify"):
        with pytest.raises(C.ConfigError, match="only valid on build steps") as error:
            F.parse_step("careful", {"name": "fix", "kind": kind, "loop": ["resume"]})
        assert "careful" in str(error.value) and "fix" in str(error.value)
    with pytest.raises(C.ConfigError, match="gates step") as error:
        F.parse_step("careful", {"kind": "gates", "loop": ["resume"]})
    assert "careful" in str(error.value) and "gates" in str(error.value)


def test_a_resumed_attempt_continues_the_conversation_with_the_feedback(tmp_path, monkeypatch):
    (tmp_path / "big.txt").write_text("MARKER-" + "x" * 2000 + "\n")
    git(tmp_path, "init", "-q")
    git(tmp_path, "add", "big.txt")
    git(tmp_path, "commit", "-q", "-m", "init")
    monkeypatch.setattr(agents, "TRIM_AT", 200)
    monkeypatch.setattr(agents, "TRIM_KEEP", 0)
    plays = {"BUILDER": [call("read_file", path="big.txt"), AIMessage("first attempt report"),
                         AIMessage("second attempt report")],
             "_calls": [], "_verdicts": [], "_seen": []}
    monkeypatch.setattr(agents, "build_model", lambda spec: SeenModel(plays=plays))
    roles = _builder_roles(tmp_path)
    step = F.Step("build", "build", loop=("trim", "map", "resume"))

    first_events = []
    first_ctx = _ctx(tmp_path, first_events)
    first_ctx.attempt = 1
    first_ctx.plan = "the original plan"
    first = roles.step(step, first_ctx)

    second_events = []
    second_ctx = _ctx(tmp_path, second_events)
    second_ctx.attempt = 2
    second_ctx.plan = "a new plan must not be sent"
    second_ctx.feedback = "verification failed; fix the greeting"
    second_ctx.earlier = ("The preceding build step finished.",)
    second = roles.step(step, second_ctx)

    assert first.steps == 2 and first.text == "first attempt report"
    assert second.steps == 1 and second.text == "second attempt report"
    assert len(plays["_seen"]) == 3
    request = plays["_seen"][2]
    assert [type(m) for m in request] == [SystemMessage, HumanMessage, AIMessage, ToolMessage,
                                          AIMessage, HumanMessage]
    assert request[1].content.startswith("Implement task demo-t01 (attempt 1).\n\n# Plan\n\nthe original plan")
    assert request[2].tool_calls[0]["name"] == "read_file"
    assert request[3].content == "[cleared: read_file(path=big.txt): call it again if you need it]"
    assert request[4].text == "first attempt report"
    assert request[5].content == (
        "# Attempt 2\n\n"
        "# Feedback to address first\n\nverification failed; fix the greeting\n\n"
        "# Earlier build steps in this attempt\n\n1. The preceding build step finished."
    )
    assert sum("# Plan" in str(m.content) for m in request[1:]) == 1
    assert sum("# Repository map" in str(m.content) for m in request[1:]) == 1

    recorded = [e for e in second_events if e["type"] != "log"]
    assert [e["type"] for e in recorded[:3]] == ["resumed", "system", "human"]
    assert recorded[0] == {"type": "resumed", "messages": 4}
    assert recorded[2]["content"] == request[5].content
    assert len([e for e in recorded if e["type"] == "human"]) == 1
    assert not [e for e in recorded if e["type"] == "tool"]
    assert [e["text"] for e in recorded if e["type"] == "ai"] == ["second attempt report"]
    assert any(e["type"] == "tool" and "MARKER-" in e["content"] for e in first_events)


def test_each_attempt_has_its_own_step_limit_and_counts(tmp_path, monkeypatch):
    def used(message, tin, tout):
        return message.model_copy(update={"usage_metadata": {
            "input_tokens": tin, "output_tokens": tout, "total_tokens": tin + tout}})

    plays = {"BUILDER": [
        used(call("list_dir", path="."), 10, 1),
        used(call("list_dir", path="."), 20, 2),
        AIMessage("not played"),
        used(call("list_dir", path="."), 30, 3),
        used(call("list_dir", path="."), 40, 4),
    ], "_calls": [], "_verdicts": [], "_seen": []}
    monkeypatch.setattr(agents, "build_model", lambda spec: SeenModel(plays=plays))
    monkeypatch.setattr(agents.prices, "cost", lambda spec, tin, tout, cached: tin / 1000)
    roles = _builder_roles(tmp_path, max_steps=2)
    step = F.Step("build", "build", loop=("resume",))

    first_events = []
    first_ctx = _ctx(tmp_path, first_events)
    first_ctx.attempt = 1
    first = roles.step(step, first_ctx)
    second_events = []
    second_ctx = _ctx(tmp_path, second_events)
    second_ctx.attempt = 2
    second_ctx.feedback = "keep going"
    second = roles.step(step, second_ctx)

    for out, tin, tout, cost in ((first, 30, 3, 0.03), (second, 70, 7, 0.07)):
        assert out.steps == 2 and out.stopped == "step limit"
        assert (out.tokens_in, out.tokens_out) == (tin, tout)
        assert out.cost_usd == pytest.approx(cost)
    assert len(plays["_seen"]) == 4                 # two fresh model calls in each attempt
    assert [e["step"] for e in first_events if e["type"] == "ai"] == [1, 2]
    assert [e["step"] for e in second_events if e["type"] == "ai"] == [1, 2]
    resumed = next(e for e in second_events if e["type"] == "resumed")
    assert resumed["messages"] == 6                 # human, two calls/results, and the limit marker


def test_the_first_attempt_and_a_resolve_start_fresh(tmp_path, monkeypatch):
    class SometimesFails(SeenModel):
        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            if any(isinstance(m, HumanMessage) and "BOOM" in str(m.content) for m in messages):
                raise RuntimeError("model exploded")
            return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)

    monkeypatch.setattr(agents, "MODEL_RETRY", {"max_retries": 1, "initial_delay": 0.0})
    plays = {"BUILDER": [AIMessage("done")], "_calls": [], "_verdicts": [], "_seen": []}
    monkeypatch.setattr(agents, "build_model", lambda spec: SometimesFails(plays=plays))
    roles = _builder_roles(tmp_path)
    step = F.Step("build", "build", loop=("resume",))

    first_events = []
    first = _ctx(tmp_path, first_events)
    first.attempt = 1
    first.plan = "the plan"
    roles.step(step, first)
    assert any("first attempt of the step in this run" in e.get("msg", "") for e in first_events)
    assert len(roles.resumes["build"].messages) == 2

    resolve_events = []
    resolve = _ctx(tmp_path, resolve_events)
    resolve.attempt = 1
    resolve.resolution = "the conflict brief"
    roles.resolve(resolve, step)
    assert any("conflict resolution" in e.get("msg", "") for e in resolve_events)
    assert not roles.resumes                              # a resolve neither resumes nor seeds memory

    after_resolve_events = []
    after_resolve = _ctx(tmp_path, after_resolve_events)
    after_resolve.attempt = 2
    after_resolve.plan = "the plan"
    after_resolve.feedback = "review after the resolve"
    roles.step(step, after_resolve)
    assert any("nothing to resume after a conflict resolution" in e.get("msg", "")
               for e in after_resolve_events)
    assert not [e for e in after_resolve_events if e["type"] == "resumed"]

    failed = _ctx(tmp_path, [])
    failed.attempt = 3
    failed.feedback = "BOOM"
    with pytest.raises(RuntimeError, match="model exploded"):
        roles.step(step, failed)
    assert roles.resumes["build"].error

    recovered_events = []
    recovered = _ctx(tmp_path, recovered_events)
    recovered.attempt = 4
    recovered.plan = "the plan"
    recovered.feedback = "recovered"
    roles.step(step, recovered)
    assert any("an earlier attempt ended in an error" in e.get("msg", "") for e in recovered_events)
    human = next(e["content"] for e in recovered_events if e["type"] == "human")
    assert human.startswith("Implement task demo-t01 (attempt 4).\n\n# Plan")
    assert not [e for e in recovered_events if e["type"] == "resumed"]

    # Every fresh case sent one new task message, never an earlier conversation.
    assert [[type(m) for m in request] for request in plays["_seen"]] == [
        [SystemMessage, HumanMessage], [SystemMessage, HumanMessage],
        [SystemMessage, HumanMessage], [SystemMessage, HumanMessage],
    ]
