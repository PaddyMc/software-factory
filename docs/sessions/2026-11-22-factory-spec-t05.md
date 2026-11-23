# factory-spec-t05

Date: 2026-11-22

## What changed

Authored the first edition of `docs/spec/09-spec.txt`, **Benchmarks and
scoring**, at baseline `8bd7012`. The chapter specifies:

- shipped case suite discovery, `case.yaml` inputs, deterministic repository
  materialization, the reference solution, and hidden-test visibility;
- flow/model variants and case/repeat cells, per-cell isolated factory homes,
  gate outcomes, hidden scoring, and the exact outcome vocabulary;
- solved/eligible denominators and worked gate-failure, false-pass, solved,
  stopped, skipped, and interrupted examples;
- sequential and parallel budgets, dry runs, interruption recovery, atomic
  results, and the run/report/compare/list/cases commands; and
- comparison behavior when a case fixture, resolved prompt, model, loop, or
  prove setting changes.

Each chapter section cites repository-relative implementation symbols and
named behavioral tests. Examples are marked non-normative, and source-only
implementation notes are identified separately. No fixtures, scoring code, or
locked acceptance tests were changed, and no paid benchmark was run.

## Files

- `docs/spec/09-spec.txt` — new specification chapter.
- `docs/sessions/2026-11-22-factory-spec-t05.md` — this task's session log.

## Commands run

- `test -s docs/spec/09-spec.txt` — exit 0.
- `uv run --offline pytest -q tests/test_bench_cases.py::test_hidden_and_solution_files_stay_out_of_the_starting_tree tests/test_bench.py::test_report_shows_solved_rates_per_variant_and_case tests/test_bench.py::test_compare_flags_changed_cases_models_and_prompts`
  — exit 0, 7 passed in 0.78s.
- `uv run --offline pytest -q` — exit 0, 460 passed in 130.45s.
