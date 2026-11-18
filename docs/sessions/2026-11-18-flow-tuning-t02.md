## [20:10] flow-tuning-t02: build candidates on a flow's build step

- Added the `candidates: 2..5` build-step option, including kind/range validation and the rule that one build step must be directly followed by the gates. Effective flow output now includes the setting.
- Added the migrated nullable `runs.candidate` column and candidate-aware run, progress, stage and `factory show` labels, including the chosen-candidate marker.
- Made a fresh first attempt build candidates sequentially from the same start commit. Candidate 1 uses the task worktree; the others use detached `TASK.cK` worktrees and matching sandboxes. Every candidate is committed and gated before the factory selects the smallest passing diff, or carries the candidate with the fewest failing gates into a single-build next attempt with its gate feedback and resumable conversation.
- Kept later attempts, conflict resolutions and CI/human-review reworks on one build. Candidate worktrees are removed after selection, failure, error or stop, by `factory clean`, and before a stale worktree is reused. All candidate costs count toward `--max-cost`.
- Files: `factory/flows.py`, `factory/db.py`, `factory/pipeline.py`, `factory/cli.py`, `tests/test_flows.py`, new `tests/test_candidates.py`, and this session log.
- Commands:
  - `uv run pytest -q tests/test_flows.py::test_candidates_is_a_build_step_option tests/test_flows.py::test_candidates_needs_one_build_step_followed_by_the_gates` — 2 passed;
  - `uv run pytest -q tests/test_candidates.py::test_each_candidate_builds_in_its_own_worktree_from_the_same_start tests/test_candidates.py::test_the_smallest_passing_candidate_is_chosen tests/test_candidates.py::test_when_none_pass_the_closest_candidate_carries_on tests/test_candidates.py::test_later_attempts_and_reworks_build_one_change tests/test_candidates.py::test_candidate_worktrees_are_removed_however_the_run_ends tests/test_candidates.py::test_show_labels_each_candidate_and_the_chosen_one` — 6 passed;
  - `uv run pytest -q tests/test_candidates.py tests/test_pipeline.py tests/test_flows.py tests/test_db.py` — 119 passed;
  - `uv run pytest -q` — 462 passed;
  - `git diff --check` — exit 0.
