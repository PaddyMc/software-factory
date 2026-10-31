# Factory troubleshooting

Symptom → cause → fix. Find the symptom with `factory show TASK` (the `note` headline), `factory show TASK --role verify` (gate table) or `factory logs TASK -n 80`.

Contents: run failed (infrastructure) · run failed (the agents) · task won't start · PRs and merging · git and the checkout

## Run failed: infrastructure

Fix the cause, then rerun the task or its plan. Nothing is wrong with the contract.

| Symptom | Cause | Fix |
|---|---|---|
| `error: PaymentRequiredResponseError … available credits` | The provider's credits ran out. Parallel runs reserve credit for in-flight requests, so it can hit before the balance reads zero | Top up credits, then rerun the plan(s) |
| `error: … ConnectError`, `name resolution`, `EAI_AGAIN` | Network or DNS outage. Model calls retry with backoff for about 30 s, then the run fails with the real error | Rerun once the network is back |
| A Python traceback from a tool kills the whole run | A factory bug: tool exceptions are meant to come back to the model as `error: <Type>: …` | Report it against the factory; it isn't the task's fault |
| Status `DEAD` | The `factory run` process was killed or crashed | `factory status --refresh` marks it failed; rerun |
| Costs show `-` | The model isn't on OpenRouter's price list, or the list couldn't be fetched | Cosmetic, but `--max-cost` can't enforce without prices |

## Run failed: the agents

Read the evidence before rerunning. A rerun costs money and usually fails the same way.

| Symptom | Cause | Fix |
|---|---|---|
| `gave up after 3 builds: Reviewer requested changes` | The reviewer kept rejecting. Usually the acceptance is ambiguous, or the builder strays beyond the goal | `factory show TASK --role review` for the findings. Tighten the contract (plan PR, then `factory sync`) and rerun; or `--max-attempts 5`; or do it by hand |
| `The previous attempt produced no changes` | The builder ended without editing, often at its step limit (`⚠ stopped: step limit` in the log) or believing it was done | `factory transcript TASK --role build`. Narrow the task, or raise `max_steps: {build: …}` in `.factory/config.yaml` |
| `no progress (same failure twice)` | The same gates failed with identical output on two builds in a row | Read the gate table. Common causes are the next three rows |
| Gate `verification` or `e2e_tests` "inconclusive", or `tests=0` | The command's filter selects zero tests, which never counts as a pass | Fix the test name or filter in the contract |
| Gates fail on downloads (a package missing from the cache) | The sandbox is offline | Fetch dependencies on the host (`cargo fetch`, `uv sync`, `npm ci`, …); for tasks that must download, run with `--network-for TASK` (plan) or `--network` (task) |
| A tool is "not found" inside the sandbox | It lives under `$HOME`, which is hidden | Add its directory to `sandbox.ro_binds` and `sandbox.path` in `.factory/config.yaml` |

## Task won't start

| Symptom | Cause | Fix |
|---|---|---|
| `TASK waits for X (status): each dependency needs a merged or an open PR` | A dependency failed, is held (`abandoned`) or is queued, possibly in another plan | Get X a PR first (run its plan), or `--force` deliberately |
| `manual: verification runs '…', which the factory refuses` | The contract's verification needs a command agents may not run (`terraform apply`, `sudo`, `gh`, `factory …`, or the project's `denied_commands`) | By design: the user does this task by hand, never through the factory |
| A plan run skips a task | It's `abandoned` (a hold, or its PR was closed) | `factory run TASK` to run it now, or `factory requeue TASK` |
| `set OPENROUTER_API_KEY first` | The key isn't exported in that shell | Export it and run the command again |
| A plan run ends with tasks still queued | Their dependencies got no PR in this run, or they wait on another plan | `factory status PLAN`; rerun the plan once the dependency has a PR |
| `.factory/config.yaml: unknown key …` | A typo in the config | Fix it; `factory config` shows what was understood |

## PRs and merging

| Symptom | Cause | Fix |
|---|---|---|
| A stacked PR's base is `factory/<dep>` | Expected: it is built on the dependency's open PR | Merge the dependency first, then `factory status --refresh` |
| A stacked PR merged into `factory/<dep>` instead of the trunk | It was merged before the refresh retargeted it, and the repository keeps head branches after merge | Refresh after every merge and check the PR's base. If it happened, the change isn't on the trunk; rerun the task |
| `cannot stack TASK: its open dependencies conflict` | Two open dependency PRs edit the same lines | Merge one of them, refresh, rerun |
| Status `conflict`; a stacked PR's diff shows its dependency's changes | A restack hit a conflict (it retargeted the PR to the trunk already), or GitHub reports the PR conflicting | `factory run TASK` resolves it |
| Sibling PRs of one plan conflict (lockfiles, session logs) | Independent tasks ran in parallel from the same base | Merge one, `factory status --refresh` (the other becomes `conflict`), then `factory run PLAN` |
| `conflict` resolution `failed` | The builder couldn't reconcile the change, or review or gates rejected the result. The PR still has its old head | `factory show TASK --role resolve`; run the task again to rebuild it from scratch |
| A conflicting PR stays `pr_open` after refresh | GitHub hadn't computed `mergeable` yet (`UNKNOWN`) | Refresh again in a minute |
| Status `ci_failed` | A check failed on the PR's head, which is the factory's candidate | `factory show TASK --role ci` for the checks and logs; `factory run TASK` fixes it. If the cause is the CI runner (a missing tool, for example), fix the workflow by hand instead |
| `… not the factory's candidate: someone pushed to it` | A commit the factory didn't make is on the PR branch | Fix CI on that branch by hand, or `factory run TASK --force` to rebuild |
| A CI fix `failed`, or the PR goes `ci_failed` again | The builder couldn't reproduce or fix it; the gates can't run CI's own checks, so CI on the new head decides | `factory show TASK --role build`; run the task again to rebuild it from scratch, or fix by hand |
| PR edits don't apply | `gh pr edit` can fail on some repositories (a deprecated GraphQL field); the factory edits PRs through the REST API instead | By hand: `gh api -X PATCH repos/{owner}/{repo}/pulls/N -f body=…` (or `-f base=…`) |

## Git and the checkout

| Symptom | Cause | Fix |
|---|---|---|
| `git pull` fails over local changes | The checkout holds uncommitted copies of work that has since merged (e.g. a plan written here, then PR'd from a worktree) | Confirm they match: `git diff origin/<trunk> -- <files>` is empty. Then `git stash -u && git pull && git stash drop` |
| A task's PR targets an unexpected branch | Runs branch from, and target, the checkout's current branch | `git branch --show-current` before kicking off; `--base <trunk>` to override |
| A run used an old version of a contract | Each run reads contracts from the main checkout's working tree when it starts; a run already going keeps the version it started with | Pull or edit the plan before starting the run. `factory sync` refreshes the board, not running tasks |
