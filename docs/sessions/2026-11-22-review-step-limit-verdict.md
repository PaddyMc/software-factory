## [21:30] review-step-limit-verdict: a review out of calls gets one more call for its verdict

- Why: a review that reached `max_steps` before writing its VERDICT line counted as CHANGES
  (`parse_verdict`, and `apply_proof` for a proving review). That skipped strict's proof rule and sent
  the task back to the builder. factory-spec-t04 built three times: reviews 1 and 2 ended
  `CHANGES (step limit)` with no findings, and each extra build → gates → review round took 10–15
  minutes. Three of strict's six reviews on the board had used all 60 calls.
- `factory/agents.py`: when a review step stops at its step limit and its last text has no VERDICT line,
  `LangChainRoles._verdict_call` makes one more model call. Tools are bound with `tool_choice="none"`,
  and the call carries the conversation (as `trim` left it, without the call-limit marker or a trailing
  unanswered tool call) plus `VERDICT_CALL`, which asks for the complete final review and its VERDICT line.
  The call is counted in the run's steps, tokens and cost, and logged and recorded as a `verdict` nudge. The
  run is still recorded `(step limit)`. If the call fails, the review keeps today's outcome (CHANGES).
- Tests: `tests/test_agent_loop.py` (the extra call and what it sends, no extra call when the verdict
  came in time, a failed call) and `tests/test_pipeline.py::test_a_review_out_of_calls_gives_its_verdict_instead_of_another_build`
  (a reviewer with `max_steps: 1` now approves on the first build; on main the run fails after three builds).
- Docs: `docs/architecture.md` (step limits, reviewer row), `docs/reference.md` (the step-limit troubleshooting row).
- Commands: `uv run --offline pytest -q tests/test_agent_loop.py tests/test_pipeline.py -k "out_of_calls or verdict"`
  (3 of the 4 new tests fail with main's `agents.py`), `GIT_CONFIG_GLOBAL=/dev/null uv run --offline pytest -q` (full suite).
