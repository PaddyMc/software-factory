import re

from factory import prbody
from factory.contracts import Task


def test_clean_report_drops_the_preamble():
    report = "All evidence collected. I checked the diff.\n\n## Summary\nThe change is sound.\n"
    assert prbody.clean_report(report) == "## Summary\nThe change is sound."
    assert prbody.clean_report("  A report with no heading.  \n") == "A report with no heading."
    assert prbody.clean_report("#!/usr/bin/env python\nprint('hello')\n") == "#!/usr/bin/env python\nprint('hello')"


def test_clean_report_keeps_the_last_draft():
    report = (
        "I will review this now.\n"
        "## Acceptance criteria\nFirst draft.\n"
        "Actually, let me reconsider the evidence.\n"
        "## Acceptance criteria\nSecond draft.\n"
        "Actually, one more check is needed.\n"
        "## Acceptance criteria\nLast draft.\nVERDICT: APPROVE\n"
    )
    cleaned = prbody.clean_report(report, "## Acceptance criteria")
    assert cleaned == "## Acceptance criteria\nLast draft.\nVERDICT: APPROVE"
    assert "First draft" not in cleaned and "Second draft" not in cleaned

    one_draft = "Preamble.\n## Summary\nKeep this too.\n## Acceptance criteria\nOnly draft."
    assert prbody.clean_report(one_draft, "## Acceptance criteria") == (
        "## Summary\nKeep this too.\n## Acceptance criteria\nOnly draft."
    )


def test_cap_cuts_at_a_line_closes_a_fence_and_points_to_the_rest():
    report = "## Report\n```python\n" + "".join(f"value_{i} = {i}\n" for i in range(20)) + "```\nDone.\n"
    result = prbody.cap(report, 120, "POINTER")
    note = result.splitlines()[-1]
    match = re.fullmatch(r"… kept (\d+) of (\d+) characters: POINTER", note)
    assert match
    kept, total = map(int, match.groups())
    assert total == len(report)
    assert result[:kept] == report[:kept]
    assert report[kept] == "\n"                         # the cut is at a whole-line boundary
    assert result.endswith("\n```\n\n" + note)         # the opening fence was closed before the note
    assert sum(line.startswith("```") for line in result.splitlines()) % 2 == 0
    assert len(result) <= 120

    short = "  short enough\n"
    assert prbody.cap(short, len(short), "POINTER") is short


def test_cap_never_exceeds_the_limit():
    assert prbody.BODY_LIMIT == 60_000
    assert prbody.BLOCK_LIMIT == 12_000
    inputs = [
        "x" * 5_000,
        "".join(f"line {i}: {'y' * 30}\n" for i in range(200)),
        "## Report\n```text\n" + "filler\n" * 500,
        "short text",
        "",
    ]
    for text in inputs:
        for limit in (0, 1, 2, 10, 40, 80, 160, 1_000, 2_000, prbody.BLOCK_LIMIT):
            result = prbody.cap(text, limit, "factory show demo-t01 --step review")
            assert len(result) <= limit, (len(text), limit, len(result))
            if len(text) <= limit:
                assert result == text


def test_shorten_cuts_at_a_word():
    assert prbody.shorten("a title that fits", 72) == "a title that fits"
    assert prbody.shorten("one two three four", 14) == "one two three…"
    assert prbody.shorten("abcdefghij", 6) == "abcde…"
    assert prbody.shorten("one two three four\na second line", 14) == "one two three…"
    assert prbody.shorten("", 10) == ""
    for limit in range(30):
        assert len(prbody.shorten("one two three four", limit)) <= limit


def test_parse_summary_reads_the_fixed_shape():
    parsed = prbody.parse_summary(
        "TITLE: Add summary parsing\n\n"
        "## What changed\n"
        "- Adds the parser in `factory/prbody.py`.\n"
        "  Its continuations stay with the bullet.\n"
        "1. Bounds the parsed bullets\n\n"
        "## What to check\n"
    )
    assert parsed == prbody.Summary(
        title="Add summary parsing",
        changed=["Adds the parser in `factory/prbody.py`. Its continuations stay with the bullet.",
                 "Bounds the parsed bullets"],
        check=[],
    )


def test_parse_summary_ignores_preamble_and_accepts_other_heading_styles():
    parsed = prbody.parse_summary(
        "I have finished checking.\n- this preamble bullet is ignored\n"
        "TITLE: Accept lenient markdown\n"
        "### wHaT ChAnGeD:\n"
        "* first bullet\n  with more detail\n"
        "1) second bullet\n"
        "**WHAT TO CHECK:**\n"
        "1. inspect the parser\n"
        "2) check the assumption\n"
        "## Unrelated notes\n- not part of the summary\n"
        "### What changed\n- the first section still wins\n"
    )
    assert parsed == prbody.Summary(
        "Accept lenient markdown",
        ["first bullet with more detail", "second bullet"],
        ["inspect the parser", "check the assumption"],
    )
    assert prbody.parse_summary("TITLE: No changes\n## What to check\n- something\n") is None
    empty_title = prbody.parse_summary("TITLE:\nTITLE: later\n## What changed\n- one\n")
    assert empty_title is not None and empty_title.title == ""


def test_a_summary_is_bounded():
    parsed = prbody.Summary(
        title="A very long title " + "word " * 30,
        changed=[f"changed {i} " + ("x" * 800 if i == 0 else "") for i in range(10)],
        check=[f"check {i}" for i in range(10)],
    )
    bounded = prbody.bound_summary(parsed, "demo-t01", "verify")
    assert len(bounded.title) <= 72 and bounded.title.endswith("…")
    assert len(bounded.changed) == 5 and len(bounded.check) == 8
    assert all(len(bullet) <= 400 for bullet in bounded.changed + bounded.check)
    assert bounded.changed[0].endswith("…")
    assert bounded.changed[-1] == "6 more bullets: factory show demo-t01 --step verify"
    assert bounded.check[-1] == "3 more bullets: factory show demo-t01 --step verify"
    assert prbody.bound_summary(prbody.Summary("", ["one"], []), "demo-t01", "verify").title == ""


def test_fallback_summary_uses_the_goal_the_diff_and_the_findings():
    task = Task(
        id="demo-t01",
        goal="Add the greeting module and " + "explain every detail " * 30,
        spec_refs=(), depends_on=(), non_goals=(), acceptance=("it works",), verification=(), risk="low",
    )
    files = [f"src/file-{i}.py" for i in range(13)]
    reviews = {
        "review": (
            "Review preamble\n## Findings\n- an old finding\n"
            "## Acceptance criteria\n- met\n"
            "## Review findings\n" + "\n".join(f"{i}. finding {i}" for i in range(1, 11)) +
            "\n## Notes\n- outside the findings\nVERDICT: APPROVE"
        ),
        "second-review": "## Findings\n* inspect the second review\nVERDICT: APPROVE",
    }
    summary = prbody.fallback_summary(task, files, reviews)
    assert summary.title == prbody.shorten(task.goal, 72)
    assert summary.changed[0] == prbody.shorten(task.goal, 400)
    assert summary.changed[1].startswith("13 files changed: ")
    assert "src/file-0.py" in summary.changed[1] and "src/file-9.py" in summary.changed[1]
    assert "src/file-10.py" not in summary.changed[1]
    assert summary.check[0] == "review: 1. finding 1"
    assert not any("old finding" in bullet or "outside the findings" in bullet for bullet in summary.check)
    assert len(summary.check) == 8 and all(len(bullet) <= 400 for bullet in summary.check)
    assert "4 more bullets" in summary.check[-1]
    assert "factory show demo-t01 --step review" in summary.check[-1]
    assert "factory show demo-t01 --step second-review" in summary.check[-1]
