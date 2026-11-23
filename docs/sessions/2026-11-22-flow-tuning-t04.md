## [22:32] flow-tuning-t04: compare candidate flows with bench

- Recorded every resolved bench step's `candidates` setting, including the default of 1, and added candidate-count changes to `bench compare` alongside model, prompt, loop and prove changes. Missing values in older results retain that default.
- Derived `candidates_built` and `candidates_passed` from each candidate flow cell's build and gate run records, with zero defaults before a run produces records. `bench report --cells` now shows both counts when candidates were built. Hidden scoring continues to use the pipeline's chosen `candidate_sha` unchanged.
- Files: `factory/bench/run.py`, `factory/bench/report.py`, and this session log.
- Commands:
  - `uv run pytest -q tests/test_bench.py::test_results_record_candidates_and_compare_flags_a_change tests/test_bench.py::test_cells_count_the_candidates_built_and_passed tests/test_bench.py::test_a_candidates_cell_is_scored_on_the_chosen_candidate` — 3 passed;
  - `uv run pytest -q tests/test_bench.py tests/test_bench_cases.py` — 68 passed;
  - `uv run pytest -q tests/test_bench.py::test_parallel_cells_run_at_once_and_all_finish` — 1 passed on rerun after a timing-sensitive failure in the first full-suite run;
  - `uv run pytest -q` — 473 passed on rerun;
  - `git diff --check` — exit 0.
- Review follow-up: restored variant-attributed compare summaries while retaining the candidate step-prefixed line required by the locked acceptance test. Added regression coverage for attribution across multiple variants and for ordinary cell lines carrying no candidate text; documented the legacy cell-shape compatibility at the counters.
  - Reviewer's multi-variant compare reproduction — exit 0;
  - Targeted acceptance tests — 3 passed;
  - `uv run pytest -q tests/test_bench.py tests/test_bench_cases.py` — 69 passed;
  - `uv run pytest -q` — 474 passed.
