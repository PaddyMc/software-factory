## [19:59] flow-tuning-t01: ask again for a missing review verdict

- Added one bounded re-ask for review steps without a VERDICT line. It continues the same conversation with the same prompt and tools, excludes injected call-limit markers, observes the extra messages, and counts their calls, tokens and cost in the original output.
- Recorded answered re-asks as `(asked again)` and unanswered ones as `CHANGES (no verdict)`; the next builder now receives explicit no-verdict feedback followed by the last report and an instruction to address its blocker or major findings.
- Extended the scripted reviewer and added four agent-loop tests plus two end-to-end pipeline tests for re-ask conversations, step-limit stops, the three-call cap, verdict routing, outcomes, transcripts and feedback.
- Documented the behaviour in the architecture and both troubleshooting references, keeping the shipped and installed factory-ops copies identical.
- Files: `factory/agents.py`, `factory/pipeline.py`, `tests/fake_model.py`, `tests/test_agent_loop.py`, `tests/test_pipeline.py`, `docs/reference.md`, `docs/architecture.md`, `factory/templates/skills/factory-ops/references/troubleshooting.md`, `.claude/skills/factory-ops/references/troubleshooting.md`, and this session log.
- Commands:
  - `uv run pytest -q tests/test_agent_loop.py::test_a_review_without_a_verdict_is_asked_once_more tests/test_agent_loop.py::test_a_review_stopped_at_its_step_limit_is_asked_for_its_verdict tests/test_agent_loop.py::test_a_review_still_without_a_verdict_counts_as_changes tests/test_agent_loop.py::test_a_review_with_a_verdict_is_not_asked_again` — 4 passed;
  - `uv run pytest -q tests/test_pipeline.py::test_a_review_without_a_verdict_tells_the_builder_none_came tests/test_pipeline.py::test_a_review_answered_when_asked_again_routes_on_its_verdict` — 2 passed;
  - `grep -q 'CHANGES (no verdict)' docs/reference.md` — exit 0;
  - `grep -q 'CHANGES (no verdict)' factory/templates/skills/factory-ops/references/troubleshooting.md` — exit 0;
  - `uv run pytest -q tests/test_agent_loop.py tests/test_pipeline.py tests/test_flows.py tests/test_templates.py` — 150 passed;
  - `uv run pytest -q` — 460 passed;
  - `git diff --check` — exit 0.
