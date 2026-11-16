"""factory top, merged logs, liveness, cost."""

import json
import subprocess
import sys

from factory import observe, prices
from factory.cli import main
from factory.contracts import parse_text
from factory.db import open_db, pid_alive
from conftest import plan_text


def _db(home):
    db = open_db(home)
    for t in parse_text(plan_text(), "docs/plans/demo/demo.md"):
        db.upsert_task(t)
    return db


def _dead_pid():
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    return p.pid


def test_top_shows_running_task_activity_cost_and_failures(home):
    db = _db(home)
    import os
    db.update("demo-t01", status="building", attempts=1)
    db.claim("demo-t01", os.getpid())
    run = db.start_run("demo-t01", "build", 1)
    db.progress("demo-t01", run, "build#1 step 7/120 · 12k in / 1k out · $0.021", 7, 12000, 1000, 0.021)
    db.heartbeat("demo-t01", "[build#1] → run(command=cargo test -p demo-node)")
    (home / "logs").mkdir()
    (home / "logs/demo-t01.log").write_text("00:00:01 [stage] building (build #1)\n00:00:02 [build#1] → run(command=cargo test)\n")
    screen = observe.render_top(db, home, width=200)
    assert "1 running" in screen and "spent $0.02" in screen
    assert "demo-t01" in screen and "building" in screen and "build#1 step 7/120" in screen and "$0.02" in screen
    assert "↳ [build#1] → run(command=cargo test -p demo-node)" in screen
    assert "recent events" in screen and "demo-t01                       00:00:02 [build#1]" in screen


def test_dead_run_is_flagged_and_refresh_fails_it(home, monkeypatch, capsys):
    db = _db(home)
    db.update("demo-t01", status="building")
    db.claim("demo-t01", _dead_pid())
    assert not pid_alive(db.task("demo-t01")["pid"])
    assert "DEAD: process" in observe.detail(db, db.task("demo-t01"))
    assert main(["status"]) == 0
    assert "DEAD" in capsys.readouterr().out
    assert main(["status", "--refresh"]) == 0
    row = open_db(home).task("demo-t01")
    assert row["status"] == "failed" and "exited mid-run" in row["note"]


def test_logs_all_merges_tasks_in_time_order(home, capsys):
    (home / "logs").mkdir()
    (home / "logs/a-t01.log").write_text("10:00:01 [stage] one\n10:00:03 [stage] three\n")
    (home / "logs/b-t01.log").write_text("10:00:02 [stage] two\n")
    assert main(["logs", "--all"]) == 0
    lines = [l.split()[0] + " " + l.split()[-1] for l in capsys.readouterr().out.splitlines()]
    assert lines == ["a-t01 one", "b-t01 two", "a-t01 three"]


def test_cost_from_cached_openrouter_prices(home):
    prices._memo.clear()
    cache = prices.cache_path()
    cache.parent.mkdir(parents=True)
    cache.write_text(json.dumps({"z-ai/glm-5.3": {"prompt": 0.04e-6, "completion": 6e-6}}))
    assert abs(prices.cost("openrouter:z-ai/glm-5.3", 1_000_000, 1_000) - (0.04 + 0.006)) < 1e-9
    assert prices.cost("openrouter:unknown/model", 10, 10) is None
    assert prices.cost("anthropic:claude-opus-5-5", 10, 10) is None
    prices._memo.clear()


def test_top_and_status_group_tasks_by_plan_with_a_task_counter(home, capsys):
    import os
    from conftest import TASK
    db = _db(home)
    for t in parse_text(plan_text(TASK.replace("demo-", "other-")), "docs/plans/x/other.md"):
        db.upsert_task(t)
    db.update("demo-t01", status="pr_open", candidate_sha="c1", pr_url="https://github.test/pr/1")
    db.update("demo-t02", status="building", stacked_on="demo-t01")
    db.claim("demo-t02", os.getpid())
    screen = observe.render_top(db, home, width=200)
    assert "demo  ◆▶  0/2 merged · 1 PR open · 1 running · $0.00" in screen
    lines = screen.splitlines()
    assert lines.index(next(l for l in lines if l.startswith("demo  "))) < \
        lines.index(next(l for l in lines if l.startswith("  demo-t01")))
    assert "other plans" in screen and "other" in screen.split("other plans")[1]
    assert "0/2 merged · 1 ready · 1 waiting" in screen.split("other plans")[1]
    only = observe.render_top(db, home, width=200, plan="other")
    assert "other  ··  0/2 merged · 1 ready · 1 waiting" in only and "demo-t01" not in only

    assert main(["status", "demo"]) == 0
    out = capsys.readouterr().out
    assert out.splitlines()[0] == "demo  ◆▶  0/2 merged · 1 PR open · 1 running" and "other-t01" not in out
    assert "https://github.test/pr/1" in out


def test_transcript_shows_each_steps_thoughts_first(tmp_path):
    reasoning = "Compare the header per step, then read the report module."
    long_reasoning = "t" * 3000
    events = [
        {"at": "2026-11-16T09:00:03.000+00:00", "type": "ai", "step": 1,
         "text": "The compare header is missing the step's prompt hash.", "reasoning": reasoning,
         "usage": {"in": 18204, "out": 210, "reasoning": 318}, "cost_usd": 0.004,
         "tool_calls": [{"name": "read_file", "args": {"path": "factory/bench/report.py"}}]},
        {"at": "2026-11-16T09:00:04.000+00:00", "type": "ai", "step": 2, "text": "The plan is ready.",
         "reasoning": long_reasoning, "usage": {"in": 19000, "out": 40, "reasoning": 0},
         "cost_usd": None, "tool_calls": []},
    ]
    path = tmp_path / "run.jsonl"
    path.write_text("\n".join(json.dumps(e) for e in events))

    rendered = observe.render_transcript(path)
    lines = rendered.splitlines()
    header = next(line for line in lines if "[agent step 1]" in line)
    assert header.endswith("18204 in / 210 out (318 thinking) $0.0040")
    assert lines.index(header) < lines.index(f"thinks: {reasoning}") \
        < lines.index("The compare header is missing the step's prompt hash.") \
        < lines.index('  → read_file {"path": "factory/bench/report.py"}')
    assert "thinks: " + "t" * 2000 in rendered
    assert "… (1000 more chars; --full)" in rendered
    assert "[agent step 2] 19000 in / 40 out\nthinks: " in rendered

    full = observe.render_transcript(path, full=True)
    assert "thinks: " + long_reasoning in full
    assert "… (1000 more chars; --full)" not in full


def test_a_model_that_did_not_share_its_thoughts_is_said_so(tmp_path):
    events = [
        {"at": "2026-11-16T09:00:03.000+00:00", "type": "ai", "step": 1, "text": "Done.",
         "reasoning": "", "usage": {"in": 100, "out": 30, "reasoning": 121}, "tool_calls": []},
        {"at": "2026-11-16T09:00:04.000+00:00", "type": "ai", "step": 2, "text": "No thought.",
         "reasoning": "", "usage": {"in": 120, "out": 10, "reasoning": None}, "tool_calls": []},
    ]
    path = tmp_path / "run.jsonl"
    path.write_text("\n".join(json.dumps(e) for e in events))

    lines = observe.render_transcript(path).splitlines()
    header = "09:00:03 [agent step 1] 100 in / 30 out (121 thinking)"
    thinks = "thinks: (121 tokens; the model didn't share its reasoning)"
    assert lines.index(header) < lines.index(thinks) < lines.index("Done.")
    assert sum(line.startswith("thinks:") for line in lines) == 1
    assert "09:00:04 [agent step 2] 120 in / 10 out" in lines


def test_trace_counts_thinking_tokens(tmp_path):
    events = [
        {"at": "2026-11-16T09:00:00.000+00:00", "type": "system", "model": "fake:x", "max_steps": 5,
         "content": "S" * 20},
        {"at": "2026-11-16T09:00:01.000+00:00", "type": "human", "content": "go"},
        {"at": "2026-11-16T09:00:03.000+00:00", "type": "ai", "step": 1, "text": "",
         "usage": {"in": 1000, "out": 210, "cache_read": 0, "reasoning": 152}, "cost_usd": 0.004,
         "tool_calls": [{"name": "read_file", "args": {"path": "src/a.rs"}}]},
        {"at": "2026-11-16T09:00:04.000+00:00", "type": "tool", "name": "read_file", "content": "contents"},
        {"at": "2026-11-16T09:00:05.000+00:00", "type": "ai", "step": 2, "text": "next",
         "usage": {"in": 1200, "out": 40, "cache_read": 0}, "cost_usd": None, "tool_calls": []},
        {"at": "2026-11-16T09:00:06.000+00:00", "type": "ai", "step": 3, "text": "done",
         "usage": {"in": 1300, "out": 300, "cache_read": 0, "reasoning": None}, "cost_usd": 0.002,
         "tool_calls": []},
    ]
    path = tmp_path / "run.jsonl"
    path.write_text("\n".join(json.dumps(e) for e in events))

    assert [r["thinking"] for r in observe.trace_rows(events)] == [152, None, None]
    rendered = observe.render_trace(path, width=200)
    lines = rendered.splitlines()
    head = lines[2].split()
    assert head[head.index("out"):head.index("out") + 3] == ["out", "think", "cost"]
    step1 = next(line for line in lines if line.startswith("   1 "))
    step2 = next(line for line in lines if line.startswith("   2 "))
    assert f"{210:>6} {152:>6}" in step1
    assert f"{40:>6} {'-':>6}" in step2
    tokens = next(line for line in lines if line.lstrip().startswith("tokens "))
    assert tokens.endswith("output 550 (152 thinking)")

    for event in events:
        if event["type"] == "ai":
            event["usage"].pop("reasoning", None)
    path.write_text("\n".join(json.dumps(e) for e in events))
    without_counts = observe.render_trace(path, width=200)
    old_lines = without_counts.splitlines()
    for step, output in ((1, 210), (2, 40), (3, 300)):
        row = next(line for line in old_lines if line.startswith(f"{step:>4} "))
        assert f"{output:>6} {'-':>6}" in row
    old_tokens = next(line for line in old_lines if line.lstrip().startswith("tokens "))
    assert old_tokens.endswith("output 550")
    assert "thinking" not in without_counts


def test_transcripts_without_thoughts_print_as_before(tmp_path):
    events = [
        {"at": "2026-11-16T09:00:00.000+00:00", "type": "system", "model": "fake:x", "max_steps": 5,
         "content": "system prompt"},
        {"at": "2026-11-16T09:00:01.000+00:00", "type": "human", "content": "Plan the work"},
        {"at": "2026-11-16T09:00:02.000+00:00", "type": "ai", "step": 1, "text": "Read the file.",
         "usage": {"in": 100, "out": 20}, "cost_usd": 0.001,
         "tool_calls": [{"name": "read_file", "args": {"path": "src/a.rs"}}]},
        {"at": "2026-11-16T09:00:03.000+00:00", "type": "tool", "name": "read_file", "content": "contents"},
    ]
    path = tmp_path / "old-run.jsonl"
    path.write_text("\n".join(json.dumps(e) for e in events))

    assert observe.render_transcript(path) == "\n".join([
        "09:00:00 [system] model=fake:x max_steps=5 (13 chars; --full to show)",
        "09:00:01 [task message]",
        "Plan the work",
        "09:00:02 [agent step 1] 100 in / 20 out $0.0010",
        "Read the file.",
        '  → read_file {"path": "src/a.rs"}',
        "09:00:03 [tool read_file]",
        "contents",
    ])

    trace = observe.render_trace(path, width=200)
    row = next(line for line in trace.splitlines() if line.startswith("   1 "))
    assert f"{20:>6} {'-':>6}" in row
    tokens = next(line for line in trace.splitlines() if line.lstrip().startswith("tokens "))
    assert tokens.endswith("output 20")
    assert "thinking" not in trace
