"""Load bench fixture cases, materialize their repositories, and score hidden tests."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import yaml

from .. import config as C
from .. import contracts, globs, verification
from ..verification import PASS, classify

KINDS = ("feature", "bugfix", "multi-file", "refactor", "algorithm")
REQUIRED_KEYS = {"title", "kind", "requires", "config", "contract", "hidden"}
OPTIONAL_KEYS = {"pass_to_pass", "protected"}
KEYS = REQUIRED_KEYS | OPTIONAL_KEYS
ID_RE = re.compile(r"^[a-z][a-z0-9-]*$")
FIXTURES = Path(__file__).resolve().parent / "fixtures"

_GIT_ENV = {
    "GIT_AUTHOR_NAME": "Factory Bench",
    "GIT_AUTHOR_EMAIL": "bench@factory.invalid",
    "GIT_COMMITTER_NAME": "Factory Bench",
    "GIT_COMMITTER_EMAIL": "bench@factory.invalid",
    "GIT_AUTHOR_DATE": "2026-01-01T00:00:00+00:00",
    "GIT_COMMITTER_DATE": "2026-01-01T00:00:00+00:00",
}


class CaseError(ValueError):
    pass


@dataclass(frozen=True)
class Case:
    id: str
    dir: Path
    title: str
    kind: str
    requires: tuple[str, ...]
    config: dict
    cfg: C.Config
    contract: contracts.Task
    hidden: tuple[str, ...]
    pass_to_pass: tuple[str, ...]
    protected: tuple[str, ...]

    @property
    def repo_dir(self) -> Path:
        return self.dir / "repo"

    @property
    def hidden_dir(self) -> Path:
        return self.dir / "hidden"

    @property
    def solution_dir(self) -> Path:
        return self.dir / "solution"


@dataclass(frozen=True)
class CommandResult:
    cmd: str
    outcome: str
    output: str


@dataclass(frozen=True)
class HiddenScore:
    commands: tuple[CommandResult, ...]

    @property
    def passed(self) -> bool:
        return all(c.outcome == PASS for c in self.commands)


@dataclass(frozen=True)
class CandidateScore:
    hidden: HiddenScore
    pass_to_pass: HiddenScore
    tampered: bool

    @property
    def outcome(self) -> str:
        if self.tampered:
            return "tampered"
        if not self.hidden.passed:
            return "false_pass"
        if not self.pass_to_pass.passed:
            return "regressed"
        return "solved"


def _git(cwd: Path, *args: str, env: dict[str, str] | None = None) -> str:
    return subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, text=True,
                          check=True).stdout.strip()


def _string_list(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) and item for item in value)


def _has_files(directory: Path) -> bool:
    return directory.is_dir() and any(path.is_file() for path in directory.rglob("*"))


def load_case(dir: Path) -> Case:
    """Load and validate one case directory."""
    dir = Path(dir)
    case_id = dir.name
    try:
        data = yaml.safe_load((dir / "case.yaml").read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as e:
        raise CaseError(f"{case_id}: cannot read case.yaml: {e}") from None
    if not isinstance(data, dict):
        raise CaseError(f"{case_id}: case.yaml must be a mapping")
    missing = sorted(REQUIRED_KEYS - set(data))
    unknown = sorted(set(data) - KEYS, key=str)
    if missing:
        raise CaseError(f"{case_id}: case.yaml missing key(s): {', '.join(missing)}")
    if unknown:
        raise CaseError(f"{case_id}: case.yaml unknown key(s): {', '.join(map(str, unknown))}")
    if not ID_RE.fullmatch(case_id):
        raise CaseError(f"{case_id}: case id must match {ID_RE.pattern}")
    if data["kind"] not in KINDS:
        raise CaseError(f"{case_id}: kind {data['kind']!r} must be one of {', '.join(KINDS)}")
    for key in ("requires", "hidden", "pass_to_pass", "protected"):
        if not _string_list(data.get(key, [])):
            raise CaseError(f"{case_id}: {key} must be a list of non-empty strings")
    if not isinstance(data["config"], dict):
        raise CaseError(f"{case_id}: config must be a mapping")
    try:
        cfg = C.parse(data["config"])
    except C.ConfigError as e:
        raise CaseError(f"{case_id}: invalid config: {e}") from None

    plan = f"docs/plans/{case_id}.md"
    try:
        task = contracts.task_from_mapping(data["contract"], plan=plan)
    except contracts.ContractError as e:
        raise CaseError(f"{case_id}: invalid contract: {e}") from None
    errors = contracts.validate_tasks([task])
    if errors:
        raise CaseError(f"{case_id}: invalid contract: {'; '.join(errors)}")
    if task.id != f"{case_id}-t01":
        raise CaseError(f"{case_id}: contract id {task.id!r} must be {case_id}-t01")
    for cmd in data["hidden"]:
        if not verification.is_test_command(cmd):
            raise CaseError(f"{case_id}: hidden command is not a test command: {cmd!r}")
    if not (dir / "repo").is_dir():
        raise CaseError(f"{case_id}: repo/ is missing or not a directory")
    for name in ("hidden", "solution"):
        if not _has_files(dir / name):
            raise CaseError(f"{case_id}: {name}/ is empty or missing")
    return Case(id=case_id, dir=dir, title=data["title"], kind=data["kind"],
                requires=tuple(data["requires"]), config=data["config"], cfg=cfg, contract=task,
                hidden=tuple(data["hidden"]), pass_to_pass=tuple(data.get("pass_to_pass", [])),
                protected=tuple(data.get("protected", [])))


def load_cases(dirs=None) -> list[Case]:
    """Load cases below suite directories, sorted by case id."""
    roots = [FIXTURES] if dirs is None else [Path(d) for d in dirs]
    found: dict[str, Case] = {}
    for root in roots:
        if not root.is_dir():
            raise CaseError(f"{root}: case suite directory is missing or not a directory")
        for directory in sorted(root.iterdir()):
            if not directory.is_dir() or not (directory / "case.yaml").is_file():
                continue
            case = load_case(directory)
            if case.id in found:
                raise CaseError(f"{case.id}: duplicate case in {case.dir} and {found[case.id].dir}")
            found[case.id] = case
    return sorted(found.values(), key=lambda case: case.id)


def materialize(case: Case, dest: Path) -> str:
    """Create the case's starting repository and return its deterministic base commit."""
    dest = Path(dest)
    shutil.copytree(case.repo_dir, dest)
    config_path = dest / C.CONFIG_PATH
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(yaml.safe_dump(case.config, sort_keys=True, default_flow_style=False),
                           encoding="utf-8")
    plan_path = dest / case.contract.plan
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    contract_yaml = yaml.safe_dump([case.contract.mapping()], sort_keys=False, default_flow_style=False)
    plan_path.write_text(f"# Plan: {case.title}\n\n```yaml\n{contract_yaml}```\n", encoding="utf-8")

    _git(dest, "init", "-q", "-b", "main")
    _git(dest, "add", "-A")
    env = {**os.environ, **_GIT_ENV}
    _git(dest, "-c", "commit.gpgsign=false", "commit", "-q", "-m", f"bench case {case.id}", env=env)
    return _git(dest, "rev-parse", "HEAD")


@contextmanager
def _detached_worktree(repo: Path, sha: str, prefix: str) -> Iterator[Path]:
    scratch = Path(tempfile.mkdtemp(prefix=prefix))
    worktree = scratch / "wt"
    added = False
    try:
        _git(repo, "worktree", "add", "-q", "--detach", str(worktree), sha)
        added = True
        yield worktree
    finally:
        try:
            if added:
                _git(repo, "worktree", "remove", "--force", str(worktree))
        finally:
            shutil.rmtree(scratch, ignore_errors=True)


def _score_commands(commands: tuple[str, ...], box) -> HiddenScore:
    results = []
    for cmd in commands:
        result = box.run(cmd)
        results.append(CommandResult(cmd, classify(cmd, result.code, result.output), result.output))
    return HiddenScore(tuple(results))


def score_hidden(case: Case, repo: Path, sha: str, sandbox) -> HiddenScore:
    """Score a commit with the case's hidden files in a disposable linked worktree."""
    with _detached_worktree(Path(repo), sha, f"factory-bench-{case.id}-") as worktree:
        shutil.copytree(case.hidden_dir, worktree, dirs_exist_ok=True)
        return _score_commands(case.hidden, sandbox(worktree))


def _changed_paths(repo: Path, base: str, sha: str) -> list[str]:
    # A rename is also a deletion of its source, which may itself be protected.
    return _git(repo, "diff", "--name-only", "--no-renames", f"{base}..{sha}").splitlines()


def score_candidate(case: Case, repo: Path, base: str, sha: str, sandbox) -> CandidateScore:
    """Run both test suites in one scratch worktree and apply grading precedence."""
    repo = Path(repo)
    changed = _changed_paths(repo, base, sha)
    tampered = any(globs.matches_any(path, case.protected) for path in changed)
    with _detached_worktree(repo, sha, f"factory-bench-{case.id}-") as worktree:
        shutil.copytree(case.hidden_dir, worktree, dirs_exist_ok=True)
        box = sandbox(worktree)
        hidden = _score_commands(case.hidden, box)
        pass_to_pass = _score_commands(case.pass_to_pass, box)
    return CandidateScore(hidden=hidden, pass_to_pass=pass_to_pass, tampered=tampered)


def _counted_path(path: str, session_log: str | None) -> bool:
    """Whether a path contributes to the implementation-scope metrics."""
    if path == "tests" or path.startswith("tests/"):
        return False
    if session_log:
        session_log = session_log.rstrip("/")
        if path == session_log or path.startswith(session_log + "/"):
            return False
    return True


def _diff_lines(numstat: str, session_log: str | None) -> int:
    total = 0
    for line in numstat.splitlines():
        parts = line.split("\t", 2)
        if len(parts) != 3 or not _counted_path(parts[2], session_log):
            continue
        added, deleted = parts[:2]
        # Git uses dashes rather than line counts for binary files.
        total += int(added) if added.isdigit() else 0
        total += int(deleted) if deleted.isdigit() else 0
    return total


def candidate_scope(case: Case, repo: Path, base: str, sha: str) -> dict:
    """Measure a candidate's implementation diff and paths beyond the reference solution."""
    repo = Path(repo)
    session_log = case.cfg.session_log
    candidate_numstat = _git(repo, "diff", "--numstat", f"{base}..{sha}")
    candidate_paths = _changed_paths(repo, base, sha)
    with _detached_worktree(repo, base, f"factory-bench-{case.id}-reference-") as worktree:
        shutil.copytree(case.solution_dir, worktree, dirs_exist_ok=True)
        _git(worktree, "add", "-A")
        reference_numstat = _git(worktree, "diff", "--cached", "--numstat", base)
        reference_paths = _git(worktree, "diff", "--cached", "--name-only", base).splitlines()
    extra = sorted(path for path in set(candidate_paths) - set(reference_paths)
                   if _counted_path(path, session_log))
    return {
        "tampered": any(globs.matches_any(path, case.protected) for path in candidate_paths),
        "diff_lines": _diff_lines(candidate_numstat, session_log),
        "reference_lines": _diff_lines(reference_numstat, session_log),
        "extra_files": extra,
    }
