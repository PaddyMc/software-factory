## [18:30] pr-descriptions-t03: The fixed PR body layout

- Rebuilt `pipeline.pr_body` in the contracted order: conditional stack/resolution/rework lines, What changed, What to check, Checks, collapsed gate/task/reviewer blocks, a rule and the metadata footer with the full-report pointer last.
- Added gate-result state with per-command test counts, per-attempt review outcomes, the Checks paragraph, fence-aware heading demotion, contract and footer rendering, and the reviewer → task → gate-table → whole-body shrink ladder.
- Kept the existing conditional wording and final pointer unchanged. Reviewer reports are capped before demotion so cap notes continue to count the original report characters; demotion only prepends heading markers.
- Added the three pure-helper tests and two end-to-end layout/stacking tests named by the contract.
- Files: `factory/prbody.py`, `factory/pipeline.py`, `tests/test_prbody.py`, `tests/test_pipeline.py`, and this session log.
- Commands (all final runs pass):
  - the contract's focused five-test `uv run pytest -q tests/test_prbody.py::test_checks_paragraph_counts_gates_tests_and_verdicts ... tests/test_pipeline.py::test_a_stacked_pr_body_starts_with_its_merge_order` command — 5 passed;
  - `uv run pytest -q tests/test_pipeline.py tests/test_prbody.py` — 75 passed;
  - `uv run pytest -q` — 311 passed;
  - `uv run python -m compileall -q factory/prbody.py factory/pipeline.py tests/test_prbody.py tests/test_pipeline.py` — exit 0;
  - `git diff --check` — exit 0.
