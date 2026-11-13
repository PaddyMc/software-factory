"""End to end: `factory bench run` with real pipelines, gates, git and hidden scoring.

Only the models are scripted. Every cell gets its own repository and factory home, so these
runs also exercise the isolation between a bench and the repository that invoked it.
"""

import hashlib
import json
import re
import shutil
from pathlib import Path

import pytest
import yaml
from langchain_core.messages import AIMessage

from factory import agents, prices
from factory.bench import run as bench_run
from factory.cli import main
from factory.db import open_db
from conftest import git
from fake_model import ScriptedModel, call

BENCH_CASES = Path(__file__).parent / "bench_cases"
SANDBOX = [] if shutil.which("bwrap") else ["--no-sandbox"]


@pytest.fixture
def bench_repo(repo, home, fake_gh, monkeypatch):
    (repo / ".factory/config.yaml").write_text(
        "name: bench-test\n"
        "flows:\n"
        "  lean: [build, review]\n")
    agents_dir = repo / ".factory/agents"
    agents_dir.mkdir(parents=True)
    for role in ("planner", "builder", "reviewer", "verifier"):
        (agents_dir / f"{role}.md").write_text(
            f"---\nmodel: fake:{role}\nmax_steps: 20\n---\nYou are the {role.upper()} for one task.\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "bench agents and flows")
    git(repo, "push", "-q", "origin", "main")
    monkeypatch.setenv("FAKE_API_KEY", "x")
    monkeypatch.setitem(agents.PROVIDER_KEYS, "fake", "FAKE_API_KEY")
    monkeypatch.setitem(agents.PROVIDER_KEYS, "scripted", "FAKE_API_KEY")
    monkeypatch.chdir(repo)
    return repo


def _plays():
    solution = BENCH_CASES / "adder/solution"
    calc = (solution / "adder/calc.py").read_text()
    visible = (solution / "tests/test_adder.py").read_text()
    common = {
        "PLANNER": [call("list_dir", path="."), AIMessage("**Files**: adder/calc.py\n**Steps**: add add and its test")],
        "REVIEWER": [call("git_diff", stat=True), "VERDICT"],
        "VERIFIER": [call("read_file", path="adder/calc.py"), AIMessage("**Summary**\n- adds add(a, b)\n")],
        "_verdicts": [],
        "_calls": [],
    }
    good = {**common, "_calls": [], "_verdicts": [], "BUILDER": [
        call("write_file", path="adder/calc.py", content=calc),
        call("write_file", path="tests/test_adder.py", content=visible),
        AIMessage("Implemented add and its visible test.\nRESULT: DONE"),
    ]}
    bad = {**common, "_calls": [], "_verdicts": [], "BUILDER": [
        call("write_file", path="adder/calc.py", content=calc.replace("return a + b", "return 5")),
        call("write_file", path="tests/test_adder.py", content=visible),
        AIMessage("Implemented add and a weak visible test.\nRESULT: DONE"),
    ]}
    return good, bad


def _use_scripted(monkeypatch):
    good, bad = _plays()
    monkeypatch.setattr(agents, "build_model",
                        lambda spec: ScriptedModel(plays=bad if spec.endswith(":bad") else good))
    return good, bad


def _args(*extra, max_cost="50"):
    args = ["bench", "run", "--cases", str(BENCH_CASES)]
    if max_cost is not None:
        args += ["--max-cost", str(max_cost)]
    return args + list(extra) + SANDBOX


def _latest_results(home):
    run_dir = next((home / "bench").iterdir())
    return run_dir, json.loads((run_dir / "results.json").read_text())


def _cell_dir(run_dir, cell):
    return run_dir / cell["dir"]


def test_a_bench_run_scores_each_cell_with_gates_and_hidden_tests(bench_repo, home, monkeypatch, capsys):
    _use_scripted(monkeypatch)
    assert main(_args("--model", "scripted:good", "--model", "scripted:bad")) == 0
    run_dir, results = _latest_results(home)
    assert re.fullmatch(r"\d{8}-\d{6}", results["run"]["id"])
    assert results["run"]["ended_at"] and results["run"]["max_cost"] == 50
    assert results["cases"]["adder"]["kind"] == "feature"
    assert re.fullmatch(r"[0-9a-f]{40}", results["cases"]["adder"]["base"])
    assert re.fullmatch(r"[0-9a-f]{64}", results["cases"]["adder"]["fixture_sha"])

    cells = {cell["variant"]: cell for cell in results["cells"]}
    assert set(cells) == {"default@scripted:good", "default@scripted:bad"}
    assert cells["default@scripted:good"]["outcome"] == "solved"
    assert cells["default@scripted:bad"]["outcome"] == "false_pass"
    expected = {"variant", "case", "repeat", "outcome", "attempts", "cost_usd", "seconds", "model_calls",
                "tokens_in", "tokens_out", "review_changes", "step_limit_stops", "failed_gates", "dir"}
    for cell in cells.values():
        assert expected <= set(cell)
        assert cell["case"] == "adder" and cell["repeat"] == 1
        assert cell["attempts"] == 1 and cell["model_calls"] > 0
        assert cell["tokens_in"] >= 0 and cell["tokens_out"] >= 0
        assert cell["review_changes"] == 0 and cell["step_limit_stops"] == 0
        assert cell["failed_gates"] == [] and cell["dir"].startswith("cells/")
        directory = _cell_dir(run_dir, cell)
        for name in ("factory.db", "repo", "worktrees", "logs", "transcripts", "hidden.log"):
            assert (directory / name).exists(), name
        assert git(directory / "repo", "remote") == ""

    solved_log = (_cell_dir(run_dir, cells["default@scripted:good"]) / "hidden.log").read_text()
    false_log = (_cell_dir(run_dir, cells["default@scripted:bad"]) / "hidden.log").read_text()
    assert "bench_hidden.test_adder" in solved_log and "[pass]" in solved_log
    assert "FAILED" in false_log and "AssertionError" in false_log
    out = capsys.readouterr().out
    assert "default@scripted:good" in out and "default@scripted:bad" in out
    assert "cost/cell" in out and "total" in out and "min/cell" in out
    assert "adder" in out and "1/1 100%" in out and "0/1 0%" in out


def test_each_variant_runs_its_flow_and_model(bench_repo, home, monkeypatch):
    _use_scripted(monkeypatch)
    assert main(_args("--flow", "default", "--flow", "lean")) == 0
    run_dir, results = _latest_results(home)
    assert list(results["variants"]) == ["default", "lean"]
    assert all(variant["model"] is None for variant in results["variants"].values())
    assert [step["name"] for step in results["variants"]["lean"]["steps"]] == ["build", "review"]
    assert [step["name"] for step in results["variants"]["default"]["steps"]] == ["plan", "build", "review", "verify"]
    assert {step["model"] for step in results["variants"]["default"]["steps"]} == {
        "fake:planner", "fake:builder", "fake:reviewer", "fake:verifier"}

    for cell in results["cells"]:
        db = open_db(_cell_dir(run_dir, cell))
        try:
            runs = db.runs("adder-t01")
            pairs = [(run["role"], run["step"]) for run in runs]
            if cell["variant"] == "lean":
                assert pairs == [("build", "build"), ("review", "review"), ("verify", "gates")]
            else:
                assert pairs == [("plan", "plan"), ("build", "build"), ("review", "review"),
                                 ("verify", "gates"), ("verify", "verify")]
            assert {run["flow"] for run in runs} == {cell["variant"]}
        finally:
            db.close()


def test_prompts_and_flows_come_from_the_invoking_repository(bench_repo, home, monkeypatch):
    _use_scripted(monkeypatch)
    assert main(_args("--model", "scripted:good")) == 0
    run_dir, results = _latest_results(home)
    steps = results["variants"]["default@scripted:good"]["steps"]
    build = next(step for step in steps if step["kind"] == "build")
    prompt = bench_repo / ".factory/agents/builder.md"
    assert build["prompt_sha"] == hashlib.sha256(prompt.read_bytes()).hexdigest()
    assert build["max_steps"] == 20 and build["model"] == "scripted:good"
    transcript = next((_cell_dir(run_dir, results["cells"][0]) / "transcripts/adder-t01").glob("*-build-1.jsonl"))
    first = json.loads(transcript.read_text().splitlines()[0])
    assert first["type"] == "system"
    assert "You are the BUILDER for one task." in first["content"]
    assert first["model"] == "scripted:good" and first["max_steps"] == 20


def test_a_bench_run_leaves_the_board_and_the_repository_alone(bench_repo, home, fake_gh, monkeypatch, capsys):
    _use_scripted(monkeypatch)
    assert main(["sync"]) == 0
    capsys.readouterr()
    db = open_db(home)
    board_before = [dict(row) for row in db.tasks()]
    db.close()
    refs_before = git(bench_repo, "for-each-ref")
    worktrees_before = git(bench_repo, "worktree", "list", "--porcelain")
    gh_before = fake_gh.read_bytes() if fake_gh.exists() else None

    assert main(_args("--model", "scripted:good")) == 0
    db = open_db(home)
    assert [dict(row) for row in db.tasks()] == board_before
    db.close()
    assert git(bench_repo, "for-each-ref") == refs_before
    assert git(bench_repo, "worktree", "list", "--porcelain") == worktrees_before
    assert (fake_gh.read_bytes() if fake_gh.exists() else None) == gh_before
    run_dir, results = _latest_results(home)
    assert git(_cell_dir(run_dir, results["cells"][0]) / "repo", "remote") == ""


def test_the_budget_caps_cells_and_stops_starting_new_ones(bench_repo, home, monkeypatch, capsys):
    monkeypatch.setattr(prices, "cost", lambda spec, tin, tout, cache_read=0: 0.40)
    _use_scripted(monkeypatch)
    assert main(_args("--model", "scripted:good", "--repeat", "2", max_cost="1.0")) == 1
    run_dir, results = _latest_results(home)
    assert results["run"]["max_cost"] == 1.0
    first, second = results["cells"]
    assert first["outcome"] == "stopped" and first["cost_usd"] >= 1.0
    assert "cost limit exceeded" in first["error"]
    assert second["outcome"] == "skipped" and second["cost_usd"] == 0
    assert second["attempts"] == 0 and second["model_calls"] == 0
    assert not _cell_dir(run_dir, second).exists()
    out = capsys.readouterr().out
    assert "stopped" in out and "skipped (budget spent)" in out


def test_bench_run_refuses_before_any_work(bench_repo, home, tmp_path, monkeypatch, capsys):
    good, _ = _use_scripted(monkeypatch)

    assert main(_args(max_cost=None)) == 1
    err = capsys.readouterr().err
    assert "--max-cost" in err and "--dry-run" in err

    assert main(_args("--flow", "nope")) == 1
    assert "unknown flow nope (flows: default, lean)" in capsys.readouterr().err

    assert main(_args("--case", "nope")) == 1
    assert "unknown case nope (cases: adder)" in capsys.readouterr().err

    monkeypatch.delenv("FAKE_API_KEY")
    assert main(_args("--model", "scripted:good")) == 1
    assert "set FAKE_API_KEY first" in capsys.readouterr().err
    monkeypatch.setenv("FAKE_API_KEY", "x")

    broken = tmp_path / "broken-suite"
    shutil.copytree(BENCH_CASES, broken)
    data = yaml.safe_load((broken / "adder/case.yaml").read_text())
    del data["contract"]["goal"]
    (broken / "adder/case.yaml").write_text(yaml.safe_dump(data, sort_keys=False))
    assert main(_args("--cases", str(broken))) == 1
    err = capsys.readouterr().err
    assert "adder:" in err and "invalid contract" in err

    missing = tmp_path / "missing-suite"
    shutil.copytree(BENCH_CASES, missing)
    data = yaml.safe_load((missing / "adder/case.yaml").read_text())
    data["requires"] = ["not-a-command-xyz"]
    (missing / "adder/case.yaml").write_text(yaml.safe_dump(data, sort_keys=False))
    assert main(_args("--cases", str(missing))) == 1
    err = capsys.readouterr().err
    assert "adder:" in err and "not-a-command-xyz" in err and "missing from its sandbox" in err

    assert not (home / "bench").exists()
    assert good["_calls"] == []


@pytest.mark.skipif(not shutil.which("bwrap"), reason="bubblewrap required")
def test_hidden_files_readable_in_the_sandbox_are_refused(bench_repo, home, tmp_path, monkeypatch, capsys):
    good, _ = _use_scripted(monkeypatch)
    bound = tmp_path / "bound-suite"
    shutil.copytree(BENCH_CASES, bound)
    case_dir = (bound / "adder").resolve()
    data = yaml.safe_load((case_dir / "case.yaml").read_text())
    data["config"]["sandbox"]["ro_binds"] = [str(case_dir)]
    (case_dir / "case.yaml").write_text(yaml.safe_dump(data, sort_keys=False))
    assert main(_args("--cases", str(bound))) == 1
    err = capsys.readouterr().err
    assert "adder:" in err and "readable inside the sandbox" in err
    assert "hidden/bench_hidden/test_adder.py" in err and "solution/adder/calc.py" in err
    assert not (home / "bench").exists()

    exposed = tmp_path / "exposed-suite"
    shutil.copytree(BENCH_CASES, exposed)
    case_dir = (exposed / "adder").resolve()
    data = yaml.safe_load((case_dir / "case.yaml").read_text())
    data["config"]["dependency_sources"] = [str(case_dir)]
    (case_dir / "case.yaml").write_text(yaml.safe_dump(data, sort_keys=False))
    assert main(_args("--cases", str(exposed))) == 1
    err = capsys.readouterr().err
    assert "adder:" in err and "dependency_sources" in err and "hidden/" in err
    assert not (home / "bench").exists()
    assert good["_calls"] == []


def test_dry_run_prints_the_cells_and_creates_nothing(bench_repo, home, monkeypatch, capsys):
    good, bad = _use_scripted(monkeypatch)
    assert main(_args("--flow", "default", "--flow", "lean", "--model", "scripted:good",
                      "--dry-run", max_cost=None)) == 0
    out = capsys.readouterr().out
    assert "[1/2] default@scripted:good · adder #1" in out
    assert "[2/2] lean@scripted:good · adder #1" in out
    assert "default@scripted:good: plan scripted:good" in out
    assert "lean@scripted:good: build scripted:good · review scripted:good" in out
    assert "FAKE_API_KEY" in out
    assert not any(home.iterdir())

    assert main(_args("--dry-run", max_cost=None)) == 0
    out = capsys.readouterr().out
    assert "default: plan fake:planner · build fake:builder" in out
    assert not any(home.iterdir())
    assert good["_calls"] == [] and bad["_calls"] == []


def test_results_are_written_after_every_cell(bench_repo, home, monkeypatch):
    good, _ = _plays()
    interrupted = {"now": False}

    def model(spec):
        if interrupted["now"]:
            raise KeyboardInterrupt
        return ScriptedModel(plays=good)

    monkeypatch.setattr(agents, "build_model", model)
    writes = []
    real_write = bench_run.write_results

    def spy(run_dir, results):
        writes.append([dict(cell) for cell in results["cells"]])
        real_write(run_dir, results)
        if len(results["cells"]) == 1:
            interrupted["now"] = True

    monkeypatch.setattr(bench_run, "write_results", spy)
    assert main(_args("--model", "scripted:good", "--repeat", "2")) == 1
    assert [len(cells) for cells in writes[:3]] == [0, 1, 2]
    _, results = _latest_results(home)
    assert results["run"]["ended_at"]
    assert [cell["outcome"] for cell in results["cells"]] == ["solved", "error"]
    assert results["cells"][0]["attempts"] == 1
    assert results["cells"][1]["error"] == "interrupted"
    assert json.loads((home / "bench" / results["run"]["id"] / "results.json").read_text()) == results
