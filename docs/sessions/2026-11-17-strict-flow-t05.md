## [19:45] strict-flow-t05: red-checked, locked acceptance tests

- Added acceptance-command discovery from verification test commands and newly written e2e tests. Each tester try is now committed and run through those commands at the test commit: zero selected tests or no red command discards the try as `not-red`, while a committed try's report ends with its red and already-passing commands.
- Added the no-test-work skip: without a verification test command or any e2e configuration, the pipeline records one `skipped` test run with a one-line reason, commits nothing, and continues without test-step state.
- Carried the committed test files and red commands through pipeline state. Fresh builder conversations now receive the locked-files block, the add-only rule, and the instruction to report contradictory tests with `RESULT: BLOCKED`; resumed conversations keep their existing message shape.
- Added `acceptance_untouched` immediately after `plan_untouched` when a test commit is supplied. It rejects deleted acceptance files and any removed test-step line, allows appended lines, and lists the locked files and red commands on success. It remains absent for ordinary flows, direct gate runs, resolutions, and reworks.
- Added the five contracted pipeline tests, both gate tests, and an e2e red-check/PR regression test.
- Intentional t04 fixture adjustment: `_test_flow` now gives the demo task the stdlib `python3 -m unittest tests.test_greet` command. The scripted test uses `unittest.TestCase`, with an empty `tests/__init__.py` in the demo base, because stdlib unittest neither collects bare test functions nor imports the non-package demo `tests/` directory reliably. The existing t04 report assertion changed from exact equality to a prefix check plus a red-command assertion because criterion 3 appends the red-check report; no other existing test body changed.
- Files: `factory/pipeline.py`, `factory/agents.py`, `factory/gates.py`, `tests/fake_model.py`, `tests/test_pipeline.py`, `tests/test_gates.py`, and this session log.
- Commands:
  - `uv run pytest -q tests/test_pipeline.py::test_tests_that_pass_before_the_change_are_rejected tests/test_pipeline.py::test_a_verification_command_that_selects_no_tests_sends_the_tester_back tests/test_pipeline.py::test_the_builder_is_told_which_tests_are_locked tests/test_pipeline.py::test_a_builder_that_edits_a_locked_test_fails_the_gate tests/test_pipeline.py::test_a_task_without_test_commands_skips_the_test_step` — 5 passed;
  - `uv run pytest -q tests/test_gates.py::test_acceptance_untouched_allows_added_lines_only tests/test_gates.py::test_acceptance_untouched_is_absent_without_a_test_commit` — 2 passed;
  - `uv run pytest -q tests/test_pipeline.py tests/test_gates.py tests/test_tester.py` — 95 passed;
  - `uv run pytest -q tests/test_pipeline.py::test_an_e2e_test_the_test_step_wrote_is_red tests/test_pipeline.py::test_reworks_skip_the_test_step tests/test_pipeline.py::test_a_test_step_commits_the_tests_before_the_first_build` — 3 passed;
  - `uv run pytest -q` — 433 passed;
  - `uv run python -m compileall -q factory/pipeline.py factory/agents.py factory/gates.py tests/fake_model.py tests/test_pipeline.py tests/test_gates.py` — exit 0;
  - `git diff --check` — exit 0.
