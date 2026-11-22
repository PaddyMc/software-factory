"""Acceptance tests for the two chapters task factory-spec-t03 ships: docs/spec/05-spec.txt
(verification gates) and docs/spec/06-spec.txt (PR lifecycle and rework).

The chapters document existing behavior, so these tests read them as data and pin the contract's
acceptance criteria with pattern checks whose messages say exactly what is missing. The contract's
verification command selects three behavioral tests of that existing behavior, and each of them
finishes by running its chapter's acceptance here, so those named tests stay red until the
chapters meet the contract:

    tests/test_verification.py::test_zero_filtered_test_is_not_pass    -> chapter_05_acceptance
    tests/test_ci.py::test_red_only_judges_the_factorys_own_candidate  -> chapter_06_acceptance
    tests/test_reviews.py::test_addressed_reviews_no_longer_count      -> chapter_06_acceptance
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import pytest

from factory.gates import ALL as GATE_ORDER     # the shipped gates, in evaluation order

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "docs/spec"
SESSIONS = ROOT / "docs/sessions"
TASK = "factory-spec-t03"
BASELINE = "8bd7012"     # the first edition's baseline (docs/plans/factory-spec.md)
SERIES = {f"{i:02d}" for i in range(10)}

# The sources each chapter must cite (all of ALL_SOURCES must appear across the two chapters).
SOURCES = {
    "05": ("factory/gates.py", "factory/verification.py", "factory/pipeline.py"),
    "06": ("factory/pipeline.py", "factory/ci.py", "factory/reviews.py", "factory/stack.py"),
}
ALL_SOURCES = ("factory/gates.py", "factory/verification.py", "factory/pipeline.py",
               "factory/prbody.py", "factory/cli.py", "factory/stack.py",
               "factory/reviews.py", "factory/ci.py", "factory/merges.py")
# The behavioral tests the contract's verification command selects, per chapter.
NAMED_TESTS = {
    "05": ("tests/test_verification.py::test_zero_filtered_test_is_not_pass",),
    "06": ("tests/test_ci.py::test_red_only_judges_the_factorys_own_candidate",
           "tests/test_reviews.py::test_addressed_reviews_no_longer_count"),
}


def _chapter(number: str) -> str:
    """The chapter's text, as UTF-8 plain text, or a named failure."""
    path = SPEC / f"{number}-spec.txt"
    if not path.is_file():
        pytest.fail(f"docs/spec/{number}-spec.txt has not been written", pytrace=False)
    return path.read_text(encoding="utf-8")


def _prose(text: str) -> str:
    """The chapter without its fenced examples (citations live in the prose)."""
    return re.sub(r"(?ms)^```.*?^```", "", text)


def _cites(text: str, pattern: str, why: str) -> None:
    """The chapter matches `pattern`; `why` states the acceptance criterion behind it."""
    assert re.search(pattern, text, re.IGNORECASE), f"{why}: not found ({pattern})"


def _near(text: str, a: str, b: str, why: str, window: int = 400) -> None:
    """`a` and `b` are written close together (either order): the chapter ties them."""
    one = re.compile(rf"(?is){a}[\s\S]{{0,{window}}}?{b}")
    two = re.compile(rf"(?is){b}[\s\S]{{0,{window}}}?{a}")
    assert one.search(text) or two.search(text), f"{why}: not written near each other ({a} … {b})"


def _names_in_order(text: str, names) -> bool:
    """Some stretch of the chapter names every gate in `names`' order, close enough together to
    read as a list. A gate may be written with `_`, `-` or a space between its words."""
    pattern = {g: g.replace("_", "[-_ ]?") for g in names}
    spots = {g: [m.start() for m in re.finditer(pattern[g], text, re.IGNORECASE)] for g in names}
    if any(not found for found in spots.values()):
        return False
    for start in spots[names[0]]:
        at, ok = start, True
        for gate in names[1:]:
            at = next((p for p in spots[gate] if p > at), None)
            if at is None or at - start > 1600:
                ok = False
                break
        if ok:
            return True
    return False


# ------------------------------------------------------------- the two files

def test_both_chapters_exist_as_non_empty_utf8_text():
    """The contract's own first verification command: `test -s` on both files."""
    for number in ("05", "06"):
        path = SPEC / f"{number}-spec.txt"
        assert path.is_file(), f"docs/spec/{number}-spec.txt has not been written"
        assert path.stat().st_size > 0, f"docs/spec/{number}-spec.txt is empty"
        path.read_text(encoding="utf-8")     # Chapter conventions: UTF-8 plain text


# ------------------------------------------------------- chapter conventions

@pytest.mark.parametrize("number", ["05", "06"])
def test_each_chapter_follows_the_conventions(number):
    """Acceptance: both chapters follow the Chapter conventions of docs/plans/factory-spec.md."""
    text = _chapter(number)
    first = text.splitlines()[0]
    assert re.match(rf"^{number}\b", first), (
        f"{number}-spec.txt must open with its two-digit number and title, not {first!r}")
    title = re.sub(rf"^{number}[\s.:\-–—]*", "", first).strip()
    assert re.search(r"[A-Za-z]", title), f"{number}-spec.txt must name its title on its first line"
    assert BASELINE in text, f"{number}-spec.txt must state the first edition's baseline {BASELINE}"
    _cites(text, r"\bscope\b", f"{number} carries a scope statement")
    for section in ("1", "2"):
        assert re.search(rf"(?m)^\s*{section}[.:)\s]", text), \
            f"{number} must be organized into numbered sections (section {section} not found)"
    outside = sorted(set(re.findall(r"\b(\d{2})-spec\.txt\b", text)) - SERIES)
    assert not outside, f"{number} references chapters outside the series: {outside}"


@pytest.mark.parametrize("number", ["05", "06"])
def test_each_chapter_cites_source_with_a_symbol_or_line(number):
    """Chapter conventions: cite repository-relative source paths with symbol names."""
    assert re.search(r"factory/[\w/]+\.py:\w+", _chapter(number)), (
        f"{number}-spec.txt must cite source paths with symbol names, "
        "e.g. factory/gates.py:run_gates (Chapter conventions)")


@pytest.mark.parametrize("number", ["05", "06"])
def test_each_chapter_cites_its_source_and_the_named_behavioral_tests(number):
    """Acceptance: both chapters cite source and the named behavioral tests of the contract."""
    text = _chapter(number)
    for path in SOURCES[number]:
        assert path in text, f"{number}-spec.txt must cite its source {path}"
    for node in NAMED_TESTS[number]:
        assert node in text, f"{number}-spec.txt must cite the behavioral test {node}"


def test_the_chapters_cite_every_contract_source():
    """Every source the task contract's spec_refs names is cited across the two chapters."""
    both = _chapter("05") + "\n" + _chapter("06")
    missing = [source for source in ALL_SOURCES if source not in both]
    assert not missing, "the two chapters must cite the task's spec_refs sources: " + ", ".join(missing)


@pytest.mark.parametrize("number", ["05", "06"])
def test_cited_source_and_test_paths_exist(number):
    """A cited python path is repository-relative and exists."""
    for path in sorted(set(re.findall(r"(?:factory|tests)/[\w./-]+\.py\b", _prose(_chapter(number))))):
        assert (ROOT / path).is_file(), f"{number}-spec.txt cites {path}, which does not exist"


@pytest.mark.parametrize("number", ["05", "06"])
def test_cited_pytest_node_ids_exist(number):
    """A cited pytest node id names a test that exists in this repository."""
    for node in sorted(set(re.findall(r"tests/[\w./-]+\.py::test_\w+", _prose(_chapter(number))))):
        path, name = node.split("::")
        assert (ROOT / path).is_file(), f"{number}-spec.txt cites {node}, whose file does not exist"
        assert re.search(rf"def {name}\(", (ROOT / path).read_text()), f"{node} is not a test here"


# ------------------------------------------------------- 05: the verification gates

def test_05_lists_the_gates_in_evaluation_order():
    """Acceptance: 05 lists gates in evaluation order, and when checks apply or can be skipped."""
    text = _chapter("05")
    assert _names_in_order(text, GATE_ORDER), (
        "05 must list the shipped gates in evaluation order, close enough together to read as a "
        "list (factory/gates.py:ALL): " + " < ".join(GATE_ORDER))
    _near(text, r"acceptance_untouched", r"test (commit|step)",
          "acceptance_untouched applies only to a candidate that carries the test step's committed "
          "tests (a test commit)")
    _cites(text, r"configur",
           "the session_log, unit_tests and e2e gates apply only when the project configures them")
    _cites(text, r"skip", "a gate can be skipped (--skip-gates); the chapter says what that means")
    _near(text, r"skip", r"pass",
          "a skipped gate counts as passing (it is not run and not failed), so the candidate can "
          "still publish")


def test_05_names_the_candidate_and_base_the_gates_judge():
    """Acceptance: the candidate and base used."""
    text = _chapter("05")
    _cites(text, r"\bcandidate\b", "05 names the candidate commit the gates judge")
    _cites(text, r"\bbase\b", "05 names the base commit the candidate is judged against")
    _cites(text, r"\borigin\b",
           "the base is the trunk tip as origin has it (or an open dependency's candidate)")
    _near(text, r"\bHEAD\b", r"candidate",
          "the clean gate checks the worktree HEAD is the candidate and the worktree is clean")
    _near(text, r"\bbase\b", r"(worktree|start)",
          "the base is where the worktree started: base..candidate is the change under judgment")


def test_05_says_how_failed_and_inconclusive_commands_affect_publication():
    """Acceptance: how failed and inconclusive commands affect publication."""
    text = _chapter("05")
    _cites(text, r"\binconclusive\b", "05 names the inconclusive outcome")
    _cites(text, r"non-?zero|exit (code|status)|exit(ed|s|ing)?\s+[1-9]",
           "a command that exits non-zero fails")
    _cites(text, r"no PR|PR (is )?open(s|ed)? only|only when every|not published|blocks? (the )?PR",
           "a failed gate blocks publication: a PR is opened only when every gate passes")
    _near(text, r"\binconclusive\b", r"(no PR|not open|blocks?|fails?|publication)",
          "an inconclusive command blocks publication exactly like a failed one "
          "(factory/gates.py:run_named only counts PASS as ok)")


def test_05_shows_a_zero_test_result():
    """Acceptance: show a zero-test result (a selection that runs no tests is never a pass)."""
    text = _chapter("05")
    _cites(text, r"no tests ran|\d+ (?:filtered out|deselected|selected)|running 0 tests|Ran 0 tests",
           "05 shows a zero-test result (pytest's `no tests ran` / `N deselected`, cargo's "
           "`N filtered out`)")
    _near(text, r"no tests ran|\d+ (?:filtered out|deselected|selected)|running 0 tests|Ran 0 tests",
          r"(inconclusive|never a pass)",
          "the zero-test result is shown as inconclusive, never a pass "
          "(tests/test_verification.py::test_zero_filtered_test_is_not_pass)")


def test_05_distinguishes_the_session_log_convention_from_what_the_gate_enforces():
    """Acceptance: distinguish the session-log naming convention from what the gate enforces."""
    text = _chapter("05")
    _cites(text, r"docs/sessions", "05 names the session-log directory the gate examines")
    _cites(text, r"YYYY-MM-DD|\d{4}-\d{2}-\d{2}|<today>|<date", "05 shows the dated filename pattern")
    _cites(text, r"\bconvention\b",
           "the dated filename docs/sessions/<today>-<task id>.md is a writing convention")
    _cites(text, r"not enforced|doesn'?t (check|enforce|require|look)|only (checks|requires|examines)"
                 r"|any (changed |new )?(file|entry|path)|whatever (file|name|path)|changed paths? under",
           "the gate enforces a changed path under the log directory, not the dated name")


# ------------------------------------- 06: the PR lifecycle and rework

def test_06_traces_pr_creation_the_verifier_fallback_and_the_no_pr_path():
    """Acceptance: 06 traces PR creation and verifier fallback, and the no-PR path."""
    text = _chapter("06")
    _cites(text, r"factory/", "the PR is pushed to the factory/<task> branch")
    _near(text, r"creat\w*", r"PR",
          "a PR is created against the base branch when none is open (gh pr create)")
    _near(text, r"(open|existing|the same) PR", r"(edit|update|reuse|keep)",
          "an already-open PR is edited (reused), never duplicated")
    _near(text, r"summary", r"(title|body)",
          "the PR's title and body are built from the verifier's summary")
    _cites(text, r"fallback", "the verifier's summary has a fallback shape")
    _cites(text, r"unpars\w+|pars(e|es|ed|ing)|can'?t read",
           "the fixed shape is parsed; an unparseable summary falls back to one built from the "
           "contract and the change")
    _near(text, r"fallback", r"summary", "the fallback summary", 400)
    _cites(text, r"--no-pr", "the no-PR path runs with --no-pr")
    _near(text, r"--no-pr", r"push",
          "--no-pr stops after the gates pass, before the push: the task stays verifying with the "
          "note `gates passed; --no-pr`")


def test_06_traces_dependency_branches_bottom_up_merging_refresh_and_restack():
    """Acceptance: 06 traces dependency branches, bottom-up merging, refresh and restack."""
    text = _chapter("06")
    _cites(text, r"stack", "dependency branches stack a task on its open dependency")
    _cites(text, r"(targets?|base[sd]?|pointed at)[\s\S]{0,300}factory/",
           "a stacked PR targets the dependency's factory/<dep> branch, so the diff shows only the "
           "task's change")
    _cites(text, r"(dependency|dep)[\s\S]{0,120}(candidate|head)",
           "the task's worktree starts at the dependency's candidate, which must merge first")
    _cites(text, r"bottom", "stacks are merged bottom-up, and the merge is the human's")
    _near(text, r"bottom", r"merg", "bottom-up merging")
    _cites(text, r"--refresh", "factory status --refresh reads every open PR after a merge")
    _cites(text, r"after (each|every) merge", "refresh runs after each merge of a stack")
    _cites(text, r"restack", "a merged or moved dependency restacks the tasks stacked on it")
    _cites(text, r"rebas", "a restack replays the task's own commits onto the new base (a rebase)")
    _cites(text, r"retarget",
           "a restacked PR is retargeted: to the trunk, or to a dependency that is still open")


def test_06_gives_the_order_of_conflict_human_review_and_ci_rework():
    """Acceptance: the order of conflict, human review and CI rework."""
    text = _chapter("06")
    _cites(text, r"\bconflict\b", "conflict rework")
    _near(text, r"conflict", r"(resolv|replay)",
          "a conflicting PR is resolved: its change is replayed onto the new base, then gates run")
    _cites(text, r"ci_failed", "CI rework enters through the ci_failed status")
    _near(text, r"CI", r"fix", "a ci_failed run fixes the CI failures on the PR's branch")
    _cites(text, r"changes_requested", "human-review rework enters through the changes_requested status")
    _near(text, r"review", r"address", "a changes_requested run addresses the review's findings")
    _cites(text, r"conflict[\s\S]{0,400}(first|before)|(first|before)[\s\S]{0,400}conflict",
           "the order: a conflicting PR is resolved before its CI or its reviews are reworked")
    _cites(text, r"restack[\s\S]{0,400}(first|before)|(first|before)[\s\S]{0,400}restack",
           "the order: a ci_failed or changes_requested run restacks first — the failure may be "
           "the dependency's move, so the new head is judged before the fix is written")
    _cites(text, r"(review|changes_requested)[\s\S]{0,300}(ci_failed|CI)[\s\S]{0,200}"
                 r"(first|before|over|wins|precedence)"
                 r"|(before|first)[\s\S]{0,200}(ci_failed|CI)[\s\S]{0,300}(review|changes_requested)"
                 r"|(review|changes_requested)[\s\S]{0,200}(first|before|over|wins|precedence)"
                 r"[\s\S]{0,300}(ci_failed|CI)",
           "the order: on one head, a review that requests changes is recorded before a failing CI "
           "(changes_requested wins over ci_failed)")


def test_06_states_review_eligibility_the_watermark_and_candidate_ownership():
    """Acceptance: review eligibility and watermark, candidate ownership."""
    text = _chapter("06")
    _cites(text, r"author", "any submitted review by the PR's author counts as a request")
    _near(text, r"write", r"admin",
          "a review from anyone else needs write or admin permission to request changes")
    _cites(text, r"latest", "only a reviewer's latest review decides")
    _cites(text, r"CHANGES_REQUESTED", "a review requests changes only in the CHANGES_REQUESTED state")
    _cites(text, r"COMMENTED", "a COMMENTED review neither requests changes nor clears one")
    _cites(text, r"watermark|reviews_addressed", "the reviews_addressed watermark")
    _near(text, r"watermark|reviews_addressed", r"(answer|address)",
          "the watermark: a PR comment answering a review makes it no longer count")
    _cites(text, r"someone else pushed|not ours|whoever pushed|moved by someone else|another push",
           "candidate ownership: CI and reviews judge the factory's own candidate only — a head "
           "someone else pushed is not ours to fix")


def test_06_states_the_leased_update_and_the_failure_outcomes():
    """Acceptance: leased update and failure outcomes."""
    text = _chapter("06")
    _cites(text, r"force-with-lease|\blease\b", "the PR's head is updated with a leased push")
    _near(text, r"lease", r"push",
          "the leased push refuses to overwrite a commit pushed since: it fails instead of "
          "destroying someone's work")
    _cites(text, r"(max|last) attempt|out of attempts|attempts? (run out|are (used up|exhausted)|exhaust)"
                 r"|gives? up",
           "a rework that runs out of attempts fails the task")
    _cites(text, r"from scratch",
           "the failed rework leaves the PR at its old head; running the task again rebuilds it "
           "from scratch")
    _cites(text, r"no[- ]change",
           "a no-change attempt is not a candidate: feedback loops back to the builder")
    _near(text, r"answer", r"(PR|comment)",
          "a review rework that needs no code change is answered on the PR as a comment")


def test_06_relates_a_restacked_head_to_the_last_gated_commit():
    """Acceptance: how a restacked head relates to the last gated commit."""
    text = _chapter("06")
    _cites(text, r"gates? (ran|run) on|last gated|never (ran|saw|gated)|hasn'?t (run|been gated)"
                  r"|not gated|without gates",
           "a restacked head carries commits the gates never saw: the gates ran on the last gated "
           "commit")
    _near(text, r"restack", r"gat",
          "the restack's PR comment names the commit the gates ran on (Candidate old → new; the "
           "gates ran on old)")
    _cites(text, r"(every|new|each) head[\s\S]{0,250}CI|CI[\s\S]{0,250}(every|new|each) head",
           "CI — not the gates — judges every new head a restack pushes")


# ---------------------------------------------------------------- session log

def test_the_task_wrote_a_dated_session_entry():
    """Acceptance: add docs/sessions/YYYY-MM-DD-factory-spec-t03.md using the execution date."""
    entries = sorted(SESSIONS.glob(f"*-{TASK}.md"))
    assert entries, f"the task must add docs/sessions/YYYY-MM-DD-{TASK}.md, dated when executed"
    for entry in entries:
        try:
            dt.date.fromisoformat(entry.name[:10])
        except ValueError:
            pytest.fail(f"{entry.name}: the session entry must be dated YYYY-MM-DD", pytrace=False)
        assert entry.read_text(encoding="utf-8").strip(), f"{entry.name} is empty"
    logs = [entry.read_text(encoding="utf-8") for entry in entries]
    assert any("05-spec.txt" in log and "06-spec.txt" in log for log in logs), (
        "the session entry must record the chapters this task wrote (05-spec.txt and 06-spec.txt)")


# ------------------------------------------------- the contract's named tests

def chapter_05_acceptance() -> None:
    """Everything factory-spec-t03 requires of docs/spec/05-spec.txt; the contract's verification
    command runs it through tests/test_verification.py::test_zero_filtered_test_is_not_pass."""
    test_both_chapters_exist_as_non_empty_utf8_text()
    test_each_chapter_follows_the_conventions("05")
    test_each_chapter_cites_source_with_a_symbol_or_line("05")
    test_each_chapter_cites_its_source_and_the_named_behavioral_tests("05")
    test_the_chapters_cite_every_contract_source()
    test_cited_source_and_test_paths_exist("05")
    test_cited_pytest_node_ids_exist("05")
    test_05_lists_the_gates_in_evaluation_order()
    test_05_names_the_candidate_and_base_the_gates_judge()
    test_05_says_how_failed_and_inconclusive_commands_affect_publication()
    test_05_shows_a_zero_test_result()
    test_05_distinguishes_the_session_log_convention_from_what_the_gate_enforces()
    test_the_task_wrote_a_dated_session_entry()


def chapter_06_acceptance() -> None:
    """Everything factory-spec-t03 requires of docs/spec/06-spec.txt; the contract's verification
    command runs it through tests/test_ci.py::test_red_only_judges_the_factorys_own_candidate and
    tests/test_reviews.py::test_addressed_reviews_no_longer_count."""
    test_both_chapters_exist_as_non_empty_utf8_text()
    test_each_chapter_follows_the_conventions("06")
    test_each_chapter_cites_source_with_a_symbol_or_line("06")
    test_each_chapter_cites_its_source_and_the_named_behavioral_tests("06")
    test_the_chapters_cite_every_contract_source()
    test_cited_source_and_test_paths_exist("06")
    test_cited_pytest_node_ids_exist("06")
    test_06_traces_pr_creation_the_verifier_fallback_and_the_no_pr_path()
    test_06_traces_dependency_branches_bottom_up_merging_refresh_and_restack()
    test_06_gives_the_order_of_conflict_human_review_and_ci_rework()
    test_06_states_review_eligibility_the_watermark_and_candidate_ownership()
    test_06_states_the_leased_update_and_the_failure_outcomes()
    test_06_relates_a_restacked_head_to_the_last_gated_commit()
    test_the_task_wrote_a_dated_session_entry()
