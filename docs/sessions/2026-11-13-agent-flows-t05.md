## [21:22] agent-flows-t05: Document agent flows

- Documented how to define and choose a flow, step-kind and override resolution, the order rules,
  the plan/attempt/review/gates/verify lifecycle, attempt-ending feedback, rework entry points and
  the flow/step run records. Added `flows.py` to the architecture components and refreshed the
  default-flow limitation now that gates-first flows exist.
- Added `flow`/`flows` configuration and the `lean`, `careful`, `gates-first` and `test-first`
  examples to the reference. Covered `--flow` and `--step` command usage and added troubleshooting
  for unknown flows, invalid step order and review prompts without a verdict line.
- Marked roadmap item 7 done and taught the shipped factory-ops skill how to start a run with
  another flow and inspect the flow and step recorded for each run. Installed skill copies were
  deliberately left untouched.
- Files: `docs/architecture.md`, `docs/reference.md`, `NEXT.md`,
  `factory/templates/skills/factory-ops/SKILL.md`,
  `docs/sessions/2026-11-13-agent-flows-t05.md` (new). No code or tests changed.
- Commands (all pass):
  - `grep -q '^## Agent flows' docs/architecture.md` — exit 0;
  - `grep -q -- '--flow' docs/reference.md` — exit 0;
  - `grep -q 'docs/architecture.md#agent-flows' NEXT.md` — exit 0;
  - `grep -q -- '--flow' factory/templates/skills/factory-ops/SKILL.md` — exit 0;
  - `uv run pytest -q tests/test_templates.py` — 28 passed;
  - `uv run pytest -q` — 242 passed;
  - `git diff --check` — exit 0.
- Follow-up, outside this task's scope: the shipped `factory/templates/config.yaml` comments still
  describe models and step limits but not `flow`/`flows`.
