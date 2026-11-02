## [21:40] session-log-per-task: one session log file per task

- Parallel factory tasks all appended to `docs/sessions/<today>.md`, so sibling PRs always conflicted
  on it. Each task now writes its own `<session_log>/<today>-<task id>.md`.
- `factory/agents.py`: the project rule tells agents to add a NEW `<today>-<task id>.md` and not edit
  other log files. `factory/gates.py`: the failure hint names the expected per-task file (the gate
  still accepts any `*.md` added under the log directory, so older per-day logs keep passing).
- Convention updated in `docs/sessions/README.md`, `factory/templates/session-log.md`,
  `factory/templates/config.yaml`, `factory/config.py`, `docs/reference.md`, the plan-workstream and
  factory-ops skills (repo copies and templates), and the remaining `pr-review-rework` criteria.
- `uv run pytest -q` — 187 passed. `factory validate-plan docs/plans/pr-review-rework.md` — ok (5 tasks).
