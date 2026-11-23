"""The agent loop itself: step accounting, recursion backstop, trace, cached-token cost."""

import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from factory import agents, observe, prices
from factory.agents import Ctx, LangChainRoles, recursion_limit
from factory.contracts import parse_text
from fake_model import ScriptedModel, call
from conftest import plan_text


def _roles(tmp_path, max_steps):
    d = tmp_path / ".factory/agents"
    d.mkdir(parents=True)
    (d / "planner.md").write_text(f"---\nmodel: fake:x\nmax_steps: {max_steps}\n---\nYou are the PLANNER.\n")
    return LangChainRoles(tmp_path)


def _ctx(tmp_path, events):
    task = parse_text(plan_text(), "p.md")[0]
    return Ctx(task=task, worktree=tmp_path, base_sha="0" * 40, attempt=0, sandbox=None,
               record=events.append, log=lambda tag, msg: events.append({"type": "log", "msg": msg}))


def _review_roles(tmp_path, max_steps):
    d = tmp_path / ".factory/agents"
    d.mkdir(parents=True)
    (d / "reviewer.md").write_text(
        f"---\nmodel: fake:x\nmax_steps: {max_steps}\n---\n"
        "You are the REVIEWER.\n\nEnd with VERDICT: APPROVE or VERDICT: CHANGES.\n")
    return LangChainRoles(tmp_path)


def _review_ctx(tmp_path, events):
    task = parse_text(plan_text(), "p.md")[0]
    return Ctx(task=task, worktree=tmp_path, base_sha="0" * 40, attempt=1, sandbox=None,
               record=events.append,
               log=lambda tag, msg: events.append({"type": "log", "tag": tag, "msg": msg}))


def _watch_reviewer(monkeypatch, plays):
    seen = []

    class SeenModel(ScriptedModel):
        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            seen.append(list(messages))
            return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)

    monkeypatch.setattr(agents, "build_model", lambda spec: SeenModel(plays=plays))
    return seen


def test_finishing_on_the_last_allowed_step_is_not_killed(tmp_path, monkeypatch):
    """Regression: 4 graph nodes per step; a 2*steps+10 recursion limit killed runs that finished near max_steps."""
    max_steps = 25
    plays = {"PLANNER": [call("list_dir", path=".") for _ in range(max_steps - 1)] + [AIMessage("the plan")],
             "_calls": [], "_verdicts": []}
    monkeypatch.setattr(agents, "build_model", lambda spec: ScriptedModel(plays=plays))
    events = []
    out = _roles(tmp_path, max_steps).plan(_ctx(tmp_path, events))
    assert out.text == "the plan" and out.steps == max_steps and out.stopped is None
    assert recursion_limit(max_steps) > 4 * max_steps


def test_hitting_the_step_limit_is_reported_not_raised(tmp_path, monkeypatch):
    plays = {"PLANNER": [call("list_dir", path=".")] * 50, "_calls": [], "_verdicts": []}
    monkeypatch.setattr(agents, "build_model", lambda spec: ScriptedModel(plays=plays))
    events = []
    out = _roles(tmp_path, 5).plan(_ctx(tmp_path, events))
    assert out.stopped == "step limit" and out.steps == 5
    assert {"type": "stopped", "reason": "step limit", "steps": 5} in events
    assert any("⚠ stopped: step limit" in e.get("msg", "") for e in events)



def _reviewer_roles(tmp_path, max_steps):
    d = tmp_path / ".factory/agents"
    d.mkdir(parents=True)
    (d / "reviewer.md").write_text(f"---\nmodel: fake:x\nmax_steps: {max_steps}\n---\n"
                                   "You are the REVIEWER. End with VERDICT: APPROVE or VERDICT: CHANGES.\n")
    return LangChainRoles(tmp_path)


class Recording(ScriptedModel):
    """Records how tools were bound and every request the model was sent."""
    def bind_tools(self, tools, **kwargs):
        self.plays["_binds"].append(kwargs)
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.plays["_seen"].append(list(messages))
        return super()._generate(messages, stop, run_manager, **kwargs)


def _review_plays(*script):
    return {"REVIEWER": list(script), "_calls": [], "_verdicts": [], "_binds": [], "_seen": []}


def test_a_review_out_of_calls_gets_one_more_call_for_its_verdict(tmp_path, monkeypatch):
    """Regression: a review that ran out of model calls before its VERDICT line counted as CHANGES, skipping
    a proving review's proof and costing another build (factory-spec-t04 built three times for it)."""
    report = "## Findings\n1. [minor] fine\n\nVERDICT: APPROVE"
    plays = _review_plays(call("list_dir", path="."), call("list_dir", path="."), AIMessage(report))
    monkeypatch.setattr(agents, "build_model", lambda spec: Recording(plays=plays))
    events = []
    out = _reviewer_roles(tmp_path, 2).review(_ctx(tmp_path, events))

    assert out.verdict == "APPROVE" and out.text == report
    assert out.stopped == "step limit" and out.steps == 3          # the limit is still reported
    closing = plays["_seen"][-1]
    assert isinstance(closing[-1], HumanMessage) and closing[-1].content == agents.VERDICT_CALL
    assert sum(isinstance(m, ToolMessage) for m in closing) == 2   # it judges from what it already read
    assert not any(str(m.content).startswith(agents.CALL_LIMIT_MARKER) for m in closing)
    assert plays["_binds"][-1].get("tool_choice") == "none"
    assert {"type": "nudge", "kind": "verdict", "text": agents.VERDICT_CALL} in events


def test_a_review_with_its_verdict_gets_no_extra_call(tmp_path, monkeypatch):
    plays = _review_plays(call("list_dir", path="."), AIMessage("VERDICT: CHANGES"))
    monkeypatch.setattr(agents, "build_model", lambda spec: Recording(plays=plays))
    events = []
    out = _reviewer_roles(tmp_path, 2).review(_ctx(tmp_path, events))
    assert out.verdict == "CHANGES" and out.steps == 2 and out.stopped is None
    assert len(plays["_seen"]) == 2 and not any(e["type"] == "nudge" for e in events)


def test_a_failed_verdict_call_leaves_the_review_without_a_verdict(tmp_path, monkeypatch):
    class FailsToClose(Recording):
        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            if messages[-1].content == agents.VERDICT_CALL:
                raise RuntimeError("502: provider unavailable")
            return super()._generate(messages, stop, run_manager, **kwargs)

    plays = _review_plays(call("list_dir", path="."))
    monkeypatch.setattr(agents, "build_model", lambda spec: FailsToClose(plays=plays))
    events = []
    out = _reviewer_roles(tmp_path, 1).review(_ctx(tmp_path, events))
    assert out.verdict == "CHANGES" and out.stopped == "step limit" and out.steps == 1
    assert any("⚠ verdict call failed: RuntimeError: 502" in e.get("msg", "") for e in events)

def test_a_failing_tool_call_goes_back_to_the_model(tmp_path, monkeypatch):
    """Regression: list_dir on a directory the task is meant to create raised FileNotFoundError and killed the run."""
    plays = {"PLANNER": [call("list_dir", path="infra"), call("read_file", path=".factory"),
                         call("read_file", path="../outside.md"), AIMessage("the plan")],
             "_calls": [], "_verdicts": []}
    monkeypatch.setattr(agents, "build_model", lambda spec: ScriptedModel(plays=plays))
    events = []
    out = _roles(tmp_path, 10).plan(_ctx(tmp_path, events))
    assert out.text == "the plan" and out.stopped is None and out.steps == 4
    results = [e["content"] for e in events if e["type"] == "tool"]
    assert results[0] == "error: FileNotFoundError: [Errno 2] No such file or directory: 'infra'"
    assert results[1] == "error: IsADirectoryError: [Errno 21] Is a directory: '.factory'"
    assert results[2].startswith("error: PermissionError: ../outside.md is outside the worktree and the dependency sources")
    assert sum("⚠ list_dir: error:" in e.get("msg", "") for e in events) == 1


def test_a_model_that_keeps_failing_ends_the_run_with_its_error(tmp_path, monkeypatch):
    """Regression: out of credits, the retry middleware's error text was taken as the agent's answer
    (empty builds, CHANGES reviews) and three builds were burnt before the task failed."""
    class OutOfCredits(ScriptedModel):
        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            raise RuntimeError("402: This request would exceed your available credits")

    monkeypatch.setattr(agents, "MODEL_RETRY", {"max_retries": 1, "initial_delay": 0.0})
    monkeypatch.setattr(agents, "build_model", lambda spec: OutOfCredits(plays={"_calls": [], "_verdicts": []}))
    with pytest.raises(RuntimeError, match="available credits"):
        _roles(tmp_path, 5).plan(_ctx(tmp_path, []))


def test_reasoning_is_recorded_with_each_step(tmp_path, monkeypatch):
    reasoning = "The repository layout comes first; then the plan can name its files."
    plays = {"PLANNER": [call("list_dir", path="."), AIMessage(
        "the plan", additional_kwargs={"reasoning_content": reasoning},
        usage_metadata={"input_tokens": 100, "output_tokens": 30, "total_tokens": 130,
                        "output_token_details": {"reasoning": 25}})],
             "_calls": [], "_verdicts": []}
    monkeypatch.setattr(agents, "build_model", lambda spec: ScriptedModel(plays=plays))
    events = []
    out = _roles(tmp_path, 5).plan(_ctx(tmp_path, events))
    ai = [e for e in events if e["type"] == "ai"]
    assert ai[0]["reasoning"] == "" and ai[0]["usage"]["reasoning"] is None
    assert ai[1]["reasoning"] == reasoning
    assert ai[1]["usage"] == {"in": 100, "out": 30, "cache_read": 0, "reasoning": 25}
    assert ai[1]["text"] == "the plan" and out.text == "the plan"
    assert out.thinking == 25 and out.tokens_out == 30
    logs = [e["msg"] for e in events if e["type"] == "log"]
    assert any(line.startswith("done: 2 steps, 100 tokens in / 30 out (25 thinking)") for line in logs)


def test_reasoning_blocks_in_the_content_are_recorded_and_kept_out_of_the_answer(tmp_path, monkeypatch):
    reply = AIMessage(content=[{"type": "reasoning", "reasoning": "first"},
                               {"type": "reasoning", "reasoning": "second"},
                               {"type": "text", "text": "the plan"}])
    plays = {"PLANNER": [reply], "_calls": [], "_verdicts": []}
    monkeypatch.setattr(agents, "build_model", lambda spec: ScriptedModel(plays=plays))
    events = []
    out = _roles(tmp_path, 5).plan(_ctx(tmp_path, events))
    event = next(e for e in events if e["type"] == "ai")
    assert event["reasoning"] == "first\n\nsecond" and event["usage"]["reasoning"] is None
    assert event["text"] == "the plan" and out.text == "the plan"


def test_the_log_gets_a_thinks_line_before_the_step_says_and_calls(tmp_path, monkeypatch):
    reply = AIMessage(
        "considering", additional_kwargs={"reasoning_content": "t" * 1000},
        tool_calls=[{"name": "list_dir", "args": {"path": "."}, "id": "c-list_dir-1", "type": "tool_call"}])
    plays = {"PLANNER": [reply, AIMessage("the plan")], "_calls": [], "_verdicts": []}
    monkeypatch.setattr(agents, "build_model", lambda spec: ScriptedModel(plays=plays))
    events = []
    _roles(tmp_path, 5).plan(_ctx(tmp_path, events))
    logs = [e["msg"] for e in events if e["type"] == "log"]
    thinks = [line for line in logs if line.startswith("thinks: ")]
    assert thinks == ["thinks: " + "t" * 239 + "…"]
    says = logs.index("says: considering")
    call_log = next(i for i, line in enumerate(logs) if line.startswith("→ list_dir("))
    assert logs.index(thinks[0]) < says < call_log


def test_a_step_without_reasoning_records_none(tmp_path, monkeypatch):
    plays = {"PLANNER": [AIMessage("the plan")], "_calls": [], "_verdicts": []}
    monkeypatch.setattr(agents, "build_model", lambda spec: ScriptedModel(plays=plays))
    events = []
    out = _roles(tmp_path, 5).plan(_ctx(tmp_path, events))
    event = next(e for e in events if e["type"] == "ai")
    assert event["reasoning"] == "" and event["usage"]["reasoning"] is None
    logs = [e["msg"] for e in events if e["type"] == "log"]
    assert not any(line.startswith("thinks: ") for line in logs)
    assert out.thinking == 0
    assert "done: 1 steps, 0 tokens in / 0 out" in logs


def test_a_recorded_runs_thoughts_show_in_its_transcript_and_trace(tmp_path, monkeypatch):
    reasoning = "Read the repository first so the plan names real files."
    reply = AIMessage(
        "the plan", additional_kwargs={"reasoning_content": reasoning},
        usage_metadata={"input_tokens": 100, "output_tokens": 30, "total_tokens": 130,
                        "output_token_details": {"reasoning": 25}})
    plays = {"PLANNER": [reply], "_calls": [], "_verdicts": []}
    monkeypatch.setattr(agents, "build_model", lambda spec: ScriptedModel(plays=plays))
    events = []
    _roles(tmp_path, 5).plan(_ctx(tmp_path, events))
    transcript_path = tmp_path / "recorded-run.jsonl"
    transcript_path.write_text("\n".join(json.dumps(e) for e in events))

    transcript = observe.render_transcript(transcript_path)
    lines = transcript.splitlines()
    header = next(line for line in lines if "[agent step 1]" in line)
    assert "100 in / 30 out (25 thinking)" in header
    assert lines.index(header) < lines.index(f"thinks: {reasoning}") < lines.index("the plan")

    trace = observe.render_trace(transcript_path, width=200)
    row = next(line for line in trace.splitlines() if line.startswith("   1 "))
    assert f"{30:>6} {25:>6}" in row
    tokens = next(line for line in trace.splitlines() if line.lstrip().startswith("tokens "))
    assert tokens.endswith("output 30 (25 thinking)")


def test_trace_shows_context_growth_timing_and_largest_results(tmp_path):
    t = tmp_path / "run.jsonl"
    ev = [
        {"at": "2026-10-10T01:00:00.000+00:00", "type": "system", "model": "openrouter:x", "max_steps": 40, "content": "S" * 100},
        {"at": "2026-10-10T01:00:00.000+00:00", "type": "human", "content": "go"},
        {"at": "2026-10-10T01:00:02.000+00:00", "type": "ai", "step": 1, "text": "", "usage": {"in": 1000, "out": 50, "cache_read": 0},
         "cost_usd": 0.001, "tool_calls": [{"name": "read_file", "args": {"path": "src/a.rs"}}]},
        {"at": "2026-10-10T01:00:02.500+00:00", "type": "tool", "name": "read_file", "content": "x" * 9000},
        {"at": "2026-10-10T01:00:05.500+00:00", "type": "ai", "step": 2, "text": "", "usage": {"in": 3500, "out": 40, "cache_read": 1000},
         "cost_usd": 0.002, "tool_calls": [{"name": "run", "args": {"command": "cargo test -p x"}}]},
        {"at": "2026-10-10T01:01:05.500+00:00", "type": "tool", "name": "run", "content": "exit 0"},
        {"at": "2026-10-10T01:01:07.500+00:00", "type": "ai", "step": 3, "text": "done", "usage": {"in": 3600, "out": 300},
         "cost_usd": 0.003, "tool_calls": []},
    ]
    t.write_text("\n".join(json.dumps(e) for e in ev))
    rows = observe.trace_rows(ev)
    assert [r["model_s"] for r in rows] == [2.0, 3.0, 2.0]
    assert [r["tools_s"] for r in rows] == [0.5, 60.0, 0.0]
    assert [r["ctx_in"] for r in rows] == [1000, 3500, 3600] and rows[0]["result_chars"] == 9000
    out = observe.render_trace(t, width=200)
    assert "context re-sent every step: 1,000 → 3,600; 1,000 served from cache" in out
    assert "time  model 7s · tools 1m00s" in out
    assert "step 1: 9,000 chars read_file(path=src/a.rs)" in out
    assert "slowest tools  step 2: 1m00s run(command=cargo test -p x)" in out
    assert "final answer ×1" in out


def test_cached_input_is_priced_at_the_cache_rate(home):
    prices._memo.clear()
    cache = prices.cache_path()
    cache.parent.mkdir(parents=True)
    cache.write_text(json.dumps({"deepseek/v4": {"prompt": 1e-6, "completion": 2e-6, "cache_read": 0.1e-6},
                                 "z/no-cache": {"prompt": 1e-6, "completion": 2e-6}}))
    assert abs(prices.cost("openrouter:deepseek/v4", 1000, 10, cache_read=800) - (200e-6 + 80e-6 + 20e-6)) < 1e-12
    assert abs(prices.cost("openrouter:z/no-cache", 1000, 10, cache_read=800) - (1000e-6 + 20e-6)) < 1e-12
    prices._memo.clear()


def test_a_review_without_a_verdict_is_asked_once_more(tmp_path, monkeypatch):
    first = "## Findings\n1. [major] src/greet.txt:1 — check the greeting\n\nFinal verdict: APPROVE"
    reply = "## Findings\n1. [major] src/greet.txt:1 — the greeting is wrong\n\nVERDICT: CHANGES"
    plays = {"REVIEWER": [AIMessage(first), call("git_diff", stat=True), AIMessage(reply)],
             "_calls": [], "_verdicts": []}
    seen = _watch_reviewer(monkeypatch, plays)
    events = []

    out = _review_roles(tmp_path, 5).review(_review_ctx(tmp_path, events))

    assert out.reasked and out.verdict == "CHANGES" and out.text == reply and out.steps == 3
    reask = next(e for e in events if e["type"] == "reask")
    assert reask["content"].startswith("Your review ended without a VERDICT line.")
    assert ("review#1", "⚠ no VERDICT line: asking once more") in [
        (e["tag"], e["msg"]) for e in events if e["type"] == "log"]
    reask_at = events.index(reask)
    assert [e["type"] for e in events[reask_at + 1:] if e["type"] != "log"] == ["ai", "tool", "ai"]

    assert len(seen) == 3
    request = seen[1]
    assert isinstance(request[0], SystemMessage)
    assert isinstance(request[1], HumanMessage) and request[1].content == seen[0][1].content
    assert isinstance(request[2], AIMessage) and request[2].text == first
    assert isinstance(request[-1], HumanMessage) and request[-1].content == agents.REASK
    assert not any(str(m.content).startswith(agents.CALL_LIMIT_MARKER) for m in request)


def test_a_review_stopped_at_its_step_limit_is_asked_for_its_verdict(tmp_path, monkeypatch):
    closing = "## Findings\n1. [major] src/greet.txt:1 — still checking the greeting"
    reply = "## Findings\n1. [major] src/greet.txt:1 — the greeting is wrong\n\nVERDICT: CHANGES"
    plays = {"REVIEWER": [call("list_dir", path="."), call("list_dir", path="."), AIMessage(closing), AIMessage(reply)],
             "_calls": [], "_verdicts": []}
    seen = _watch_reviewer(monkeypatch, plays)
    events = []

    out = _review_roles(tmp_path, 2).review(_review_ctx(tmp_path, events))

    assert out.stopped == "step limit" and out.reasked
    assert out.verdict == "CHANGES" and out.text == reply
    kinds = [e["type"] for e in events]
    assert kinds.index("stopped") < kinds.index("reask")
    assert len(seen) == 4
    assert isinstance(seen[2][-1], HumanMessage) and seen[2][-1].content == agents.VERDICT_CALL
    assert isinstance(seen[3][-1], HumanMessage) and seen[3][-1].content == agents.REASK
    assert not any(str(m.content).startswith(agents.CALL_LIMIT_MARKER) for m in seen[3])


def test_a_review_still_without_a_verdict_counts_as_changes(tmp_path, monkeypatch):
    first = "## Findings\n1. [major] one unfinished finding"
    last = "## Findings\n1. [major] the last unfinished report\n\nFinal verdict: APPROVE"
    plays = {"REVIEWER": [AIMessage(first), AIMessage(last)], "_calls": [], "_verdicts": []}
    monkeypatch.setattr(agents, "build_model", lambda spec: ScriptedModel(plays=plays))
    events = []

    out = _review_roles(tmp_path, 5).review(_review_ctx(tmp_path, events))

    assert out.verdict == "CHANGES" and out.reasked and out.text == last and out.steps == 2
    assert len(plays["_calls"]) == 2

    cap_root = tmp_path / "capped"
    capped = {"REVIEWER": [call("list_dir", path=".")], "_calls": [], "_verdicts": []}
    monkeypatch.setattr(agents, "build_model", lambda spec: ScriptedModel(plays=capped))
    out = _review_roles(cap_root, 1).review(_review_ctx(cap_root, []))
    assert agents.REASK_STEPS == 3
    # The step-limit VERDICT_CALL precedes the REASK_STEPS calls in the same run.
    assert out.steps == 1 + 1 + agents.REASK_STEPS and out.verdict == "CHANGES"
    assert len(capped["_calls"]) == 1 + 1 + agents.REASK_STEPS


def test_a_review_with_a_verdict_is_not_asked_again(tmp_path, monkeypatch):
    reply = "## Findings\n1. [minor] ok\n\nVERDICT: APPROVE"
    plays = {"REVIEWER": [AIMessage(reply)], "_calls": [], "_verdicts": []}
    seen = _watch_reviewer(monkeypatch, plays)
    events = []

    out = _review_roles(tmp_path, 5).review(_review_ctx(tmp_path, events))

    assert out.reasked is False and out.verdict == "APPROVE" and out.text == reply
    assert not any(e["type"] == "reask" for e in events)
    assert not any("asking once more" in e.get("msg", "") for e in events)
    assert len(seen) == 1 and plays["_calls"] == [("REVIEWER", 0)]
