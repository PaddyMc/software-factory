"""Classify verification command results. A command that selects zero tests is
inconclusive, never a pass."""

from __future__ import annotations

import re

PASS, FAIL, INCONCLUSIVE = "pass", "fail", "inconclusive"

_CARGO_RESULT = re.compile(r"^test result: \w+\. (\d+) passed; (\d+) failed", re.M)
_UNITTEST_RAN = re.compile(r"^Ran (\d+) tests? in\b", re.M)
_PYTEST_COUNTS = re.compile(r"(\d+) (passed|failed|error|errors)\b")
# pytest's last line, alone on its line: bare under -q, framed in "=" otherwise. "1 failed, 1 passed in
# 0.02s", "=== 2 deselected in 0.00s ===", "no tests ran in 0.00s". A traceback indents the source it
# quotes, so a test whose source holds such text isn't read as the summary.
_PYTEST_SUMMARY = re.compile(
    r"^(?:=+ )?(no tests ran|\d+ \w+(?:, \d+ \w+)*) in \d+(?:\.\d+)?s(?: \(\d+:\d\d:\d\d\))?(?: =+)?[ \t\r]*$",
    re.M)
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def tests_run(output: str) -> int | None:
    """Number of tests that ran, or None if the output is not a test run."""
    cargo = _CARGO_RESULT.findall(output)
    if cargo:
        return sum(int(p) + int(f) for p, f in cargo)
    unittest = _UNITTEST_RAN.search(output)
    if unittest:
        return int(unittest.group(1))
    summaries = _PYTEST_SUMMARY.findall(_ANSI.sub("", output))  # one per pytest run in the output
    counts = [int(n) for s in summaries for n, _ in _PYTEST_COUNTS.findall(s)]
    if counts:
        return sum(counts)
    if any(s == "no tests ran" or "deselected" in s for s in summaries):
        return 0
    if re.search(r"^running 0 tests", output, re.M):
        return 0
    return None


def is_test_command(cmd: str) -> bool:
    return ("pytest" in cmd or re.search(r"\bcargo (\S+ )*test\b", cmd) is not None
            or re.search(r"-m\s+unittest\b", cmd) is not None)


def classify(cmd: str, exit_code: int, output: str) -> str:
    if exit_code != 0:
        # pytest exit 5 = no tests collected
        return INCONCLUSIVE if (exit_code == 5 and "pytest" in cmd) else FAIL
    if is_test_command(cmd) and tests_run(output) == 0:
        return INCONCLUSIVE
    return PASS
