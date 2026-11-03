## [22:30] agent-flows-t01: named agent flows in the config

- `.factory/config.yaml` can now define named agent flows under `flows:` and pick the default one
  with `flow:` (default `"default"`). A step is a bare kind string (`plan`, `build`, `review`,
  `verify`, `gates`) or a mapping with `kind` plus optional `name`, `model` and `max_steps`.
- New `factory/flows.py`: frozen `Step(name, kind, model, max_steps)` and `Flow(name, steps)`
  dataclasses, the built-in `DEFAULT` flow (today's plan, build, review, gates, verify, each named
  after its kind), and parsing/validation. Validation errors name the flow and the offending step;
  the order rules are `[plan]? build+ (review|gates)* [verify]?`, and a flow without a gates step
  gets one inserted after its last review (else its last build), so every flow holds exactly one.
- `factory/config.py`: `Config` gains `flow` and `flows`, parsed through `factory/flows.py`
  (imported lazily inside `parse()`, since flows.py takes `ConfigError` from config.py). The
  built-in `default` flow cannot be redefined and `flow` must name a known flow. `factory config`
  prints both through its existing dataclass dump; no CLI change was needed.
- New `tests/test_flows.py` with the seven contract tests (default flow shape, step parsing,
  gates placement, order rules, name rules, default/`flow` checks, `factory config` output).
- Files: `factory/flows.py` (new), `factory/config.py`, `tests/test_flows.py` (new),
  `docs/sessions/2026-11-02-agent-flows-t01.md` (new).
- Commands: `uv run pytest -q tests/test_flows.py::<the seven named tests>` — 13 passed;
  `uv run pytest -q tests/test_config.py` — 12 passed; `uv run pytest -q` — 200 passed.
