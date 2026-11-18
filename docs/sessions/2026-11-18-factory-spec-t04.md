# factory-spec-t04 — 2026-11-18

## What changed

- Added `docs/spec/07-spec.txt`, mapping every top-level CLI command and specifying run targets, status refresh, stop/clean/hold/requeue, version output, and the local web interface's reads, eligibility, request checks, forms and background jobs.
- Added `docs/spec/08-spec.txt`, distinguishing logs, traces, transcripts, task/run records and statistics; documented older optional fields, reasoning, usage/cost accounting, prompt versions, merge outcomes, filters, metric denominators and the first-attempt example.
- Documentation only; no commands, web endpoints or serialization formats were added or changed.

## Files

- `docs/spec/07-spec.txt`
- `docs/spec/08-spec.txt`
- `docs/sessions/2026-11-18-factory-spec-t04.md`

## Commands run

- `test -s docs/spec/07-spec.txt && test -s docs/spec/08-spec.txt`
- `uv run --offline pytest -q tests/test_spec_t04.py`
- `uv run --offline pytest -q tests/test_web.py::test_each_action_runs_its_factory_command_as_a_job tests/test_observe.py::test_transcripts_without_thoughts_print_as_before tests/test_stats.py::test_first_attempt_pass_rate_and_attempts_per_pr`
- `uv run --offline pytest -q`

Results: all commands exited 0. The spec acceptance suite passed 19 tests, the three contract-selected behavioral tests passed, and the full suite passed 473 tests. `git diff --check` and AST checks that every cited behavioral test function and source symbol exists also exited 0.

## Review follow-up

- Corrected the `show`/`top` command map entries, run-record cardinality, log-follow termination, trace timing intervals, and the distinction between transcript run totals and trace headings after checking the exact shipped source.
- Re-ran the spec suite (19 passed), the three contract-selected behavioral tests (3 passed), all citation checks, `git diff --check`, and the full suite (473 passed); every command exited 0.
