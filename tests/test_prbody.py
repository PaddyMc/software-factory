import re

from factory import prbody


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
