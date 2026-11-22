# flow-tuning-t05: document build candidates (2026-11-22, 23:15 UTC)

## What changed

- Added the architecture's Build candidates subsection: a three-candidate first-attempt diagram, sequential build and gate runs, selector and deterministic fallback rules, later-attempt/rework behaviour, and cost accounting. Added the selector to the Roles table and its prompt/configuration notes.
- Documented the `candidates` flow-step key, its validation rules and a complete example in the reference, including `select` model/step settings and troubleshooting for invalid flow shape and selector fallback.
- Marked NEXT.md item 14 done with a link to Build candidates.
- Added a commented candidates flow to both the shipped config template and this repository's config. Documented choosing and inspecting candidate flows in the shipped factory-ops skill and copied it to `.claude/skills/factory-ops/`.
- Changed no implementation or test files.

## Files

- `docs/architecture.md`
- `docs/reference.md`
- `NEXT.md`
- `factory/templates/config.yaml`
- `.factory/config.yaml`
- `factory/templates/skills/factory-ops/SKILL.md`
- `.claude/skills/factory-ops/SKILL.md`
- `docs/sessions/2026-11-22-flow-tuning-t05.md` (this log)

## Commands run

- The contract's five `grep -q` checks for architecture, reference, NEXT.md and both templates — all exit 0.
- `uv run pytest -q tests/test_templates.py` — **41 passed**, exit 0 (run twice).
- `cmp factory/templates/skills/factory-ops/SKILL.md .claude/skills/factory-ops/SKILL.md` — exit 0.
- `uv run pytest -q` — **481 passed**, exit 0.
- `git diff --check` — exit 0 (run before and after the tests).
