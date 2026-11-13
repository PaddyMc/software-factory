## [12:00] agent-flows-t04: `--flow`, reworks under a flow, and `--step`

- `factory run TASK --flow NAME` and `factory run PLAN --flow NAME` pick the flow for one run or a
  whole plan run instead of the configured `flow`. An unknown name is refused before any work with
  `unknown flow NAME (flows: default, …)`, and the chosen flow's step models are checked for
  provider keys before anything starts (task and plan paths). A plan run passes `--flow` through
  `_child_args` to every child `factory run`.
- Conflict resolutions, CI fixes and human-review reworks run the chosen flow's steps after their
  fixed entry. The resolve agent now runs on the flow's first build step's model and step limit
  (still under the resolve message and tag); a clean replay still goes straight to the gates, and
  a review's CHANGES sends the next attempt through the flow's build steps, review steps and gates
  in order. CI and human-review reworks keep the rework brief in view on every build step of every
  attempt, and every review step of a human-review rework gets the review brief. Push leases, PR
  comments and rework run records are unchanged apart from the new flow/step columns.
- `factory show`, `factory trace` and `factory transcript` accept `--step NAME` to filter runs, and
  `factory show` labels each run heading with its flow and step.
- This task also carries its prerequisite changes (agent-flows-t02/t03, whose PRs had not reached
  `main` when this branch was cut): `LangChainRoles.step`, per-step prompt/model/step-limit and
  `flow_models` in `factory/agents.py`; `Options.flow` and the flow-shaped graph in
  `factory/pipeline.py`; the `runs.flow`/`runs.step` columns in `factory/db.py`; the configured
  flow's key check and `factory prompt STEP --flow F` in `factory/cli.py`; and the t02/t03 tests.
- The gates step's pass edge now routes to the next post-build step when one remains (a flow may put
  `gates` before some `review` steps), and a trailing review step's APPROVE routes to verify/pr; the
  graph recursion limit scales with the number of flow steps. `factory show` labels pre-migration runs
  with placeholders, and its transcript hint names the step.
- Files: `factory/cli.py`, `factory/agents.py`, `factory/pipeline.py`, `factory/db.py`,
  `tests/test_pipeline.py`, `tests/test_scheduler.py`, `tests/test_flows.py`,
  `docs/sessions/2026-11-13-agent-flows-t04.md` (new).
- Commands (all pass):
  - `uv run pytest -q tests/test_pipeline.py::test_the_flow_flag_overrides_the_configured_flow tests/test_pipeline.py::test_an_unknown_flow_is_refused_before_any_work tests/test_pipeline.py::test_a_ci_fix_runs_the_flows_build_and_review_steps tests/test_pipeline.py::test_a_conflict_resolution_is_reviewed_by_every_review_step tests/test_pipeline.py::test_a_review_rework_runs_every_review_step_with_the_brief tests/test_pipeline.py::test_show_filters_runs_by_step` — 6 passed;
  - `uv run pytest -q tests/test_scheduler.py::test_a_plan_run_passes_its_flow_to_each_task` — 1 passed;
  - `uv run pytest -q tests/test_pipeline.py::test_gates_first_flow_reviews_on_a_passing_build` — 1 passed;
  - `uv run pytest -q tests/test_pipeline.py tests/test_scheduler.py tests/test_ci.py` — 66 passed;
  - `uv run pytest -q` — 220 passed.
