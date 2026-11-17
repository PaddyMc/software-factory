"""End-to-end bench runs: real pipelines and git, with scripted models and no GitHub calls."""

import copy
import datetime as dt
import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from langchain_core.messages import AIMessage

from factory import agents, prices
from factory.cli import main
from factory.db import open_db
from conftest import git
from fake_model import ScriptedModel, call


SANDBOX = [] if shutil.which("bwrap") else ["--no-sandbox"]
BENCH_CASES = Path(__file__).parent / "bench_cases"
GOOD_CALC = (BENCH_CASES / "adder/solution/calc/__init__.py").read_text()
VISIBLE_TEST = (BENCH_CASES / "adder/solution/tests/test_adder.py").read_text()
BAD_CALC = """def double(x):
    return x * 2


def add(a, b):
    return 5
"""


def _plays(calc: str) -> dict:
    return {
        "PLANNER": [call("list_dir", path="."), AIMessage("**Files**: calc/__init__.py, tests/test_adder.py\n**Steps**: implement add and test it")],
        "BUILDER": [
            call("write_file", path="calc/__init__.py", content=calc),
            call("write_file", path="tests/test_adder.py", content=VISIBLE_TEST),
            call("run", command="python3 -m unittest -q"),
            AIMessage("Implemented add and its visible test.\nRESULT: DONE"),
        ],
        "REVIEWER": [call("git_diff", stat=True), "VERDICT"],
        "VERIFIER": [call("read_file", path="calc/__init__.py"), AIMessage(
            "TITLE: Adds integer addition\n\n## What changed\n- calc.add returns a sum and has a visible test\n\n"
            "## What to check\n- hidden arithmetic cases\n")],
        "_verdicts": [],
        "_calls": [],
    }


GOOD = _plays(GOOD_CALC)
BAD = _plays(BAD_CALC)
STRICT_REPRO = "python3 -c 'from calc import add; assert add(2, 3) == 5'"
STRICT_GOOD = {
    "TESTER": [call("write_file", path="tests/test_adder.py", content=VISIBLE_TEST), AIMessage(
        "Wrote the locked acceptance test for calc.add.")],
    "BUILDER": [
        call("write_file", path="calc/__init__.py", content=GOOD_CALC),
        call("run", command="python3 -m unittest -q"),
        AIMessage("Implemented calc.add without changing the acceptance test.\nRESULT: DONE"),
    ],
    "REVIEWER": [
        call("git_diff", stat=True),
        call("run", command=STRICT_REPRO),
        AIMessage(f"## Findings\n1. [minor] calc/__init__.py:1 — no blocking findings\n"
                  f"   REPRO: {STRICT_REPRO}\n\nVERDICT: APPROVE"),
    ],
    "VERIFIER": [call("read_file", path="calc/__init__.py"), AIMessage(
        "TITLE: Adds integer addition\n\n## What changed\n- calc.add returns a sum\n\n"
        "## What to check\n- hidden arithmetic cases\n")],
    "_verdicts": [],
    "_calls": [],
}
CONFIGURED_SPECS = tuple(f"fake:{role}" for role in ("planner", "builder", "reviewer", "verifier"))


@pytest.fixture
def bench_repo(repo, home, fake_gh, monkeypatch):
    agents_dir = repo / ".factory/agents"
    agents_dir.mkdir(parents=True)
    for role in ("planner", "builder", "reviewer", "verifier"):
        (agents_dir / f"{role}.md").write_text(
            f"---\nmodel: fake:{role}\nmax_steps: 20\n---\n"
            f"You are the {role.upper()} for one bench task.\n"
        )
    with (repo / ".factory/config.yaml").open("a") as f:
        f.write("flows:\n  lean: [build, review]\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "bench agents and lean flow")
    monkeypatch.setenv("FAKE_API_KEY", "x")
    monkeypatch.setitem(agents.PROVIDER_KEYS, "fake", "FAKE_API_KEY")
    monkeypatch.chdir(repo)
    return repo


def _scripted(monkeypatch, plays_by_spec):
    def build(spec):
        if spec not in plays_by_spec:
            raise AssertionError(f"unexpected model spec: {spec}")
        return ScriptedModel(plays=copy.deepcopy(plays_by_spec[spec]))

    monkeypatch.setattr(agents, "build_model", build)


CHILD_BOOTSTRAP = r"""
import copy
import json
import os
import sys
import time

sys.path.insert(0, os.environ["BENCH_T05_TESTS_DIR"])
import test_bench
from factory import agents, prices
from factory.bench.run import cell_main

plays = {"scripted:good": test_bench.GOOD, "scripted:bad": test_bench.BAD}
def build(spec):
    if spec not in plays:
        raise AssertionError(f"unexpected model spec: {spec}")
    return test_bench.ScriptedModel(plays=copy.deepcopy(plays[spec]))
agents.build_model = build
if "BENCH_T05_FAKE_COST" in os.environ:
    fake_cost = float(os.environ["BENCH_T05_FAKE_COST"])
    prices.cost = lambda spec, tin, tout, cache_read=0: fake_cost

def log(event):
    with open(os.environ["BENCH_T05_LOG"], "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "pid": os.getpid(), "event": event,
            "dir": sys.argv[sys.argv.index("--dir") + 1],
            "cost_limit": float(sys.argv[sys.argv.index("--cost-limit") + 1]),
        }) + "\n")

log("start")
try:
    time.sleep(float(os.environ.get("BENCH_T05_SLEEP", "0")))
    code = cell_main(sys.argv[1:])
finally:
    log("end")
sys.exit(code)
"""


def _child_launcher(monkeypatch, tmp_path, *, sleep=0.0, cost=None, crash_numbers=(), ctrl_c_at=None):
    """Run real cell_main children with scripted models, plus optional crash/interrupt injection."""
    import factory.bench.run as bench_run

    log_path = tmp_path / "children.jsonl"
    monkeypatch.setenv("BENCH_T05_TESTS_DIR", str(Path(__file__).resolve().parent))
    monkeypatch.setenv("BENCH_T05_LOG", str(log_path))
    monkeypatch.setenv("BENCH_T05_SLEEP", str(sleep))
    if cost is not None:
        monkeypatch.setenv("BENCH_T05_FAKE_COST", str(cost))
    launches = 0

    def factory(root, *, cases_dir, max_attempts, sandbox_on):
        def launch(cell):
            nonlocal launches
            launches += 1
            if launches == ctrl_c_at:
                raise KeyboardInterrupt
            if cell.number in crash_numbers:
                argv = [sys.executable, "-c", "import sys; sys.stderr.write('boom\\n'); sys.exit(3)"]
            else:
                argv = [sys.executable, "-c", CHILD_BOOTSTRAP,
                        *bench_run.cell_argv(cell, cases_dir=cases_dir, max_attempts=max_attempts,
                                             sandbox_on=sandbox_on)]
            return subprocess.Popen(argv, cwd=root, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.PIPE, start_new_session=True, text=True)
        return launch

    monkeypatch.setattr(bench_run, "default_launch", factory)
    monkeypatch.setattr(bench_run, "POLL_SECONDS", 0.02)
    return log_path


def _args(*extra, max_cost="5", cases=BENCH_CASES, sandbox=True):
    args = ["bench", "run", "--cases", str(cases)]
    if max_cost is not None:
        args += ["--max-cost", str(max_cost)]
    if sandbox:
        args += SANDBOX
    return args + list(extra)


def bench_run_dir(home: Path) -> Path:
    runs = list((home / "bench").iterdir())
    assert len(runs) == 1
    return runs[0]


def load_results(home: Path) -> dict:
    return json.loads((bench_run_dir(home) / "results.json").read_text())


def test_a_bench_run_scores_each_cell_with_gates_and_hidden_tests(bench_repo, home, monkeypatch):
    _scripted(monkeypatch, {"scripted:good": GOOD, "scripted:bad": BAD})
    assert main(_args("--model", "scripted:good", "--model", "scripted:bad")) == 0

    results = load_results(home)
    assert list(results["variants"]) == ["default@scripted:good", "default@scripted:bad"]
    assert results["cases"]["adder"]["kind"] == "feature"
    assert len(results["cases"]["adder"]["base"]) == 40
    assert len(results["cases"]["adder"]["fixture_sha"]) == 64
    assert [cell["outcome"] for cell in results["cells"]] == ["solved", "false_pass"]
    fields = {"variant", "case", "repeat", "outcome", "attempts", "cost_usd", "seconds", "model_calls",
              "tokens_in", "tokens_out", "review_changes", "step_limit_stops", "failed_gates", "dir"}
    for cell in results["cells"]:
        assert set(cell) == fields
        assert cell["case"] == "adder" and cell["repeat"] == 1
        assert cell["attempts"] == 1 and cell["model_calls"] > 0
        assert cell["cost_usd"] == 0.0 and cell["seconds"] >= 0
        assert cell["tokens_in"] == cell["tokens_out"] == 0
        assert cell["review_changes"] == cell["step_limit_stops"] == 0
        assert cell["failed_gates"] == []
        directory = bench_run_dir(home) / cell["dir"]
        assert (directory / "factory.db").is_file()
        assert (directory / "repo").is_dir()
        assert (directory / "worktrees").is_dir()
        assert (directory / "logs").is_dir()
        assert (directory / "transcripts").is_dir()
        db = open_db(directory)
        gate = next(run for run in db.runs("adder-t01") if run["step"] == "gates")
        assert gate["outcome"] == "pass" and gate["sha"] == db.task("adder-t01")["candidate_sha"]
        db.close()

    good, bad = results["cells"]
    good_log = (bench_run_dir(home) / good["dir"] / "hidden.log").read_text()
    bad_log = (bench_run_dir(home) / bad["dir"] / "hidden.log").read_text()
    assert "python3 -m unittest -v bench_hidden.test_adder" in good_log
    assert "Ran 4 tests" in good_log and "OK" in good_log and "hidden: PASS" in good_log
    assert "Ran 4 tests" in bad_log and "FAILED" in bad_log and "hidden: FAIL" in bad_log


def test_a_strict_cell_is_scored_like_any_other(bench_repo, home, monkeypatch):
    _scripted(monkeypatch, {"scripted:strict": STRICT_GOOD})
    assert main(_args("--flow", "strict", "--model", "scripted:strict")) == 0

    results = load_results(home)
    cell = results["cells"][0]
    assert cell["outcome"] == "solved" and cell["attempts"] == 1
    assert "hidden: PASS" in (bench_run_dir(home) / cell["dir"] / "hidden.log").read_text()
    db = open_db(bench_run_dir(home) / cell["dir"])
    runs = db.runs("adder-t01")
    assert [(run["role"], run["step"]) for run in runs] == [
        ("test", "test"), ("build", "build"), ("verify", "gates"),
        ("review", "review"), ("verify", "verify"),
    ]
    assert runs[0]["outcome"] == "committed" and runs[0]["sha"]
    gates = next(run for run in runs if run["step"] == "gates")
    assert gates["outcome"] == "pass" and "acceptance_untouched" in gates["report"]
    review = next(run for run in runs if run["role"] == "review")
    assert review["outcome"] == "APPROVE"
    assert "## Proof" in review["report"] and "Result: **passed**" in review["report"]
    events = [json.loads(line) for line in Path(review["transcript"]).read_text().splitlines()]
    system = next(event["content"] for event in events if event["type"] == "system")
    assert "# Proof rules" in system
    db.close()


def test_each_variant_runs_its_flow_and_model(bench_repo, home, monkeypatch):
    _scripted(monkeypatch, {spec: GOOD for spec in CONFIGURED_SPECS})
    assert main(_args("--flow", "default", "--flow", "lean")) == 0
    results = load_results(home)
    assert list(results["variants"]) == ["default", "lean"]

    for cell in results["cells"]:
        db = open_db(bench_run_dir(home) / cell["dir"])
        runs = db.runs("adder-t01")
        assert all(run["flow"] == cell["variant"] for run in runs)
        assert all(run["step"] for run in runs)
        steps = {run["step"] for run in runs}
        if cell["variant"] == "lean":
            assert "plan" not in steps and "verify" not in steps
            assert steps == {"build", "review", "gates"}
        else:
            assert {"plan", "build", "review", "gates", "verify"} == steps
        described = {step["name"]: step for step in results["variants"][cell["variant"]]["steps"]}
        for run in runs:
            if run["step"] != "gates":
                assert run["model"] == described[run["step"]]["model"]
        db.close()

    assert results["variants"]["default"]["model"] is None
    assert results["variants"]["default"]["steps"][0]["model"] == "fake:planner"
    lean_steps = {step["name"]: step for step in results["variants"]["lean"]["steps"]}
    assert lean_steps["build"]["model"] == "fake:builder"
    assert lean_steps["review"]["model"] == "fake:reviewer"


def test_prompts_and_flows_come_from_the_invoking_repository(bench_repo, home, monkeypatch):
    _scripted(monkeypatch, {"scripted:good": GOOD})
    assert main(_args("--flow", "default", "--flow", "lean", "--model", "scripted:good")) == 0
    results = load_results(home)
    assert list(results["variants"]) == ["default@scripted:good", "lean@scripted:good"]

    prompt = (bench_repo / ".factory/agents/builder.md").read_text()
    default = results["variants"]["default@scripted:good"]
    build = next(step for step in default["steps"] if step["name"] == "build")
    assert build["prompt_sha"] == hashlib.sha256(prompt.encode()).hexdigest()
    default_cell = next(cell for cell in results["cells"] if cell["variant"] == "default@scripted:good")
    db = open_db(bench_run_dir(home) / default_cell["dir"])
    build_run = next(run for run in db.runs("adder-t01") if run["step"] == "build")
    events = [json.loads(line) for line in Path(build_run["transcript"]).read_text().splitlines()]
    system = next(event["content"] for event in events if event["type"] == "system")
    assert prompt.split("---\n", 2)[-1].strip() in system
    db.close()

    lean_cell = next(cell for cell in results["cells"] if cell["variant"] == "lean@scripted:good")
    db = open_db(bench_run_dir(home) / lean_cell["dir"])
    assert {run["step"] for run in db.runs("adder-t01")} == {"build", "review", "gates"}
    db.close()


def test_a_bench_run_leaves_the_board_and_the_repository_alone(bench_repo, home, fake_gh, monkeypatch):
    assert main(["sync"]) == 0
    db = open_db(home)
    before_board = [dict(row) for row in db.tasks()]
    db.close()
    before_db = (home / "factory.db").read_bytes()
    before_refs = git(bench_repo, "for-each-ref")
    before_worktrees = git(bench_repo, "worktree", "list", "--porcelain")
    fake_gh.write_text(json.dumps({"prs": {}, "calls": []}))
    _scripted(monkeypatch, {"scripted:good": GOOD})

    assert main(_args("--model", "scripted:good")) == 0
    assert git(bench_repo, "for-each-ref") == before_refs
    assert git(bench_repo, "worktree", "list", "--porcelain") == before_worktrees
    assert (home / "factory.db").read_bytes() == before_db
    db = open_db(home)
    assert [dict(row) for row in db.tasks()] == before_board
    db.close()
    assert json.loads(fake_gh.read_text())["calls"] == []
    for cell in load_results(home)["cells"]:
        assert git(bench_run_dir(home) / cell["dir"] / "repo", "remote") == ""


def test_sync_releases_the_board_database(bench_repo, home, monkeypatch):
    import factory.cli as cli

    opened = []
    real_db = cli._db

    def retain_db():
        db = real_db()
        opened.append(db)
        return db

    monkeypatch.setattr(cli, "_db", retain_db)
    assert main(["sync"]) == 0
    assert len(opened) == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        opened[0].tasks()


def test_the_budget_caps_cells_and_stops_starting_new_ones(bench_repo, home, monkeypatch):
    monkeypatch.setattr(prices, "cost", lambda spec, tin, tout, cache_read=0: 0.40)
    _scripted(monkeypatch, {"scripted:good": GOOD})
    assert main(_args("--model", "scripted:good", "--repeat", "3", max_cost="1.0")) == 1
    results = load_results(home)
    assert [cell["outcome"] for cell in results["cells"]] == ["stopped", "skipped", "skipped"]
    first, *later = results["cells"]
    assert first["cost_usd"] >= 1.0 and first["dir"] is not None
    assert all(cell["dir"] is None and cell["cost_usd"] == 0.0 for cell in later)
    assert all(cell["attempts"] == 0 for cell in later)


def test_a_flow_with_a_test_step_needs_the_cases_test_paths(bench_repo, home, tmp_path, monkeypatch, capsys):
    missing = tmp_path / "missing-test-paths" / "adder"
    missing.parent.mkdir()
    shutil.copytree(BENCH_CASES / "adder", missing)
    data = yaml.safe_load((missing / "case.yaml").read_text())
    del data["config"]["test_paths"]
    (missing / "case.yaml").write_text(yaml.safe_dump(data, sort_keys=False))
    monkeypatch.setattr(agents, "build_model", lambda spec: (_ for _ in ()).throw(
        AssertionError("a cell started")))

    assert main(_args("--flow", "strict", "--model", "scripted:good", cases=missing.parent)) == 1
    error = capsys.readouterr().err
    assert "adder" in error and "strict" in error and "test_paths" in error
    assert not (home / "bench").exists()


def test_bench_run_refuses_before_any_work(bench_repo, home, tmp_path, monkeypatch, capsys):
    def refuse(extra, expected, *, cases=BENCH_CASES, sandbox=True):
        assert main(_args(*extra, cases=cases, sandbox=sandbox)) == 1
        captured = capsys.readouterr()
        assert expected in captured.err
        assert not (home / "bench").exists()

    assert main(_args(max_cost=None)) == 1
    assert "--max-cost is required" in capsys.readouterr().err
    assert not (home / "bench").exists()
    refuse(("--flow", "nope"), "unknown flow nope (flows: default, lean, strict)")
    refuse(("--case", "nope"), "unknown case nope (cases: adder)")

    broken = tmp_path / "broken-cases" / "adder"
    broken.parent.mkdir()
    shutil.copytree(BENCH_CASES / "adder", broken)
    (broken / "case.yaml").write_text("title: [\n")
    refuse((), "adder: cannot read case.yaml", cases=broken.parent)

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    refuse(("--model", "openrouter:x"), "set OPENROUTER_API_KEY first")

    missing = tmp_path / "missing-cases" / "adder"
    missing.parent.mkdir()
    shutil.copytree(BENCH_CASES / "adder", missing)
    command = "definitely-not-a-real-command-bench-t03"
    text = (missing / "case.yaml").read_text().replace("requires: [python3]", f"requires: [{command}]")
    (missing / "case.yaml").write_text(text)
    refuse((), command, cases=missing.parent)

    exposed = tmp_path / "exposed-cases" / "adder"
    exposed.parent.mkdir()
    shutil.copytree(BENCH_CASES / "adder", exposed)
    data = yaml.safe_load((exposed / "case.yaml").read_text())
    data["config"]["dependency_sources"] = [str(exposed)]
    (exposed / "case.yaml").write_text(yaml.safe_dump(data, sort_keys=False))
    refuse(("--no-sandbox",), "adder: hidden/solution files readable under its dependency_sources",
           cases=exposed.parent, sandbox=False)

    from factory import sandbox as S
    with monkeypatch.context() as m:
        m.setattr(S, "available", lambda: False)
        refuse((), "bubblewrap (bwrap) is required", sandbox=False)


def test_hidden_files_readable_in_the_sandbox_are_refused(bench_repo, home, tmp_path, capsys):
    if not shutil.which("bwrap"):
        pytest.skip("the hidden-file visibility check needs bubblewrap")
    visible = tmp_path / "visible-cases" / "adder"
    visible.parent.mkdir()
    shutil.copytree(BENCH_CASES / "adder", visible)
    data = yaml.safe_load((visible / "case.yaml").read_text())
    data["config"]["sandbox"]["ro_binds"] = [str(visible)]
    (visible / "case.yaml").write_text(yaml.safe_dump(data, sort_keys=False))

    assert main(_args(cases=visible.parent)) == 1
    error = capsys.readouterr().err
    assert "adder: hidden/solution files readable inside its sandbox" in error
    assert "hidden/bench_hidden/test_adder.py" in error
    assert not (home / "bench").exists()


def test_dry_run_prints_the_cells_and_creates_nothing(bench_repo, home, monkeypatch, capsys):
    monkeypatch.delenv("FAKE_API_KEY")
    monkeypatch.setattr(agents, "build_model", lambda spec: (_ for _ in ()).throw(
        AssertionError("dry-run called a model")))
    before = list(home.iterdir())
    assert main(["bench", "run", "--cases", str(BENCH_CASES), "--dry-run", "--repeat", "2",
                 "--flow", "default", "--flow", "lean"]) == 0
    out = capsys.readouterr().out
    assert "4 cells" in out
    assert "variant default" in out and "variant lean" in out
    assert "fake:builder" in out and "FAKE_API_KEY" in out
    assert "default · adder #1" in out and "lean · adder #1" in out
    assert not (home / "bench").exists()
    assert list(home.iterdir()) == before


def test_results_are_written_after_every_cell(bench_repo, home, monkeypatch):
    import factory.bench.run as bench_run

    _scripted(monkeypatch, {"scripted:good": GOOD})
    snapshots = []
    real_write = bench_run.write_results

    def spy(run_dir, results):
        snapshots.append(copy.deepcopy(results))
        real_write(run_dir, results)

    monkeypatch.setattr(bench_run, "write_results", spy)
    real_pipeline = bench_run.Pipeline
    calls = 0

    class InterruptSecondPipeline(real_pipeline):
        def run(self):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise KeyboardInterrupt
            return super().run()

    monkeypatch.setattr(bench_run, "Pipeline", InterruptSecondPipeline)
    assert main(_args("--model", "scripted:good", "--repeat", "2")) == 1

    after_first = next(snapshot for snapshot in snapshots if len(snapshot["cells"]) == 1)
    assert after_first["cells"][0]["outcome"] == "solved"
    after_second = next(snapshot for snapshot in snapshots if len(snapshot["cells"]) == 2)
    assert [cell["outcome"] for cell in after_second["cells"]] == ["solved", "error"]
    results = load_results(home)
    assert [cell["outcome"] for cell in results["cells"]] == ["solved", "error"]
    assert results["cells"][0]["repeat"] == 1 and results["cells"][1]["repeat"] == 2
    assert results["run"]["ended_at"] is not None


def test_parallel_cells_run_at_once_and_all_finish(bench_repo, home, tmp_path, monkeypatch):
    child_log = _child_launcher(monkeypatch, tmp_path, sleep=0.5)
    assert main(_args("--model", "scripted:good", "--repeat", "4", "--parallel", "2")) == 0

    parallel_dir = bench_run_dir(home)
    parallel = load_results(home)
    assert len(parallel["cells"]) == 4
    for cell in parallel["cells"]:
        assert cell["outcome"] == "solved" and cell["dir"]
        assert cell["attempts"] == 1 and cell["model_calls"] > 0
        directory = parallel_dir / cell["dir"]
        assert (directory / "factory.db").is_file()
        assert (directory / "repo").is_dir()
        assert (directory / "hidden.log").is_file()
        assert json.loads((directory / "cell.json").read_text()) == cell

    events = [json.loads(line) for line in child_log.read_text().splitlines()]
    assert sum(event["event"] == "start" for event in events) == 4
    assert sum(event["event"] == "end" for event in events) == 4
    live = peak = 0
    for event in events:
        live += 1 if event["event"] == "start" else -1
        peak = max(peak, live)
    assert peak == 2

    _scripted(monkeypatch, {"scripted:good": GOOD})
    assert main(_args("--model", "scripted:good", "--repeat", "4")) == 0
    run_dirs = sorted((home / "bench").iterdir())
    assert len(run_dirs) == 2 and run_dirs[0] == parallel_dir
    sequential = json.loads((run_dirs[1] / "results.json").read_text())

    def comparable(results):
        ordered = sorted(results["cells"], key=lambda cell: (cell["variant"], cell["case"], cell["repeat"]))
        return [{key: value for key, value in cell.items() if key not in ("seconds", "dir")}
                for cell in ordered]

    assert comparable(parallel) == comparable(sequential)


def test_parallel_runs_keep_to_the_budget(bench_repo, home, tmp_path, monkeypatch):
    child_log = _child_launcher(monkeypatch, tmp_path, cost=0.40)
    assert main(_args("--model", "scripted:good", "--repeat", "4", "--parallel", "2",
                      max_cost="1.0")) == 1
    cells = load_results(home)["cells"]
    stopped = [cell for cell in cells if cell["outcome"] == "stopped"]
    skipped = [cell for cell in cells if cell["outcome"] == "skipped"]
    assert len(stopped) == len(skipped) == 2
    assert all(cell["cost_usd"] >= 1.0 and cell["dir"] is not None for cell in stopped)
    assert all(cell["cost_usd"] == 0.0 and cell["attempts"] == 0 and cell["dir"] is None
               for cell in skipped)

    starts = [json.loads(line) for line in child_log.read_text().splitlines()
              if json.loads(line)["event"] == "start"]
    assert len(starts) == 2
    assert all(0.0 < event["cost_limit"] <= 1.0 for event in starts)


def test_a_crashed_cell_process_is_recorded_as_an_error(bench_repo, home, tmp_path, monkeypatch, capsys):
    _child_launcher(monkeypatch, tmp_path, sleep=0.1, crash_numbers=(2,))
    assert main(_args("--model", "scripted:good", "--repeat", "3", "--parallel", "2")) == 1
    run_dir = bench_run_dir(home)
    cells = {cell["repeat"]: cell for cell in load_results(home)["cells"]}
    assert [cells[number]["outcome"] for number in (1, 2, 3)] == ["solved", "error", "solved"]
    crash_dir = run_dir / cells[2]["dir"]
    assert crash_dir.is_dir()
    crash_log = (crash_dir / "crash.log").read_text()
    assert "child exited with status 3" in crash_log and "boom" in crash_log
    line = next(line for line in capsys.readouterr().out.splitlines() if "adder #2" in line)
    assert "error" in line and "child exit 3" in line and "crash.log" in line


def test_default_launch_runs_a_cell_process_like_the_scheduler(monkeypatch, tmp_path):
    import factory.bench.run as bench_run
    from factory import config as C
    from factory.bench import cases

    root = tmp_path / "root"
    root.mkdir()
    monkeypatch.chdir(tmp_path)
    cfg = C.load(root)
    variant = bench_run.variants(cfg, ["default"], ["scripted:good"])[0]
    case = cases.load_cases([BENCH_CASES])[0]
    cell = bench_run.Cell(variant, case, 2, root / "cells/default@scripted:good/adder/r2", 1.25, 2)
    seen = {}
    monkeypatch.setattr(bench_run.subprocess, "Popen", lambda argv, **kw: seen.update(argv=argv, kw=kw))

    bench_run.default_launch(root, cases_dir="case-suite", max_attempts=2, sandbox_on=False)(cell)
    assert seen["argv"] == [
        sys.executable, "-m", "factory.bench.run", "--case", "adder",
        "--cases", str(tmp_path / "case-suite"), "--flow", "default", "--model", "scripted:good",
        "--dir", str(cell.directory), "--max-attempts", "2", "--cost-limit", "1.250000", "--no-sandbox",
    ]
    assert seen["kw"] == {
        "cwd": root, "stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
        "stderr": subprocess.PIPE, "start_new_session": True, "text": True,
    }


def test_ctrl_c_stops_starting_cells_and_records_them_as_errors(bench_repo, home, tmp_path,
                                                                 monkeypatch, capsys):
    _child_launcher(monkeypatch, tmp_path, sleep=30.0, ctrl_c_at=2)
    assert main(_args("--model", "scripted:good", "--repeat", "4", "--parallel", "2")) == 1
    results = load_results(home)
    assert results["run"]["ended_at"] is not None
    assert len(results["cells"]) == 1
    assert results["cells"][0]["repeat"] == 1 and results["cells"][0]["outcome"] == "error"
    out = capsys.readouterr().out
    line = next(line for line in out.splitlines() if "adder #1" in line)
    assert "(interrupted)" in line
    assert "1/0/0/3" in out


def test_parallel_must_be_at_least_one(bench_repo, home, capsys):
    assert main(_args("--parallel", "0")) == 1
    assert "--parallel must be at least 1" in capsys.readouterr().err
    assert not (home / "bench").exists()


def _steps(model="fake:builder", prompt="a" * 64):
    return [{"name": "build", "kind": "build", "model": model, "max_steps": 20, "prompt_sha": prompt}]


def _cell(variant, case, *, repeat=1, outcome="solved", attempts=1, cost=0.25, seconds=120.0,
          directory=None):
    return {
        "variant": variant,
        "case": case,
        "repeat": repeat,
        "outcome": outcome,
        "attempts": attempts,
        "cost_usd": cost,
        "seconds": seconds,
        "model_calls": 4,
        "tokens_in": 100,
        "tokens_out": 50,
        "review_changes": 0,
        "step_limit_stops": 0,
        "failed_gates": [],
        "dir": directory,
    }


def _write_run(home, run_id, cases, variants, cells, *, repeat=1, sandbox=True, max_cost=5.0):
    started = dt.datetime.strptime(run_id, "%Y%m%d-%H%M%S").replace(tzinfo=dt.timezone.utc)
    case_records = {}
    for case_id, value in cases.items():
        if isinstance(value, dict):
            record = copy.deepcopy(value)
            record.setdefault("kind", "feature")
            record.setdefault("base", "0" * 40)
            record.setdefault("fixture_sha", "0" * 64)
        else:
            record = {"kind": "feature", "base": "0" * 40, "fixture_sha": value}
        case_records[case_id] = record
    variant_records = {}
    for variant_id, value in variants.items():
        if isinstance(value, dict):
            record = copy.deepcopy(value)
            record.setdefault("steps", _steps())
        else:
            record = {"steps": copy.deepcopy(value)}
        record.setdefault("flow", variant_id)
        record.setdefault("model", None)
        variant_records[variant_id] = record
    results = {
        "run": {
            "id": run_id,
            "started_at": started.isoformat(),
            "ended_at": started.isoformat(),
            "factory": "0.1.0",
            "sandbox": sandbox,
            "max_cost": max_cost,
            "max_attempts": 3,
            "repeat": repeat,
        },
        "cases": case_records,
        "variants": variant_records,
        "cells": cells,
    }
    run_dir = home / "bench" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "results.json").write_text(json.dumps(results, indent=2) + "\n")
    return run_dir


def test_report_shows_solved_rates_per_variant_and_case(home, capsys):
    older = "20261115-060000"
    newest = "20261115-063000"
    _write_run(home, older, {"slugify": "o" * 64}, {"default": _steps()},
               [_cell("default", "slugify")])
    cases = {"slugify": "s" * 64, "money-rounding": "m" * 64}
    variants = {"default": _steps(), "lean": _steps()}
    cells = [
        _cell("default", "slugify", repeat=1, cost=0.10, seconds=60),
        _cell("default", "slugify", repeat=2, cost=0.20, seconds=120),
        _cell("default", "money-rounding", repeat=1, cost=0.30, seconds=180),
        _cell("default", "money-rounding", repeat=2, outcome="false_pass", cost=0.40, seconds=240),
        _cell("lean", "slugify", repeat=1, outcome="failed", cost=0.50, seconds=300),
        _cell("lean", "slugify", repeat=2, cost=0.60, seconds=360),
        _cell("lean", "money-rounding", repeat=1, cost=0.70, seconds=420),
        _cell("lean", "money-rounding", repeat=2, outcome="failed", cost=0.80, seconds=480),
    ]
    _write_run(home, newest, cases, variants, cells, repeat=2)

    assert main(["bench", "report"]) == 0
    out = capsys.readouterr().out
    assert f"bench {newest}" in out
    assert "2 cases · 2 variants × 2 · $3.60 of $5.00 · factory 0.1.0" in out
    default = next(line for line in out.splitlines() if line.startswith("default "))
    lean = next(line for line in out.splitlines() if line.startswith("lean "))
    assert default.split()[1] == "4" and "3/4 75%" in default
    assert lean.split()[1] == "4" and "2/4 50%" in lean
    slugify = next(line for line in out.splitlines() if line.startswith("slugify "))
    money = next(line for line in out.splitlines() if line.startswith("money-rounding "))
    assert slugify.split() == ["slugify", "2/2", "1/2"]
    assert money.split() == ["money-rounding", "1/2", "1/2"]

    assert main(["bench", "report", "19990101-000000"]) == 1
    error = capsys.readouterr().err
    assert "unknown bench run 19990101-000000" in error
    assert older in error and newest in error

    _write_run(home, newest, cases, variants, cells, repeat=2, sandbox=False)
    assert main(["bench", "report", newest]) == 0
    assert "unsandboxed: agents could read the hidden tests" in capsys.readouterr().out


def test_report_cells_lists_each_cell_and_its_directory(home, capsys):
    run_id = "20261115-080000"
    cells = []
    for variant in ("default", "lean"):
        for repeat, seconds in ((1, 60.0), (2, 366.0)):
            directory = f"cells/{variant}/slugify/r{repeat}"
            cells.append(_cell(
                variant, "slugify", repeat=repeat, outcome="solved" if repeat == 1 else "false_pass",
                attempts=repeat if repeat == 1 else 3, cost=0.25 * len(cells) + 0.25,
                seconds=seconds + (120 if variant == "lean" else 0), directory=directory,
            ))
    run_dir = _write_run(home, run_id, {"slugify": "s" * 64},
                         {"default": _steps(), "lean": _steps()}, cells, repeat=2)

    assert main(["bench", "report", run_id, "--cells"]) == 0
    out = capsys.readouterr().out
    for cell in cells:
        directory = str(run_dir / cell["dir"])
        line = next(line for line in out.splitlines() if directory in line)
        attempts = f"{cell['attempts']} attempt" + ("" if cell["attempts"] == 1 else "s")
        assert cell["variant"] in line
        assert f"{cell['case']} #{cell['repeat']}" in line
        assert cell["outcome"] in line and attempts in line
        assert f"${cell['cost_usd']:.2f}" in line
        assert f"{cell['seconds'] / 60:.1f} min" in line
    assert sum(str(run_dir / "cells") in line for line in out.splitlines()) == 4


def test_report_of_an_interrupted_run_counts_cells_not_run(home, capsys):
    run_id = "20261115-090000"
    _write_run(home, run_id, {"slugify": "s" * 64}, {"default": _steps()},
               [_cell("default", "slugify", repeat=1)], repeat=3)

    assert main(["bench", "report", run_id]) == 0
    out = capsys.readouterr().out
    assert "not run: 2 of 3 cells" in out
    row = next(line for line in out.splitlines() if line.startswith("default "))
    assert row.split()[1] == "3"
    assert "1/1 100%" in row and "0/0/0/2" in row

    assert main(["bench", "report", run_id, "--cells"]) == 0
    out = capsys.readouterr().out
    assert "default · slugify #2: not run, -, -, -, -" in out
    assert "default · slugify #3: not run, -, -, -, -" in out


def test_compare_pairs_variants_and_cases_across_runs(home, capsys):
    a, b = "20261115-100000", "20261115-103000"
    cases = {"slugify": "s" * 64, "money-rounding": "m" * 64}
    _write_run(home, a, cases, {"default": _steps()}, [
        _cell("default", "slugify", attempts=1, cost=0.40, seconds=120),
        _cell("default", "money-rounding", outcome="false_pass", attempts=2, cost=0.60, seconds=180),
    ])
    _write_run(home, b, cases, {"default": _steps()}, [
        _cell("default", "slugify", outcome="failed", attempts=3, cost=0.20, seconds=60),
        _cell("default", "money-rounding", attempts=1, cost=0.40, seconds=300),
    ])

    assert main(["bench", "compare", a, b]) == 0
    out = capsys.readouterr().out
    assert f"compare {a} → {b}" in out
    assert "cases: 2 in both, unchanged" in out
    assert "variants: 1 in both" in out
    row = next(line for line in out.splitlines() if line.startswith("default "))
    for expected in ("1/2 → 1/2", "1 → 0", "$0.50 → $0.30", "1.5 → 2.0", "2.5 → 3.0"):
        assert expected in row
    slugify = next(line for line in out.splitlines() if line.startswith("slugify "))
    money = next(line for line in out.splitlines() if line.startswith("money-rounding "))
    assert "1/1 → 0/1" in slugify
    assert "0/1 → 1/1" in money

    assert main(["bench", "compare", a, "19990101-000000"]) == 1
    error = capsys.readouterr().err
    assert "unknown bench run 19990101-000000" in error
    assert a in error and b in error


def test_compare_flags_changed_cases_models_and_prompts(home, capsys):
    a, b = "20261115-110000", "20261115-113000"

    def step(name, kind, model, prompt):
        return {**_steps(model, prompt)[0], "name": name, "kind": kind}

    a_steps = [
        step("build", "build", "fake:old", "p" * 64),
        step("review", "review", "fake:r", "q" * 64),
        step("verify", "verify", "fake:v", "v" * 64),
    ]
    b_steps = [
        step("build", "build", "fake:new", "p" * 64),
        step("review", "review", "fake:r", "z" * 64),
    ]
    _write_run(home, a, {"slugify": "a" * 64, "rate-limiter": "r" * 64},
               {"default": a_steps, "lean": _steps()}, [_cell("default", "slugify")])
    _write_run(home, b, {"slugify": "b" * 64, "money-rounding": "m" * 64},
               {"default": b_steps, "strict": _steps()}, [_cell("default", "slugify")])

    assert main(["bench", "compare", a, b]) == 0
    out = capsys.readouterr().out
    assert "slugify (aaaaaaaaaaaa → bbbbbbbbbbbb)" in out
    assert f"only in {a}: rate-limiter" in out
    assert f"only in {b}: money-rounding" in out
    assert f"only in {a}: lean" in out
    assert f"only in {b}: strict" in out
    assert "build: model fake:old → fake:new" in out
    assert "review: prompt_sha qqqqqqqqqqqq → zzzzzzzzzzzz" in out
    assert f"verify: only in {a}" in out
    assert any(line.startswith("default ") and "1/1 → 1/1" in line for line in out.splitlines())


def test_results_record_loop_and_prove_and_compare_flags_a_change(bench_repo, home, capsys):
    import factory.bench.run as bench_run
    from factory import config as C

    cfg = C.load(bench_repo)
    first = bench_run.variant_steps(bench_repo, cfg.flows["strict"], cfg, "scripted:strict")
    assert [(step["name"], step["loop"], step["prove"]) for step in first] == [
        ("test", ["map", "trim", "nudge"], False),
        ("build", ["map", "trim", "nudge", "resume"], False),
        ("review", ["trim"], True),
        ("verify", [], False),
    ]
    second = copy.deepcopy(first)
    next(step for step in second if step["name"] == "build")["loop"] = ["map", "trim", "nudge"]
    next(step for step in second if step["name"] == "review")["prove"] = False

    a, b = "20261115-114500", "20261115-115000"
    _write_run(home, a, {"adder": "a" * 64}, {"strict": first}, [_cell("strict", "adder")])
    _write_run(home, b, {"adder": "a" * 64}, {"strict": second}, [_cell("strict", "adder")])
    recorded = json.loads((home / "bench" / a / "results.json").read_text())
    assert all(set(step) >= {"loop", "prove"} for step in recorded["variants"]["strict"]["steps"])

    assert main(["bench", "compare", a, b]) == 0
    out = capsys.readouterr().out
    assert ("build: loop ['map', 'trim', 'nudge', 'resume'] → ['map', 'trim', 'nudge']" in out)
    assert "review: prove True → False" in out


def test_list_shows_runs_newest_first_and_cases_lists_the_suite(home, capsys):
    older, newer, broken = "20261115-060000", "20261115-063000", "20261115-070000"
    _write_run(home, older, {"slugify": "s" * 64}, {"default": _steps()},
               [_cell("default", "slugify", cost=0.25)], repeat=2)
    _write_run(home, newer, {"slugify": "s" * 64}, {"default": _steps()},
               [_cell("default", "slugify", cost=0.75)])
    broken_dir = home / "bench" / broken
    broken_dir.mkdir(parents=True)
    (broken_dir / "results.json").write_text("{oops")

    assert main(["bench", "list"]) == 0
    captured = capsys.readouterr()
    assert captured.out.index(newer) < captured.out.index(older)
    assert broken not in captured.out
    assert (f"{older}  2026-11-15T06:00:00+00:00  1 cases  1 variants  1/2 cells  $0.25"
            in captured.out)
    assert (f"{newer}  2026-11-15T06:30:00+00:00  1 cases  1 variants  1/1 cells  $0.75"
            in captured.out)
    assert str(broken_dir / "results.json") in captured.err

    assert main(["bench", "cases"]) == 0
    out = capsys.readouterr().out
    expected = [
        ("slugify", "feature", "Slugify titles for URLs"),
        ("money-rounding", "bugfix", "Round ledger money exactly to cents"),
        ("report-json", "multi-file", "Add --format json to the report tool"),
        ("ini-refactor", "refactor", "Extract one shared settings parser"),
        ("rate-limiter", "algorithm", "Implement the token-bucket rate limiter"),
    ]
    for case_id, kind, title in expected:
        assert f"{case_id:<18} {kind:<12} {title}" in out

    assert main(["bench", "cases", "--cases", str(BENCH_CASES)]) == 0
    out = capsys.readouterr().out
    assert f"{'adder':<18} {'feature':<12} Add integer addition to the calc package" in out


def test_a_cell_can_be_inspected_with_factory_show(bench_repo, home, monkeypatch, capsys):
    _scripted(monkeypatch, {"scripted:good": GOOD})
    assert main(_args("--model", "scripted:good")) == 0
    cell = load_results(home)["cells"][0]
    cell_home = bench_run_dir(home) / cell["dir"]
    db = open_db(cell_home)
    transcripts = [run["transcript"] for run in db.runs("adder-t01") if run["transcript"]]
    db.close()
    assert transcripts
    monkeypatch.setenv("FACTORY_HOME", str(cell_home))
    capsys.readouterr()

    assert main(["show", "adder-t01"]) == 0
    out = capsys.readouterr().out
    assert "adder-t01" in out and "## build #1" in out and "step build" in out

    assert main(["trace", "adder-t01"]) == 0
    capsys.readouterr()
    assert main(["transcript", "adder-t01"]) == 0
    assert transcripts[-1] in capsys.readouterr().out
