"""evals-t03: `factory bench check` — a case is trusted only once it proves itself sound.

These tests pin down what the two new modules and the command expose:

  factory/bench/check.py
      STRONG        the share of its mutants a case's hidden tests must kill for the case to
                    count as strong: 0.6 (60%)
  factory/bench/mutate.py
      Up to N (default 20) mutants of a case's solution: for each Python file the solution
      changes, AST mutations of the functions it changes — a comparison operator swapped, `+`
      and `-` swapped, an integer constant plus one, `True` and `False` swapped, a `return`
      value replaced with `None` — chosen in a fixed order seeded by the case id, so the same
      case always gives the same mutants. A mutant is killed when a hidden command fails on it.

  `factory bench check [--cases DIR] [CASE…] [--mutants N] [--json]`
      Loads the cases (the shipped suite by default) and, per case, in case-id order, one line:
          CASE: ok, K/N mutants killed (P%)
          CASE: weak, K/N mutants killed (P%)      K/N below check.STRONG
          CASE: broken, REASON                    REASON names the expectation that failed —
                                                  `hidden` or `pass_to_pass` — and the side it
                                                  failed on, `base` or `solution`
      The exit code is 1 when any case is broken, else 0. `--json` prints the same per case as
      one JSON object, no text around it: {"cases": [{"case", "verdict", "killed", "mutants",
      "rate", "reason"}]}, in case-id order, `rate` the share killed/mutants.

The suites below are built by hand in a temporary directory, and their hidden tests live in
`bench_hidden/checks.py` (not `test_*.py`) so that the cases' `python3 -m unittest -q`
pass-to-pass command never discovers them, however the check lays the hidden files out.
"""

import json
import re
import shutil
from pathlib import Path

import pytest
import yaml

from factory.bench import cases
from factory.cli import main

SHIPPED = [case.id for case in cases.load_cases()]

CALC = '''\
"""A tiny calc package."""


def double(x):
    """Return x times two."""
    return x * 2


def flood(n):
    """Return n plus one while n stays below three."""
    if n < 3:
        return n + 1
    return n + 2
'''

SOLUTION_ARITHMETIC = '''\
"""A tiny calc package."""


def double(x):
    """Return x times two."""
    return x * 2


def flood(n):
    """Return n plus one while n stays below three."""
    if n < 3:
        return n + 1
    return n + 2


def add(a, b):
    """Return a plus b."""
    return a + b


def sub(a, b):
    """Return a minus b."""
    return a - b


def twice(x):
    """Return x added to itself."""
    return x + x
'''

ALREADY_CALC = '''\
"""A tiny calc package."""


def double(x):
    """Return x times two."""
    return x * 2


def add(a, b):
    """Return a plus b."""
    return a + b
'''

ALREADY_SOLUTION = '''\
"""A tiny calc package."""


def double(x):
    """Return x times two."""
    return x * 2


def add(a, b):
    """Return a plus b."""
    return a + b


def sub(a, b):
    """Return a minus b."""
    return a - b
'''

WRONG_SOLUTION = '''\
"""A tiny calc package."""


def double(x):
    """Return x times two."""
    return x * 2


def add(a, b):
    """Return a plus b."""
    return a - b
'''

REGRESSED_SOLUTION = '''\
"""A tiny calc package."""


def double(x):
    """Return x times two."""
    return x * 3


def add(a, b):
    """Return a plus b."""
    return a + b
'''

KINDS_SOURCE = '''\
"""One function per kind of mutant."""


def add(a, b):
    """Return a plus b."""
    return a + b


def below(x):
    """Return whether x is below three."""
    return x < 3


def answer():
    """Return the answer."""
    return 42


def flag():
    """Return True."""
    return True
'''

WIDE_FUNCTIONS = 24


def _wide_source() -> str:
    lines = ['"""One function per wide mutant."""', ""]
    for n in range(WIDE_FUNCTIONS):
        lines += [f"def w{n}(a, b):", f'    """Return a plus b, variant {n}."""', "    return a + b", ""]
    return "\n".join(lines)


def _wide_hidden() -> str:
    lines = ["import unittest", "", "from calc.wide import *", "", "class HiddenWideTests(unittest.TestCase):"]
    for n in range(WIDE_FUNCTIONS):
        lines += [f"    def test_w{n}(self):", f"        self.assertEqual(w{n}(2, 3), 5)",
                  f"        self.assertEqual(w{n}(-1, 1), 0)", ""]
    return "\n".join(lines)


REPO_TEST = '''\
import unittest

from calc import double


class CalcTests(unittest.TestCase):
    def test_double(self):
        self.assertEqual(double(3), 6)
        self.assertEqual(double(-2), -4)
        self.assertEqual(double(0), 0)
'''

REPO_TEST_RED = '''\
import unittest

from calc import double


class CalcTests(unittest.TestCase):
    def test_double_is_seven(self):
        self.assertEqual(double(3), 7)
'''

HIDDEN_ARITHMETIC = '''\
import unittest

from calc import add, sub, twice


class HiddenArithmeticTests(unittest.TestCase):
    def test_add(self):
        self.assertEqual(add(2, 3), 5)
        self.assertEqual(add(-1, 1), 0)
        self.assertEqual(add(10, -4), 6)

    def test_sub(self):
        self.assertEqual(sub(5, 3), 2)
        self.assertEqual(sub(-1, -2), 1)
        self.assertEqual(sub(0, 7), -7)

    def test_twice(self):
        self.assertEqual(twice(4), 8)
        self.assertEqual(twice(-3), -6)
        self.assertEqual(twice(0), 0)
'''

HIDDEN_ADD = '''\
import unittest

from calc import add


class HiddenAddTests(unittest.TestCase):
    def test_add(self):
        self.assertEqual(add(2, 3), 5)
        self.assertEqual(add(-1, 1), 0)
        self.assertEqual(add(10, -4), 6)
'''

KINDS_HIDDEN = '''\
import unittest

from calc.kinds import add, answer, below, flag


class HiddenKindsTests(unittest.TestCase):
    def test_add(self):
        self.assertEqual(add(2, 3), 5)
        self.assertEqual(add(-1, 1), 0)

    def test_below(self):
        self.assertTrue(below(2))
        self.assertFalse(below(3))
        self.assertFalse(below(4))

    def test_answer(self):
        self.assertEqual(answer(), 42)

    def test_flag(self):
        self.assertIs(flag(), True)
'''

HIDDEN_COMMAND = "python3 -m unittest -v bench_hidden.checks"
PASS_TO_PASS = ["python3 -m unittest -q"]


def _case_yaml(case_id: str, title: str) -> str:
    return yaml.safe_dump({
        "title": title,
        "kind": "feature",
        "requires": ["python3"],
        "config": {
            "test_paths": ["tests/**"],
            "unit_tests": ["python3 -m unittest -q"],
            "dependency_sources": [],
            "sandbox": {"ro_binds": [], "rw_binds": [], "path": [], "hide": []},
        },
        "contract": {
            "id": f"{case_id}-t01",
            "goal": f"Add the {case_id} arithmetic helpers to the calc package",
            "spec_refs": [f"docs/plans/{case_id}.md"],
            "depends_on": [],
            "non_goals": ["Changing double(x), or adding a dependency"],
            "acceptance": ["The calc package gains the arithmetic helpers in the plan"],
            "verification": ["python3 -m unittest -v tests.test_calc"],
            "risk": "low",
        },
        "hidden": [HIDDEN_COMMAND],
        "pass_to_pass": PASS_TO_PASS,
        "protected": ["tests/test_calc.py"],
    }, sort_keys=False, default_flow_style=False)


def _case(root: Path, case_id: str, *, hidden_tests: str, solution: dict[str, str],
          repo: dict[str, str] | None = None, title: str = "") -> Path:
    """Write one case below `root`: the shared repo, its hidden tests in bench_hidden/checks.py,
    and the files the solution lays over it."""
    files = {
        "repo/calc/__init__.py": CALC,
        "repo/tests/__init__.py": "",
        "repo/tests/test_calc.py": REPO_TEST,
        "hidden/bench_hidden/__init__.py": "",
        "hidden/bench_hidden/checks.py": hidden_tests,
    }
    files.update({f"repo/{name}": text for name, text in (repo or {}).items()})
    files.update({f"solution/{name}": text for name, text in solution.items()})
    directory = root / case_id
    for name, text in files.items():
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    (directory / "case.yaml").write_text(_case_yaml(case_id, title or f"{case_id} arithmetic"),
                                         encoding="utf-8")
    return directory


def _sound_suite(root: Path) -> Path:
    """Three cases over the same repo, all sound in their base and solution expectations:
    `kinds` (a solution file with one function per kind of mutant, all covered by its hidden
    tests), `shallow` (hidden tests that cover add only) and `sums` (hidden tests that cover
    add, sub and twice, everything its solution changes)."""
    _case(root, "kinds", hidden_tests=KINDS_HIDDEN, solution={"calc/kinds.py": KINDS_SOURCE},
          title="one function per kind of mutant")
    _case(root, "shallow", hidden_tests=HIDDEN_ADD,
          solution={"calc/__init__.py": SOLUTION_ARITHMETIC}, title="hidden tests that cover add only")
    _case(root, "sums", hidden_tests=HIDDEN_ARITHMETIC,
          solution={"calc/__init__.py": SOLUTION_ARITHMETIC}, title="hidden tests that cover it all")
    return root


def _broken_base_suite(root: Path) -> Path:
    """`already`: hidden tests that pass on the base, so they don't need the change.
    `base-regression`: a pass-to-pass suite that is red on the base."""
    _case(root, "already", hidden_tests=HIDDEN_ADD, repo={"calc/__init__.py": ALREADY_CALC},
          solution={"calc/__init__.py": ALREADY_SOLUTION}, title="hidden tests that need nothing")
    _case(root, "base-regression", hidden_tests=HIDDEN_ARITHMETIC,
          repo={"tests/test_calc.py": REPO_TEST_RED},
          solution={"calc/__init__.py": SOLUTION_ARITHMETIC}, title="a red base suite")
    return root


def _broken_solution_suite(root: Path) -> Path:
    """`wrong`: a solution whose hidden tests fail. `solution-regression`: a solution that
    breaks its pass-to-pass suite."""
    _case(root, "solution-regression", hidden_tests=HIDDEN_ADD,
          solution={"calc/__init__.py": REGRESSED_SOLUTION}, title="a solution that regresses the suite")
    _case(root, "wrong", hidden_tests=HIDDEN_ADD,
          solution={"calc/__init__.py": WRONG_SOLUTION}, title="a solution that fails its tests")
    return root


def _case_line(out: str, case_id: str) -> str:
    for line in out.splitlines():
        if line.startswith(f"{case_id}: "):
            return line
    raise AssertionError(f"no {case_id}: line in the check's output: {out!r}")


def _mutant_line(out: str, case_id: str) -> tuple[str, int, int]:
    """(verdict, killed, total) from the case's `CASE: ok, K/N mutants killed (P%)` line."""
    line = _case_line(out, case_id)
    matched = re.fullmatch(rf"{re.escape(case_id)}: (ok|weak), (\d+)/(\d+) mutants killed \(\d+%\)", line)
    assert matched, f"{case_id}: expected a mutant line, got {line!r}"
    return matched[1], int(matched[2]), int(matched[3])


def _broken_line(out: str, case_id: str) -> str:
    line = _case_line(out, case_id)
    assert line.startswith(f"{case_id}: broken"), f"{case_id}: expected a broken line, got {line!r}"
    return line


def test_a_sound_case_passes_the_check(tmp_path, capsys):
    """A sound case reads ok and the check exits 0: its hidden tests fail on the base (they need
    the change), pass on the solution, its pass-to-pass suite passes on both sides, and its
    hidden tests kill every mutant of the functions its solution changes — a mutant of `double`,
    which the solution leaves alone, would be charged to tests that never needed it."""
    suite = _sound_suite(tmp_path / "suite")
    code = main(["bench", "check", "--cases", str(suite)])
    out, err = capsys.readouterr()
    assert code == 0, err
    assert "broken" not in out
    for case_id in ("kinds", "sums"):
        verdict, killed, total = _mutant_line(out, case_id)
        assert verdict == "ok", f"{case_id}: {out}"
        assert killed == total, f"{case_id}: its hidden tests kill every mutant: {out}"
        assert 0 < total <= 20, f"{case_id}: {out}"
    kinds_total = _mutant_line(out, "kinds")[2]
    assert kinds_total >= 9, "kinds: each of its functions offers a mutant of every kind"
    # selecting one case checks only that case
    capsys.readouterr()
    assert main(["bench", "check", "--cases", str(suite), "sums"]) == 0
    out, err = capsys.readouterr()
    _mutant_line(out, "sums")
    assert "kinds: " not in out and "shallow: " not in out
    # an unknown case is refused
    capsys.readouterr()
    code = main(["bench", "check", "--cases", str(suite), "nope"])
    out, err = capsys.readouterr()
    assert code == 1
    assert "nope" in err


def test_hidden_tests_that_pass_on_the_base_are_broken(tmp_path, capsys):
    """`already`'s hidden tests pass on the base — they don't need the change — so the case is
    broken, the line says which expectation failed (a hidden command, on the base) and the check
    exits 1. `base-regression` is broken the other base way: its pass-to-pass suite is red on the
    base. A broken case gets no mutant verdict, and --json prints the same per case, reason
    included."""
    suite = _broken_base_suite(tmp_path / "suite")
    code = main(["bench", "check", "--cases", str(suite)])
    out, err = capsys.readouterr()
    assert code == 1, out
    assert ": ok," not in out and ": weak," not in out
    line = _broken_line(out, "already")
    assert "hidden" in line and "base" in line, line
    line = _broken_line(out, "base-regression")
    assert "base" in line and any(word in line for word in ("pass_to_pass", "pass-to-pass")), line
    capsys.readouterr()
    code = main(["bench", "check", "--cases", str(suite), "--json"])
    out, err = capsys.readouterr()
    assert code == 1, err
    data = json.loads(out)
    records = {record["case"]: record for record in data["cases"]}
    assert set(records) == {"already", "base-regression"}
    for case_id, record in records.items():
        assert record["verdict"] == "broken", record
        assert set(record) >= {"case", "verdict", "reason"}, record
        assert record["reason"], record


def test_a_solution_that_fails_its_tests_is_broken(tmp_path, capsys):
    """`wrong`'s solution fails its own hidden tests, and `solution-regression`'s solution breaks
    its pass-to-pass suite: both cases are broken, their lines say which expectation failed on
    the solution, and the check exits 1."""
    suite = _broken_solution_suite(tmp_path / "suite")
    code = main(["bench", "check", "--cases", str(suite)])
    out, err = capsys.readouterr()
    assert code == 1, out
    line = _broken_line(out, "wrong")
    assert "hidden" in line and "solution" in line, line
    line = _broken_line(out, "solution-regression")
    assert "solution" in line and any(word in line for word in ("pass_to_pass", "pass-to-pass")), line


def test_mutants_are_deterministic(tmp_path, capsys):
    """The same case always gives the same mutants: two checks of the same suite print the same
    lines, and so does a check of a copy of that suite under another path — the mutants are
    chosen in a fixed order seeded by the case id, not by where the case happens to live.
    --mutants N caps how many mutants each case gets."""
    suite = _sound_suite(tmp_path / "suite")
    runs = []
    for _ in range(2):
        capsys.readouterr()
        assert main(["bench", "check", "--cases", str(suite), "--mutants", "3", "--json"]) == 0
        runs.append(capsys.readouterr().out)
    assert runs[0] == runs[1], "the same suite must give the same mutants twice"
    texts = []
    for _ in range(2):
        capsys.readouterr()
        assert main(["bench", "check", "--cases", str(suite), "--mutants", "3"]) == 0
        texts.append(capsys.readouterr().out)
    assert texts[0] == texts[1], "the same suite must give the same mutants twice"
    copy = tmp_path / "copy"
    shutil.copytree(suite, copy)
    capsys.readouterr()
    assert main(["bench", "check", "--cases", str(copy), "--mutants", "3"]) == 0
    copied = capsys.readouterr().out
    assert copied == texts[0], "the same case id under another path must give the same mutants"
    for case_id in ("kinds", "shallow", "sums"):
        _, _, total = _mutant_line(texts[0], case_id)
        assert total == 3, f"{case_id}: --mutants caps its mutants at 3: {texts[0]}"
        data = json.loads(runs[0])
        record = next(r for r in data["cases"] if r["case"] == case_id)
        assert record["mutants"] == 3, record


def test_weak_hidden_tests_are_flagged(tmp_path, capsys):
    """`shallow` is sound in every base and solution expectation — its hidden tests fail on the
    base and pass on the solution, and its pass-to-pass suite passes on both sides — but they
    cover one function out of the three its solution changes, so most mutants live and the case
    reads weak. Only a broken case fails the check, so the exit code stays 0."""
    from factory.bench import check
    assert check.STRONG == pytest.approx(0.6)
    suite = _sound_suite(tmp_path / "suite")
    code = main(["bench", "check", "--cases", str(suite)])
    out, err = capsys.readouterr()
    assert code == 0, err
    verdict, killed, total = _mutant_line(out, "shallow")
    assert verdict == "weak", out
    assert 1 <= killed < total, out
    assert killed / total < check.STRONG, out
    verdict, killed, total = _mutant_line(out, "sums")     # the same repo and solution, fuller tests
    assert verdict == "ok", out
    assert killed == total, out


def test_check_prints_json(tmp_path, capsys):
    """--json prints the same per case as one JSON object, in case-id order, no text around it:
    each record carries the case, its verdict, the mutants it ran and how many its hidden tests
    killed, and their share as `rate`. The default mutant budget is 20 per case: `wide`'s
    solution offers more mutants than that, `sums`' fewer."""
    from factory.bench import check
    suite = tmp_path / "suite"
    _case(suite, "shallow", hidden_tests=HIDDEN_ADD, solution={"calc/__init__.py": SOLUTION_ARITHMETIC})
    _case(suite, "sums", hidden_tests=HIDDEN_ARITHMETIC, solution={"calc/__init__.py": SOLUTION_ARITHMETIC})
    _case(suite, "wide", hidden_tests=_wide_hidden(), solution={"calc/wide.py": _wide_source()})
    code = main(["bench", "check", "--cases", str(suite), "--json"])
    out, err = capsys.readouterr()
    assert code == 0, err
    data = json.loads(out)
    records = {record["case"]: record for record in data["cases"]}
    assert [record["case"] for record in data["cases"]] == ["shallow", "sums", "wide"]
    for case_id, verdict in (("shallow", "weak"), ("sums", "ok"), ("wide", "ok")):
        record = records[case_id]
        assert record["verdict"] == verdict, record
        assert set(record) >= {"case", "verdict", "killed", "mutants", "rate"}, record
        assert isinstance(record["killed"], int) and isinstance(record["mutants"], int), record
        assert 0 <= record["killed"] <= record["mutants"] <= 20, record
        assert record["rate"] == pytest.approx(record["killed"] / record["mutants"]), record
    assert records["wide"]["mutants"] == 20, "the default budget: 20 mutants when more are available"
    assert records["wide"]["killed"] == 20
    assert records["sums"]["mutants"] < 20, "only the mutants the solution offers"
    assert records["sums"]["killed"] == records["sums"]["mutants"]
    assert records["shallow"]["killed"] < records["shallow"]["mutants"]
    assert records["shallow"]["killed"] / records["shallow"]["mutants"] < check.STRONG


def test_no_shipped_case_is_broken(capsys):
    """`factory bench check` — the shipped suite by default — reads every shipped case as ok or
    weak: none is broken, so the check exits 0."""
    code = main(["bench", "check"])
    out, err = capsys.readouterr()
    assert code == 0, err
    for case_id in SHIPPED:
        verdict, _, total = _mutant_line(out, case_id)
        assert verdict in ("ok", "weak"), f"{case_id}: {out}"
        assert 0 < total <= 20, f"{case_id}: {out}"
    assert "broken" not in out