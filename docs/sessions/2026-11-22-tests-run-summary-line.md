## [21:11] tests-run-summary-line: count pytest tests from its summary line only

- Why: factory-spec-t03's red check rejected both tester tries as "selects no tests" although each
  ran three red tests. `verification.tests_run` returned 0 whenever "no tests ran" appeared anywhere
  in the output, before reading the counts. The tester had hooked a check into
  `test_zero_filtered_test_is_not_pass`, whose source holds that phrase, so pytest's traceback
  quoted it above `3 failed in 0.05s`. The counts regex had the same flaw: it summed every
  "N passed/failed" anywhere in the output.
- `factory/verification.py`: `tests_run` reads only pytest's summary lines (bare under `-q`, framed in
  `=` otherwise, with ANSI colour stripped), one per pytest run in the output. A summary of only
  deselected tests or "no tests ran" is 0, as before. Cargo and unittest parsing are unchanged.
- `tests/test_verification.py`: `test_only_pytests_summary_line_counts_the_tests` (t03's output, framed,
  coloured, two runs, all deselected) and `test_real_pytest_output_quoting_the_summary_phrases_counts_its_tests`
  (a real pytest run, `-q` and default, whose traceback quotes "no tests ran" and "9 failed"). Both fail
  on main and pass with the change.
- Commands: `uv run --offline pytest -q tests/test_verification.py` (9 passed; 2 failed with main's
  `verification.py`), `GIT_CONFIG_GLOBAL=/dev/null uv run --offline pytest -q` (full suite).
