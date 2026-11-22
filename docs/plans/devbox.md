# Plan: Run the backlog unattended (devbox)

**Status:** Planned (2026-11-22). Workstream scoped; awaiting kickoff: `devbox-t01` runs once this plan is merged and synced. Roadmap: [NEXT.md item 18](../../NEXT.md#18-run-the-backlog-unattended).

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

### Milestones

| # | Deliverable | Exit criteria | Parallelizable with |
|---|---|---|---|
| **M1** | A flow per plan | The t01 tests in `tests/test_config.py` and `tests/test_pipeline.py` pass | — |
| **M2** | `factory start` | The t02 tests in `tests/test_worker.py` pass | — |
| **M3** | Daily retries | The t03 tests in `tests/test_worker.py` pass | M5 |
| **M4** | The checkout keeps up | The t04 tests in `tests/test_worker.py` pass | M5 |
| **M5** | You can see the worker | The t05 tests in `tests/test_worker_status.py` and `tests/test_web.py` pass | M3, M4 |
| **M6** | Docs | `tests/test_templates.py::test_the_docs_describe_the_worker` passes, and `tests/test_templates.py` passes | — |

**Sequence:** `M1 → M2 → (M3 → M4) ∥ M5 → M6`. t01 and t02 share `factory/cli.py`. t02, t03 and t04 share `factory/worker.py` and `tests/test_worker.py`. t05 changes only `factory/observe.py`, `cmd_status` and `cmd_top` in `factory/cli.py`, `factory/web/views.py`, `tests/test_worker_status.py` and `tests/test_web.py`, so it runs beside t03 and t04.

### Task Contracts

| Milestone | Task IDs | Coverage |
|---|---|---|
| **M1** | `devbox-t01` | `plan_flows` and `Config.flow_for` in `factory/config.py`; the flow choice in `cmd_run_one`, `cmd_run_plan` and `cmd_sync` in `factory/cli.py`; tests in `tests/test_config.py` and `tests/test_pipeline.py` |
| **M2** | `devbox-t02` | New `factory/worker.py`; `factory start` and `factory stop worker` in `factory/cli.py`; `DB.spent_today` in `factory/db.py`; new `tests/test_worker.py` |
| **M3** | `devbox-t03` | The daily retry rule in `factory/worker.py`; tests in `tests/test_worker.py` |
| **M4** | `devbox-t04` | Updating the checkout, draining and the restart in `factory/worker.py`; tests in `tests/test_worker.py` |
| **M5** | `devbox-t05` | The worker's line in `factory/observe.py`, `factory status`, `factory top` and the web board; new `tests/test_worker_status.py`, tests in `tests/test_web.py` |
| **M6** | `devbox-t06` | `docs/reference.md`, `docs/architecture.md`, `README.md`, `NEXT.md` and the factory-ops skill (template and installed copy); a new test in `tests/test_templates.py` |

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
    - "Claiming tasks across boards"
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
  goal: "The docs describe the worker and plan_flows: docs/reference.md, docs/architecture.md, README.md, NEXT.md and the factory-ops skill, in its template and installed copy"
  spec_refs:
    - "docs/plans/devbox.md#design"
    - "docs/reference.md"
    - "docs/architecture.md"
    - "README.md"
    - "NEXT.md"
  depends_on:
    - devbox-t04
    - devbox-t05
  non_goals:
    - "Changing behaviour"
    - "A service unit, a container image or a setup script"
  acceptance:
    - "docs/reference.md lists `factory start` with every flag and its default, and `factory stop worker`, and describes plan_flows with the other config keys. Its troubleshooting table has rows for `a worker is already running on this board`, `budget reached` and each `not updating TRUNK` reason"
    - "docs/architecture.md has a section headed `## The worker` that covers the poll (load, refresh), which tasks start, each task's flow, the daily budget, daily retries, updating the checkout with draining and the restart, worker.json, and the signals. It states the budget's bound: up to `--parallel` runs may each spend up to the budget that was left when they started. Its Policy says the worker fast-forwards the main checkout's trunk and spends within the budget unattended, while agents still never commit to the checkout"
    - "README.md has a section headed `## Run it on a devbox`. It covers what the box needs (Linux, bwrap, uv, git, an authenticated gh, and the provider key in the worker's environment), cloning and installing (editable for the factory itself), `factory sync`, and `factory start --budget USD` in a terminal multiplexer. It covers watching from another machine with `factory web --no-open` and `ssh -L 8765:127.0.0.1:8765 HOST`. It says keeping the worker alive is up to the box: tmux, screen or a service you write"
    - "NEXT.md's item 18 row and section say the worker is done and link docs/architecture.md#the-worker. Item 6 says the worker runs a backlog on one remote box, while a shared board stays open"
    - "The factory-ops skill has request rows for running the backlog unattended (`factory start --budget USD`), stopping the worker, and choosing a plan's flow with plan_flows. They are in factory/templates/skills/factory-ops/SKILL.md and .claude/skills/factory-ops/SKILL.md, which stay identical"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_templates.py::test_the_docs_describe_the_worker"
    - "uv run pytest -q tests/test_templates.py"
  risk: low
```

Planned test additions, all new:
- **`devbox-t01`:** `tests/test_config.py::test_plan_flows_name_a_known_flow_for_a_plan`, plus `test_a_task_runs_on_its_plans_flow_unless_flow_is_given`, `test_a_plan_run_gives_its_tasks_the_plans_flow` and `test_sync_warns_about_plan_flows_that_match_no_plan` in `tests/test_pipeline.py`.
- **`devbox-t02`:** a new `tests/test_worker.py` with the nine tests its verification names.
- **`devbox-t03`:** three tests added to `tests/test_worker.py`.
- **`devbox-t04`:** four tests added to `tests/test_worker.py`.
- **`devbox-t05`:** a new `tests/test_worker_status.py` with three tests, plus `tests/test_web.py::test_the_board_shows_the_worker`.
- **`devbox-t06`:** `tests/test_templates.py::test_the_docs_describe_the_worker`.

Every contract names at least one test that doesn't exist yet, so each one fits this repository's `strict` flow. Each verification filter must select its tests; zero matching tests is not a pass.

### Risks

1. **Unattended spending passes the budget.** Running tasks finish after the budget is reached, so the day can end over it. **Action:** each task the worker starts gets `--max-cost` capped at the budget left when it starts, which bounds the overrun to `--parallel` times that amount. Runs on unpriced models are warned about at start, and t06 documents the bound.
2. **Daily retries repeat a contract's failure at full cost.** A task that fails because of its contract fails again every day. **Action:** one retry per task per UTC day, counted from the board, within the daily budget. The waiting line counts the tasks waiting to retry. `factory abandon` holds a task for good.
3. **Updating code under running processes.** A pull while a task runs could change the prompts, config or (editable) factory code that it reads mid-run. **Action:** the worker drains first: it fast-forwards only when no task on the board runs, and it restarts itself when its own package changed. A dependency change only logs a reinstall reminder.
4. **A long task holds back an update.** While draining, the worker starts nothing, so one slow run delays both the update and every other task. **Action:** the `draining` state and its detail say what it waits for, and `factory stop TASK` ends a run you don't want to wait for.
5. **GitHub load and refresh side effects.** Each poll's refresh queries every open PR and may restack and comment. **Action:** refresh runs every `--poll` seconds (default 120), not at every 5-second check. Restacks happen only when a dependency merged or moved, as with `factory status --refresh` today.
6. **Two runners on one backlog.** A worker on a devbox and a plan run on a laptop, each with its own board, can build the same task. **Action:** the worker refuses to start beside another worker on its board. Running the backlog from one board stays the rule, and t06's README section says so, since claiming tasks across boards is out of scope.

---

## Problem

The factory runs work only while someone is at the terminal:

- `factory run PLAN` (`factory/scheduler.py:72`) runs one plan and ends "when nothing more can start". A task whose dependency is in another plan waits until someone reruns its plan.
- Merges, CI failures, review requests and conflicts reach the board only through `factory status --refresh` (`factory/cli.py:509`). A plan run refreshes once, when it starts (`factory/cli.py:136`), so a PR merged mid-run, or a review posted after the run, waits for a person.
- New plans and factory fixes reach the board only when someone pulls the checkout and runs `factory sync`.
- A docs plan needs `--flow gates-first` typed by hand every time. `flow:` is one setting for the whole repository.
- Nothing caps what unattended runs spend in a day; `--max-cost` caps one task.

So the backlog moves only as fast as someone at the keyboard. NEXT.md item 6 ("Runs need this machine") names the larger gap: hosted workspaces and a shared board. This plan covers the part that doesn't need either. It lets one long-running command on one box take the backlog as far as it can go and wait for your merges.

## Goal

On any Linux box that can run the factory, `factory start --budget 20` keeps the board moving until stopped. It loads merged plans, starts each ready task on its plan's flow, reworks PRs that conflict, fail CI or get review requests, and retries failed tasks once a day. It waits for your merges, stays within the day's budget, and keeps the checkout on the trunk. `factory status`, `factory top` and the web page show what it is doing.

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
- no live process runs it.

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

## Files Changed

| File | Change |
|---|---|
| `factory/config.py` | `plan_flows`, its validation, `Config.flow_for` (t01) |
| `factory/cli.py` | Flow choice in `cmd_run_one`, `cmd_run_plan`, `cmd_sync` (t01); `factory start`, `factory stop worker` (t02); the worker's line in `cmd_status`, `cmd_top` (t05) |
| `factory/worker.py` | New: the worker loop, task choice and budget (t02), daily retries (t03), checkout updates and the restart (t04) |
| `factory/db.py` | `DB.spent_today` (t02) |
| `factory/observe.py` | `worker_line` (t05) |
| `factory/web/views.py` | The worker's line on the board (t05) |
| `tests/test_config.py`, `tests/test_pipeline.py` | t01 tests |
| `tests/test_worker.py` | New: t02, t03 and t04 tests |
| `tests/test_worker_status.py` | New: t05 tests |
| `tests/test_web.py` | t05 test |
| `tests/test_templates.py` | t06 test |
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

### End-to-end tests

- **t02:** `test_start_until_idle_runs_the_backlog_to_prs` runs `factory start --until-idle --budget 5` through `cli.main` on the demo repository. The worker's launch is replaced with one that runs each child `factory run TASK --quiet` in-process on the `ScriptedModel`, as `tests/test_bench.py` replaces bench's launch. The test checks it opens a PR for each ready task and exits 0.
- **t06:** `tests/test_templates.py::test_the_docs_describe_the_worker` checks the documented commands, flags, config key and README section.

## Verification

- Every contract's verification passes at its candidate.
- **After t04, on the box:**
  1. Start `factory start --budget 5 --until-idle` on a board with one ready task. It builds the task's PR and exits.
  2. Without `--until-idle`, merge a plan PR on GitHub. Within one poll the worker logs `updated main: …` and starts the new plan's first task.
- **After t05:** `factory status` on another terminal shows the worker's line.

## Cross-Workstream Coordination

- **Depends on:** none. `devbox-t01` can run once this plan is merged and synced.
- **Required by:** none.
- **Overlaps, with no ordering:**
  - [steer](steer.md) `steer-t01` changes `factory/cli.py` and `factory/db.py`, and [security-review](security-review.md) `security-review-t06` changes `factory/cli.py`.
  - `security-review-t02` changes `factory/config.py`.
  - [plan-pages](plan-pages.md) `plan-pages-t01`…`t03` and `steer-t04` change `factory/web/views.py`.

  The factory's conflict resolution handles these as it did for steer and security-review.
- **Related:** NEXT.md item 6 ("Runs need this machine"). This plan lets one remote box run the backlog while you watch with `factory web` over `ssh -L`. The shared board and hosted workspaces stay open there.

## Notes / Out of Scope

- **Keeping the worker alive and setting up a box.** Systemd units, container images and setup scripts are out (the Devbox decision). The README section lists what a box needs.
- **Claiming tasks across boards** (NEXT.md item 6 and the architecture's known limitations) is out. One worker per board is refused; two boards on one backlog remain a person's call.
- **Starting or stopping the worker from the web page.** The board only shows it. A long-lived job would need a design of its own on the Activity page.
- **A flow per task inside one plan.** `plan_flows` works per plan, so docs tasks inside a code plan rely on the strict test step's `no tests needed` rule (#93).
- **Retry back-off over days, and notifications** (desktop, GitHub or chat) when the worker waits or reaches its budget.
- **Reinstalling the factory's dependencies** after `pyproject.toml` or `uv.lock` change. The worker only reminds you.
