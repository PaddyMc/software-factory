# factory-spec-t03 — 2026-11-22

## What changed

- Added `docs/spec/05-spec.txt`, describing gate order, candidate/base selection,
  applicability and skipping, zero-test handling, and the session-log convention.
- Added `docs/spec/06-spec.txt`, describing PR creation/fallback, stacks,
  refresh/restack, review and CI precedence, ownership, leased updates, and rework.
- No production code or locked acceptance test was changed.

## Files

- `docs/spec/05-spec.txt` (new)
- `docs/spec/06-spec.txt` (new)
- `docs/sessions/2026-11-22-factory-spec-t03.md` (new)

## Commands run

- `test -s docs/spec/05-spec.txt && test -s docs/spec/06-spec.txt` — exit 0.
- `uv run --offline pytest -q tests/test_spec_chapters_05_06.py` — 24 passed.
- `uv run --offline pytest -q tests/test_verification.py::test_zero_filtered_test_is_not_pass tests/test_ci.py::test_red_only_judges_the_factorys_own_candidate tests/test_reviews.py::test_addressed_reviews_no_longer_count` — 3 passed.
- `uv run pytest -q` — 484 passed in 121.71s.
- `git diff --check` — exit 0.
