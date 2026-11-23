# factory-spec-t02 — 2026-11-23

## What changed

- Added chapter 03 for the `8bd7012` flow contract: built-in and configured
  flows, step/model/limit overrides, gate insertion, role outputs, verdict
  parsing, attempt routing, no-progress stopping, and a rejected-attempt trace.
- Added chapter 04 for the same edition: actor/resource authority, direct file
  tool scope, default bubblewrap isolation, provider and GitHub credentials,
  cache and dependency-source boundaries, and network/no-sandbox overrides.
- Kept later flow options out of the specification and made no runtime or
  security changes.
- Validated every cited source symbol and test node against the edition; test
  node IDs also resolve in the checkout.

## Files

- `docs/spec/03-spec.txt` (new)
- `docs/spec/04-spec.txt` (new)
- `docs/sessions/2026-11-23-factory-spec-t02.md` (new)

## Commands run

- `test -s docs/spec/03-spec.txt && test -s docs/spec/04-spec.txt` — exit 0.
- `uv run --offline pytest -q tests/test_flows.py::test_gates_go_after_the_last_review_unless_placed tests/test_flows.py::test_each_kind_gets_its_tools tests/test_tools.py::test_writes_go_anywhere_in_the_worktree_but_git tests/test_tools.py::test_reads_reach_dependency_sources_only` — exit 0; 4 passed.
- `uv run --offline pytest -q` — exit 0; 462 passed.
- Source/test citation audit against `8bd7012` — exit 0; no missing symbols or
  test node IDs (31 chapter-03 and 20 chapter-04 unique test references).
- `git diff --check -- docs/spec/03-spec.txt docs/spec/04-spec.txt` — exit 0.
