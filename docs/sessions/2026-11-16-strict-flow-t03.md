## [23:07] strict-flow-t03: resumed build conversations

- Added the build-only `resume` loop behaviour, with flow/step-named configuration errors on plan, review, verify and gates steps.
- Kept a per-`LangChainRoles`, per-build-step conversation in memory. Later attempts seed a fresh agent with the earlier messages and one new `# Attempt N` human message containing current feedback and any earlier-build reports; the plan and repository map are not added again. First attempts, conflict resolutions and their following attempts, and attempts after an error start fresh with a reason in the log. Resolutions neither resume nor seed memory.
- Reused the trim middleware's view when storing a conversation, so resumed calls retain the same cleared-result placeholders while each attempt's transcript keeps only its own full results. Resumed transcripts open with `resumed` (including the carried-message count), then the system and new human events; carried messages are not recorded again.
- Kept model-call limits, nudge budgets, steps, tokens and cost per attempt. Step-limit and graph-recursion stops still leave a resumable conversation, while an escaping error invalidates the whole chain.
- Added the four loop tests and the CLI end-to-end gate-feedback retry test; updated the existing pinned `LOOP` tuple. Default-flow and non-resume behaviour remains covered by the unmodified flow, agent-loop and pipeline regressions.
- Files: `factory/flows.py`, `factory/agents.py`, `tests/test_loop.py`, `tests/test_pipeline.py`, and this session log.
- Commands:
  - the contract's five-test `uv run pytest -q tests/test_loop.py::test_resume_is_for_build_steps_only ... tests/test_pipeline.py::test_a_resuming_builder_gets_gate_feedback_in_the_same_conversation` command — 5 passed;
  - `uv run pytest -q tests/test_loop.py tests/test_pipeline.py tests/test_flows.py` — 100 passed;
  - `uv run pytest -q` — 416 passed;
  - `uv run python -m compileall -q factory/agents.py factory/flows.py` — exit 0;
  - `git diff --check` — exit 0.
