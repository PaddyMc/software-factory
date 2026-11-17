## [20:31] strict-flow-t07: the built-in strict flow

- Added the built-in `strict` flow: an independently modelled test step with map/trim/nudge, a map/trim/nudge/resume build, gates, a proving trim review, and verification. It has no planner and inherits models and step limits by kind. Both built-ins are always present in effective config, `strict` remains opt-in, and redefining either built-in is refused.
- Added resolved-model comparison for test and build steps. `factory run` now writes the same-model blind-spots warning to the task run log and stderr without stopping the run; `factory prompt` prints it to stderr too, including `factory prompt test --flow strict`.
- Added an end-to-end strict pipeline test in which the first builder fails `acceptance_untouched`, the resumed second builder restores the locked test and passes gates, and a proving review and verifier report precede the open PR. Added run-log/stderr/prompt warning coverage and strict shape/redefinition coverage.
- Updated flow-list assertions in the flow, pipeline, bench, and web tests. The web run-form fixture now expects the second built-in option, and its flow-flag test uses built-in `strict` rather than redefining it.
- Files: `factory/flows.py`, `factory/config.py`, `factory/agents.py`, `factory/cli.py`, `tests/test_flows.py`, `tests/test_pipeline.py`, `tests/test_bench.py`, `tests/test_web.py`, and this session log.
- Commands:
  - `uv run pytest -q tests/test_flows.py::test_strict_is_built_in_and_cannot_be_redefined tests/test_flows.py::test_without_flows_the_default_flow_is_todays_pipeline tests/test_pipeline.py::test_the_strict_flow_tests_builds_gates_and_proves_before_a_pr tests/test_pipeline.py::test_a_tester_and_builder_on_one_model_are_warned_about tests/test_pipeline.py::test_an_unknown_flow_is_refused_before_any_work tests/test_scheduler.py::test_a_plan_run_passes_its_flow_to_each_task` — 6 passed;
  - `uv run pytest -q tests/test_flows.py tests/test_pipeline.py tests/test_scheduler.py` — 115 passed;
  - `uv run pytest -q tests/test_web.py::test_run_form_lists_what_will_run_and_previews_the_command tests/test_web.py::test_starting_a_run_launches_factory_run_with_the_forms_flags tests/test_bench.py::test_bench_run_refuses_before_any_work` — 3 passed;
  - `uv run pytest -q` — 446 passed (an earlier run exposed the two stale web fixtures, which were updated as described above);
  - `uv run python -m compileall -q factory/flows.py factory/config.py factory/agents.py factory/cli.py tests/test_flows.py tests/test_pipeline.py tests/test_bench.py tests/test_web.py` — exit 0;
  - `git diff --check` — exit 0.
