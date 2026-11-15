## [19:37] pr-descriptions-t05: Document the factory PR layout

- Documented a factory PR body's fixed order and sources, its deterministic size limits and shrink ladder, the verifier-written summary and deterministic fallback, title and commit formats, and the location of every full report. Added the squash-merge setting that puts the PR title on the trunk.
- Updated the verifier's role and handover descriptions and the remaining stale PR wording; added fallback and capped-report troubleshooting, marked roadmap item 11 done, and taught the shipped factory-ops skill how to read PRs and recover full reports.
- Files: `docs/architecture.md`, `docs/reference.md`, `NEXT.md`, `factory/templates/skills/factory-ops/SKILL.md`, `factory/templates/skills/factory-ops/references/troubleshooting.md`, and this session log.
- Commands (all final runs pass):
  - the contract's five `grep -q` checks for the architecture section and fallback, reference fallback, roadmap link, and factory-ops What to check text — exit 0;
  - `uv run pytest -q tests/test_templates.py` — 29 passed;
  - `uv run pytest -q` — 314 passed;
  - `git diff --check` — exit 0.
