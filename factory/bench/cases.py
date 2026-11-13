"""Load bench fixture cases, materialize their repositories, and score hidden tests."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import yaml

from .. import config as C
from .. import contracts, verification
from ..verification import PASS, classify

KINDS = ("feature", "bugfix", "multi-file", "refactor", "algorithm")
KEYS = {"title", "kind", "requires", "config", "contract", "hidden"}
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
    missing = sorted(KEYS - set(data))
    unknown = sorted(set(data) - KEYS, key=str)
    if missing:
        raise CaseError(f"{case_id}: case.yaml missing key(s): {', '.join(missing)}")
    if unknown:
        raise CaseError(f"{case_id}: case.yaml unknown key(s): {', '.join(map(str, unknown))}")
    if not ID_RE.fullmatch(case_id):
        raise CaseError(f"{case_id}: case id must match {ID_RE.pattern}")
    if data["kind"] not in KINDS:
        raise CaseError(f"{case_id}: kind {data['kind']!r} must be one of {', '.join(KINDS)}")
    for key in ("requires", "hidden"):
        if not _string_list(data[key]):
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
                hidden=tuple(data["hidden"]))


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


def score_hidden(case: Case, repo: Path, sha: str, sandbox) -> HiddenScore:
    """Score a commit with the case's hidden files in a disposable linked worktree."""
    repo = Path(repo)
    scratch = Path(tempfile.mkdtemp(prefix=f"factory-bench-{case.id}-"))
    worktree = scratch / "wt"
    added = False
    try:
        _git(repo, "worktree", "add", "-q", "--detach", str(worktree), sha)
        added = True
        shutil.copytree(case.hidden_dir, worktree, dirs_exist_ok=True)
        box = sandbox(worktree)
        results = []
        for cmd in case.hidden:
            result = box.run(cmd)
            results.append(CommandResult(cmd, classify(cmd, result.code, result.output), result.output))
        return HiddenScore(tuple(results))
    finally:
        try:
            if added:
                _git(repo, "worktree", "remove", "--force", str(worktree))
        finally:
            shutil.rmtree(scratch, ignore_errors=True)
