## [21:15] flow-tuning-t03: select among passing candidates

- Added the shipped, replaceable `select` role and selector prompt, including model/step-limit configuration, candidate-flow model preflight, reserved step names, and the run-record role.
- Added a read-only selector run whenever multiple first-attempt candidates pass. Its contract message contains every passing candidate's capped diffstat and diff plus its gate table, in task-id-seeded order. The last valid `CHOICE:` line selects a passing candidate; a missing or invalid choice records `fallback` and keeps the smallest passing diff. One passing candidate skips the selector.
- Carried the candidate count, passing count and selection method into the PR's Checks paragraph. Preserved the existing no-passing-candidate and later-attempt behavior.
- Kept the fake model's caller-owned script/recording dictionary shared across model instances so the locked selector spy can inspect its message, tools and tool results. No locked test line was changed or removed.
- Files: `factory/agents.py`, `factory/config.py`, `factory/db.py`, `factory/flows.py`, `factory/pipeline.py`, new `factory/prompts/selector.md`, `tests/fake_model.py`, and this session log.
- Commands:
  - `uv run pytest -q tests/test_candidates.py::test_the_selector_picks_among_passing_candidates tests/test_candidates.py::test_a_selector_without_a_valid_choice_falls_back_to_the_smallest_diff tests/test_candidates.py::test_one_passing_candidate_needs_no_selector tests/test_candidates.py::test_the_selector_sees_candidates_in_a_seeded_order tests/test_candidates.py::test_the_pr_says_how_its_change_was_chosen` — 5 passed;
  - `uv run pytest -q tests/test_templates.py::test_role_prompts_ship_with_the_factory tests/test_templates.py::test_selector_prompt_matches_choice_parser` — 7 passed;
  - `uv run pytest -q tests/test_candidates.py tests/test_pipeline.py tests/test_templates.py` — 127 passed;
  - `uv run pytest -q` — 470 passed;
  - `uv run python` invoking `factory.cli.main(["prompt", "select"])` — exit 0, shipped selector prompt printed;
  - `git diff --check` — exit 0.
