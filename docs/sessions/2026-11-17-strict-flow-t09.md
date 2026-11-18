## [21:22] strict-flow-t09: document the strict flow

- Documented the optional test step and its order, the `loop` and `prove` step options, and the built-in `strict` flow with a default-versus-strict table and a resumed-attempt run diagram. Added the tester role, the test-to-builder locked-test handover, and the `acceptance_untouched` gate.
- Documented trim, map, nudge and resume with their implemented limits; explained the red check, two tester tries, the test lock, REPRO proof and `APPROVE (unproven)`. Reworked the relevant known limitations to distinguish default behaviour from strict, while keeping the without-change gate and holdout tests open.
- Updated the configuration and flow reference, added a single-behaviour `default-trim` bench example and five strict-flow troubleshooting rows, and marked NEXT.md items 2 and 9 done with links to the strict-flow architecture.
- Added commented `test_paths` and `flow: strict` examples to the shipped config, mirrored the template comments in this repository's config, and expanded factory-ops with strict selection and diagnosis guidance. Refreshed the tracked `.claude` factory-ops copy required by `tests/test_templates.py`; the `.agents` relative symlink continues to point at it.
- Files: `.claude/skills/factory-ops/SKILL.md`, `.factory/config.yaml`, `NEXT.md`, `docs/architecture.md`, `docs/reference.md`, `factory/templates/config.yaml`, `factory/templates/skills/factory-ops/SKILL.md`, and this session log.
- Commands:
  - the contract's seven `grep -q` documentation checks — exit 0;
  - `uv run pytest -q tests/test_templates.py` — 31 passed (the first run had 30 passed and one failure pinning the stale installed factory-ops copy, which was then refreshed);
  - `uv run pytest -q` — 454 passed;
  - `cmp -s factory/templates/skills/factory-ops/SKILL.md .claude/skills/factory-ops/SKILL.md` — exit 0;
  - `git diff --check` — exit 0.
