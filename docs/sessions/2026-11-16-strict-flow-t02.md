## [22:45] strict-flow-t02: repository maps and once-only agent nudges

- Added `map` and `nudge` to the validated flow-step loop behaviours, available to every agent kind while gates steps still reject loop options.
- Added an opt-in task-message suffix built from `git ls-files`: top-level tracked files, recursive tracked-file counts for directories through depth two, a 120-line repository-map cap with an omitted-directory count, and spec-reference line counts or `(not a file)` markers. Non-git directories leave the original message unchanged.
- Added opt-in nudge middleware for the three-quarter model-call budget (rounded up), six combined successful writes to one normalized path, and three consecutive non-zero exits of one exact command. Successful runs reset that command's streak; refused and errored tool calls do not count. Each budget, path and command is nudged at most once.
- Nudges are request-only human messages, so they do not alter model-call, token, cost or step-limit accounting. Each is also recorded as a `nudge` transcript event with its kind and text and logged under the step tag. Shared nearest-preceding tool-call pairing now serves both trim and nudge middleware; triggers read the full agent state so trimming cannot erase earlier outcomes.
- Added the five contract tests and extended loop parsing coverage for both new behaviours on every agent kind. The repeated-edit test also forces trimming to prove cleared results do not reset its count. Existing agent-loop, flow and pipeline tests remain unchanged and pass.
- Files: `factory/flows.py`, `factory/agents.py`, `tests/test_loop.py`, and this session log.
- Commands:
  - the contract's five-test `uv run pytest -q tests/test_loop.py::test_map_lists_the_tree_and_the_spec_references ...` command — 5 passed;
  - `uv run pytest -q tests/test_loop.py tests/test_agent_loop.py tests/test_flows.py` — 40 passed;
  - `uv run pytest -q` — 411 passed (including `tests/test_pipeline.py`);
  - `uv run python -m compileall -q factory/flows.py factory/agents.py` — exit 0;
  - `git diff --check` — exit 0.
