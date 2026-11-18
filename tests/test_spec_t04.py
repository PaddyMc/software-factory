"""Acceptance tests for factory-spec-t04: docs/spec/07-spec.txt and 08-spec.txt.

The contract ships two chapters of the numbered factory specification:

- 07 maps every shipped top-level `factory` command to its observable effect or
  the chapter that owns it, and covers task and plan targets, stop, clean,
  hold/requeue, read-only status versus refresh, version output, and how the
  local web page's reads, action eligibility, request checks, run forms and
  background jobs relate to those commands.
- 08 distinguishes logs, traces, transcripts, task/run records and stats, and
  covers missing optional fields in older records, model-provided reasoning,
  token and cost accounting, prompt versions, merge outcomes, the time and plan
  filters, metric denominators, and a first-attempt pass-rate example that
  agrees with the stats tests.

Both chapters must follow docs/plans/factory-spec.md#chapter-conventions — UTF-8
plain text opening with its two-digit number and title, the first edition's
baseline 8bd7012, a scope statement and numbered sections, stable chapter
references, and citations of repository-relative source (with symbol names) and
the named behavioral tests — and the task must add its session entry at
docs/sessions/YYYY-MM-DD-factory-spec-t04.md.

These tests hold the chapters to those criteria mechanically; the truth of the
prose against the cited code is the reviewer's check. tests/conftest.py keeps
the contract's acceptance command red until both files exist and are non-empty.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "docs" / "spec"
SESSIONS = ROOT / "docs" / "sessions"
TASK = "factory-spec-t04"
BASELINE = "8bd7012"                      # first-edition baseline (docs/plans/factory-spec.md)

# The contract's spec_refs: the source the two chapters are written from.
SPEC_SOURCES = (
    "factory/cli.py",
    "factory/version.py",
    "factory/web/server.py",
    "factory/web/jobs.py",
    "factory/web/views.py",
    "factory/observe.py",
    "factory/log.py",
    "factory/prices.py",
    "factory/stats.py",
)

# The named behavioral tests the contract's verification command runs.
WEB_TEST = "tests/test_web.py::test_each_action_runs_its_factory_command_as_a_job"
TRANSCRIPT_TEST = "tests/test_observe.py::test_transcripts_without_thoughts_print_as_before"
STATS_TEST = "tests/test_stats.py::test_first_attempt_pass_rate_and_attempts_per_pr"


def _chapter(number: str) -> str:
    """The chapter's text, as UTF-8 plain text, or a named failure."""
    path = SPEC / f"{number}-spec.txt"
    if not path.is_file():
        pytest.fail(f"docs/spec/{number}-spec.txt has not been written", pytrace=False)
    return path.read_text(encoding="utf-8")


def _mentions(text: str, needle: str) -> bool:
    """The needle appears as its own word (a trailing plural is allowed)."""
    return re.search(rf"(?<![\w-]){re.escape(needle)}s?(?![\w-])", text) is not None


def _absent(text: str, checks: dict[str, str]) -> list[str]:
    """The reasons of every check whose pattern the text does not match."""
    return [why for pattern, why in checks.items() if not re.search(pattern, text, re.IGNORECASE)]


def _top_level_commands() -> list[str]:
    """Every top-level `factory` command shipped in factory/cli.py:main."""
    source = (ROOT / "factory/cli.py").read_text(encoding="utf-8")
    commands = sorted(set(re.findall(r"\bsub\.add_parser\(\"([^\"]+)\"", source)))
    assert commands, "could not derive the top-level commands from factory/cli.py:main"
    return commands


# ------------------------------------------------------------- the two files

def test_both_chapters_exist_as_non_empty_utf8_text():
    """The contract's own first verification command: `test -s` on both files."""
    for number in ("07", "08"):
        path = SPEC / f"{number}-spec.txt"
        assert path.is_file(), f"docs/spec/{number}-spec.txt has not been written"
        assert path.stat().st_size > 0, f"docs/spec/{number}-spec.txt is empty"
        path.read_text(encoding="utf-8")     # Chapter conventions: UTF-8 plain text


# ------------------------------------------------------- chapter conventions

@pytest.mark.parametrize("number", ["07", "08"])
def test_chapter_opens_with_its_number_title_and_baseline(number):
    text = _chapter(number)
    lines = text.splitlines()
    assert lines, f"{number}-spec.txt is empty"
    first = lines[0]
    assert re.match(rf"^{number}\b", first), (
        f"{number}-spec.txt must open with its two-digit number and title, not {first!r}")
    title = re.sub(rf"^{number}[\s.:\-–—]*", "", first).strip()
    assert re.search(r"[A-Za-z]", title), f"{number}-spec.txt must name its title on its first line"
    assert BASELINE in text, f"{number}-spec.txt must state the first edition's baseline {BASELINE}"


@pytest.mark.parametrize("number", ["07", "08"])
def test_chapter_states_its_scope_and_uses_numbered_sections(number):
    text = _chapter(number)
    assert re.search(r"\bscope\b", text, re.IGNORECASE), f"{number}-spec.txt must state its scope"
    numbered = set(re.findall(r"(?m)^\s*(\d+)[.):]?\s+\S", text))
    numbered |= {m for m in re.findall(r"(?i)\bsections?\s+(\d+)", text)}
    assert len(numbered) >= 2, f"{number}-spec.txt must be organized into numbered sections"


@pytest.mark.parametrize("number", ["07", "08"])
def test_chapter_cites_source_with_a_symbol_or_line(number):
    assert re.search(r"factory/[\w/]+\.py:\w+", _chapter(number)), (
        f"{number}-spec.txt must cite source paths with symbol names, "
        "e.g. factory/cli.py:cmd_stop (Chapter conventions)")


def test_chapters_cite_every_contract_source():
    both = _chapter("07") + "\n" + _chapter("08")
    missing = [source for source in SPEC_SOURCES if source not in both]
    assert not missing, "the two chapters must cite the task's spec_refs sources: " + ", ".join(missing)


def test_chapters_cite_the_named_behavioral_tests():
    assert WEB_TEST in _chapter("07"), (
        "07-spec.txt must cite the named behavioral test of its web actions: " + WEB_TEST)
    text = _chapter("08")
    assert TRANSCRIPT_TEST in text, "08-spec.txt must cite the named transcript test: " + TRANSCRIPT_TEST
    assert STATS_TEST in text, "08-spec.txt must cite the named stats test: " + STATS_TEST


# ----------------------------------------------------- 07: operator interfaces

def test_07_maps_every_shipped_top_level_command():
    text = _chapter("07")
    missing = [command for command in _top_level_commands() if not _mentions(text, command)]
    assert not missing, (
        "07-spec.txt must map every shipped top-level factory command "
        "(to its observable effect or its owning chapter): " + ", ".join(missing))


def test_07_covers_the_operator_topics():
    problems = _absent(_chapter("07"), {
        r"--version": "the `factory --version` flag beside `factory version`",
        r"describ": "what version output adds from the factory's own checkout (git describe)",
        r"--refresh": "`factory status --refresh` against the read-only board",
        r"read-?only": "that `factory status` without `--refresh` only reads the board",
        r"\bhold": "the hold `factory abandon` puts a task on and `factory requeue` lifts",
        r"127\.0\.0\.1|localhost": "that `factory web` serves the local board (loopback only)",
        r"eligib": "which web actions apply to which task or plan (eligibility)",
        r"\btokens?\b": "the web request checks (the form's token)",
        r"\bforms?\b": "the run form and the command it starts",
        r"\bjobs?\b": "web commands running as background jobs",
    })
    assert not problems, "07-spec.txt does not cover: " + "; ".join(problems)


def test_07_covers_task_and_plan_targets():
    text = _chapter("07")
    assert re.search(r"(?i)\bstop\b[^\n]{0,200}\bplan\b", text) or \
           re.search(r"(?i)\bplan\b[^\n]{0,200}\bstop\b", text), (
        "07-spec.txt must map `factory stop` onto both a task and a plan target")
    assert re.search(r"(?i)\brun\b[^\n]{0,200}\bplan\b", text) or \
           re.search(r"(?i)\bplan\b[^\n]{0,200}\brun\b", text), (
        "07-spec.txt must map `factory run` onto both a task and a plan target")


def test_07_points_at_owning_chapters_by_filename():
    assert re.search(r"\b\d{2}-spec\.txt\b", _chapter("07")), (
        "07-spec.txt must point at owning chapters by the stable filenames of the series, "
        "e.g. 09-spec.txt (Chapter conventions: stable references)")


# ------------------------------------------- 08: observability and statistics

def test_08_distinguishes_the_observability_surfaces():
    problems = _absent(_chapter("08"), {
        r"\blogs?\b": "the run log (`factory logs`)",
        r"\btraces?\b": "the trace (`factory trace`)",
        r"\btranscripts?\b": "the transcript (`factory transcript`)",
        r"\brecords?\b": "the task and run records behind them",
        r"\bstats?\b|\bstatistic": "`factory stats`",
    })
    assert not problems, "08-spec.txt does not distinguish: " + "; ".join(problems)


def test_08_states_the_accounting_rules():
    problems = _absent(_chapter("08"), {
        r"older|missing|absent|unrecorded|\black\b":
            "that older records can miss optional fields",
        r"reasoning|thinking":
            "model-provided reasoning, shown when the model shares it",
        r"\btokens?\b": "token accounting",
        r"\bcost": "cost accounting",
        r"pric": "where the per-token prices come from",
        r"prompt[ _-]?versions?": "prompt versions",
    })
    assert not problems, "08-spec.txt does not state: " + "; ".join(problems)


def test_08_states_the_merge_outcomes():
    text = _chapter("08")
    assert re.search(r"\bmerge", text, re.IGNORECASE), "08-spec.txt must cover merge outcomes"
    assert "as_built" in text, "08-spec.txt must name the as_built merge outcome"
    assert re.search(r"\bedited\b", text), "08-spec.txt must name the edited merge outcome"


def test_08_states_the_time_and_plan_filters_and_denominators():
    text = _chapter("08")
    for flag in ("--since", "--until", "--plan"):
        assert flag in text, f"08-spec.txt must document the stats {flag} filter"
    assert re.search(r"denominat", text, re.IGNORECASE), (
        "08-spec.txt must state the metric denominators")


def test_08_gives_a_first_attempt_pass_rate_example():
    text = _chapter("08")
    assert re.search(r"(?i)first[- ]attempt", text), (
        "08-spec.txt must give a first-attempt pass-rate example that agrees with "
        + STATS_TEST)
    assert re.search(r"(?is)first[- ]attempt[\s\S]{0,300}?\d", text), (
        "the first-attempt pass-rate example must state its numbers (a rate over a denominator)")
    assert re.search(r"(?is)first[- ]attempt[\s\S]{0,400}?\bbuilds?\b", text) or \
           re.search(r"(?is)\bbuilds?\b[\s\S]{0,400}?first[- ]attempt", text), (
        "the example must agree with the stats tests: the denominator is the tasks with a build run")


# ---------------------------------------------------------------- session log

def test_session_entry_records_this_task():
    entries = sorted(SESSIONS.glob(f"*-{TASK}.md"))
    assert entries, f"the task must add docs/sessions/YYYY-MM-DD-{TASK}.md, dated when executed"
    for entry in entries:
        try:
            dt.date.fromisoformat(entry.name[:10])
        except ValueError:
            pytest.fail(f"{entry.name}: the session entry must be dated YYYY-MM-DD", pytrace=False)
    logs = [entry.read_text(encoding="utf-8") for entry in entries]
    assert any("07-spec.txt" in log and "08-spec.txt" in log for log in logs), (
        f"the session entry must record the chapters this task wrote")
