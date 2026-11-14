## [22:47] agent-flows-t02: every agent runs through LangChainRoles.step

- `factory/agents.py`: `LangChainRoles._run` generalized into `step(step, ctx, tag=None, message=None)`.
  Each kind's tools and task message live in `_kit` (plan: read; build: read+write+sandboxed run, with the
  fresh `ToolLog` attached to the Output; review: read+git_diff, verdict from `parse_verdict`; verify:
  read+git_diff+run) — byte-identical messages, log lines and records for the default flow's steps. The log
  tag is the step name, with `#attempt` for build and review steps, so the default flow logs exactly as today.
  `plan`, `build`, `resolve`, `review` and `verify` keep their signatures and delegate with the default
  flow's steps (`resolve` passes the build step, the resolve message and `tag="resolve"`).
- Step-level resolution next to the role helpers (which stay): `step_prompt_source` (a custom step's
  `.factory/agents/<name>.md` when the name differs from the kind and the file exists, else the kind's
  override or shipped prompt), `load_step`, `step_model` (`--model` > step `model` > `models[kind]` >
  frontmatter > default), `step_limit` (step `max_steps` > `max_steps[kind]` > frontmatter > 60) and
  `flow_models` (every agent step of a flow, gates excluded). `Ctx` gains `earlier`: a build step's message
  lists the earlier build steps' final messages of the attempt under `# Earlier build steps in this attempt`.
- A review step whose prompt has no `VERDICT:` line logs a warning that every review will count as CHANGES
  (`parse_verdict` already fails safe). The check is a substring match: the shipped reviewer prompt mentions
  `VERDICT:` only inline, so the default flow is not warned about.
- `factory/cli.py`: `factory prompt STEP [--flow F]` prints a step's resolved prompt, model and step limit
  (role names work exactly as before; unknown names still exit 2), and prints the same VERDICT warning.
- Six new tests in `tests/test_flows.py`: custom-vs-kind prompt resolution, model/limit precedence and
  `flow_models`, per-kind tools/messages/verdict, the `earlier` block, the VERDICT warning, and
  `factory prompt` for a flow step.
- Files: `factory/agents.py`, `factory/cli.py`, `tests/test_flows.py`,
  `docs/sessions/2026-11-02-agent-flows-t02.md` (new).
- Commands: `uv run pytest -q tests/test_flows.py::<the six named tests>` — 6 passed;
  `uv run pytest -q tests/test_agent_loop.py tests/test_pipeline.py` — 43 passed;
  `uv run pytest -q` — 206 passed.
