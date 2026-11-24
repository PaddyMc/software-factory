"""Prove bench cases sound and measure how well their hidden tests kill mutants."""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .. import sandbox as S
from ..verification import FAIL, PASS
from . import cases, mutate

STRONG = 0.60
DEFAULT_MUTANTS = mutate.DEFAULT_MUTANTS


class CheckError(RuntimeError):
    """A case selection or mutant budget that cannot be checked."""


@dataclass(frozen=True)
class CheckResult:
    case: str
    verdict: str
    killed: int = 0
    mutants: int = 0
    rate: float = 0.0
    reason: str = ""

    def record(self) -> dict:
        return {
            "case": self.case,
            "verdict": self.verdict,
            "killed": self.killed,
            "mutants": self.mutants,
            "rate": self.rate,
            "reason": self.reason,
        }

    def line(self) -> str:
        if self.verdict == "broken":
            return f"{self.case}: broken, {self.reason}"
        return (f"{self.case}: {self.verdict}, {self.killed}/{self.mutants} mutants killed "
                f"({self.rate:.0%})")


def _broken(case: cases.Case, suite: str, side: str, detail: str) -> CheckResult:
    return CheckResult(case.id, "broken", reason=f"{suite} {side}: {detail}")


def _first_not_passed(score: cases.HiddenScore) -> cases.CommandResult | None:
    return next((command for command in score.commands if command.outcome != PASS), None)


def _clear_bytecode(worktree: Path) -> None:
    # Equal-sized rewrites within one second must never reuse an earlier mutant's pyc.
    for cache in worktree.rglob("__pycache__"):
        shutil.rmtree(cache)


def check_case(case: cases.Case, mutant_limit: int = DEFAULT_MUTANTS) -> CheckResult:
    """Check one case's base and reference expectations, then score its mutants."""
    if mutant_limit < 0:
        raise CheckError("--mutants must not be negative")
    with tempfile.TemporaryDirectory(prefix=f"factory-bench-check-{case.id}-") as scratch:
        scratch = Path(scratch)
        repo = scratch / "repo"
        base = cases.materialize(case, repo)
        sandbox_on = S.available()

        def make_sandbox(worktree: Path):
            return S.make(worktree, scratch / "cache", sandbox=sandbox_on, cfg=case.cfg.sandbox)

        with cases._detached_worktree(repo, base, f"factory-bench-check-{case.id}-base-") as worktree:
            box = make_sandbox(worktree)
            pass_to_pass = cases._score_commands(case.pass_to_pass, box)
            if not pass_to_pass.passed:
                command = _first_not_passed(pass_to_pass)
                return _broken(case, "pass_to_pass", "base",
                               f"{command.cmd!r} was {command.outcome}; expected all commands to pass")
            shutil.copytree(case.hidden_dir, worktree, dirs_exist_ok=True)
            hidden = cases._score_commands(case.hidden, box)
            if not any(command.outcome == FAIL for command in hidden.commands):
                return _broken(case, "hidden", "base",
                               "no command failed; expected at least one fail-to-pass command to fail")

        with cases._detached_worktree(repo, base, f"factory-bench-check-{case.id}-solution-") as worktree:
            shutil.copytree(case.solution_dir, worktree, dirs_exist_ok=True)
            box = make_sandbox(worktree)
            pass_to_pass = cases._score_commands(case.pass_to_pass, box)
            if not pass_to_pass.passed:
                command = _first_not_passed(pass_to_pass)
                return _broken(case, "pass_to_pass", "solution",
                               f"{command.cmd!r} was {command.outcome}; expected all commands to pass")
            shutil.copytree(case.hidden_dir, worktree, dirs_exist_ok=True)
            hidden = cases._score_commands(case.hidden, box)
            if not hidden.passed:
                command = _first_not_passed(hidden)
                return _broken(case, "hidden", "solution",
                               f"{command.cmd!r} was {command.outcome}; expected all commands to pass")

            selected = mutate.mutants(case, mutant_limit)
            originals = {mutant.path: (case.solution_dir / mutant.path).read_text(encoding="utf-8")
                         for mutant in selected}
            killed = 0
            for mutant in selected:
                for relative, source in originals.items():
                    (worktree / relative).write_text(source, encoding="utf-8")
                mutant.apply(worktree)
                _clear_bytecode(worktree)
                score = cases._score_commands(case.hidden, box)
                killed += any(command.outcome == FAIL for command in score.commands)

    total = len(selected)
    rate = killed / total if total else 0.0
    verdict = "weak" if rate < STRONG else "ok"
    return CheckResult(case.id, verdict, killed, total, rate)


def select_cases(cases_dir: str | None = None, case_ids: list[str] | None = None) -> list[cases.Case]:
    loaded = cases.load_cases([cases_dir] if cases_dir else None)
    by_id = {case.id: case for case in loaded}
    for case_id in case_ids or []:
        if case_id not in by_id:
            raise CheckError(f"unknown case {case_id} (cases: {', '.join(sorted(by_id))})")
    wanted = set(case_ids or [])
    return [case for case in loaded if not wanted or case.id in wanted]


def check_cases(loaded: list[cases.Case], mutant_limit: int = DEFAULT_MUTANTS) -> list[CheckResult]:
    return [check_case(case, mutant_limit) for case in loaded]
