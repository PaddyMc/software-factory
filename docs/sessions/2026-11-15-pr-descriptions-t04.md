## [18:52] pr-descriptions-t04: Readable PR titles and commit messages

- Added shared PR-title and commit-message helpers. New PRs use the verifier's summary title, falling back to the contract goal through `prbody.shorten` when the title is empty; existing PRs continue to have only their bodies edited.
- Commit subjects now use `factory(ID): GOAL`, word-cut to fit 72 characters. Build, CI-rework, review-rework, and conflict-resolution commits put their attempt or replay reason in the body after a blank line.
- Replaced the rework subject suffixes with commit-body wording and added the three contracted tests. The existing CI and review-rework tests now read the attempt from `git log --format=%B`.
- Files: `factory/pipeline.py`, `tests/test_pipeline.py`, and this session log.
- Commands (all final runs pass):
  - the contract's focused five-test `uv run pytest -q tests/test_pipeline.py::test_a_new_pr_is_titled_with_the_verifiers_title ... tests/test_pipeline.py::test_requested_changes_are_addressed_on_the_pr_branch_then_reviewed_and_gated` command — 5 passed;
  - `uv run pytest -q tests/test_pipeline.py tests/test_prbody.py` — 78 passed;
  - `uv run pytest -q` — 314 passed;
  - `uv run python -m compileall -q factory/pipeline.py tests/test_pipeline.py` — exit 0;
  - `git diff --check` — exit 0.
