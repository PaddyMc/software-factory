## Software factory

This repository uses the [software factory](https://github.com/PaddyMc/software-factory). `factory run <plan>` takes each task contract in a plan to its own pull request: planner → builder → reviewer → verifier agents work in a sandboxed worktree, and a PR is opened only when every gate passes. Merging the PR is the human approval.

- **Work** is a task contract (8-key fenced YAML) in the plans that `.factory/config.yaml` points at. Write plans with `/plan-workstream` and check them with `factory validate-plan`.
- **State** lives on each maintainer's local board, never in the plans: `factory sync`, `factory status [--refresh]`, `factory top`, `factory show <task>`.
- **Review** a factory PR with `/review-task <task>`. The `factory-ops` skill answers questions about operating the factory.
- **Merge** stacked PRs bottom-up, and run `factory status --refresh` after each merge.
- Agents never commit to your checkout, push, merge, or see secrets.
