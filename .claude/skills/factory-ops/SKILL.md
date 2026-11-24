---
name: factory-ops
description: Operate the software factory (the `factory` CLI) in this repository. Covers starting runs of a plan or a task, watching them, explaining why a task failed, rerunning or requeuing tasks (including abandoned → queued), holding tasks, stopping a run, merging stacked factory PRs, loading new plans, and resetting the board. Use whenever the user asks how to run, start or kick off the factory or the backlog; asks what a run is doing or what's left; asks about a failed, stuck, queued, abandoned, conflict, ci_failed, changes_requested or DEAD task; pastes `factory` output or a factory error; asks how the factory is doing or whether a change helped; asks about merging factory PRs; asks how to compare flows or models with `factory bench`; or asks what the factory will do. Not for writing plans (/plan-workstream) or judging a PR's content (/review-task).
---

# Factory ops

The user asks short operational questions ("what is the command", "how do I rerun everything", "how do I move this from abandoned to queued"). Answer with the exact command first, then only the caveats that apply now.

## Ground in live state first

Statuses change while runs proceed, so never answer from memory. From the repository root:

```bash
factory status [PLAN]            # board grouped by plan, task counters, what each task waits for
factory show TASK                # status, branch, base, PR, note (failure reason), every agent report
factory stats [--since DATE] [--until DATE] [--plan P] [--json]   # board metrics over a window
factory config                   # this repository's settings: plans, gates, models, board location
factory version                  # which factory code is running (an editable install runs whatever its checkout holds)
pgrep -af "factory run" | grep -v pgrep   # runs active right now
```

These are read-only and safe to run, as are `top --once`, `logs`, `transcript`, `trace`, `stats` and `validate-plan`. `factory sync` only loads contracts into the board.

## What you may and may not do

- **Starting runs needs the provider key** (`OPENROUTER_API_KEY` by default), which your shell usually doesn't have. Give the user the command; in Claude Code they can run it with the `!` prefix.
- **While a run is active,** don't switch the main checkout's branch, don't reset the board, and don't remove worktrees.
- **Never** merge PRs or record approvals for the user, pass secrets into the sandbox, or run tasks that need secrets or spend money. Those are the user's.
- **Reruns cost money.** Diagnose before suggesting one.

## How it works

- **Task:** an 8-key YAML contract in the plans (`plans` in `.factory/config.yaml`). Its state lives only in the board, `$FACTORY_HOME/factory.db` (`factory config` names the directory); plans carry no status.
- **`factory run TASK`:** the built-in `default` flow is planner → builder ⇄ reviewer → deterministic gates → verifier → PR; `flows:` and `--flow NAME` reshape it. It runs with up to `--max-attempts` (3) builds, in `$FACTORY_HOME/worktrees/TASK` on branch `factory/TASK`, in an offline bubblewrap sandbox. It ends `pr_open` or `failed`. Nothing retries automatically across runs.
- **Choosing `strict`:** use `factory run TASK --flow strict` (or a plan run with the same flag), or set `flow: strict` in `.factory/config.yaml`. This second built-in has no planner: a tester maps, trims and nudges while writing red-checked tests under the required `test_paths`; the builder maps, trims, nudges and resumes across attempts; the gates run before a trimming, proving reviewer; then the verifier writes the PR report. `default` is unchanged, and neither built-in can be redefined.
- **Choosing a flow with candidates:** a build step can set `candidates: N` (2 to 5); pick such a flow with `factory run TASK --flow NAME` or `flow: NAME`. The flow needs one build step directly followed by the gates. Its first attempt builds N candidates, the gates judge each, and a selector chooses among multiple passing candidates. Later attempts and reworks build one change. Every candidate and the selector count against `--max-cost`.
- **Reading a task's candidate runs:** `factory show TASK` labels each candidate's runs `candidate K of N` and marks the chosen one; `factory show TASK --step select` prints the selector's comparison. A selector run recorded as `fallback` had no valid choice, so the factory chose the smallest passing diff.
- **`factory run PLAN`** (the plan's file name without `.md`, or its path): every task of the plan without a PR, in dependency order, `--parallel N` (default 3) at once, one PR per task.
- **`factory web`:** serves the board as a page at `http://127.0.0.1:8765` (`--port N`, `--no-open`). It shows every plan at `/plans`, with each plan's page linking its tasks. It shows the board, each task's contract, runs, reports and live log, and each run's transcript, and can run, stop or hold tasks: every button runs the `factory` command it names as a job on the activity page. It is loopback-only; reach another machine with `ssh -L 8765:127.0.0.1:8765 HOST`.
- **Stacking:** a task starts once each dependency is merged or has an open PR. On an open PR it is built on top of it, and its PR targets `factory/<dep>`.
- **Statuses:** `queued → planning → building → reviewing → verifying → pr_open → merged`, or `failed`, or `abandoned` (a closed PR, or a deliberate hold), or `conflict` (an open PR that no longer applies to its base), or `ci_failed` (an open PR whose CI fails on its head), or `changes_requested` (an open PR a review asks to change).
- **Conflicts:** `factory status --refresh` marks a PR `conflict` when GitHub reports it conflicting or a restack can't rebase it. `factory run TASK` (or its plan) replays the change onto the new base: the builder resolves the conflicted files, and review and every gate run again before the same PR is force-pushed, leased on its old head. If the resolution fails, the task is `failed` and the PR is untouched; running it again rebuilds it from scratch (`--force` does that at once).
- **CI failures:** `factory status --refresh` marks a PR `ci_failed` when a check fails on the factory's own candidate. Checks on a commit someone else pushed are ignored, and so are cancelled and still-running ones. `factory run TASK` (or its plan) builds on the PR's branch at that head, with the failing checks and their GitHub Actions logs as the builder's feedback; review and every gate run again before the same PR is force-pushed, leased on the failing head. A stacked PR whose dependency merged or moved is restacked instead, with no agent, and goes back to `pr_open` for CI to judge. A check that passes on re-run (a flake) puts the task back to `pr_open`. If the fix fails, the task is `failed` and the PR is untouched. The gates can't run CI's own checks, so a fix that doesn't hold shows up `ci_failed` again on the next refresh.
- **Review comments:** `factory status --refresh` marks a PR `changes_requested` when an unaddressed review requests changes (a write-access reviewer's latest decision, or any submitted review by the PR's author); the latest review wins, so an approval or a dismissal after a request clears it. `factory run TASK` (or its plan) addresses them on the PR's branch: the builder gets the reviews as feedback, review and every gate run again, and the same PR is force-pushed leased on its old head with a comment naming what was addressed. A no-change answer goes on the PR as a comment and the reviews count as addressed. `factory show TASK --role human_review` shows the brief.
- **Measuring:** every agent run records a prompt version, a hash of its system prompt with the task-specific parts left out. Refresh records a `merge` run — `as_built`, or `edited` with the human's commits — when a task's PR merges and its final head can be read. `factory stats` summarises the board over a window, with per-step rows split by flow, model and prompt version.
- **PR layout:** the title is `TASK: <verifier's title>` (or the contract goal when that title is empty). The body reads `## What changed` and `## What to check` (written by the verifier, or by the factory's fallback when the verify run's outcome is `report (fallback)`), `## Checks`, then collapsed Gate table, The task, Acceptance tests when a test step committed them, and one report block per reviewer. Long reports are cut with a pointer: `factory show TASK --step STEP` prints that step's whole report, while `factory show TASK` prints the planner's plan and every agent's full report. The task's web page has the same full reports.
- **Merging is the human gate.** Merge from the bottom of a stack up, and run `factory status --refresh` after **every** merge: it records the merge and rebases and retargets the PRs stacked on it. Unless the repository deletes head branches on merge, GitHub won't retarget them itself. A stacked PR merged before that lands in its dependency's branch. If the dependency had already merged, the refresh marks the task `conflict` instead of `merged`, and `factory run TASK` replays its changes onto the trunk in a new PR. Set the repository's squash-merge default commit message to the pull request title so the verifier's title is what lands on the trunk.
- **Branches:** runs branch from origin's copy of the checkout's current branch and target it (`--base` overrides). Each run reads contracts from the checkout's working tree when it starts, uncommitted edits included.
- **Settings:** the gates, plans location, models and step limits come from `.factory/config.yaml`, always read from the main checkout. A repository can replace a role's prompt with `.factory/agents/<planner|tester|builder|reviewer|verifier|selector>.md`.

## Requests and answers

| The user asks | Answer |
|---|---|
| Start, kick off, "finish the backlog" | `export OPENROUTER_API_KEY=…` then `factory run PLAN --parallel 3 --max-cost 10 --notify`, one per plan (separate terminals are fine). Add `--network-for TASK` for tasks that must download, and `--flow NAME` to run a different agent flow than the config's `flow` (a key of `flows:`). A task whose dependency in another plan has no PR yet waits, so rerun its plan once it does. The user still merges each PR, and manual tasks stay manual |
| Run the stricter flow | `factory run TASK --flow strict` for one task, or set `flow: strict` for the repository. Set `test_paths` first: strict writes and red-checks tests before the build, resumes failed builds, runs gates before the proving review, and has no planner. Compare it with `default` through `factory bench` before drawing conclusions |
| What's happening | `factory top [PLAN]` (live, per plan: ✓ merged ◆ PR open ≠ PR conflicts ! CI fails ▶ running ✗ failed · queued ⊘ held), `factory logs TASK -f` or `factory logs --all -f`, `factory show TASK`, `factory transcript TASK --role build`, `factory trace TASK`. Each run records its flow and step; `factory show TASK` labels them and `--step NAME` filters |
| What's left | `factory status` (counters such as `2/8 merged · 2 failed · 4 waiting`) |
| How is the factory doing? / Did that prompt or model change help? | `factory stats [--since DATE] [--until DATE] [--plan P] [--json]`: outcomes, attempts, costs, gates, reworks and human edits, plus per-step rows split by flow, model and prompt version. Before/after comparisons by version are confounded by the task mix; `factory bench` is the controlled comparison. `factory show TASK --role merge` shows one merged task's record |
| Why did X fail | The diagnosis steps below |
| Will failures retry? / Rerun everything | Not between runs; within a run, up to 3 builds. Rerun the plan to retry every failed task in it once: `factory run PLAN`. One task: `factory run TASK`. Leftover worktrees are replaced automatically |
| Abandoned (or failed) → queued | `factory requeue TASK…`; the next plan run picks them up. Or run it now with `factory run TASK` |
| Hold a task | `factory abandon TASK --note "hold: <why>"`. Plan runs skip `abandoned` tasks |
| Stop a run | `factory stop TASK` (or `factory stop PLAN`): SIGTERM, then SIGKILL after `--wait SECONDS` (default 10); the task ends `failed` with a stopped note. The web page's Stop button runs the same command |
| I merged a PR | `factory status --refresh`; it records the merge when the final head can be read (a `merge` run: `factory show TASK --role merge`). Then the next PR in the stack, or `factory run PLAN` to continue (it also resolves PRs the merge put in `conflict` and fixes PRs in `ci_failed`) |
| A PR has conflicts | `factory status --refresh`, then `factory run TASK` (or `factory run PLAN`) |
| A PR's CI is red | `factory status --refresh` (marks it `ci_failed`), then `factory run TASK` (or `factory run PLAN`). `factory show TASK --role ci` shows the failing checks and the logs the builder gets. A problem with the CI runner itself (a missing tool, a broken workflow) is not the task's to fix: fix the workflow by hand |
| A review requests changes | `factory status --refresh` (marks it `changes_requested`), then `factory run TASK` (or `factory run PLAN`) to address it. `factory show TASK --role human_review` shows the brief |
| The PR body cut a report / What does `report (fallback)` mean? | Run the pointer's `factory show TASK --step STEP` for the whole report; `factory show TASK` has the planner's plan and every agent's full report, also available on the task's web page. `report (fallback)` means the verifier's summary couldn't be parsed, so the factory wrote one; the PR still opens |
| Review a factory PR | `/review-task TASK` (Codex: `$review-task TASK`) |
| New work | `/plan-workstream` (Codex: `$plan-workstream`) → plan PR → `factory sync` → `factory run PLAN` |
| Several boards | One board per `FACTORY_HOME`. Parallelism comes from `--parallel` and concurrent plan runs. Use a separate `FACTORY_HOME` for experiments |
| Several people, one backlog | Each keeps their own board; never commit `factory.db`. `factory sync && factory status --refresh` takes up the open and merged `factory/*` PRs others opened. Nothing claims a task across boards, so agree who runs which plan |
| Costs | `--max-cost USD` caps each task; `top` and `status` show spend. Keep the provider's credits topped up |
| Models, step limits | `models:` and `max_steps:` per role (`plan`, `test`, `build`, `review`, `verify`, `select`) in `.factory/config.yaml`; one-off `--model provider:model` |
| Compare flows or models | Compare flows with `factory bench run --flow A --flow B --repeat 3 --max-cost USD`; compare models by repeating `--model provider:model` on one flow. Then use `factory bench report` or `factory bench compare RUN_A RUN_B`. Fixture cases run in isolated cells without PRs, leaving the board and checkout untouched. A run spends real money, capped by `--max-cost`, so give the user the command rather than running it yourself |
| Clean the board, start again | references/board.md |

## Diagnosing a failed task

1. `factory show TASK`: read the `note` headline, for example `gave up after 3 builds: Reviewer requested changes`, `no progress (same failure twice)` or `error: …`.
2. Get the evidence: `factory show TASK --role verify` (gate table) or `--role review` (findings), and `factory logs TASK -n 80`. For a test-bearing flow, `factory show TASK --step test` shows every tester try and the red-check result.
3. Match it in references/troubleshooting.md. Separate the two kinds of failure:
   - **Infrastructure** (credits, network, a crash, a dead process): fix the cause and rerun.
   - **The agents** (reviewer loop, no changes, gates that never pass): fix the contract, give it network, or do the task by hand.
4. Report the cause, the evidence (quote the note), and the one command that fixes it.

### Strict-flow results

- **A failed test step:** run `factory show TASK --step test`. Read each try's outcome and report: `no-changes` or `out-of-scope` means its commit was unusable; `not-red` covers `the tests pass before the change` and `COMMAND selects no tests: write the tests it names`. The report also distinguishes red commands from regression commands that already pass. A bad try is discarded and retried once with the reason; after two bad tries no build runs. `no tests needed` is a pass: every test command already passed before the change (a documentation or spec task naming existing tests), the tester wrote nothing, and the build ran without locked tests. Check the contract's test commands and `test_paths` before suggesting a rerun.
- **A failed `acceptance_untouched` gate:** read the gate detail with `factory show TASK --role verify`. The candidate deleted a tester-written file or removed a line from one. The builder may add lines and other tests, but cannot change or remove a line from the test commit; this is a lock violation, not an ordinary red test. A fresh rerun writes new acceptance tests rather than letting the failed builder weaken these.
- **A review recorded `APPROVE (unproven)`:** this is not a failed review. The reviewer reported CHANGES, but the factory reproduced no failing REPRO and found no `[scope]` blocker or major, so the verdict is APPROVE. Read the findings and `## Proof` with `factory show TASK --step review`; they remain in the PR and the verifier's input for the human to judge.

## References

- `references/troubleshooting.md`: symptom → cause → fix. Read when a run failed, a task won't start, a PR looks wrong, or git refuses.
- `references/board.md`: checking for active runs and resetting the board. Read before touching factory state.
- The factory's `docs/reference.md` (every command and flag, config, troubleshooting) and `docs/architecture.md` (the pipeline, the gates, the sandbox).
