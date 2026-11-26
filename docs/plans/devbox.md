# Plan: Run the backlog unattended (devbox)

**Status:** Planned (2026-11-22), revised 2026-11-26 to claim each task with a draft PR. Workstream scoped; awaiting kickoff: `devbox-t01` runs once this plan is merged and synced. Roadmap: [NEXT.md item 18](../../NEXT.md#18-run-the-backlog-unattended).

## Plan at a Glance

**Problem:** The factory only makes progress while someone types commands at a terminal. Two machines working on one backlog can build the same task twice, because neither knows what the other is doing.

**Goal:** When this workstream is complete, `factory start` keeps the backlog moving on any number of machines until stopped, within a daily budget. Before a machine builds a task, it claims the task by opening its pull request as a draft. Only one machine works on a task at a time, and GitHub shows which.

**In scope:** the worker, its budget, retries and checkout updates; claiming tasks with draft PRs; releasing claims and taking over abandoned ones.

**Out of scope:** setting up machines, one shared database across machines, and webhooks: the worker checks GitHub every two minutes.

**Approach:**
1. Give each plan its own flow, then add `factory start`.
2. Add daily retries and checkout updates, and show the worker.
3. Claim tasks with draft PRs, release them when a run ends, and take over silent ones.
4. Teach every machine to read the others' claims, then document it all.

**First task:** `devbox-t01` gives each plan its own flow, so the worker starts every task on the right flow.

> **Reading guide:** Start here for the purpose and scope. Read **Execution Plan** for sequencing and review boundaries, **Task Contracts** for factory-executable work, and **Design** plus the remaining sections for implementation detail.

---

## Execution Plan

### Locked Decisions

| Decision | Choice |
|---|---|
| Devbox | **A foreground command.** `factory start` runs the backlog on whatever machine it is started on, until stopped. Keeping it alive (tmux, screen, a service you write) and setting up the box stay yours; the README says what a box needs |
| Checkout | **Fast-forward the trunk every poll.** When the checkout is on the trunk with no changes to tracked files and origin's trunk is a fast-forward ahead, the worker drains its task runs, fast-forwards and loads the contracts, so merged plans, config and (with an editable install) factory code reach the box with nobody logged in. Otherwise it leaves the checkout alone and says why |
| Budget | **A daily budget, counted from the board.** `--budget USD` is required. The day's spend is every run on the board since 00:00 UTC, so a restart doesn't reset it. At the budget the worker starts nothing and lets running tasks finish |
| Failed tasks | **Retried once a UTC day.** A failed task none of whose runs started today is startable; one that fails today, whoever ran it, waits for tomorrow. Held (abandoned) tasks never run |
| Flow per task | **`plan_flows:` in `.factory/config.yaml`.** It maps a plan to a flow. `factory start`, `factory run PLAN`, `factory run TASK` and every rework take a task's flow from it; `--flow` overrides, and `flow:` stays the fallback |
| Claims | **A draft PR per task, in this plan.** A run that will push claims its task before any agent runs. A fresh build opens the task's PR as a draft; a rework turns the open PR back into a draft. The lock is a leased push of an empty claim commit, which exactly one board can win; the draft PR is how every board and person sees it. The worker and `factory run` both claim, so a worker on a box and a run on a laptop never build one task twice |
| Claim coverage | **Fresh builds and reworks.** Conflict resolutions, CI fixes, review rework and `--force` rebuilds claim too, because every worker sees the same PR state at its refresh. `--no-pr` runs and `factory bench` claim nothing |
| Failed runs | **The draft closes, with the failure in a comment.** A failed fresh build's draft is closed and its branch deleted; a failed rework puts the PR's old head back and makes it ready again. Every board counts a claim that failed today as a run that started today, so the fleet retries a failed task once a day, not once per box |
| Stale claims | **Heartbeat and take-over.** The claiming run rewrites the claim's heartbeat at least every 5 minutes. Any board may take over a claim that has been silent for 30 minutes, with a leased push only one board can win; a claim this board made for a run whose process is gone can be taken over at once |

### Milestones

| # | Deliverable | Exit criteria | Parallelizable with |
|---|---|---|---|
| **M1** | A flow per plan | The t01 tests in `tests/test_config.py` and `tests/test_pipeline.py` pass | — |
| **M2** | `factory start` | The t02 tests in `tests/test_worker.py` pass | — |
| **M3** | Daily retries | The t03 tests in `tests/test_worker.py` pass | M5 |
| **M4** | The checkout keeps up | The t04 tests in `tests/test_worker.py` pass | M5 |
| **M5** | You can see the worker | The t05 tests in `tests/test_worker_status.py` and `tests/test_web.py` pass | M3, M4 |
| **M6** | A fresh build claims its task with a draft PR | The t07 tests in `tests/test_claims.py` pass | M3, M4 |
| **M7** | A rework claims its open PR | The t08 tests in `tests/test_claims.py` pass | M3, M4 |
| **M8** | Claims end cleanly and stale ones are taken over | The t09 tests in `tests/test_claims.py` pass | M3, M4 |
| **M9** | Every board reads the others' claims | The t10 tests in `tests/test_claims_refresh.py` pass | M3, M4 |
| **M10** | The worker and plan runs skip claimed tasks | The t11 tests in `tests/test_worker.py` and `tests/test_scheduler.py` pass | — |
| **M11** | Docs | `tests/test_templates.py::test_the_docs_describe_the_worker` and `test_the_docs_describe_claims` pass, and `tests/test_templates.py` passes | — |

**Sequence:** `M1 → M2 → (M3 → M4) ∥ (M5 → M6 → M7 → M8 → M9) → M10 → M11`. Task IDs keep their numbers from the first version of this plan, so the claim tasks are t07 to t11 and the docs task stays t06, last. File overlaps:
- t01 and t02 share `factory/cli.py`.
- t02, t03, t04 and t11 share `factory/worker.py` and `tests/test_worker.py`.
- t05 changes `factory/observe.py`, `cmd_status` and `cmd_top` in `factory/cli.py`, `factory/web/views.py`, `tests/test_worker_status.py` and `tests/test_web.py`.
- t07 to t10 share `factory/claims.py`, `factory/cli.py`, `factory/pipeline.py` and `tests/conftest.py`'s fake `gh`, and t10 changes `factory/db.py` and `factory/stack.py`.

So the claim chain follows t05 one task at a time, and runs beside t03 and t04, which change only the worker.

### Task Contracts

| Milestone | Task IDs | Coverage |
|---|---|---|
| **M1** | `devbox-t01` | `plan_flows` and `Config.flow_for` in `factory/config.py`; the flow choice in `cmd_run_one`, `cmd_run_plan` and `cmd_sync` in `factory/cli.py`; tests in `tests/test_config.py` and `tests/test_pipeline.py` |
| **M2** | `devbox-t02` | New `factory/worker.py`; `factory start` and `factory stop worker` in `factory/cli.py`; `DB.spent_today` in `factory/db.py`; new `tests/test_worker.py` |
| **M3** | `devbox-t03` | The daily retry rule in `factory/worker.py`; tests in `tests/test_worker.py` |
| **M4** | `devbox-t04` | Updating the checkout, draining and the restart in `factory/worker.py`; tests in `tests/test_worker.py` |
| **M5** | `devbox-t05` | The worker's line in `factory/observe.py`, `factory status`, `factory top` and the web board; new `tests/test_worker_status.py`, tests in `tests/test_web.py` |
| **M6** | `devbox-t07` | New `factory/claims.py`: the board id, the claim commit, the draft PR and its claim block; claiming in `cmd_run_one` in `factory/cli.py`; the claimed draft becoming the task's PR in `Pipeline.pr` in `factory/pipeline.py`; draft PRs in `tests/conftest.py`'s fake `gh`; new `tests/test_claims.py` |
| **M7** | `devbox-t08` | Claiming an open PR for conflict, CI and review reworks and `--force` rebuilds in `factory/claims.py`, `factory/cli.py` and `factory/pipeline.py`; tests in `tests/test_claims.py` |
| **M8** | `devbox-t09` | Releasing a claim when a run fails or stops, the heartbeat, and taking over stale claims in `factory/claims.py`, `factory/cli.py` and `factory/pipeline.py`; tests in `tests/test_claims.py` |
| **M9** | `devbox-t10` | Reading claims, failed claims and other boards' pushes in the refresh (`_adopt`, `_refresh` in `factory/cli.py`); the candidate marker in `factory/pipeline.py` and `factory/stack.py`; claim columns and readiness in `factory/db.py`; new `tests/test_claims_refresh.py` |
| **M10** | `devbox-t11` | Skipping claimed tasks and counting failed claims in the daily retry in `factory/worker.py` and `factory/scheduler.py`; tests in `tests/test_worker.py` and `tests/test_scheduler.py` |
| **M11** | `devbox-t06` | The worker, plan_flows and claims in `docs/reference.md`, `docs/architecture.md`, `README.md`, `NEXT.md` and the factory-ops skill (template and installed copy); new tests in `tests/test_templates.py` |

```yaml
- id: devbox-t01
  goal: "`plan_flows:` in .factory/config.yaml maps a plan to the flow its tasks run on. `factory run PLAN`, `factory run TASK` and every rework take a task's flow from it unless `--flow` is given, and the config's `flow` stays the fallback"
  spec_refs:
    - "docs/plans/devbox.md#a-flow-per-plan"
    - "factory/config.py"
    - "factory/cli.py"
  depends_on: []
  non_goals:
    - "A flow per task within one plan"
    - "The worker (devbox-t02)"
    - "Changing this repository's .factory/config.yaml"
  acceptance:
    - "Config has a `plan_flows` field, a dict from plan name to flow name, empty by default. A plan name is what `factory run PLAN` takes: the plan file's name without `.md`"
    - "Loading a config whose plan_flows names a flow that is neither defined nor built in raises ConfigError `plan_flows.NAME: unknown flow FLOW (flows: ...)`, with the flows listed in sorted order. A plan_flows that isn't a mapping of strings to strings raises ConfigError `plan_flows must map plan names to flow names`"
    - "`Config.flow_for(plan, override=None)` returns the Flow named by override, else the one plan_flows gives the plan, else the one `flow` names. An override that names no flow raises ConfigError `unknown flow NAME (flows: ...)`"
    - "`factory run TASK` without `--flow` runs on the flow plan_flows gives the task's plan, so its runs record that flow, and `--flow` overrides it. The same holds when the run resolves a conflict, fixes CI or addresses a review. Provider keys and test_paths are checked for that flow"
    - "`factory run PLAN` without `--flow` passes `--flow` with the plan's flow from plan_flows to every task it starts, and checks provider keys and test_paths for that flow. With `--flow`, that flow is used for every task, as today"
    - "`factory sync` prints `warning: plan_flows names NAME, which matches no plan` for each plan_flows key that matches no plan it loaded, and still exits 0"
    - "`factory config` shows plan_flows"
    - "A config without plan_flows behaves as today, and the existing tests pass unmodified"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_config.py::test_plan_flows_name_a_known_flow_for_a_plan tests/test_pipeline.py::test_a_task_runs_on_its_plans_flow_unless_flow_is_given tests/test_pipeline.py::test_a_plan_run_gives_its_tasks_the_plans_flow tests/test_pipeline.py::test_sync_warns_about_plan_flows_that_match_no_plan"
    - "uv run pytest -q tests/test_config.py tests/test_flows.py tests/test_scheduler.py tests/test_pipeline.py"
  risk: low

- id: devbox-t02
  goal: "`factory start --budget USD` runs the board's ready tasks across every plan as a foreground worker that keeps going. Every poll it loads the contracts and checks GitHub; it starts each startable task on its plan's flow, up to `--parallel` at once; it waits when nothing can start; and it starts nothing once the day's spend reaches the budget"
  spec_refs:
    - "docs/plans/devbox.md#the-worker"
    - "docs/plans/devbox.md#choosing-tasks"
    - "docs/plans/devbox.md#the-budget"
    - "docs/plans/devbox.md#stopping-and-worker-json"
    - "factory/scheduler.py"
    - "factory/cli.py"
    - "factory/db.py"
  depends_on:
    - devbox-t01
  non_goals:
    - "Retrying failed tasks (devbox-t03)"
    - "Updating the checkout (devbox-t04)"
    - "Showing the worker in status, top or the web page (devbox-t05)"
    - "Installing a service, building a container image or setting up a box"
    - "Claiming tasks with draft PRs (devbox-t07 to devbox-t11)"
    - "Changing `factory run PLAN`"
  acceptance:
    - "`factory start` takes `--budget USD` (required, greater than 0), `--plan NAME` (repeatable; default every plan), `--parallel N` (default 3), `--poll SECONDS` (default 120) and `--until-idle`. It also takes `--base`, `--flow`, `--model`, `--max-cost`, `--max-attempts`, `--network-for`, `--skip-gates` and `--no-sandbox`, with their `factory run` meanings. It runs in the foreground and logs one timestamped line per event, as a plan run does. An unknown `--plan` exits 1 with `NAME is not a plan (a plan's file name without .md)`"
    - "At start, and then every `--poll` seconds, it loads every contract from the checkout into the board as `factory sync` does, then runs the refresh that `factory status --refresh` runs. Between polls it checks its task runs every 5 seconds"
    - "A task is startable when its plan is selected and its status is queued, conflict, ci_failed or changes_requested. Every dependency must also be merged or have an open PR, the factory must be able to run it (it isn't manual), and no live process may be running it. The worker starts startable tasks as child `factory run TASK --quiet` processes, up to `--parallel` at once. Plans go in file-name order and each plan's tasks in dependency order. Each child gets `--flow` with the task's flow from Config.flow_for, plus the pass-through flags. A task with an open dependency stacks on it, as in a plan run"
    - "An abandoned task is never started, and a failed task isn't started (devbox-t03 adds daily retries). A task whose child run exits with the task still queued is not started again by this worker, and the worker logs the last line of the child's stderr"
    - "`DB.spent_today()` returns the sum of cost_usd over the board's runs that started since 00:00 UTC today, whoever ran them, counting a run without a cost as 0"
    - "When the day's spend is at or over the budget, the worker starts nothing and lets running task runs finish. It logs once `budget reached: $SPENT of $BUDGET today; starting nothing until 00:00 UTC`, and after UTC midnight it starts tasks again. Each task it starts gets `--max-cost` set to the smaller of `--max-cost` and the budget left at that moment"
    - "At start, for each model of the selected plans' flows that has no known price, it logs `warning: no price for MODEL; its runs don't count toward --budget`"
    - "When nothing is running and nothing can start, it logs one line saying what it waits for, and only when that changes. The line names the open PRs waiting for a merge or a review, or the tasks waiting for a dependency, or says the selected plans have nothing left to run"
    - "With `--until-idle` it exits 0 after a poll at which nothing is running and nothing can start. Without it, it runs until stopped"
    - "It writes $FACTORY_HOME/worker.json with its pid, start time, budget, selected plans, state (`working`, `waiting` or `budget`), a one-line detail and the time of the last update. It rewrites the file when any of these change, and removes it when it exits. When worker.json names a live process, `factory start` exits 1 with `a worker is already running on this board (pid PID); factory stop worker stops it`"
    - "`factory stop worker` sends the worker SIGTERM. The worker terminates its task runs, which end failed with the stop note as a plan run's do, removes worker.json and exits 1. Ctrl-C stops the worker but leaves its task runs running in the background, as a plan run does, and exits 0. With no worker running, `factory stop worker` prints `nothing to stop: no worker is running` and exits 0"
    - "It exits 1 before starting anything when a provider key that a selected plan's flow needs is unset, or when a flow with a test step has no test_paths, printing the message `factory run PLAN` prints"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_worker.py::test_start_runs_ready_tasks_across_plans_up_to_parallel tests/test_worker.py::test_each_task_gets_its_plans_flow_and_a_max_cost_within_the_budget tests/test_worker.py::test_dependents_start_once_their_dependency_has_a_pr tests/test_worker.py::test_open_prs_that_need_rework_are_started tests/test_worker.py::test_the_worker_starts_nothing_at_the_days_budget tests/test_worker.py::test_held_and_refused_tasks_are_not_started tests/test_worker.py::test_until_idle_exits_once_nothing_runs_or_can_start tests/test_worker.py::test_one_worker_per_board_and_stop_worker_stops_it tests/test_worker.py::test_start_until_idle_runs_the_backlog_to_prs"
    - "uv run pytest -q tests/test_worker.py tests/test_scheduler.py tests/test_stop.py tests/test_db.py"
  risk: medium

- id: devbox-t03
  goal: "The worker retries each failed task at most once per UTC day. A failed, ready task none of whose runs started today is startable, so a task that fails today waits for tomorrow, whoever ran it"
  spec_refs:
    - "docs/plans/devbox.md#failed-tasks"
    - "factory/worker.py"
  depends_on:
    - devbox-t02
  non_goals:
    - "Retrying abandoned (held) tasks"
    - "More than one retry a day, or backing off over several days"
    - "Changing the retry rule of `factory run PLAN`"
    - "Updating the checkout (devbox-t04)"
  acceptance:
    - "A task with status failed is startable by the worker when the rest of devbox-t02's rule holds and none of its runs on the board started since 00:00 UTC today. The worker starts it as `factory run TASK`, so a failed rework rebuilds as that command does today"
    - "When it starts one, the worker logs `retry  TASK (failed: NOTE)`, with NOTE the first line of the task's note clipped to 140 characters"
    - "A failed task whose latest run started today isn't started again that day, including one that failed in a run the worker started. After the next UTC midnight it is startable again"
    - "An abandoned task is never started, whatever its runs"
    - "When failed tasks wait for tomorrow, the waiting line ends with `N failed task(s) retry after 00:00 UTC`"
    - "Retries spend from the same daily budget as every other run"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_worker.py::test_a_failed_task_is_retried_once_a_day tests/test_worker.py::test_a_task_that_failed_today_waits_for_tomorrow tests/test_worker.py::test_held_tasks_are_never_retried"
    - "uv run pytest -q tests/test_worker.py tests/test_scheduler.py"
  risk: low

- id: devbox-t04
  goal: "Each poll, the worker brings the checkout up to date. It does so when the checkout is on the trunk with no changes to tracked files and origin's trunk is a fast-forward ahead. It starts nothing new, waits for the board's task runs to finish, fast-forwards, and loads the contracts. When the update changed the factory code it runs from, it restarts itself"
  spec_refs:
    - "docs/plans/devbox.md#updating-the-checkout"
    - "factory/worker.py"
    - "factory/pipeline.py"
  depends_on:
    - devbox-t03
  non_goals:
    - "Updating a checkout with changes to tracked files, with local commits, or on another branch"
    - "Reinstalling the factory or its dependencies"
    - "Fetching or updating any branch but the trunk"
    - "Showing the worker elsewhere (devbox-t05)"
  acceptance:
    - "The worker's trunk is `--base`, else the branch checked out when `factory start` starts. With a detached HEAD and no `--base`, `factory start` exits 1 with `the checkout has no branch checked out: check out the trunk or pass --base`"
    - "At each poll, before it loads the contracts, the worker fetches origin's trunk. Suppose origin's trunk is ahead of HEAD and HEAD is its ancestor, the checkout is on the trunk, and no tracked file has changes. Then the worker starts no new task and sets its state to `draining`, with the detail `origin/TRUNK is N commit(s) ahead; updating once K task run(s) finish`. Once no task on the board runs in a live process, it runs `git merge --ff-only` to origin's trunk, logs `updated TRUNK: OLD..NEW (N commits)` with short hashes, and loads the contracts"
    - "Otherwise it leaves the checkout alone and keeps working. It logs once per distinct reason one of: `not updating TRUNK: the checkout has changes to tracked files`, `not updating TRUNK: it has N commit(s) origin doesn't`, `not updating TRUNK: the checkout is on BRANCH`, or `not updating TRUNK: can't reach origin (ERROR)`. Untracked files don't block an update"
    - "When the factory package the worker runs from lies inside the checkout (an editable install) and the update changed a file under that package's directory, the worker logs `restarting on the updated factory code`. It then replaces its process with the same command line, which keeps its pid and worker.json"
    - "When the update changed pyproject.toml or uv.lock, it logs `pyproject.toml or uv.lock changed: reinstall the factory if its dependencies changed`"
    - "The worker never commits, pushes, resets, stashes or cleans the checkout"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_worker.py::test_the_worker_fast_forwards_the_trunk_once_runs_finish tests/test_worker.py::test_a_checkout_it_cannot_fast_forward_is_left_alone_and_reported tests/test_worker.py::test_new_factory_code_restarts_the_worker tests/test_worker.py::test_a_detached_checkout_needs_base"
    - "uv run pytest -q tests/test_worker.py"
  risk: medium

- id: devbox-t05
  goal: "`factory status`, `factory top` and the web board show the worker: whether one is running, since when, its state and detail, and the day's spend against its budget"
  spec_refs:
    - "docs/plans/devbox.md#what-you-see"
    - "factory/observe.py"
    - "factory/cli.py"
    - "factory/web/views.py"
  depends_on:
    - devbox-t02
  non_goals:
    - "Starting or stopping the worker from the web page"
    - "Notifications"
    - "A history of past workers"
    - "Changing factory/worker.py"
  acceptance:
    - "`observe.worker_line(db, home)` reads $FACTORY_HOME/worker.json. For a live pid it returns `worker: pid PID since HH:MM UTC · STATE · $SPENT of $BUDGET today · DETAIL`, with SPENT from DB.spent_today() to two decimals. For a dead pid it returns `worker: pid PID is gone (last update HH:MM UTC); factory start starts a new one`. With no file, or one it can't parse, it returns None"
    - "`factory status` prints the worker's line first when there is one. `factory status --json` is unchanged"
    - "`factory top` shows the worker's line under its header"
    - "The web board shows the worker's line above the plans, escaped, in an element with class `worker`. With no worker there is no such element"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_worker_status.py::test_status_and_top_show_the_worker tests/test_worker_status.py::test_a_dead_worker_is_shown_as_gone tests/test_worker_status.py::test_no_worker_means_no_line tests/test_web.py::test_the_board_shows_the_worker"
    - "uv run pytest -q tests/test_worker_status.py tests/test_observe.py tests/test_web.py"
  risk: low

- id: devbox-t06
  goal: "The docs describe the worker, plan_flows and claims: docs/reference.md, docs/architecture.md, README.md, NEXT.md and the factory-ops skill, in its template and installed copy"
  spec_refs:
    - "docs/plans/devbox.md#design"
    - "docs/plans/devbox.md#claims"
    - "docs/reference.md"
    - "docs/architecture.md"
    - "README.md"
    - "NEXT.md"
  depends_on:
    - devbox-t11
  non_goals:
    - "Changing behaviour"
    - "A service unit, a container image or a setup script"
  acceptance:
    - "docs/reference.md lists `factory start` with every flag and its default, and `factory stop worker`, and describes plan_flows with the other config keys. Its troubleshooting table has rows for `a worker is already running on this board`, `budget reached` and each `not updating TRUNK` reason"
    - "docs/reference.md says `factory run TASK` exits 75 when another board holds the task's claim, and its troubleshooting table has rows for `claimed by HOST since`, `the claim was taken over by HOST; nothing pushed` and `GitHub refused a draft PR`"
    - "docs/architecture.md has a section headed `## The worker` that covers the poll (load, refresh), which tasks start, each task's flow, the daily budget, daily retries, updating the checkout with draining and the restart, worker.json, and the signals. It states the budget's bound: up to `--parallel` runs may each spend up to the budget that was left when they started. Its Policy says the worker fast-forwards the main checkout's trunk and spends within the budget unattended, while agents still never commit to the checkout"
    - "docs/architecture.md has a section headed `### Claims` under `## The worker`. It covers the claim commit and its leased push, the draft PR and its claim block, which runs claim, the heartbeat and the 30-minute take-over, how a failed or stopped run ends its claim, what other boards' refreshes do with claims and the candidate marker, and exit status 75. Its known limitations no longer say that two boards can run the same task at once. They say a repository without draft PRs runs unclaimed, and that a rework's claim commit can dismiss approvals where branch protection dismisses stale reviews"
    - "README.md has a section headed `## Run it on a devbox`. It covers what the box needs (Linux, bwrap, uv, git, an authenticated gh, and the provider key in the worker's environment), cloning and installing (editable for the factory itself), `factory sync`, and `factory start --budget USD` in a terminal multiplexer. It covers watching from another machine with `factory web --no-open` and `ssh -L 8765:127.0.0.1:8765 HOST`. It says keeping the worker alive is up to the box: tmux, screen or a service you write. It says several boxes can work one backlog, each with its own board, because every run claims its task with a draft PR, and that each box's `--budget` counts only that box's spend"
    - "NEXT.md's item 18 row and section say the worker is done and link docs/architecture.md#the-worker. Item 6 says several boxes can share one backlog through claims, while a shared board for one live view of every box stays open"
    - "The factory-ops skill has request rows for running the backlog unattended (`factory start --budget USD`), stopping the worker, choosing a plan's flow with plan_flows, and a task claimed by another board (what the claim says, and that a run takes over a claim silent for 30 minutes). They are in factory/templates/skills/factory-ops/SKILL.md and .claude/skills/factory-ops/SKILL.md, which stay identical"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_templates.py::test_the_docs_describe_the_worker tests/test_templates.py::test_the_docs_describe_claims"
    - "uv run pytest -q tests/test_templates.py"
  risk: low

- id: devbox-t07
  goal: "A `factory run TASK` fresh build that will open a PR claims its task before any agent runs. It pushes an empty claim commit that creates `factory/TASK` only if no branch of that name exists, then opens the task's PR as a draft with a claim block. A run that loses the claim builds nothing and exits 75. A run that passes its gates pushes its candidate over the claim commit, sets the PR's title and body, and marks it ready for review"
  spec_refs:
    - "docs/plans/devbox.md#claims"
    - "docs/plans/devbox.md#the-lock"
    - "docs/plans/devbox.md#the-claim-block"
    - "factory/cli.py"
    - "factory/pipeline.py"
    - "tests/conftest.py"
  depends_on:
    - devbox-t05
  non_goals:
    - "Claiming an open PR for a rework or a `--force` rebuild (devbox-t08)"
    - "Ending a claim when a run fails or stops, the heartbeat, or taking over a claim that has a draft PR (devbox-t09)"
    - "Reading other boards' claims in the refresh (devbox-t10)"
    - "Changing the worker or plan runs (devbox-t11)"
    - "Claiming for `--no-pr` runs or `factory bench`"
  acceptance:
    - "`claims.board_id(home)` in the new factory/claims.py returns the id stored in $FACTORY_HOME/board-id. It creates the file on first use with 12 random lowercase hex characters, so a board keeps one id across runs and restarts, and two FACTORY_HOMEs on one machine are two boards"
    - "A fresh build of a task that has no open PR, run without `--no-pr`, claims the task after its base is chosen and before its worktree is created or any agent runs. The claim commit is an empty commit whose parent is the base sha, made with `git commit-tree`, so no ref, file or index of the checkout changes. Its message is `factory: claim TASK [skip ci]` with the trailers `Factory-Board: ID` and `Factory-Host: HOST`. The run pushes it to `refs/heads/factory/TASK` with `--force-with-lease=refs/heads/factory/TASK:`, which the remote applies only when that branch doesn't exist"
    - "When `factory/TASK` exists on origin with no open PR, and its head isn't a claim commit committed less than 1800 seconds ago, the branch is a leftover. The run claims over it with a push leased on its head, as a fresh build replaced such a branch before"
    - "After the claim push the run opens the task's PR with `gh pr create --draft` against the run's base (the trunk, or the dependency's branch when stacked), titled as `pr_title` titles a PR without a summary. The body is the claim block. Its first line is `<!-- factory-claim JSON -->`, with JSON an object with the keys board, host, kind (`build`), since and heartbeat, the last two UTC ISO times. One plain sentence follows, saying the factory is building the task on HOST since HH:MM UTC and the draft becomes ready for review when its gates pass. `claims.parse(body)` returns the block's fields, or None for a body without one. The task's pr_url is the draft's url"
    - "When the claim push is rejected because the branch exists, the run creates no worktree and runs no agent, and leaves the task's status as it was. It sets the task's note to `claimed by HOST since HH:MM UTC: URL` when the branch's open PR has a claim block, `factory/TASK already has an open PR: URL` when it has an open PR without one, or `claimed: factory/TASK was just created on origin` otherwise. It prints the note to stderr and exits 75. Any other failure of the push exits 1 with `can't push the claim: MESSAGE`, before any agent runs"
    - "When the gates pass, the pr step pushes the candidate to `factory/TASK` with `--force-with-lease=refs/heads/factory/TASK:CLAIM`, CLAIM being the claim commit's sha, so the claim commit is never one of the PR's commits. It then sets the PR's title and body as a new PR's are set today, through the REST API (`gh api -X PATCH`). It marks the PR ready for review with GraphQL's markPullRequestReadyForReview through `gh api graphql`. The task ends pr_open with that PR's url, as today"
    - "When `gh pr create --draft` fails because the repository doesn't allow draft PRs, the run deletes the claim branch with a push leased on the claim commit, prints `warning: GitHub refused a draft PR (MESSAGE); running without a claim`, and then runs and opens its PR as today. Any other failure to open the draft deletes the branch the same way and fails the run with `can't open the claim draft: MESSAGE`"
    - "Three kinds of run take no claim and make no new gh call: a `--no-pr` run; a run on a task's open PR (a resolve, ci or human_review run, or `--force` on a task whose PR is open, judged before `--force` clears the task's PR fields); and `factory bench`. tests/test_bench.py's check that bench makes no gh call passes unchanged"
    - "tests/conftest.py's fake gh keeps each PR's draft state. `pr create --draft` makes a draft, `pr list` and `pr view` report isDraft and body when asked, `api graphql` with markPullRequestReadyForReview makes the PR ready, and `api -X PATCH` changes its title, body and state. tests/test_pipeline.py's test_a_new_pr_is_titled_with_the_verifiers_title checks the PR's final title instead of the `pr create` call. Other existing tests change only where they assert gh calls that the claim adds"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_claims.py::test_the_board_id_is_made_once_and_kept tests/test_claims.py::test_a_fresh_run_opens_a_draft_pr_before_any_agent_runs tests/test_claims.py::test_a_leftover_branch_is_claimed_over tests/test_claims.py::test_a_run_that_loses_the_claim_builds_nothing_and_exits_75 tests/test_claims.py::test_the_claimed_draft_becomes_the_tasks_pr tests/test_claims.py::test_a_repository_without_drafts_runs_unclaimed tests/test_claims.py::test_no_pr_runs_and_open_prs_take_no_new_claim"
    - "uv run pytest -q tests/test_claims.py tests/test_pipeline.py tests/test_bench.py tests/test_stack.py tests/test_reviews.py tests/test_ci.py"
  risk: high

- id: devbox-t08
  goal: "A run that rebuilds on an open PR claims that PR first: a conflict resolution, a CI fix, a review rework, or a `--force` rebuild of a task with an open PR. It pushes an empty claim commit on the PR's head, leased on that head, turns the PR into a draft and puts a claim block above its body. A run that loses the claim changes nothing and exits 75. A run that pushes replaces the claim commit and makes the PR ready again"
  spec_refs:
    - "docs/plans/devbox.md#reworks"
    - "docs/plans/devbox.md#the-claim-block"
    - "factory/claims.py"
    - "factory/cli.py"
    - "factory/pipeline.py"
  depends_on:
    - devbox-t07
  non_goals:
    - "Ending a claim when a run fails or stops, the heartbeat, or stale claims (devbox-t09)"
    - "Claiming restacks, which stay leased pushes made by the refresh"
    - "Reading other boards' claims in the refresh (devbox-t10)"
  acceptance:
    - "Before its worktree is created and before any agent runs, a resolve, ci or human_review run, or a `--force` run of a task whose PR is open, makes an empty claim commit whose parent is the PR's head (the task's candidate_sha). It carries the message and trailers devbox-t07 gives a claim commit. The run pushes it to `factory/TASK` with `--force-with-lease=refs/heads/factory/TASK:HEAD`, HEAD being that head"
    - "After the push the run turns the PR into a draft with GraphQL's convertPullRequestToDraft through `gh api graphql`. It puts the claim block above the PR's body and keeps the body below it unchanged. The block's kind is `resolve`, `ci` or `human_review`, or `build` for `--force`"
    - "When that push is rejected, the run creates no worktree, runs no agent, and leaves the PR and the task's status and candidate as they were. It sets the note `claimed by HOST since HH:MM UTC: URL` when the PR's body has another board's claim block, or `its PR moved: head is now SHA` otherwise. It prints the note to stderr and exits 75"
    - "The rework builds from the PR's head as it was before the claim, and its push is leased on the claim commit, so the PR's commits never include the claim commit. After the push, the PR's body is the new body without the claim block, the PR is ready for review again (markPullRequestReadyForReview), and the comment a rework posts today is posted"
    - "A review rework whose builder answers without changing the head pushes the PR's old head back, leased on the claim commit. It puts the PR's body back without the claim block, marks the PR ready, and posts the answer as today"
    - "When GitHub refuses to turn the PR into a draft because the repository doesn't allow drafts, the run pushes the old head back, leased on the claim commit. It prints `warning: GitHub refused a draft PR (MESSAGE); running without a claim` and runs as today"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_claims.py::test_a_ci_rework_claims_its_pr_as_a_draft_first tests/test_claims.py::test_a_rework_that_loses_the_claim_changes_nothing tests/test_claims.py::test_a_pushed_rework_replaces_the_claim_commit_and_is_ready tests/test_claims.py::test_an_answered_review_puts_the_old_head_back tests/test_claims.py::test_a_forced_rebuild_claims_the_open_pr"
    - "uv run pytest -q tests/test_claims.py tests/test_pipeline.py tests/test_reviews.py tests/test_ci.py tests/test_stack.py"
  risk: medium

- id: devbox-t09
  goal: "A claim ends with its run. A fresh build that fails or is stopped closes its draft with the failure in a comment and deletes its branch. A rework that fails or is stopped puts the PR's old head and body back and makes it ready. While a run holds a claim it rewrites the claim's heartbeat at least every 5 minutes. A run may take over a claim whose heartbeat is 30 minutes old, or a claim of this board whose run's process is gone"
  spec_refs:
    - "docs/plans/devbox.md#heartbeat-and-take-over"
    - "docs/plans/devbox.md#ending-a-claim"
    - "factory/claims.py"
    - "factory/cli.py"
    - "factory/pipeline.py"
  depends_on:
    - devbox-t08
  non_goals:
    - "Reading claims or failed claims in the refresh (devbox-t10)"
    - "A command that releases a claim by hand"
    - "Ending a claim when the run's process is killed with SIGKILL or its box dies; the take-over covers those"
  acceptance:
    - "A claimed fresh build that ends failed closes its draft PR through `gh api -X PATCH` with state closed. That includes a run stopped by `factory stop TASK` or interrupted with Ctrl-C. The run replaces the claim block's first line with `<!-- factory-claim-failed JSON -->`, JSON having the keys board, host and at. It posts the comment `The factory's run on HOST failed: NOTE`, NOTE being the first line of the task's note, and deletes `factory/TASK` with a push leased on the claim commit"
    - "A claimed rework or `--force` rebuild that ends failed or stopped pushes the PR's old head back, leased on the claim commit. It puts the PR's body back without the claim block, marks the PR ready for review, and posts the same comment. The PR stays open and the task's candidate_sha stays the old head"
    - "While a run holds a claim, a background timer rewrites the claim block's heartbeat with the current UTC time at least every claims.HEARTBEAT (300) seconds, through `gh api -X PATCH`. A heartbeat that can't reach GitHub is logged and tried again at the next tick, and doesn't stop the run. The timer stops when the run ends, however it ends, and no gh call is made for the claim after that"
    - "A claim on a task's PR is stale when its heartbeat is more than claims.TTL (1800) seconds old. It is also stale when its board is this board and no live process on this board runs the task. A fresh build or rework that finds a stale claim takes it over. It pushes its own claim commit, leased on the stale claim commit; the new commit's parent is the run's base for a fresh build, or the stale claim commit's parent for a rework. It sets the draft's base to the run's base, rewrites the claim block with its own board, host and times, and posts `Took over the claim from HOST, silent since HH:MM UTC.` When two runs try at once, exactly one push succeeds and the other run exits 75 as devbox-t07 says"
    - "A run pushes nothing and fails with `the claim was taken over by HOST; nothing pushed` in two cases: the claim block names another board when the run is about to push, or the leased push of its candidate is rejected because the claim commit moved. It leaves the PR as it is"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_claims.py::test_a_failed_fresh_build_closes_its_draft_and_deletes_its_branch tests/test_claims.py::test_a_failed_rework_puts_the_pr_back tests/test_claims.py::test_a_stopped_run_ends_its_claim tests/test_claims.py::test_the_heartbeat_is_rewritten_every_five_minutes tests/test_claims.py::test_a_stale_claim_is_taken_over_by_one_run tests/test_claims.py::test_this_boards_claim_from_a_dead_run_is_taken_over_at_once tests/test_claims.py::test_a_run_whose_claim_was_taken_over_pushes_nothing"
    - "uv run pytest -q tests/test_claims.py tests/test_pipeline.py tests/test_stop.py"
  risk: high

- id: devbox-t10
  goal: "Every board's refresh reads claims. A task whose PR carries another board's claim block is recorded as claimed, and isn't taken up, stacked on or marked for rework. A claim closed as failed is recorded with its time. A head pushed by another board's factory, as the PR body's candidate marker names it, becomes the task's candidate instead of being left to whoever pushed it. `factory status`, `factory top` and the web board say which board holds a claim"
  spec_refs:
    - "docs/plans/devbox.md#what-other-boards-do"
    - "docs/plans/devbox.md#the-claim-block"
    - "factory/cli.py"
    - "factory/db.py"
    - "factory/stack.py"
    - "factory/pipeline.py"
  depends_on:
    - devbox-t09
  non_goals:
    - "The worker's or a plan run's choice of tasks (devbox-t11)"
    - "Taking over stale claims in the refresh; only runs take over (devbox-t09)"
    - "A shared database between boards"
  acceptance:
    - "The tasks table gains the columns claim and claim_failed_at, added to older databases on open as other columns are. claim holds the claim block's JSON while another board holds the task's PR, else null. claim_failed_at holds the UTC time a claim on the task last closed as failed, else null"
    - "The refresh asks gh for isDraft and body when it lists factory PRs. Take a queued or failed task whose open PR on `factory/TASK` is a draft with another board's claim block. It isn't taken up as pr_open: its claim is recorded, and its status, pr_url and candidate stay as they were, so no dependent stacks on the claim. The claim is cleared once the PR has no claim block, and a PR that is no longer a draft is then taken up as today"
    - "A task with an open PR on this board, whose PR has another board's claim block, isn't marked conflict, ci_failed or changes_requested while the claim lasts, and its claim is recorded"
    - "Every push the factory makes to a task's PR, from the pr step and from a restack, leaves the PR's body ending with `<!-- factory-candidate SHA -->`, SHA being the pushed head. Suppose the refresh finds that a PR's head differs from the task's candidate_sha and equals the SHA in that marker. Then it records the head as candidate_sha and its merge base with the PR's base as base_sha, and carries on as it does for the board's own candidate. A head that differs from both is left to whoever pushed it, as today"
    - "A restack whose leased push is rejected changes nothing on the board. It prints `TASK: its PR moved; the next refresh takes up its head`, and the refresh carries on"
    - "A closed PR on `factory/TASK` whose body starts with a factory-claim-failed block sets the task's claim_failed_at to the block's time, when that is later than the time recorded"
    - "DB.readiness of a task with a recorded claim says `claimed on HOST since HH:MM UTC: URL`. When the claim's heartbeat is older than claims.TTL it says `claim on HOST silent since HH:MM UTC; a run takes it over`. So `factory status`, `factory top` and the web board show it. A claim this board holds isn't recorded"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_claims_refresh.py::test_refresh_records_another_boards_claim_without_taking_it_up tests/test_claims_refresh.py::test_a_claimed_pr_is_not_marked_for_rework tests/test_claims_refresh.py::test_another_boards_factory_push_becomes_the_candidate tests/test_claims_refresh.py::test_a_human_push_is_still_left_to_whoever_pushed tests/test_claims_refresh.py::test_a_failed_claim_is_recorded_with_its_time tests/test_claims_refresh.py::test_readiness_names_the_board_holding_a_claim tests/test_claims_refresh.py::test_a_rejected_restack_push_waits_for_the_next_refresh"
    - "uv run pytest -q tests/test_claims_refresh.py tests/test_claims.py tests/test_stack.py tests/test_reviews.py tests/test_ci.py tests/test_db.py tests/test_observe.py tests/test_web.py"
  risk: high

- id: devbox-t11
  goal: "The worker and `factory run PLAN` don't start a task while another board holds a live claim on it, and start a task whose claim is stale. They start again later a task whose run lost its claim (exit 75). They count a claim that failed today, on any board, as a run that started today"
  spec_refs:
    - "docs/plans/devbox.md#what-the-worker-does-with-claims"
    - "factory/worker.py"
    - "factory/scheduler.py"
  depends_on:
    - devbox-t04
    - devbox-t10
  non_goals:
    - "Changing how runs claim, end or take over claims (devbox-t07 to devbox-t09)"
    - "Changing the refresh (devbox-t10)"
    - "Showing claims anywhere new"
  acceptance:
    - "Neither the worker nor a plan run starts a task whose recorded claim has a heartbeat within claims.TTL. A task whose claim is older is startable under the other rules, so its run takes the claim over"
    - "Both log a child `factory run TASK` that exits 75 as `claimed TASK: NOTE`. That exit counts as neither refused nor failed. The worker may start the task again at a later poll, once the refresh no longer records a live claim; a plan run doesn't start it again in the same run"
    - "devbox-t03's daily rule also holds back a failed task whose claim_failed_at is since 00:00 UTC today, so a task that failed today on another board waits for tomorrow"
    - "When nothing can start and some tasks are claimed by other boards, the worker's waiting line ends with `N task(s) claimed by other boards`. A plan run's summary marks each such task `claimed on HOST`"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_worker.py::test_the_worker_skips_tasks_claimed_by_other_boards tests/test_worker.py::test_a_stale_claim_is_startable tests/test_worker.py::test_a_child_that_lost_its_claim_is_tried_again_later tests/test_worker.py::test_a_claim_that_failed_today_on_another_board_waits_for_tomorrow tests/test_scheduler.py::test_a_plan_run_skips_tasks_claimed_elsewhere"
    - "uv run pytest -q tests/test_worker.py tests/test_scheduler.py"
  risk: medium
```

Planned test additions, all new:
- **`devbox-t01`:** `tests/test_config.py::test_plan_flows_name_a_known_flow_for_a_plan`, plus `test_a_task_runs_on_its_plans_flow_unless_flow_is_given`, `test_a_plan_run_gives_its_tasks_the_plans_flow` and `test_sync_warns_about_plan_flows_that_match_no_plan` in `tests/test_pipeline.py`.
- **`devbox-t02`:** a new `tests/test_worker.py` with the nine tests its verification names.
- **`devbox-t03`:** three tests added to `tests/test_worker.py`.
- **`devbox-t04`:** four tests added to `tests/test_worker.py`.
- **`devbox-t05`:** a new `tests/test_worker_status.py` with three tests, plus `tests/test_web.py::test_the_board_shows_the_worker`.
- **`devbox-t07`:** a new `tests/test_claims.py` with the seven tests its verification names, plus the fake gh's draft support in `tests/conftest.py`.
- **`devbox-t08`:** five tests added to `tests/test_claims.py`.
- **`devbox-t09`:** seven tests added to `tests/test_claims.py`.
- **`devbox-t10`:** a new `tests/test_claims_refresh.py` with seven tests.
- **`devbox-t11`:** four tests added to `tests/test_worker.py`, plus `tests/test_scheduler.py::test_a_plan_run_skips_tasks_claimed_elsewhere`.
- **`devbox-t06`:** `tests/test_templates.py::test_the_docs_describe_the_worker` and `test_the_docs_describe_claims`.

Every contract names at least one test that doesn't exist yet, so each one fits this repository's `strict` flow. Each verification filter must select its tests; zero matching tests is not a pass.

### Risks

1. **Unattended spending passes the budget.** Running tasks finish after the budget is reached, so the day can end over it. **Action:** each task the worker starts gets `--max-cost` capped at the budget left when it starts, which bounds the overrun to `--parallel` times that amount. Runs on unpriced models are warned about at start, and t06 documents the bound.
2. **Daily retries repeat a contract's failure at full cost.** A task that fails because of its contract fails again every day. **Action:** one retry per task per UTC day, counted from the board, within the daily budget. The waiting line counts the tasks waiting to retry. `factory abandon` holds a task for good.
3. **Updating code under running processes.** A pull while a task runs could change the prompts, config or (editable) factory code that it reads mid-run. **Action:** the worker drains first: it fast-forwards only when no task on the board runs, and it restarts itself when its own package changed. A dependency change only logs a reinstall reminder.
4. **A long task holds back an update.** While draining, the worker starts nothing, so one slow run delays both the update and every other task. **Action:** the `draining` state and its detail say what it waits for, and `factory stop TASK` ends a run you don't want to wait for.
5. **GitHub load and refresh side effects.** Each poll's refresh queries every open PR and may restack and comment. **Action:** refresh runs every `--poll` seconds (default 120), not at every 5-second check. Restacks happen only when a dependency merged or moved, as with `factory status --refresh` today.
6. **Two runners on one backlog.** A worker on a devbox and a plan run on a laptop, each with its own board, could build the same task. **Action:** every run that will push claims its task first (t07, t08), and only one leased push can win. One worker per board is still refused, because two workers on one board would share one budget and one checkout.
7. **A claim bug stops every run on every board.** After t07 merges, the factory claims the tasks it builds for itself, so a broken claim blocks all PRs. **Action:** fake-gh tests cover every claim path against a bare origin. A repository without drafts falls back to running unclaimed. `--no-pr` and bench never claim. Reverting the t07 PR restores today's PR flow, because the board's schema only grows in t10.
8. **A rework's claim commit moves the PR's head.** Pushing the claim commit shows a force-push on the PR. Where branch protection dismisses stale reviews, it also dismisses approvals. **Action:** only PRs that need a rework are claimed, and a successful rework replaces their head anyway. A failed rework puts back the exact old head. t06 documents the dismissal.
9. **CI runs on claim commits.** An empty commit could start a CI run that tells nobody anything. **Action:** the claim commit's message carries `[skip ci]`, which GitHub Actions honours for push and pull_request events. t06 notes that other CI systems may run once on it.
10. **Repositories without draft PRs.** GitHub Free doesn't offer drafts on private repositories, so the claim can't open. **Action:** the run deletes its claim branch, warns `GitHub refused a draft PR`, and runs unclaimed as today (t07, t08). t06 lists this under known limitations.
11. **Clock skew between boxes.** Heartbeats are compared across machines' clocks. **Action:** a 30-minute TTL is far above normal NTP skew, and every time is UTC. A take-over that races a live run still loses its leased push, or makes the live run fail without pushing (t09), so skew can waste a build but never mix two runs' work.
12. **GitHub API load.** Heartbeats and claim reads add calls. **Action:** one PATCH per running task every 5 minutes, and the refresh reads draft state and bodies in the PR listing it already makes, once per poll.

---

## Background and Evidence

### Nothing runs unattended

The factory runs work only while someone is at the terminal:

- `factory run PLAN` (`factory/scheduler.py:72`) runs one plan and ends "when nothing more can start". A task whose dependency is in another plan waits until someone reruns its plan.
- Merges, CI failures, review requests and conflicts reach the board only through `factory status --refresh` (`factory/cli.py:509`). A plan run refreshes once, when it starts (`factory/cli.py:136`), so a PR merged mid-run, or a review posted after the run, waits for a person.
- New plans and factory fixes reach the board only when someone pulls the checkout and runs `factory sync`.
- A docs plan needs `--flow gates-first` typed by hand every time. `flow:` is one setting for the whole repository.
- Nothing caps what unattended runs spend in a day; `--max-cost` caps one task.

So the backlog moves only as fast as someone at the keyboard. NEXT.md item 6 ("Runs need this machine") names the larger gap: hosted workspaces and a shared board. This plan covers the part that doesn't need either: long-running commands on one or more boxes that take the backlog as far as it can go and wait for your merges.

### Nothing tells one board what another is doing

Each board is a local SQLite file, and GitHub is the only state boards share. Today that sharing covers finished work, not running work:
- A run counts as running only on its own machine. `pid_alive` (`factory/db.py:238`) checks the pid with `os.kill`, and `cmd_run_one` checks it before it starts (`factory/cli.py:191`).
- A fresh build's push uses `--force-with-lease` with no expected value (`factory/pipeline.py:819`). So a second board building the same task either replaces the first one's work or is refused, depending on what it last fetched. Either way it has already paid for the whole build.
- `_adopt` (`factory/cli.py:425`) takes up any open PR on `factory/TASK` as `pr_open`, with its head as the candidate. A draft that only claims the task would be stacked on as if it were finished work, which is why claims need a marker other boards recognise.
- `_refresh` (`factory/cli.py:544`) leaves a PR whose head isn't the board's candidate "to whoever pushed it". After one board reworks a PR, every other board would stop looking after it; the candidate marker fixes that.
- A restack's push is leased on the board's own candidate (`factory/stack.py:112`), so of two boards restacking one PR, the second is refused.
- GitHub opens a PR only when its head has a commit its base doesn't. That is why a claim needs a commit before any work exists.
- Ubuntu's `gh` 2.4 breaks on `pr edit` for some setups (`factory/stack.py:44`) and has no `pr ready --undo`, so the factory edits PRs through `gh api`. Claims do the same.

## Design

### The worker

```text
factory start --budget USD [--plan P]... [--parallel 3] [--poll 120] [--until-idle]
  │
  ├─ refuse: another live worker on this board · missing provider keys · test step without test_paths
  │
  └─ loop ───────────────────────────────────────────────────────────────────────────┐
       every --poll seconds:                                                          │
         update the checkout (t04): fetch · drain · ff-only · restart on new code     │
         load contracts (sync) · refresh (merges, CI, reviews, conflicts, restack)    │
       every 5 seconds:                                                               │
         reap finished task runs (log status, PR, cost)                               │
         budget left? ── no ──► state budget: start nothing                           │
            │ yes                                                                     │
         start startable tasks up to --parallel (each on Config.flow_for(plan))       │
         nothing running and nothing startable ──► state waiting: log what for        │
            └── --until-idle: exit 0 ───────────────────────────────────────────────── ┘
```

`factory/worker.py` reuses the plan scheduler's pieces: `scheduler.default_launch` for the child `factory run TASK --quiet` processes, the same stop handling, and `_refresh` and `db.sync` from the CLI. The plan run itself doesn't change.

### Choosing tasks

A task is startable when all of these hold:
- its plan is selected (`--plan`, default every plan);
- its status is `queued`, `conflict`, `ci_failed` or `changes_requested`, or `failed` under the [daily rule](#failed-tasks) (t03);
- `db.ready`: every dependency is merged or has an open PR;
- it isn't manual (`gates.manual_reason`);
- no live process runs it;
- no other board holds a live [claim](#claims) on it (t11).

Plans go in file-name order and each plan's tasks in `contracts.plan_order`. A child that exits with its task still `queued` refused to start. The worker logs its stderr and doesn't start that task again, as a plan run treats a task that failed in the same run.

### A flow per plan

```yaml
flow: strict
plan_flows:
  factory-spec: gates-first
  example: lean
```

`Config.flow_for(plan, override)` resolves `--flow`, then `plan_flows[plan]`, then `flow`. Every entry point uses it, so a task runs on the same flow whether the worker, a plan run, a single run, the web page's Run form or a rework starts it. Unknown flows fail when the config is loaded. A key that matches no plan is a `factory sync` warning, since plans come and go.

### The budget

`DB.spent_today()` sums `runs.cost_usd` since 00:00 UTC over the whole board. Costs are written as each agent step finishes (`DB.progress`), so running tasks count. At or over the budget the worker starts nothing and logs the state once. A task started with budget left gets `--max-cost min(--max-cost, left)`. A model with no price in the OpenRouter list records no cost, so the worker warns at start about any such model its flows use.

### Failed tasks

A failed task is startable once per UTC day: when none of its runs started since today's midnight (t03). That holds whoever ran it, so a task that failed in a manual run this morning waits for tomorrow too. `abandoned` stays the hold that nothing overrides.

### Updating the checkout

```text
fetch origin TRUNK
  ├─ can't reach origin ─────────────► log once, keep working
  ├─ not on TRUNK / tracked changes / local commits ─► log once, keep working
  ├─ up to date ─────────────────────► nothing
  └─ fast-forward ahead ─► state draining (start nothing) ─► no live task run on the board
                             └─► git merge --ff-only ─► sync ─► restart if the factory package changed
```

The worker never commits, pushes, resets, stashes or cleans the checkout. A restart is `os.execv` of the same command line, so the pid and `worker.json` carry over. State lives on the board, so the budget and retry rules survive it. An editable install runs from the checkout, so the restarted worker and every later child run the merged code. The worker can't reinstall dependencies; when `pyproject.toml` or `uv.lock` changed it says so.

### Stopping and worker.json

`$FACTORY_HOME/worker.json`:

```json
{"pid": 4242, "started_at": "2026-11-22T22:05:44+00:00", "budget": 20.0, "plans": [],
 "state": "waiting", "detail": "3 PRs wait for a merge: #87, #89, #93", "updated_at": "2026-11-22T23:10:02+00:00"}
```

One live worker per board. SIGTERM, which is what `factory stop worker` sends, terminates its task runs as `factory stop PLAN` does. Ctrl-C leaves them running, as a plan run's Ctrl-C does. Both remove the file. A crash leaves the file with a dead pid, which `factory status` reports and the next `factory start` replaces.

### What you see

```text
$ factory status
worker: pid 4242 since 22:05 UTC · waiting · $6.40 of $20.00 today · 3 PRs wait for a merge: #87, #89, #93
agent-flows  ✓✓✓✓✓  5/5 merged
...
```

The same line sits under `factory top`'s header and above the plans on the web board.

### Claims

A claim tells every board, and anyone looking at GitHub, that one run is working on a task. The lock is git's own: a push with `--force-with-lease=REF:EXPECTED`, which the remote applies only while the branch still has the expected value. Of two racing runs, exactly one push succeeds. The draft PR is the record of the claim: which board holds it, since when, and when it was last heard from.

```text
factory run TASK   (a fresh build, or a run on an open PR; never --no-pr or bench)
  │
  ├─ claim commit: empty · parent = the base (fresh) or the PR head (rework)
  │    "factory: claim TASK [skip ci]"   Factory-Board: ID   Factory-Host: HOST
  │
  ├─ push factory/TASK --force-with-lease=refs/heads/factory/TASK:EXPECTED
  │    EXPECTED  ""                    fresh build: the branch must not exist     (t07)
  │              a leftover's head     no open PR and no recent claim commit      (t07)
  │              the PR head           rework or --force                          (t08)
  │              the stale claim       take-over                                  (t09)
  │    rejected ──► note "claimed by HOST since HH:MM UTC: URL" · exit 75 · nothing built
  │
  ├─ draft: gh pr create --draft (fresh) · convertPullRequestToDraft (rework)
  │    claim block at the top of the body · heartbeat every 5 minutes             (t09)
  │
  ├─ plan · test · build · review · gates, unchanged
  │    a rework builds from the PR head as it was, never from the claim commit
  │
  ├─ passed ─► push the candidate, leased on the claim commit
  │            title · body + candidate marker · markPullRequestReadyForReview
  └─ failed or stopped                                                             (t09)
       fresh  ─► close the draft (factory-claim-failed) · comment · delete the branch, leased
       rework ─► push the old head back, leased · body without the claim block · ready · comment
```

#### The lock

The claim commit is an empty commit made with `git commit-tree`. It is an object in the repository with no ref, so the checkout's branches, index and files don't change, and agents never see it. It exists because GitHub opens a PR only when its head has a commit its base doesn't. The candidate push replaces it, leased on its sha, so it is never one of the PR's commits and never merges. `[skip ci]` keeps GitHub Actions from running on it.

A fresh build expects `factory/TASK` not to exist. A branch that exists with no open PR, and whose head isn't a claim commit from the last 30 minutes, is a leftover from a closed PR or a board reset. The run claims over it with a lease on its head, as a fresh build replaced such a branch before.

#### The claim block

```text
<!-- factory-claim {"board": "3f9c1a7e02bd", "host": "devbox-1", "kind": "build", "since": "2026-11-26T10:00:00+00:00", "heartbeat": "2026-11-26T10:05:00+00:00"} -->
The factory is building this task on devbox-1 since 10:00 UTC. This draft becomes ready for review when its gates pass.
```

- `board` is `$FACTORY_HOME/board-id`, 12 random hex characters made on first use. Two FACTORY_HOMEs on one machine are two boards.
- `host` is the machine's hostname, for people.
- `kind` is `build`, `resolve`, `ci` or `human_review`.

A fresh build's body is the block alone. A rework puts the block above the PR's existing body and takes it off again when it ends. Every factory push leaves `<!-- factory-candidate SHA -->` at the end of the body (t10). The factory edits PRs through `gh api`: REST for the body, title, base and state, and GraphQL's markPullRequestReadyForReview and convertPullRequestToDraft for the draft state.

#### Reworks

A conflict resolution, CI fix, review rework or `--force` rebuild runs on an open PR, so its claim commit's parent is the PR's head, and its push is leased on that head. Today's rework leases its push on the old head (`Rework.old_candidate`). Under a claim it leases on the claim commit, and builds from the head as it was. While the claim lasts the PR is a draft, so nobody can merge it halfway through a rework. A review answered without a change, or a failed rework, pushes the old head back, so the PR ends exactly as it was.

#### Heartbeat and take-over

| Constant | Value | Meaning |
|---|---|---|
| `claims.HEARTBEAT` | 300 s | The claiming run rewrites the block's `heartbeat` at least this often, from a background timer, so a long gates run or model call doesn't let it lapse |
| `claims.TTL` | 1800 s | A claim with an older heartbeat is stale, and any run may take it over |

A claim made by this board is also stale as soon as no live process on this board runs its task, after a crash or `kill -9`. A take-over pushes a new claim commit, leased on the stale one, so only one of several taking runs wins. The run then rewrites the block and comments `Took over the claim from HOST, silent since HH:MM UTC.` A run that finds, just before its push, that the block names another board pushes nothing. So does a run whose candidate push is refused because the claim commit moved. Either fails with `the claim was taken over by HOST; nothing pushed`.

#### Ending a claim

| The run | Fresh build | Rework or `--force` |
|---|---|---|
| passes its gates | candidate pushed · title and body set · ready for review | candidate pushed · new body · ready · the rework's comment |
| fails, or is stopped by `factory stop` or Ctrl-C | draft closed, first line `<!-- factory-claim-failed {"board", "host", "at"} -->` · comment `The factory's run on HOST failed: NOTE` · branch deleted, leased | old head pushed back, leased · body without the block · ready · the same comment |
| is killed, or its box dies | the claim stays until the take-over | the same |

#### What other boards do

Each refresh (`factory status --refresh`, a plan run's start, every worker poll) reads draft state and bodies in the PR listing it already makes (t10):
- A task whose PR has another board's claim block gets its `claim` column set. It isn't taken up as `pr_open`, nothing stacks on it, and it isn't marked `conflict`, `ci_failed` or `changes_requested` while the claim lasts.
- `DB.readiness` says `claimed on HOST since HH:MM UTC: URL`, or `claim on HOST silent since HH:MM UTC; a run takes it over`. So `factory status`, `top` and the web board show it with no change of their own.
- A PR head equal to the body's candidate marker is another board's factory push. It becomes the task's candidate, with its merge base as base_sha, instead of being left to whoever pushed it.
- A closed PR whose body starts with `factory-claim-failed` sets `claim_failed_at`.

#### What the worker does with claims

A live claim keeps a task from starting, in the worker and in plan runs; a stale one doesn't (t11). A child that exits 75 lost a race the refresh hadn't seen yet. That is neither a refusal nor a failure, so the worker tries the task again at a later poll. The daily retry rule also counts `claim_failed_at`, so the fleet retries a task that failed today on any board tomorrow, once.

## Files Changed

| File | Change |
|---|---|
| `factory/config.py` | `plan_flows`, its validation, `Config.flow_for` (t01) |
| `factory/cli.py` | Flow choice in `cmd_run_one`, `cmd_run_plan`, `cmd_sync` (t01); `factory start`, `factory stop worker` (t02); the worker's line in `cmd_status`, `cmd_top` (t05); claiming before a fresh build (t07) and before a rework (t08), take-over (t09); claims, failed claims and the candidate marker in `_adopt` and `_refresh` (t10) |
| `factory/claims.py` | New: the board id, the claim commit, the draft PR and its claim block, `parse` (t07); claiming an open PR (t08); the heartbeat, take-over and ending a claim (t09) |
| `factory/pipeline.py` | The pr step pushes over the claim commit and marks the draft ready (t07, t08); ending the claim on failure and stop (t09); the candidate marker in the body (t10) |
| `factory/stack.py` | The candidate marker on a restack, and a rejected restack push (t10) |
| `factory/worker.py` | New: the worker loop, task choice and budget (t02), daily retries (t03), checkout updates and the restart (t04); claimed tasks, exit 75 and failed claims (t11) |
| `factory/scheduler.py` | Claimed tasks and exit 75 in a plan run (t11) |
| `factory/db.py` | `DB.spent_today` (t02); the `claim` and `claim_failed_at` columns and claims in `DB.readiness` (t10) |
| `factory/observe.py` | `worker_line` (t05) |
| `factory/web/views.py` | The worker's line on the board (t05) |
| `tests/conftest.py` | The fake gh's draft PRs: `--draft`, isDraft and body, GraphQL ready and draft, PATCH of state (t07, t08) |
| `tests/test_config.py`, `tests/test_pipeline.py` | t01 tests; `test_a_new_pr_is_titled_with_the_verifiers_title` checks the final title (t07) |
| `tests/test_worker.py` | New: t02, t03 and t04 tests; t11 tests |
| `tests/test_worker_status.py` | New: t05 tests |
| `tests/test_web.py` | t05 test |
| `tests/test_claims.py` | New: t07, t08 and t09 tests |
| `tests/test_claims_refresh.py` | New: t10 tests |
| `tests/test_scheduler.py` | t11 test |
| `tests/test_templates.py` | t06 tests |
| `docs/reference.md`, `docs/architecture.md`, `README.md`, `NEXT.md`, factory-ops skill (template and installed copy) | t06 |

## Test Plan

### Unit tests

- **t01:**
  - `test_plan_flows_name_a_known_flow_for_a_plan`: parsing, `flow_for` order, and both ConfigErrors.
  - `test_a_task_runs_on_its_plans_flow_unless_flow_is_given`: the recorded flow, with and without `--flow`.
  - `test_a_plan_run_gives_its_tasks_the_plans_flow`: each child gets `--flow`.
  - `test_sync_warns_about_plan_flows_that_match_no_plan`: the warning, and exit 0.
- **t02,** in `tests/test_worker.py`, with fake child processes and an injected clock, as `tests/test_scheduler.py` does:
  - tasks across two plans start up to `--parallel`;
  - flows and `--max-cost` are passed to each child;
  - a dependent starts once its dependency's PR opens;
  - conflict, CI and review states start;
  - the budget stops new starts, and a new UTC day lifts it;
  - abandoned tasks and refused children aren't started;
  - `--until-idle` exits;
  - a second worker is refused, and `factory stop worker` stops the first.
- **t03:**
  - a task that failed yesterday is started once today;
  - a task that failed today isn't;
  - abandoned tasks never are.
- **t04,** against a repo with a bare `origin`, as in `tests/conftest.py`:
  - the worker fast-forwards after draining;
  - a dirty, diverged or off-trunk checkout, or an unreachable origin, is left alone and logged once;
  - a change under the package directory calls the injected exec with the same arguments;
  - a detached HEAD needs `--base`.
- **t05:** the worker's line in `factory status` and `factory top`, the dead-pid line, no line without a worker, and the web board's `worker` element.
- **t07,** in a new `tests/test_claims.py`. Two boards are two `$FACTORY_HOME`s sharing one bare `origin` and one fake gh state:
  - the board id is made once and kept;
  - a fresh run's draft and claim block exist before the first model call, and the claim commit is empty with the right message and trailers;
  - a leftover branch with no PR is claimed over;
  - a run racing a branch that already exists builds nothing, makes no model call, keeps the task's status and exits 75 with the note;
  - the claimed draft becomes the task's PR: the PR's commits don't include the claim commit, it has the verifier's title and body, and it is ready;
  - a repository without drafts deletes the claim branch, warns and runs unclaimed;
  - `--no-pr` and a task with an open PR add no gh call.
- **t08:**
  - a CI rework's PR is a draft with a `ci` claim block above its old body before the builder runs;
  - a rework racing a moved head exits 75 and leaves the PR as it was;
  - a pushed rework's commits don't include the claim commit, and the PR is ready with the new body;
  - an answered review puts the old head back;
  - `--force` on an open PR claims it with kind `build`.
- **t09,** with an injected clock and timer:
  - a failed fresh build closes its draft with the failed block and the comment, and deletes the branch;
  - a failed rework puts the PR's head and body back and makes it ready;
  - a run stopped by SIGTERM ends its claim the same way;
  - the heartbeat is rewritten every 300 seconds and stops when the run ends;
  - of two runs taking over one stale claim, one wins and the other exits 75;
  - this board's claim from a dead pid is taken over at once;
  - a run whose claim was taken over pushes nothing.
- **t10,** in a new `tests/test_claims_refresh.py`:
  - another board's claim is recorded, not taken up, and not stacked on;
  - a claimed open PR isn't marked conflict, ci_failed or changes_requested;
  - a head named by the candidate marker becomes the candidate;
  - a head named by no marker is still left to whoever pushed it;
  - a factory-claim-failed PR sets claim_failed_at;
  - readiness shows the live and silent claim lines;
  - a rejected restack push changes nothing and prints its line.
- **t11:**
  - the worker doesn't start a task with a live claim, and starts one with a stale claim;
  - a child that exits 75 is started again once the claim is gone;
  - a claim failed today on another board holds the task until tomorrow;
  - a plan run skips a claimed task and marks it in its summary.

### End-to-end tests

- **t02:** `test_start_until_idle_runs_the_backlog_to_prs` runs `factory start --until-idle --budget 5` through `cli.main` on the demo repository. The worker's launch is replaced with one that runs each child `factory run TASK --quiet` in-process on the `ScriptedModel`, as `tests/test_bench.py` replaces bench's launch. The test checks it opens a PR for each ready task and exits 0.
- **t07:** `test_the_claimed_draft_becomes_the_tasks_pr` runs `factory run demo-t01` through `cli.main` on the demo repository, from claim to ready PR, against the bare `origin` and the fake gh.
- **t09:** `test_a_stale_claim_is_taken_over_by_one_run` runs two boards' `factory run` against one stale claim and checks that exactly one PR results.
- **t06:** `tests/test_templates.py::test_the_docs_describe_the_worker` checks the documented commands, flags, config key and README section, and `test_the_docs_describe_claims` checks the Claims section, the exit status, the troubleshooting rows and the known limitations.

## Verification

- Every contract's verification passes at its candidate.
- **After t04, on the box:**
  1. Start `factory start --budget 5 --until-idle` on a board with one ready task. It builds the task's PR and exits.
  2. Without `--until-idle`, merge a plan PR on GitHub. Within one poll the worker logs `updated main: …` and starts the new plan's first task.
- **After t05:** `factory status` on another terminal shows the worker's line.
- **After t11, on two boxes** sharing one repository, each with its own board:
  1. Start `factory start --budget 5` on both, with one ready task. Exactly one draft PR opens, and its claim block names one box. The other box's `factory status` shows `claimed on HOST since …`.
  2. `kill -9` the claiming run. About 30 minutes later the other box takes the claim over, comments on the draft, and opens the PR.
  3. Make a task fail on one box. Its draft closes with the failure comment, and neither box retries it before 00:00 UTC.

## Cross-Workstream Coordination

- **Depends on:** none. `devbox-t01` can run once this plan is merged and synced.
- **Required by:** none.
- **Overlaps, with no ordering:**
  - [steer](steer.md) `steer-t01` changes `factory/cli.py` and `factory/db.py`, and [security-review](security-review.md) `security-review-t06` changes `factory/cli.py`.
  - `security-review-t02` changes `factory/config.py`.
  - [plan-pages](plan-pages.md) `plan-pages-t01`…`t03` and `steer-t04` change `factory/web/views.py`.
  - The claim tasks t07 to t10 change `Pipeline.pr` and the run's failure path in `factory/pipeline.py`. [steer](steer.md), [security-review](security-review.md), [thought-timeline](thought-timeline.md), [web-tools](web-tools.md) and [wiki](wiki.md) change `factory/pipeline.py` too.

  The factory's conflict resolution handles these as it did for steer and security-review.
- **Related:**
  - NEXT.md item 6 ("Runs need this machine"). With claims, several boxes can share one backlog, each with its own board, while you watch any of them with `factory web` over `ssh -L`. A shared board for one live view of every box, and hosted workspaces, stay open there.
  - The architecture's known limitation "Two boards can run the same task at once … Planned: a draft PR as the claim" is what t07 to t11 deliver, and t06 removes it.

## Notes / Out of Scope

- **Keeping the worker alive and setting up a box.** Systemd units, container images and setup scripts are out (the Devbox decision). The README section lists what a box needs.
- **A shared board.** Claims coordinate boards through GitHub. One database with a live view of every box stays NEXT.md item 6. So does one budget across boxes: each box's `--budget` counts its own board.
- **GitHub webhooks.** The worker checks GitHub every `--poll` seconds. Listening for webhooks would need an endpoint GitHub can reach.
- **Releasing a claim by hand.** A stale claim is taken over after 30 minutes, and `factory stop TASK` on the claiming box ends a live claim cleanly. A `factory release TASK` can come later if waiting turns out to hurt.
- **Claiming restacks.** A restack is a leased push with no agent and no cost, so two boards restacking one PR waste nothing. The second push is refused and its board takes up the new head at its next refresh (t10).
- **Starting or stopping the worker from the web page.** The board only shows it. A long-lived job would need a design of its own on the Activity page.
- **A flow per task inside one plan.** `plan_flows` works per plan, so docs tasks inside a code plan rely on the strict test step's `no tests needed` rule (#93).
- **Retry back-off over days, and notifications** (desktop, GitHub or chat) when the worker waits or reaches its budget.
- **Reinstalling the factory's dependencies** after `pyproject.toml` or `uv.lock` change. The worker only reminds you.
