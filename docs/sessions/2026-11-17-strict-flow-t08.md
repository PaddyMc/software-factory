## [20:57] strict-flow-t08: bench the strict flow

- Added `test_paths: ["tests/**"]` to all five shipped bench cases and the test-only adder case, covering each contract's visible verification test.
- Made `factory bench run` reject a test-bearing flow before dry-run or cell execution when a selected case has no `test_paths`, with an error naming the case and flow.
- Recorded every resolved agent step's `loop` and `prove` settings in `results.json`; compare now reports changes to either setting alongside model and prompt changes, while treating fields absent from older results as their defaults.
- Added shipped-case coverage proving solution tests are red at a standalone acceptance-test commit and the full solution passes every gate, including `acceptance_untouched`. Added bench coverage for the refusal, result comparison, and a solved scripted strict cell with a test run and proving review.
- Files: `factory/bench/run.py`, `factory/bench/report.py`, the five `factory/bench/fixtures/*/case.yaml` files, `tests/bench_cases/adder/case.yaml`, `tests/test_bench_cases.py`, `tests/test_bench.py`, and this session log.
- Commands:
  - `uv run pytest -q tests/test_bench_cases.py::test_every_shipped_case_works_under_a_test_step tests/test_bench.py::test_a_flow_with_a_test_step_needs_the_cases_test_paths tests/test_bench.py::test_results_record_loop_and_prove_and_compare_flags_a_change tests/test_bench.py::test_a_strict_cell_is_scored_like_any_other` — 8 passed;
  - `uv run pytest -q tests/test_bench_cases.py tests/test_bench.py` — 65 passed;
  - `uv run pytest -q` — 454 passed;
  - `git diff --check` — exit 0.
