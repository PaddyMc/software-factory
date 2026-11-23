## [22:37] test-step-no-tests-needed: a tester may write no tests when the commands already pass

- Why: factory-spec-t02, a spec task whose test commands name existing, passing tests, failed on strict
  without a build. Its tester rightly wrote no tests, and the test step rejected the try as "The try
  wrote no tests." (2026-11-22) after earlier tries were rejected as "the tests pass before the change".
  t01 and t04 of the same plan only got through by making core tests and conftest.py check the chapters.
- `factory/pipeline.py`: before the first try, `_passing_at_base` runs the acceptance commands at the
  base and resets the worktree. When every one selects tests and passes, a try that writes nothing is
  recorded `no tests needed`: the step passes with the tester's report and a red-check note naming the
  commands, and the build starts with no test commit and no `acceptance_untouched` lock. The gates still
  run every verification command. A command naming a test not yet written fails at the base, so a code
  task's tester can't skip its tests this way.
- `factory/agents.py`: the tester's task message gains "# These commands already pass" in that case: it
  may write no tests for a documentation or spec task and say why, and must not make an existing test or a
  shared fixture check the deliverable just to turn a command red.
- Tests: `tests/test_pipeline.py` `test_a_tester_that_writes_no_tests_passes_when_the_commands_already_pass`
  (fails on main with "The try wrote no tests.") and
  `test_a_tester_that_writes_no_tests_still_fails_when_a_command_names_a_new_test` (the guard).
- Docs: `docs/architecture.md` (the strict test step), `docs/reference.md` (a "The try wrote no tests."
  row), the factory-ops skill and its shipped template (strict-flow results).
- Commands: `uv run --offline pytest -q tests/test_pipeline.py -k "writes_no_tests or pass_before or
  selects_no_tests or strict_flow or outside_test_paths or locked"` (8 passed), `GIT_CONFIG_GLOBAL=/dev/null
  uv run --offline pytest -q` (full suite).
