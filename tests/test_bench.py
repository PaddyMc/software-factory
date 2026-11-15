"""End-to-end bench runs: real pipelines and git, with scripted models and no GitHub calls."""

import copy
import hashlib
import json
import shutil
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


def test_bench_run_refuses_before_any_work(bench_repo, home, tmp_path, monkeypatch, capsys):
    def refuse(extra, expected, *, cases=BENCH_CASES, sandbox=True):
        assert main(_args(*extra, cases=cases, sandbox=sandbox)) == 1
        captured = capsys.readouterr()
        assert expected in captured.err
        assert not (home / "bench").exists()

    assert main(_args(max_cost=None)) == 1
    assert "--max-cost is required" in capsys.readouterr().err
    assert not (home / "bench").exists()
    refuse(("--flow", "nope"), "unknown flow nope (flows: default, lean)")
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
