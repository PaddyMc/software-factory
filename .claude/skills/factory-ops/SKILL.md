---
name: factory-ops
description: Operate the software factory (the `factory` CLI) in this repository. Covers starting runs of a plan or a task, watching them, explaining why a task failed, rerunning or requeuing tasks (including abandoned → queued), holding tasks, merging stacked factory PRs, loading new plans, and resetting the board. Use whenever the user asks how to run, start or kick off the factory or the backlog; asks what a run is doing or what's left; asks about a failed, stuck, queued, abandoned, conflict, ci_failed or DEAD task; pastes `factory` output or a factory error; asks about merging factory PRs; or asks what the factory will do. Not for writing plans (/plan-workstream) or judging a PR's content (/review-task).
---

# Factory ops

The user asks short operational questions ("what is the command", "how do I rerun everything", "how do I move this from abandoned to queued"). Answer with the exact command first, then only the caveats that apply now.

## Ground in live state first

Statuses change while runs proceed, so never answer from memory. From the repository root:

```bash
factory status [PLAN]            # board grouped by plan, task counters, what each task waits for
factory show TASK                # status, branch, base, PR, note (failure reason), every agent report
factory config                   # this repository's settings: plans, gates, models, board location
pgrep -af "factory run" | grep -v pgrep   # runs active right now
```

These are read-only and safe to run, as are `top --once`, `logs`, `transcript`, `trace` and `validate-plan`. `factory sync` only loads contracts into the board.

## What you may and may not do

- **Starting runs needs the provider key** (`OPENROUTER_API_KEY` by default), which your shell usually doesn't have. Give the user the command; in Claude Code they can run it with the `!` prefix.
- **While a run is active,** don't switch the main checkout's branch, don't reset the board, and don't remove worktrees.
- **Never** merge PRs or record approvals for the user, pass secrets into the sandbox, or run tasks that need secrets or spend money. Those are the user's.
- **Reruns cost money.** Diagnose before suggesting one.

## How it works

- **Task:** an 8-key YAML contract in the plans (`plans` in `.factory/config.yaml`). Its state lives only in the board, `$FACTORY_HOME/factory.db` (`factory config` names the directory); plans carry no status.
- **`factory run TASK`:** planner → builder ⇄ reviewer → deterministic gates → verifier → PR, with up to `--max-attempts` (3) builds, in `$FACTORY_HOME/worktrees/TASK` on branch `factory/TASK`, in an offline bubblewrap sandbox. It ends `pr_open` or `failed`. Nothing retries automatically across runs.
- **`factory run PLAN`** (the plan's file name without `.md`, or its path): every task of the plan without a PR, in dependency order, `--parallel N` (default 3) at once, one PR per task.
- **Stacking:** a task starts once each dependency is merged or has an open PR. On an open PR it is built on top of it, and its PR targets `factory/<dep>`.
- **Statuses:** `queued → planning → building → reviewing → verifying → pr_open → merged`, or `failed`, or `abandoned` (a closed PR, or a deliberate hold), or `conflict` (an open PR that no longer applies to its base), or `ci_failed` (an open PR whose CI fails on its head).
- **Conflicts:** `factory status --refresh` marks a PR `conflict` when GitHub reports it conflicting or a restack can't rebase it. `factory run TASK` (or its plan) replays the change onto the new base: the builder resolves the conflicted files, and review and every gate run again before the same PR is force-pushed, leased on its old head. If the resolution fails, the task is `failed` and the PR is untouched; running it again rebuilds it from scratch (`--force` does that at once).
- **CI failures:** `factory status --refresh` marks a PR `ci_failed` when a check fails on the factory's own candidate. Checks on a commit someone else pushed are ignored, and so are cancelled and still-running ones. `factory run TASK` (or its plan) builds on the PR's branch at that head, with the failing checks and their GitHub Actions logs as the builder's feedback; review and every gate run again before the same PR is force-pushed, leased on the failing head. A stacked PR whose dependency merged or moved is restacked instead, with no agent, and goes back to `pr_open` for CI to judge. A check that passes on re-run (a flake) puts the task back to `pr_open`. If the fix fails, the task is `failed` and the PR is untouched. The gates can't run CI's own checks, so a fix that doesn't hold shows up `ci_failed` again on the next refresh.
- **Merging is the human gate.** Merge from the bottom of a stack up, and run `factory status --refresh` after **every** merge: it records the merge and rebases and retargets the PRs stacked on it. Unless the repository deletes head branches on merge, GitHub won't retarget them itself.
- **Branches:** runs branch from origin's copy of the checkout's current branch and target it (`--base` overrides). Each run reads contracts from the checkout's working tree when it starts, uncommitted edits included.
- **Settings:** the gates, plans location, models and step limits come from `.factory/config.yaml`, always read from the main checkout. A repository can replace a role's prompt with `.factory/agents/<planner|builder|reviewer|verifier>.md`.

## Requests and answers

| The user asks | Answer |
|---|---|
| Start, kick off, "finish the backlog" | `export OPENROUTER_API_KEY=…` then `factory run PLAN --parallel 3 --max-cost 10 --notify`, one per plan (separate terminals are fine). Add `--network-for TASK` for tasks that must download. A task whose dependency in another plan has no PR yet waits, so rerun its plan once it does. The user still merges each PR, and manual tasks stay manual |
| What's happening | `factory top [PLAN]` (live, per plan: ✓ merged ◆ PR open ≠ PR conflicts ! CI fails ▶ running ✗ failed · queued ⊘ held), `factory logs TASK -f` or `factory logs --all -f`, `factory show TASK`, `factory transcript TASK --role build`, `factory trace TASK` |
| What's left | `factory status` (counters such as `2/8 merged · 2 failed · 4 waiting`) |
| Why did X fail | The diagnosis steps below |
| Will failures retry? / Rerun everything | Not between runs; within a run, up to 3 builds. Rerun the plan to retry every failed task in it once: `factory run PLAN`. One task: `factory run TASK`. Leftover worktrees are replaced automatically |
| Abandoned (or failed) → queued | `factory requeue TASK…`; the next plan run picks them up. Or run it now with `factory run TASK` |
| Hold a task | `factory abandon TASK --note "hold: <why>"`. Plan runs skip `abandoned` tasks |
| I merged a PR | `factory status --refresh`. Then the next PR in the stack, or `factory run PLAN` to continue (it also resolves PRs the merge put in `conflict` and fixes PRs in `ci_failed`) |
| A PR has conflicts | `factory status --refresh`, then `factory run TASK` (or `factory run PLAN`) |
| A PR's CI is red | `factory status --refresh` (marks it `ci_failed`), then `factory run TASK` (or `factory run PLAN`). `factory show TASK --role ci` shows the failing checks and the logs the builder gets. A problem with the CI runner itself (a missing tool, a broken workflow) is not the task's to fix: fix the workflow by hand |
| Review a factory PR | `/review-task TASK` (Codex: `$review-task TASK`) |
| New work | `/plan-workstream` (Codex: `$plan-workstream`) → plan PR → `factory sync` → `factory run PLAN` |
| Several boards | One board per `FACTORY_HOME`. Parallelism comes from `--parallel` and concurrent plan runs. Use a separate `FACTORY_HOME` for experiments |
| Several people, one backlog | Each keeps their own board; never commit `factory.db`. `factory sync && factory status --refresh` takes up the open and merged `factory/*` PRs others opened. Nothing claims a task across boards, so agree who runs which plan |
| Costs | `--max-cost USD` caps each task; `top` and `status` show spend. Keep the provider's credits topped up |
| Models, step limits | `models:` and `max_steps:` per role (`plan`, `build`, `review`, `verify`) in `.factory/config.yaml`; one-off `--model provider:model` |
| Clean the board, start again | references/board.md |

## Diagnosing a failed task

1. `factory show TASK`: read the `note` headline, for example `gave up after 3 builds: Reviewer requested changes`, `no progress (same failure twice)` or `error: …`.
2. Get the evidence: `factory show TASK --role verify` (gate table) or `--role review` (findings), and `factory logs TASK -n 80`.
3. Match it in references/troubleshooting.md. Separate the two kinds of failure:
   - **Infrastructure** (credits, network, a crash, a dead process): fix the cause and rerun.
   - **The agents** (reviewer loop, no changes, gates that never pass): fix the contract, give it network, or do the task by hand.
4. Report the cause, the evidence (quote the note), and the one command that fixes it.

## References

- `references/troubleshooting.md`: symptom → cause → fix. Read when a run failed, a task won't start, a PR looks wrong, or git refuses.
- `references/board.md`: checking for active runs and resetting the board. Read before touching factory state.
- The factory's `docs/reference.md` (every command and flag, config, troubleshooting) and `docs/architecture.md` (the pipeline, the gates, the sandbox).
