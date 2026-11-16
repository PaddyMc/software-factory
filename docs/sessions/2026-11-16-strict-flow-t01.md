## [22:27] strict-flow-t01: opt-in capped reads and batched context trimming

- Added the `loop: [trim]` flow-step option with strict list, known-name, duplicate and gates-step validation; `factory config` now includes every step's loop setting. Steps without a loop keep their existing tools and middleware.
- Added optional 400-line read windows with a read-on line, and wired the cap into every agent role only for trim-enabled steps.
- Added trim middleware using LangChain's approximate token counter. It clears all eligible old results in batches, retains the latest eight by default, reuses each nearest preceding tool call's arguments, records before/after token counts, logs under the step tag, and leaves transcript tool events full.
- Used `wrap_model_call`, not `before_model`, because a before-model hook adds a graph node and would invalidate the existing recursion backstop. Cleared message positions are reapplied to later model requests; the underlying agent state therefore stays full, so the future resume task must re-derive or carry this trimming rather than expecting trimmed state.
- Added the five contract tests, including repeated tool-call ids, two clearing batches, placeholder persistence, unchanged graph nodes, capped-read wiring, and a trim run finishing on its last allowed step.
- Files: `factory/flows.py`, `factory/tools.py`, `factory/agents.py`, `tests/test_loop.py` (new), and this session log.
- Commands:
  - the contract's five-test `uv run pytest -q tests/test_loop.py::test_loop_is_a_list_of_known_behaviours ...` command — 5 passed;
  - `uv run pytest -q tests/test_agent_loop.py tests/test_flows.py tests/test_tools.py` — 41 passed;
  - `uv run pytest -q` — 406 passed (including `tests/test_pipeline.py`);
  - `uv run python -m compileall -q factory/flows.py factory/tools.py factory/agents.py` — exit 0;
  - `git diff --check` — exit 0.
