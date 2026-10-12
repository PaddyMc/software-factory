"""Classify verification command results. A command that selects zero tests is
inconclusive, never a pass."""

from __future__ import annotations

import re

PASS, FAIL, INCONCLUSIVE = "pass", "fail", "inconclusive"

_CARGO_RESULT = re.compile(r"^test result: \w+\. (\d+) passed; (\d+) failed", re.M)
_PYTEST_COUNTS = re.compile(r"(\d+) (passed|failed|error|errors)\b")


def tests_run(output: str) -> int | None:
    """Number of tests that ran, or None if the output is not a test run."""
    cargo = _CARGO_RESULT.findall(output)
    if cargo:
        return sum(int(p) + int(f) for p, f in cargo)
    if "no tests ran" in output or re.search(r"\b\d+ deselected\b", output) and not _PYTEST_COUNTS.search(output):
        return 0
    py = _PYTEST_COUNTS.findall(output)
    if py:
        return sum(int(n) for n, _ in py)
    if re.search(r"^running 0 tests", output, re.M):
        return 0
    return None


def is_test_command(cmd: str) -> bool:
    return "pytest" in cmd or re.search(r"\bcargo (\S+ )*test\b", cmd) is not None


def classify(cmd: str, exit_code: int, output: str) -> str:
    if exit_code != 0:
        # pytest exit 5 = no tests collected
        return INCONCLUSIVE if (exit_code == 5 and "pytest" in cmd) else FAIL
    if is_test_command(cmd) and tests_run(output) == 0:
        return INCONCLUSIVE
    return PASS
