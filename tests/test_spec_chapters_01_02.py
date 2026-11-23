"""Acceptance tests for the chapters of task factory-spec-t01.

docs/spec/01-spec.txt (project inputs and contracts) and docs/spec/02-spec.txt (board and
scheduling) document the factory shipped at 8bd7012; docs/plans/factory-spec.md#chapter-conventions
sets their form. The contract's verification command selects the four behavioral tests that anchor
the chapters, and each of them finishes by running its chapter's acceptance checks here:

    tests/test_contract_schema.py::test_parse_contract_exact_8_keys     -> chapter_01_acceptance
    tests/test_dependencies.py::test_reject_cycle_and_unknown_id       -> chapter_01_acceptance
    tests/test_db.py::test_upsert_keeps_status_and_refreshes_contract   -> chapter_02_acceptance
    tests/test_scheduler.py::test_a_failure_blocks_only_its_dependents  -> chapter_02_acceptance

The checks are red until the chapters are written; the unit gate runs them directly as well.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from factory.contracts import KEYS, ContractError, task_from_mapping, validate_tasks

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "docs" / "spec"
SESSIONS = ROOT / "docs" / "sessions"
BASELINE = "8bd7012"                                  # the first edition's baseline commit
SERIES = {f"{i:02d}" for i in range(10)}              # 00-spec.txt .. 09-spec.txt
SOURCES = {                                           # the contract's spec_refs, per chapter
    "01": ("factory/scaffold.py", "factory/config.py", "factory/contracts.py"),
    "02": ("factory/db.py", "factory/scheduler.py"),
}
NAMED_TESTS = {                                       # the tests the contract's verification names
    "01": ("tests/test_contract_schema.py::test_parse_contract_exact_8_keys",
           "tests/test_dependencies.py::test_reject_cycle_and_unknown_id"),
    "02": ("tests/test_db.py::test_upsert_keeps_status_and_refreshes_contract",
           "tests/test_scheduler.py::test_a_failure_blocks_only_its_dependents"),
}


def _chapter(number: str) -> str:
    """The chapter's UTF-8 text; the contract's `test -s docs/spec/<n>-spec.txt` as an assertion."""
    path = SPEC / f"{number}-spec.txt"
    assert path.is_file(), f"docs/spec/{number}-spec.txt does not exist"
    text = path.read_text(encoding="utf-8")
    assert text.strip(), f"docs/spec/{number}-spec.txt is empty"
    return text


def _cites(text: str, pattern: str, why: str) -> None:
    """The chapter must contain `pattern`; `why` names the acceptance criterion that needs it."""
    assert re.search(pattern, text, re.I), f"{why}: not found ({pattern})"


def _prose(text: str) -> str:
    """The chapter without its fenced blocks: an example carries sample commands and ids, prose
    carries the citations, so existence is checked against prose only."""
    return re.sub(r"^```.*?^```", "", text, flags=re.S | re.M)


def _fenced_tasks(text: str) -> list:
    """The chapter's fenced task contracts, read with the factory's own parser. An example the
    schema rejects (a contract with a key missing, say) is skipped, not an error: the acceptance
    criteria ask for one example that validates, not for every fence to be a valid contract."""
    tasks = []
    for block in re.findall(r"^```[a-z]*\n(.*?)^```", text, re.S | re.M):
        try:
            items = yaml.safe_load(block)
        except yaml.YAMLError:
            continue
        for item in items if isinstance(items, list) else ():
            if isinstance(item, dict) and "id" in item:
                try:
                    tasks.append(task_from_mapping(item))
                except ContractError:
                    pass
    return tasks


@pytest.mark.parametrize("number", ["01", "02"])
def test_each_chapter_follows_the_conventions(number):
    """Chapter conventions: the two-digit number and title first, the baseline, a scope statement,
    numbered sections, and references only to chapters of the series."""
    text = _chapter(number)
    first = text.splitlines()[0]
    assert re.match(rf"^{number}\b", first) and first[2:].strip(), \
        "the chapter starts with its two-digit number and title"
    assert BASELINE in text, "the chapter states the first edition's baseline (8bd7012)"
    _cites(text, r"\bscope\b", "the chapter carries a scope statement")
    for section in ("1", "2"):
        assert re.search(rf"(?m)^\s*{section}[.:)\s]", text), f"the chapter has numbered section {section}"
    outside = sorted(set(re.findall(r"\b(\d{2})-spec\.txt\b", text)) - SERIES)
    assert not outside, f"the chapter references chapters outside the series: {outside}"


def test_01_documents_project_inputs_and_contracts():
    """Acceptance: init and repeat init, precedence of project settings and state location, plan
    discovery, the eight contract keys and their validation, cross-plan IDs, cycles, and
    manual-only verification."""
    text = _chapter("01")
    _cites(text, r"factory init", "01 explains `factory init`")
    _cites(text, r"--force", "01 explains repeat init: files are kept unless --force rewrites them")
    _cites(text, r"\.factory/config\.yaml", "01 names the project settings file")
    _cites(text, r"FACTORY_HOME", "01 explains the state-location override")
    _cites(text, r"~/\.local/share/factory", "01 names the default state directory")
    _cites(text, r"precedence|\bwins?\b|overrid", "01 says which setting or location wins")
    _cites(text, r"docs/plans", "01 explains plan discovery under docs/plans")
    _cites(text, r"\bexclude\b", "01 explains that exclude globs are never read as backlog")
    for key in KEYS:
        _cites(text, rf"\b{key}\b", f"01 documents the contract key {key}")
    _cites(text, r"validate-plan", "01 explains validation through `factory validate-plan`")
    _cites(text, r"exactly", "01 states contracts carry exactly the eight keys")
    _cites(text, r"cross-plan|other plans|across plans", "01 explains cross-plan ids")
    _cites(text, r"cycle", "01 explains dependency cycles")
    _cites(text, r"manual|by hand", "01 explains manual-only verification")


def test_01_includes_a_valid_contract_and_a_rejected_dependency_example():
    """Acceptance: a valid contract example (the factory's own parser accepts it and validation is
    clean) and a rejected dependency example in the factory's own words."""
    text = _chapter("01")
    tasks = _fenced_tasks(text)
    assert tasks, "01 fences no task contract that the factory's parser accepts"
    errs = validate_tasks(tasks)
    valid = [t.id for t in tasks if not any(t.id in e for e in errs)]
    assert valid, f"01 has no example contract that validates cleanly (errors: {errs})"
    _cites(text, r"unknown dependency|dependency cycle",
           "01 shows a rejected dependency example with the factory's own error")


def test_02_distinguishes_stored_states_from_derived_readiness_and_liveness():
    """Acceptance: the board's stored statuses told apart from the readiness and liveness it derives
    (never stores) for observers."""
    text = _chapter("02")
    _cites(text, r"\bstored\b", "02 says what the board stores")
    _cites(text, r"derived|computed|inferred", "02 says readiness and liveness are derived, not stored")
    for status in ("queued", "pr_open", "merged", "failed", "abandoned"):
        _cites(text, rf"\b{status}\b", f"02 names the stored status {status}")
    _cites(text, r"readiness", "02 explains derived readiness")
    _cites(text, r"\bready\b", "02 shows a ready task's board outcome")
    _cites(text, r"liveness", "02 explains derived liveness")
    _cites(text, r"heartbeat|\bpid\b", "02 says what liveness is derived from")


def test_02_maps_plan_and_board_operations_to_board_outcomes():
    """Acceptance: sync, eligible dependencies, open PR stacking, parallel limits, holds, failures
    and reruns, each mapped to its board outcome."""
    text = _chapter("02")
    _cites(text, r"\bsync", "02 maps sync to its board outcome")
    _cites(text, r"eligible", "02 maps eligible dependencies to their outcome")
    _cites(text, r"stack", "02 maps open PR stacking to its outcome")
    _cites(text, r"parallel", "02 maps parallel limits to their outcome")
    _cites(text, r"\bhold", "02 maps holds to their outcome")
    _cites(text, r"fail", "02 maps failures to their outcome")
    _cites(text, r"re-?run", "02 maps reruns to their outcome")
    _cites(text, r"conflict", "02 says a rerun takes up tasks whose PR conflicts")
    _cites(text, r"ci_failed", "02 says a rerun takes up tasks whose PR fails CI")


def test_02_traces_a_failed_prerequisite_alongside_an_independent_task():
    """Acceptance: a failed prerequisite traced alongside an independent task that still runs."""
    text = _chapter("02")
    _cites(text, r"waits for", "02 shows the blocked dependent's readiness (waits for <dep> (failed))")
    _cites(text, r"independent", "02 traces an independent task alongside the failed prerequisite")


@pytest.mark.parametrize("number", ["01", "02"])
def test_each_chapter_cites_its_source_and_the_named_behavioral_tests(number):
    """Acceptance: each chapter cites its source files and the named behavioral tests its contract
    verifies with."""
    text = _chapter(number)
    for path in SOURCES[number]:
        assert path in text, f"{number}-spec.txt must cite its source {path}"
    for node in NAMED_TESTS[number]:
        assert node in text, f"{number}-spec.txt must cite the behavioral test {node}"


@pytest.mark.parametrize("number", ["01", "02"])
def test_cited_source_and_test_paths_exist(number):
    """A cited python path is repository-relative and exists (later chapters of the series excepted)."""
    for path in sorted(set(re.findall(r"(?:factory|tests)/[\w./-]+\.py\b", _prose(_chapter(number))))):
        assert (ROOT / path).is_file(), f"{number}-spec.txt cites {path}, which does not exist"


@pytest.mark.parametrize("number", ["01", "02"])
def test_cited_pytest_node_ids_exist(number):
    """A cited pytest node id names a test that exists in this repository."""
    for node in sorted(set(re.findall(r"tests/[\w./-]+\.py::\w+", _prose(_chapter(number))))):
        path, name = node.split("::")
        assert (ROOT / path).is_file(), f"{number}-spec.txt cites {node}, whose file does not exist"
        assert re.search(rf"def {name}\(", (ROOT / path).read_text()), f"{node} is not a test here"


def test_the_task_wrote_one_dated_session_entry():
    """Acceptance: a single session entry, docs/sessions/<execution date>-factory-spec-t01.md."""
    entries = sorted(p.name for p in SESSIONS.glob("*-factory-spec-t01.md"))
    assert entries, "no docs/sessions/<date>-factory-spec-t01.md entry"
    assert len(entries) == 1, f"a single session entry per task; found {entries}"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}-factory-spec-t01\.md", entries[0]), \
        f"the entry is dated like YYYY-MM-DD-factory-spec-t01.md: {entries[0]}"
    assert (SESSIONS / entries[0]).read_text(encoding="utf-8").strip(), "the session entry is empty"


def chapter_01_acceptance() -> None:
    """Everything factory-spec-t01 requires of docs/spec/01-spec.txt; the contract's verification
    command runs it through tests/test_contract_schema.py::test_parse_contract_exact_8_keys and
    tests/test_dependencies.py::test_reject_cycle_and_unknown_id."""
    test_each_chapter_follows_the_conventions("01")
    test_each_chapter_cites_its_source_and_the_named_behavioral_tests("01")
    test_01_documents_project_inputs_and_contracts()
    test_01_includes_a_valid_contract_and_a_rejected_dependency_example()
    test_cited_source_and_test_paths_exist("01")
    test_cited_pytest_node_ids_exist("01")
    test_the_task_wrote_one_dated_session_entry()


def chapter_02_acceptance() -> None:
    """Everything factory-spec-t01 requires of docs/spec/02-spec.txt; the contract's verification
    command runs it through tests/test_db.py::test_upsert_keeps_status_and_refreshes_contract and
    tests/test_scheduler.py::test_a_failure_blocks_only_its_dependents."""
    test_each_chapter_follows_the_conventions("02")
    test_each_chapter_cites_its_source_and_the_named_behavioral_tests("02")
    test_02_distinguishes_stored_states_from_derived_readiness_and_liveness()
    test_02_maps_plan_and_board_operations_to_board_outcomes()
    test_02_traces_a_failed_prerequisite_alongside_an_independent_task()
    test_cited_source_and_test_paths_exist("02")
    test_cited_pytest_node_ids_exist("02")
    test_the_task_wrote_one_dated_session_entry()
