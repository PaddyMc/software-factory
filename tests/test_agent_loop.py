"""The agent loop itself: step accounting, recursion backstop, trace, cached-token cost."""

import json

import pytest
from langchain_core.messages import AIMessage

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
    assert results[2] == "error: PermissionError: ../outside.md is outside the worktree"
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
