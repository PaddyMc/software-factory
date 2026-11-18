## [19:53] strict-flow-t06: the proving reviewer

- Added the review-only `prove` step option, defaulting to false and included in the effective config dump. Non-boolean values and enabling it on other step kinds are rejected with the flow and step named.
- Proving reviewers now receive the sandboxed `run` tool alongside their read and diff tools, with the same built-in and configured command refusals as builders. Their generated system prompt includes the non-per-task Proof rules immediately after the project rules, so the prompt version covers them.
- Added ordered, distinct REPRO parsing (capped at five), denied-command checks, independent 300-second sandbox reruns, output tails, and a `## Proof` report section. Reproduced failures and blocker/major `[scope]` findings preserve CHANGES; other reported change requests become `APPROVE (unproven)`, while reported approvals and missing-verdict fail-safe behavior are preserved.
- The review node now records the proof-augmented report and effective outcome, routes on the effective verdict, and gives standing CHANGES feedback including Proof. It resets/cleans reviewer writes before running REPROs on the committed candidate, then resets/cleans REPRO writes afterward, retaining ignored files and logging discarded paths from both rounds. Ordinary reviews retain their previous behavior.
- Added the seven proof unit tests and three end-to-end pipeline tests covering tool access, verdicts, unproven PR reporting/verifier input, candidate worktree restoration before and after REPROs, and reproduced Proof in the next builder's feedback. Review follow-up also made `prove: null` invalid and recognized `[scope]` on finding continuation lines.
- Files: `factory/flows.py`, `factory/agents.py`, `factory/pipeline.py`, `tests/test_prove.py`, `tests/test_pipeline.py`, and this session log.
- Commands:
  - `uv run pytest -q tests/test_prove.py::test_prove_is_a_review_step_option tests/test_prove.py::test_a_proving_reviewer_can_run_commands_and_gets_the_proof_rules tests/test_prove.py::test_changes_stands_on_a_reproduced_failure tests/test_prove.py::test_changes_stands_on_a_scope_finding tests/test_prove.py::test_unproven_changes_becomes_an_approval tests/test_prove.py::test_a_passing_timed_out_or_denied_repro_is_unproven tests/test_prove.py::test_a_missing_verdict_is_still_changes` — 7 passed;
  - `uv run pytest -q tests/test_pipeline.py::test_a_proving_review_leaves_the_worktree_at_the_candidate tests/test_pipeline.py::test_an_unproven_review_does_not_send_the_build_back` — 2 passed;
  - `uv run pytest -q tests/test_pipeline.py tests/test_flows.py tests/test_templates.py` — 130 passed;
  - `uv run pytest -q` — 443 passed;
  - `uv run python -m compileall -q factory/flows.py factory/agents.py factory/pipeline.py tests/test_prove.py tests/test_pipeline.py` — exit 0;
  - `git diff --check` — exit 0.
