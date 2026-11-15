## [18:16] pr-descriptions-t02: The verifier's summary

- Added the fixed-shape verifier prompt and passed each attempt's cleaned, capped reviewer reports to the verify step under their flow step names. The default scripted verifier now answers in the same parseable shape.
- Added pure summary helpers for word-boundary shortening, lenient title/section/bullet parsing, title and bullet bounds with `factory show` pointers, and a deterministic fallback built from the contract goal, changed paths and reviewers' last Findings sections.
- Kept the parsed or fallback summary in pipeline state. Unparseable verifier output now records `report (fallback)` and logs the reason without another model call; verify-less flows build the fallback without adding a verify run.
- Replaced the PR body's Verifier report with factory-rendered What changed and What to check sections, including `Nothing flagged.` for an empty check list. Full verifier output remains in its run record and the existing final `factory show` pointer is unchanged.
- Added the five summary-helper tests, the shipped-prompt example test, and three end-to-end tests for reviewer context, parsed rendering/state and fallback behavior.
- Files: `factory/prbody.py`, `factory/prompts/verifier.md`, `factory/agents.py`, `factory/pipeline.py`, `tests/fake_model.py`, `tests/test_prbody.py`, `tests/test_templates.py`, `tests/test_pipeline.py`, and this session log.
- Commands (all final runs pass):
  - the contract's six-test `uv run pytest -q tests/test_prbody.py::... tests/test_templates.py::test_verifier_prompt_asks_for_the_fixed_shape` command — 6 passed;
  - the contract's three focused pipeline tests — 3 passed;
  - `uv run pytest -q tests/test_pipeline.py tests/test_flows.py tests/test_templates.py` — 109 passed;
  - `uv run pytest -q` — 306 passed;
  - `uv run python -m compileall -q factory/prbody.py factory/agents.py factory/pipeline.py tests/fake_model.py tests/test_prbody.py tests/test_templates.py tests/test_pipeline.py` — exit 0;
  - `git diff --check` — exit 0.
