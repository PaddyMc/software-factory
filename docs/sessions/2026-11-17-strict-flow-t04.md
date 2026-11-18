## [18:45] strict-flow-t04: acceptance-test flow step

- Added the optional `test` flow kind between an optional plan and the contiguous build steps, including step validation, the reserved `tester` name, and the `test` model/step-limit role. Added `test_paths` glob configuration without changing the default flow.
- Shipped the generic tester prompt and override support. Tester agents receive the normal read tools, sandboxed `run`, and write/edit tools restricted by the same glob matcher used by the pipeline. Their task message includes the task, allowed globs, recognized verification test commands, and retry feedback.
- Added the fresh-build pipeline node with two independent tries, per-try `test` run records, scope/no-change validation, clean worktree resets, and the `factory(ID): acceptance tests` commit. Build no-change routing now recognizes both the original base and the acceptance-test commit; conflict resolutions and reworks bypass the node.
- Added the pre-run `test_paths` refusal and the cleaned, capped, demoted `Acceptance tests (NAME)` PR-body block with size-fitting fallbacks. The flow footer already includes configured steps.
- Added the four tester unit tests, four end-to-end pipeline tests, and the scripted `TESTER` role without changing the other fake-role scripts.
- Files: `factory/flows.py`, `factory/config.py`, `factory/agents.py`, `factory/tools.py`, `factory/pipeline.py`, `factory/db.py`, `factory/cli.py`, `factory/prompts/tester.md`, `tests/fake_model.py`, `tests/test_tester.py`, `tests/test_pipeline.py`, and this session log.
- Commands:
  - `uv run pytest -q tests/test_tester.py::test_a_test_step_goes_between_plan_and_build tests/test_tester.py::test_test_paths_and_the_test_role_are_configurable tests/test_tester.py::test_the_tester_writes_only_under_test_paths tests/test_tester.py::test_the_tester_prompt_ships_and_can_be_overridden` — 4 passed;
  - `uv run pytest -q tests/test_pipeline.py::test_a_test_step_commits_the_tests_before_the_first_build tests/test_pipeline.py::test_a_test_step_that_writes_outside_test_paths_is_retried_then_fails_the_task tests/test_pipeline.py::test_a_flow_with_a_test_step_needs_test_paths tests/test_pipeline.py::test_reworks_skip_the_test_step` — 4 passed;
  - `uv run pytest -q tests/test_pipeline.py tests/test_flows.py tests/test_templates.py tests/test_db.py` — 130 passed;
  - `uv run pytest -q` — 425 passed;
  - `uv run python -m compileall -q factory/flows.py factory/config.py factory/agents.py factory/tools.py factory/pipeline.py factory/db.py factory/cli.py tests/test_tester.py tests/test_pipeline.py tests/fake_model.py` — exit 0;
  - `git diff --check` — exit 0.
