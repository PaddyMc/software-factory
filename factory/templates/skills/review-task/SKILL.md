---
name: review-task
description: Review the implementation of one software-factory task contract before merge — typically a factory PR (`factory/<task-id>` branch) or hand-written work. Runs the factory's deterministic gates (`factory gates` — scope within allowed_paths, plan untouched, and whatever .factory/config.yaml configures — session log, a new e2e test, the contract's verification commands, unit and e2e tests), then judges each acceptance criterion and non-goal with the factory's reviewer checklist, producing an APPROVE / REQUEST CHANGES report. Explicit-invocation only — invoke when the user types `/review-task TASK_ID [REF]`; do not auto-trigger on phrases like "review this" (use an ordinary code review for plain diffs).
---

# Review Task

A human-invoked second opinion on one task contract's implementation. It uses the same gates and checklist as the factory's verify and review agents. **Report only:** never edit, commit, push or merge.

`/review-task TASK_ID [REF]`:
- `REF` defaults to `factory/<task-id>` if that branch exists, else `HEAD`.
- The base defaults to the repository's default branch (usually `main`).

## 1. Gates (deterministic)

```bash
factory gates <task-id> --ref <ref> --skip verification,unit_tests,e2e_tests   # cheap gates first
factory gates <task-id> --ref <ref>                                          # full
```

(Use `uv run --project <path-to-software-factory> factory …` if the CLI isn't installed.)

- **Where they run:** `<ref>` is checked out in a throwaway detached worktree, and the gates run in the bubblewrap sandbox (offline).
- **Which gates exist** depends on `.factory/config.yaml`; `factory config` shows it.
- **Whole e2e suite:** pass `--full-e2e` when the change touches paths matched by `e2e.run_all_when`.
- **Timeouts:** allow a generous one, since a cold build plus tests can take minutes.
- **Early stop:** if `scope`, `plan_untouched` or `e2e_written` fails on the cheap pass, stop and report.

## 2. Judgment

Apply `.factory/agents/reviewer.md`, the same checklist the factory's reviewer agent uses, to `git diff $(git merge-base <base> <ref>)..<ref>` with the contract open. The contract comes from the plan named in `factory show <task-id>`, or from searching the plans for the task id. Cite `path:line` for every claim.

## 3. Report

```markdown
# Review · <task-id> · APPROVE | REQUEST CHANGES

**Ref:** <ref> (<sha>) vs <base> (merge-base <sha>) · **Risk:** <risk>

## Gates
<the table from `factory gates`>

## Acceptance criteria
| # | Criterion | Verdict | Evidence |
|---|---|---|---|

## Non-goals
- <bullet> — respected / **violated** (`path:line`)

## Findings
1. **[blocker|major|minor]** `path:line` — <what, why, fix>

## Verdict
<APPROVE: ready for human merge> | <REQUEST CHANGES: the blockers above>
```

Any FAIL gate or FAIL acceptance criterion ⇒ REQUEST CHANGES. Merging stays a human decision.
