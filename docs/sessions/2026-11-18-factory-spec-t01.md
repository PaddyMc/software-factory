# factory-spec-t01 — 2026-11-18

## What changed

- Added `docs/spec/01-spec.txt`, documenting initialization and repeat initialization, effective project settings and state-directory precedence, plan discovery, the exact eight-key contract, validation, cross-plan dependencies, cycles, and manual-only verification.
- Added `docs/spec/02-spec.txt`, distinguishing stored task statuses from derived readiness and process liveness, and tracing sync, dependency readiness, open-PR stacking, parallel scheduling, holds, failures, and reruns.
- Included a valid YAML contract, rejected unknown-dependency and cycle examples, a failed-prerequisite/independent-task trace, and source and behavioral-test citations in both chapters.
- This task commit changes no runtime code, tests, schemas, or plan documents. The acceptance tests were supplied by the task's locked test step before this builder attempt and were not edited or removed.

## Files changed by this task commit

- `docs/spec/01-spec.txt` (new)
- `docs/spec/02-spec.txt` (new)
- `docs/sessions/2026-11-18-factory-spec-t01.md` (new)

## Locked acceptance-test inputs (pre-existing and unchanged)

- `tests/test_contract_schema.py`
- `tests/test_db.py`
- `tests/test_dependencies.py`
- `tests/test_scheduler.py`
- `tests/test_spec_chapters_01_02.py`

The task contract locks every line written by the test step. These files are listed here for transparency; they are not files changed by this task commit. The review cleanup also removed a duplicated sentence fragment from the end of `01-spec.txt`.

## Commands run

- `mkdir -p docs/spec` — exit 0.
- `test -s docs/spec/01-spec.txt && test -s docs/spec/02-spec.txt` — exit 0 on the initial and final runs.
- `uv run --offline pytest -q tests/test_spec_chapters_01_02.py` — initial exit 1 reported two invalid documentation citations and the not-yet-created session entry; after correcting only those items, the rerun exited 0 with 14 passed. The final source-accuracy rerun also exited 0 with 14 passed.
- `uv run --offline pytest -q tests/test_contract_schema.py::test_parse_contract_exact_8_keys tests/test_dependencies.py::test_reject_cycle_and_unknown_id tests/test_db.py::test_upsert_keeps_status_and_refreshes_contract tests/test_scheduler.py::test_a_failure_blocks_only_its_dependents` — initial exit 1 only through the shared chapter checks described above; subsequent and final runs exited 0 with 4 passed.
- `git diff --check && git status --short` — exit 0; status showed only this task's three new files.
- `uv run --offline pytest -q` — first full run exited 0 with 468 passed. After the final prose-accuracy edits, one rerun exited 1 with 467 passed and a timing-sensitive bench concurrency assertion failure; the final rerun exited 0 with 468 passed.
- `uv run --offline pytest -q tests/test_bench.py::test_parallel_cells_run_at_once_and_all_finish` — exit 0 with 1 passed, confirming the transient bench failure did not reproduce in isolation.
- Review-fix verification: `test -s docs/spec/01-spec.txt && test -s docs/spec/02-spec.txt && uv run --offline pytest -q tests/test_contract_schema.py::test_parse_contract_exact_8_keys tests/test_dependencies.py::test_reject_cycle_and_unknown_id tests/test_db.py::test_upsert_keeps_status_and_refreshes_contract tests/test_scheduler.py::test_a_failure_blocks_only_its_dependents` — exit 0 with 4 passed.
- Review-fix `uv run --offline pytest -q tests/test_spec_chapters_01_02.py` — exit 0 with 14 passed.
- Review-fix `uv run --offline pytest -q` — exit 0 with 468 passed.
- Review-fix `git diff --check` and a diff of the five locked test files against the test-step base — exit 0; the locked-test diff was empty.

No test files were modified to resolve any failure.
