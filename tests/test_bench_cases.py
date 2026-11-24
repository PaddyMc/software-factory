import copy
import re
import shutil
from pathlib import Path

import pytest
import yaml
from langchain_core.messages import AIMessage

from factory import agents, config as C, contracts, gates as G, globs, sandbox, verification
import factory.bench.run as bench_run
from factory.bench import cases
from factory.cli import main
from conftest import git
from fake_model import ScriptedModel, call
from test_bench import BENCH_CASES, GOOD_CALC, VISIBLE_TEST, bench_repo

SHIPPED = cases.load_cases()


def _sandbox_factory(case, tmp_path):
    def make(worktree):
        if shutil.which("bwrap"):
            return sandbox.make(worktree, tmp_path / "cache", cfg=case.cfg.sandbox)
        return sandbox.Unsandboxed(worktree)
    return make


@pytest.mark.parametrize("case", SHIPPED, ids=lambda case: case.id)
def test_every_shipped_case_loads_with_a_valid_contract_and_config(case):
    assert [c.id for c in SHIPPED] == sorted(c.id for c in SHIPPED)
    assert case.kind == {"slugify": "feature", "money-rounding": "bugfix", "report-json": "multi-file",
                         "ini-refactor": "refactor", "rate-limiter": "algorithm"}[case.id]
    assert case.requires == ("python3",)
    assert case.contract.id == f"{case.id}-t01"
    assert case.contract.plan == f"docs/plans/{case.id}.md"
    assert len(case.contract.mapping()) == 8
    assert set(case.contract.mapping()) == set(contracts.KEYS)
    assert not contracts.validate_tasks([case.contract])
    assert case.cfg.sandbox.ro_binds == ()
    assert case.cfg.sandbox.rw_binds == ()
    assert case.cfg.sandbox.path == ()
    assert case.cfg.sandbox.hide == ()
    assert case.cfg.dependency_sources == ()
    assert case.cfg.session_log is None
    assert case.cfg.e2e is None
    assert case.cfg.unit_tests
    assert all(verification.is_test_command(cmd) for cmd in case.hidden)
    assert any(path.is_file() for path in case.hidden_dir.rglob("*"))
    assert any(path.is_file() for path in case.solution_dir.rglob("*"))


def test_the_shipped_suite_has_five_cases_of_five_kinds():
    assert [(case.id, case.kind) for case in SHIPPED] == [
        ("ini-refactor", "refactor"),
        ("money-rounding", "bugfix"),
        ("rate-limiter", "algorithm"),
        ("report-json", "multi-file"),
        ("slugify", "feature"),
    ]


@pytest.mark.parametrize("case", SHIPPED, ids=lambda case: case.id)
def test_every_case_is_solvable_and_not_already_solved(case, tmp_path):
    repo = tmp_path / "repo"
    base = cases.materialize(case, repo)
    make_sandbox = _sandbox_factory(case, tmp_path)

    base_score = cases.score_hidden(case, repo, base, make_sandbox)
    assert not base_score.passed, [c.output for c in base_score.commands]
    for cmd in case.cfg.unit_tests:
        result = make_sandbox(repo).run(cmd)
        assert verification.classify(cmd, result.code, result.output) == verification.PASS, result.output

    shutil.copytree(case.solution_dir, repo, dirs_exist_ok=True)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "reference solution")
    sha = git(repo, "rev-parse", "HEAD")
    run = G.run_gates(case.contract, repo, base, sha, make_sandbox(repo), case.cfg)
    assert all(gate.ok is True for gate in run), G.table(run)

    score = cases.score_hidden(case, repo, sha, make_sandbox)
    assert score.passed, [c.output for c in score.commands]
    assert len(score.commands) == len(case.hidden)
    assert all(result.output for result in score.commands)


@pytest.mark.parametrize("case", SHIPPED, ids=lambda case: case.id)
def test_every_shipped_case_works_under_a_test_step(case, tmp_path):
    assert case.cfg.test_paths == ("tests/**",)
    repo = tmp_path / "repo"
    base = cases.materialize(case, repo)
    make_sandbox = _sandbox_factory(case, tmp_path)

    test_files = []
    for source in case.solution_dir.rglob("*"):
        if not source.is_file():
            continue
        relative = source.relative_to(case.solution_dir)
        if not globs.matches_any(relative.as_posix(), case.cfg.test_paths):
            continue
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        test_files.append(relative.as_posix())
    assert test_files
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "acceptance tests")
    test_commit = git(repo, "rev-parse", "HEAD")

    acceptance = [cmd for cmd in case.contract.verification if verification.is_test_command(cmd)]
    assert acceptance
    for command in acceptance:
        result = make_sandbox(repo).run(command)
        assert verification.classify(command, result.code, result.output) == verification.FAIL, result.output

    shutil.copytree(case.solution_dir, repo, dirs_exist_ok=True)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "reference solution")
    candidate = git(repo, "rev-parse", "HEAD")
    run = G.run_gates(case.contract, repo, base, candidate, make_sandbox(repo), case.cfg,
                      test_commit=test_commit, test_files=tuple(test_files), test_red=tuple(acceptance))
    assert "acceptance_untouched" in {gate.name for gate in run}
    assert all(gate.ok is True for gate in run), G.table(run)


@pytest.mark.parametrize("case", SHIPPED, ids=lambda case: case.id)
def test_a_case_materializes_to_the_same_base_commit_every_time(case, tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first_sha = cases.materialize(case, first)
    second_sha = cases.materialize(case, second)
    assert first_sha == second_sha
    assert git(first, "rev-parse", "HEAD") == first_sha
    assert git(first, "rev-list", "--count", "HEAD") == "1"
    assert git(first, "branch", "--show-current") == "main"
    assert git(second, "branch", "--show-current") == "main"


SPEC_09 = Path(__file__).resolve().parents[1] / "docs/spec/09-spec.txt"


def _spec_09() -> str:
    """The shipped benchmarks chapter, docs/spec/09-spec.txt (factory-spec-t05)."""
    assert SPEC_09.is_file(), f"missing chapter: {SPEC_09}"
    chapter = SPEC_09.read_text(encoding="utf-8")
    assert chapter.strip(), f"empty chapter: {SPEC_09}"
    return chapter


def chapter_09_covers_cases_and_visibility() -> None:
    """factory-spec-t05's acceptance: docs/spec/09-spec.txt covers case inputs, reference
    solutions, hidden tests and their visibility, follows the chapter conventions and cites its
    source and named test."""
    chapter = _spec_09()
    opening = next(line for line in chapter.splitlines() if line.strip())
    assert opening.startswith("09"), "the chapter opens with its two-digit number and title"
    assert "8bd7012" in chapter, "the chapter states the first edition's baseline: 8bd7012"
    sections = re.findall(r"(?im)^\s*(?:#+\s*)?(?:\d+[.):\s]|section\s+\d+\b)", chapter)
    assert len(sections) >= 3, "the chapter is organized into numbered sections"
    for anchor, subject in {"case.yaml": "a case's inputs", "hidden": "the hidden tests",
                            "solution": "the reference solution"}.items():
        assert anchor in chapter, f"the chapter covers {subject}: {anchor!r} appears nowhere"
    assert any(word in chapter for word in ("unsandboxed", "--no-sandbox")), \
        "the chapter covers hidden-test visibility, including the --no-sandbox caveat"
    assert "factory/bench/cases.py" in chapter, "the chapter cites factory/bench/cases.py"
    assert ("tests/test_bench_cases.py::test_hidden_and_solution_files_stay_out_of_the_starting_tree"
            in chapter), "the chapter cites this test by its node id"


@pytest.mark.parametrize("case", SHIPPED, ids=lambda case: case.id)
def test_hidden_and_solution_files_stay_out_of_the_starting_tree(case, tmp_path):
    repo = tmp_path / "repo"
    cases.materialize(case, repo)
    tracked = set(git(repo, "ls-files").splitlines())
    repo_files = {path.relative_to(case.repo_dir).as_posix()
                  for path in case.repo_dir.rglob("*") if path.is_file()}
    assert tracked == repo_files | {".factory/config.yaml", f"docs/plans/{case.id}.md"}

    for source in (case.hidden_dir, case.solution_dir):
        for path in source.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(source)
            if source == case.solution_dir and (case.repo_dir / relative).exists():
                continue                         # the solution may overwrite a starting-tree file
            assert relative.as_posix() not in tracked

    assert yaml.safe_load((repo / ".factory/config.yaml").read_text()) == case.config
    plan = repo / f"docs/plans/{case.id}.md"
    parsed = contracts.parse_text(plan.read_text(), plan=case.contract.plan)
    assert len(parsed) == 1
    assert parsed[0].mapping() == case.contract.mapping()

    # factory-spec-t05: the chapter names this test as its evidence for a case's inputs and for
    # its hidden tests and reference solution staying out of the starting tree.
    chapter_09_covers_cases_and_visibility()


def test_hidden_scoring_lays_the_hidden_files_over_the_candidate(tmp_path, monkeypatch):
    case = next(case for case in SHIPPED if case.id == "slugify")
    repo = tmp_path / "repo"
    base = cases.materialize(case, repo)
    decoy = repo / "bench_hidden"
    decoy.mkdir()
    (decoy / "__init__.py").write_text("")
    (decoy / "test_slugify.py").write_text(
        "import unittest\n\n"
        "class Decoy(unittest.TestCase):\n"
        "    def test_decoy_would_pass(self):\n"
        "        self.assertTrue(True)\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "decoy hidden test")
    sha = git(repo, "rev-parse", "HEAD")
    assert sha != base
    worktrees_before = git(repo, "worktree", "list", "--porcelain")

    real_mkdtemp = cases.tempfile.mkdtemp
    scratch_dirs = []

    def record_mkdtemp(*args, **kwargs):
        directory = real_mkdtemp(*args, **kwargs)
        scratch_dirs.append(Path(directory))
        return directory

    monkeypatch.setattr(cases.tempfile, "mkdtemp", record_mkdtemp)
    score = cases.score_hidden(case, repo, sha, _sandbox_factory(case, tmp_path))
    assert not score.passed
    assert all("decoy_would_pass" not in result.output for result in score.commands)
    assert git(repo, "worktree", "list", "--porcelain") == worktrees_before
    assert scratch_dirs and all(not path.exists() for path in scratch_dirs)


BAD_CASES = [
    ("missing-key", "missing key"),
    ("unknown-key", "unknown key"),
    ("bad-id", "must match"),
    ("bad-kind", "kind"),
    ("bad-requires", "list of non-empty strings"),
    ("contract-schema", "invalid contract"),
    ("contract-validation", "prose prefix"),
    ("contract-id", "must be slugify-t01"),
    ("config", "unknown key"),
    ("empty-hidden", "hidden/ is empty"),
    ("empty-solution", "solution/ is empty"),
    ("hidden-command", "not a test command"),
]


@pytest.mark.parametrize("problem, reason", BAD_CASES)
def test_bad_cases_are_rejected_with_the_reason(problem, reason, tmp_path):
    source = next(case for case in SHIPPED if case.id == "slugify").dir
    case_id = "Slugify" if problem == "bad-id" else "slugify"
    directory = tmp_path / case_id
    shutil.copytree(source, directory)
    data = yaml.safe_load((directory / "case.yaml").read_text())
    if problem == "missing-key":
        del data["title"]
    elif problem == "unknown-key":
        data["surprise"] = True
    elif problem == "bad-kind":
        data["kind"] = "unknown"
    elif problem == "bad-requires":
        data["requires"] = [""]
    elif problem == "contract-schema":
        del data["contract"]["risk"]
    elif problem == "contract-validation":
        data["contract"]["verification"] = ["Run the visible tests"]
    elif problem == "contract-id":
        data["contract"]["id"] = "other-t01"
    elif problem == "config":
        data["config"]["surprise"] = True
    elif problem == "hidden-command":
        data["hidden"] = ["echo hi"]
    (directory / "case.yaml").write_text(yaml.safe_dump(data, sort_keys=False))
    if problem == "empty-hidden":
        shutil.rmtree(directory / "hidden")
        (directory / "hidden").mkdir()
    elif problem == "empty-solution":
        shutil.rmtree(directory / "solution")
        (directory / "solution").mkdir()

    with pytest.raises(cases.CaseError) as error:
        cases.load_case(directory)
    assert str(error.value).startswith(f"{case_id}:")
    assert reason in str(error.value)


# --- evals-t02: pass-to-pass commands, protected paths, grading order and scope metrics -----

TRIVIAL_TEST = (
    "import unittest\n\n\n"
    "class TrivialTests(unittest.TestCase):\n"
    "    def test_nothing(self):\n"
    "        self.assertTrue(True)\n"
)


def _adder_case(root, *, keys=None, config=None):
    """A writable copy of the adder case, with top-level case.yaml `keys` set and `config`
    entries overridden."""
    case_dir = Path(root) / "adder"
    shutil.copytree(BENCH_CASES / "adder", case_dir)
    data = yaml.safe_load((case_dir / "case.yaml").read_text())
    data.update(keys or {})
    data["config"].update(config or {})
    (case_dir / "case.yaml").write_text(yaml.safe_dump(data, sort_keys=False))
    return case_dir


def _plays(writes, *, run="python3 -m unittest -q", extra=()):
    """Scripts for one lean-flow cell: the builder writes `writes` (path -> text), runs `run`
    and any `extra` commands, then reports DONE; the reviewer approves."""
    return {
        "BUILDER": [
            *[call("write_file", path=path, content=text) for path, text in writes.items()],
            *[call("run", command=command) for command in (run, *extra)],
            AIMessage("Implemented the change and its visible tests.\nRESULT: DONE"),
        ],
        "REVIEWER": [call("git_diff", stat=True), "VERDICT"],
        "_verdicts": [],
        "_calls": [],
    }


def _run_cell(bench_repo, monkeypatch, case, plays, directory):
    """Run one lean-flow cell of `case` with a scripted model in the invoking repository the
    bench runs use, and return the cell's record."""
    variant = bench_run.variants(C.load(bench_repo), ["lean"], ["scripted:cell"])[0]
    monkeypatch.setattr(agents, "build_model",
                        lambda spec: ScriptedModel(plays=copy.deepcopy(plays)))
    return bench_run.run_cell(bench_repo, case, variant, Path(directory), max_attempts=1,
                              max_cost=5.0, sandbox_on=shutil.which("bwrap") is not None)


def _outside(path, session_log):
    """Whether a path counts for scope metrics: outside tests/ and the session-log directory."""
    if path == "tests" or path.startswith("tests/"):
        return False
    if session_log and (path == session_log or path.startswith(f"{session_log.rstrip('/')}/")):
        return False
    return True


def _changed_paths(repo, base, sha):
    """The paths base..sha changed (modified, added or deleted)."""
    return [line for line in git(repo, "diff", "--name-only", f"{base}..{sha}").splitlines() if line]


def _diff_lines(repo, base, sha, session_log):
    """Lines added plus deleted by base..sha, outside tests/ and the session-log directory."""
    total = 0
    for line in git(repo, "diff", "--numstat", f"{base}..{sha}").splitlines():
        added, deleted, path = line.split("\t")
        if _outside(path, session_log):
            total += int(added) + int(deleted)
    return total


def _reference_scope(case, repo):
    """Materialize the case and apply its reference solution: the base, the diff-line count the
    cell should record as reference_lines, and the paths the solution changed."""
    base = cases.materialize(case, repo)
    shutil.copytree(case.solution_dir, repo, dirs_exist_ok=True)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "reference solution")
    sha = git(repo, "rev-parse", "HEAD")
    return base, _diff_lines(repo, base, sha, case.cfg.session_log), _changed_paths(repo, base, sha)


def test_pass_to_pass_and_protected_are_case_keys(tmp_path, capsys):
    """case.yaml accepts two optional keys: `pass_to_pass`, a list of commands, and `protected`,
    a list of repository path globs. `hidden` keeps its meaning (the fail-to-pass commands);
    unknown keys are still refused; `factory bench cases` shows each case's counts of
    fail-to-pass and pass-to-pass commands and protected globs."""
    # The keys are optional: a case without them loads with empty tuples.
    plain = cases.load_case(BENCH_CASES / "adder")
    assert plain.pass_to_pass == () and plain.protected == ()

    keys = {"pass_to_pass": ["python3 -m unittest -q tests.test_calc"],
            "protected": ["tests/**", "docs/**"]}
    case = cases.load_case(_adder_case(tmp_path, keys=keys))
    assert case.pass_to_pass == ("python3 -m unittest -q tests.test_calc",)
    assert case.protected == ("tests/**", "docs/**")
    assert case.hidden == plain.hidden          # hidden keeps its meaning

    # A key that is not a list of non-empty strings is refused; unknown keys still are too.
    for key, value, reason in (
        ("pass_to_pass", "python3 -m unittest -q", "pass_to_pass must be a list of non-empty strings"),
        ("protected", [""], "protected must be a list of non-empty strings"),
        ("surprise", ["/dev/null"], "unknown key"),
    ):
        broken = _adder_case(tmp_path / "broken" / key,
                             keys={"surprise": ["/dev/null"]} if key == "surprise" else {key: value})
        with pytest.raises(cases.CaseError) as error:
            cases.load_case(broken)
        assert reason in str(error.value)

    capsys.readouterr()
    assert main(["bench", "cases", "--cases", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert (f"{'adder':<18} {'feature':<12} 1 fail-to-pass · 1 pass-to-pass · 2 protected  "
            f"{case.title}" in out)
    assert main(["bench", "cases", "--cases", str(BENCH_CASES)]) == 0
    out = capsys.readouterr().out
    assert (f"{'adder':<18} {'feature':<12} 1 fail-to-pass · 0 pass-to-pass · 0 protected  "
            f"Add integer addition to the calc package" in out)


def test_a_candidate_that_breaks_pass_to_pass_is_regressed(bench_repo, tmp_path, monkeypatch):
    """A verified candidate that breaks a pass_to_pass command scores `regressed`: it is
    neither tampered (nothing is protected) nor a false pass (the hidden tests still pass)."""
    case = cases.load_case(_adder_case(
        tmp_path,
        keys={"pass_to_pass": ["python3 -m unittest -q tests.test_calc"]},
        config={"unit_tests": ["python3 -m unittest -q tests.test_adder"]}))
    broken_double = GOOD_CALC.replace("    return x * 2", "    return x * 3")
    writes = {"calc/__init__.py": broken_double, "tests/test_adder.py": VISIBLE_TEST}
    record = _run_cell(bench_repo, monkeypatch, case,
                       _plays(writes, run="python3 -m unittest -q tests.test_adder"),
                       tmp_path / "cell")

    assert record["outcome"] == "regressed"
    assert record["tampered"] is False and record["extra_files"] == []
    assert record["diff_lines"] >= record["reference_lines"] > 0


def test_a_candidate_that_edits_a_protected_path_is_tampered(bench_repo, tmp_path, monkeypatch):
    """A verified candidate whose change matches a protected glob scores `tampered`, ahead of a
    hidden failure: the builder also breaks `add` (the hidden tests would fail), changes
    tests/__init__.py, adds tests/test_adder.py and deletes tests/test_calc.py — every one of
    change, add and delete matches tests/**, so tampered wins over false_pass."""
    case = cases.load_case(_adder_case(tmp_path, keys={"protected": ["tests/**"]}))
    broken_add = GOOD_CALC.replace("    return a + b", "    return a + b + 1")
    writes = {"calc/__init__.py": broken_add,
              "tests/test_adder.py": TRIVIAL_TEST,          # added, matches tests/**
              "tests/__init__.py": "# doctored\n"}          # changed, matches tests/**
    record = _run_cell(bench_repo, monkeypatch, case,
                       _plays(writes, extra=("rm tests/test_calc.py",)),   # deleted, matches tests/**
                       tmp_path / "cell")

    assert record["outcome"] == "tampered"
    assert record["tampered"] is True
    assert record["extra_files"] == []          # only calc/__init__.py, which the solution changes
    assert record["diff_lines"] >= record["reference_lines"] > 0


def test_scope_counts_lines_and_files_beyond_the_reference(bench_repo, tmp_path, monkeypatch):
    """Every cell with a candidate records how far its change went beyond the reference:
    diff_lines (lines added plus deleted outside tests/ and the session-log directory),
    reference_lines (the same count for the case's solution) and extra_files (paths the
    candidate changed that the solution didn't, outside those directories)."""
    case = cases.load_case(_adder_case(tmp_path, config={"session_log": "docs/sessions"}))
    writes = {
        "calc/__init__.py": GOOD_CALC,
        "calc/extra.py": "def helper():\n    return 1\n",
        "tests/test_adder.py": VISIBLE_TEST,                              # outside scope: tests/
        "docs/sessions/2026-11-24-evals-t02.md": "## [12:00] adder-t01\n",  # outside: session log
    }
    record = _run_cell(bench_repo, monkeypatch, case, _plays(writes), tmp_path / "cell")
    assert record["outcome"] == "solved" and record["tampered"] is False

    # The counts the record should carry, derived from the case's own fixtures.
    base, reference, reference_paths = _reference_scope(case, tmp_path / "reference")
    candidate = tmp_path / "candidate"
    assert cases.materialize(case, candidate) == base
    for path, text in writes.items():
        (candidate / path).parent.mkdir(parents=True, exist_ok=True)
        (candidate / path).write_text(text)
    git(candidate, "add", "-A")
    git(candidate, "commit", "-q", "-m", "candidate")
    sha = git(candidate, "rev-parse", "HEAD")
    diff = _diff_lines(candidate, base, sha, case.cfg.session_log)
    extra = sorted(path for path in set(_changed_paths(candidate, base, sha)) - set(reference_paths)
                   if _outside(path, case.cfg.session_log))

    assert record["reference_lines"] == reference > 0
    assert record["diff_lines"] == diff
    assert diff == reference + 2          # only calc/extra.py's two lines went beyond the reference
    assert record["extra_files"] == extra == ["calc/extra.py"]


@pytest.mark.parametrize("case", SHIPPED, ids=lambda case: case.id)
def test_every_shipped_solution_still_scores_solved(bench_repo, case, tmp_path, monkeypatch):
    """Every shipped case gains pass_to_pass (its existing test command) and protected (its
    pre-existing test files), and its reference solution still scores solved, with no scope
    beyond the reference."""
    assert case.pass_to_pass == case.cfg.unit_tests
    pre_existing = sorted(path.relative_to(case.repo_dir).as_posix()
                         for path in (case.repo_dir / "tests").rglob("test_*.py") if path.is_file())
    assert pre_existing and sorted(case.protected) == pre_existing

    writes = {path.relative_to(case.solution_dir).as_posix(): path.read_text()
              for path in sorted(case.solution_dir.rglob("*")) if path.is_file()}
    record = _run_cell(bench_repo, monkeypatch, case, _plays(writes), tmp_path / case.id)

    assert record["outcome"] == "solved"
    assert record["tampered"] is False
    assert record["extra_files"] == []
    assert record["diff_lines"] == record["reference_lines"] > 0
