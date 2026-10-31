# Example plan

A plan is a Markdown file with a fenced `yaml` list of **task contracts**. `factory sync` loads every contract into your local board, and `factory run example` (the plan's file name) takes each task to its own pull request. Replace or delete this plan before you run it: it is a real, runnable task.

Each contract has exactly these 8 keys. Status never goes in the plan; `factory status` shows it.

- `id`: unique, prefixed with the plan's name.
- `goal`: one observable deliverable.
- `spec_refs`: documents the agents must read first (may be empty).
- `depends_on`: task ids that must be merged, or have an open PR to build on, first.
- `non_goals`: what the task must not do.
- `acceptance`: observable conditions that prove it is done.
- `verification`: exact commands that pass offline in the sandbox when it is done.
- `risk`: `low`, `medium` or `high`.

`/plan-workstream` writes plans in this shape with you, and `factory validate-plan` checks them.

## Task contracts

```yaml
- id: example-t01
  goal: "docs/factory.md explains how this repository plans, runs and reviews work with the software factory"
  spec_refs: []
  depends_on: []
  non_goals:
    - "Changing code, configuration, or any other document"
  acceptance:
    - "docs/factory.md exists and names the commands to plan, run, watch and review a task"
  verification:
    - "grep -q 'validate-plan' docs/factory.md"
    - "grep -q 'review-task' docs/factory.md"
  risk: low
```
