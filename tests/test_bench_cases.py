import shutil
from pathlib import Path

import pytest
import yaml

from factory import contracts, gates as G, sandbox, verification
from factory.bench import cases
from conftest import git

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
