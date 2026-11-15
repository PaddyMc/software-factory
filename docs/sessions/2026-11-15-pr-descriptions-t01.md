## [17:59] pr-descriptions-t01: Clean and bound factory PR bodies

- Added pure PR-body text helpers that strip agent preambles, retain a reviewer's last repeated draft, and cap overlong text at a line with a fence closure and a `factory show` pointer.
- Removed the planner's hand-off from the PR body. Reviewer and verifier reports are now cleaned and capped, gate details use a PR-only 160-character table, and the complete gate table still goes to the verifier and the run record.
- Added the 60,000-character body bound: reviewer blocks shrink longest-first to 2,000-character reports, then become one-line pointers, before a final whole-body cap that preserves the closing `factory show` line.
- Added unit coverage for report cleaning, capping and gate widths, plus end-to-end coverage for a 100,000-character three-draft review, plan omission, and each body-shrinking fallback. Run records retain the full reports.
- Files: `factory/prbody.py` (new), `factory/pipeline.py`, `factory/gates.py`, `tests/test_prbody.py` (new), `tests/test_pipeline.py`, `tests/test_gates.py`, and this session log.
- Commands (all final runs pass):
  - the contract's five-test `uv run pytest -q tests/test_prbody.py::... tests/test_gates.py::test_table_can_shorten_long_details` command — 5 passed;
  - `uv run pytest -q tests/test_pipeline.py::test_a_huge_review_still_opens_a_pr_that_fits tests/test_pipeline.py::test_the_pr_body_leaves_out_the_plan` — 2 passed;
  - `uv run pytest -q tests/test_pipeline.py tests/test_gates.py` — 70 passed;
  - the two added shrink-ladder pipeline tests — 2 passed;
  - `uv run pytest -q` — 297 passed;
  - `uv run python -m compileall -q factory/prbody.py factory/pipeline.py factory/gates.py tests/test_prbody.py tests/test_pipeline.py tests/test_gates.py` — exit 0;
  - `git diff --check` — exit 0.
