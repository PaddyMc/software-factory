## [00:30] agent-flows-t03: the pipeline runs the configured flow

- `factory/pipeline.py`: `Options` gains `flow` (a `flows.Flow`, default `flows.DEFAULT`), and the graph's
  fresh-build path is built from it: the plan step if any (`plan` node), then one `attempt` node that runs
  every build step in order (each commits what it leaves through `_commit`, with the earlier steps' final
  messages of the attempt passed as `ctx.earlier`), then one node per review step plus the `gates` node in
  flow order, then the `verify` node if any, then `pr`. The first CHANGES or a gates failure ends the attempt
  and loops back to the first build step with the feedback; a custom review step's feedback names it
  (`` Reviewer `NAME` requested changes: ``). HEAD still at the start after all build steps keeps today's
  no-change feedback and skips review and gates; `--max-attempts` and the identical-gate-failure stop are
  unchanged, as are the resolve/rework entry nodes (rework-under-flow is t04), commit messages, transcript
  names (`{run_id}-{role}-{attempt}.jsonl`) and log tags. Without a plan step the build steps get
  `(This flow has no plan step: plan from the contract.)`; without a verify step the PR body has no Verifier
  report section. The PR body has one `Reviewer report (<step>)` block per review step and a
  `**Flow** `<name>`: <steps>` line. `Pipeline.role` records `flow` (default the configured flow's name) and
  `step` (default the role/kind name; the gates run is role `verify`, step `gates`); `_progress` labels with
  the step name, so the default flow's labels (`plan#0`, `build#1`) are unchanged.
- `factory/db.py`: `runs` gains `flow` and `step` columns (TEXT, migrated into older databases by the existing
  MIGRATIONS loop); `start_run` takes them as optional keywords. `ROLES`, `last_report` and `--role` filters
  are untouched: a run's role stays its kind.
- `factory/agents.py`: the `Roles` protocol gains `step(step, ctx, tag=None, message=None)` (already on
  `LangChainRoles` since agent-flows-t02); the pipeline now drives every agent through it.
- `factory/cli.py`: `cmd_run_one` resolves `flow = cfg.flows[cfg.flow]`, checks every step's model keys with
  `agents.flow_models` + `missing_keys` before any work starts (same error format, keyed by step names), and
  passes the flow into `Options`. Plan runs keep the `role_models` check (t04).
- Six new end-to-end tests in `tests/test_pipeline.py`: a planner-less/report-less flow opens a PR on passing
  gates; a second reviewer's CHANGES sends the build back (feedback names the step); gates-first skips the
  reviewers when gates fail; two build steps both run and commit each attempt (the second sees the first's
  final message); runs record their flow and step under the default and a lean flow; a custom step's missing
  provider key is refused before any work.
- Files: `factory/pipeline.py`, `factory/db.py`, `factory/agents.py`, `factory/cli.py`,
  `tests/test_pipeline.py`, `docs/sessions/2026-11-02-agent-flows-t03.md` (new).
- Commands: `uv run pytest -q tests/test_pipeline.py::<the six named tests>` — 6 passed;
  `uv run pytest -q tests/test_pipeline.py tests/test_db.py` — 48 passed; `uv run pytest -q` — 212 passed.
