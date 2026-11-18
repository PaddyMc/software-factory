# Plan: Manage the factory from a browser

**Status:** Planned (2026-11-14). Workstream scoped; awaiting kickoff: t01 and t02 can run now. Roadmap: [NEXT.md item 10](../../NEXT.md#10-manage-the-factory-from-a-browser).

---

## Execution Plan

### Locked Decisions

| Decision | Choice |
|---|---|
| Scope | **Watch, act and run.** The page shows the board, each task with its contract, runs and live log, and each agent run's transcript. From it you can load plans, check GitHub, put a task on hold or take it off, remove a worktree, start a plan or task run with a cost cap, and stop a run. Merging stays on GitHub: it is the human gate |
| Build | **No new dependencies.** Python's standard-library HTTP server, server-rendered HTML, one stylesheet and one small script shipped inside the package. `factory web` works straight after install, and every task can be built and tested in the offline sandbox |
| Look | **Fixed by mockups committed with this plan.** [`docs/design/webui/`](../design/webui/) holds static pages for the board, a task, a transcript, the run form and the activity page. They use the real stylesheet, [`factory/web/static/app.css`](../../factory/web/static/app.css), which the server then serves unchanged. The palette and typefaces are fractal-dev.xyz's: near-black and greys, Instrument Serif, Hanken Grotesk and DM Mono, with four muted hues for status |
| The board lock | **Fixed first, in this plan.** `database is locked` already happens with a few parallel runs, and the page reads the board every 2 seconds. t01 opens the board in WAL mode with a 30-second busy timeout, and every web task builds on it |

### Milestones

| # | Deliverable | Exit criteria | Parallelizable with |
|---|---|---|---|
| **M1** | The board doesn't lock | The t01 tests in `tests/test_db.py` pass; `test_db`, `test_observe` and `test_pipeline` pass unmodified | M2 |
| **M2** | `factory stop` | `tests/test_stop.py` passes; `test_scheduler` and `test_pipeline` pass unmodified | M1 |
| **M3** | The board in a browser | The t03 tests in `tests/test_web.py` pass, and the board looks like `docs/design/webui/board.html` | — |
| **M4** | Task and transcript pages | The t04 and t05 tests in `tests/test_web.py` pass, and the pages look like `task.html` and `transcript.html` | — |
| **M5** | Act from the page | The t06 tests in `tests/test_web.py` pass: every action runs its `factory` command, and cross-site requests are refused | — |
| **M6** | Start runs from the page | The t07 tests in `tests/test_web.py` pass: a run needs the form, a cost cap and a valid token | — |
| **M7** | Docs | README, reference, architecture, AGENTS.md and its template, the factory-ops skill and NEXT.md describe the page and `factory stop`; `tests/test_templates.py` passes | — |

**Sequence:** `(M1 ∥ M2) → M3 → M4 → M5 → M6 → M7`. The web tasks run one after another because each one changes `factory/web/` and `tests/test_web.py`. t03 waits for t02 as well as t01 because both add a subcommand to `factory/cli.py`.

### Task Contracts

| Milestone | Task IDs | Coverage |
|---|---|---|
| **M1** | `webui-t01` | WAL mode, the busy timeout and skippable heartbeats in `factory/db.py`; the run-log line in `factory/pipeline.py`; tests in `tests/test_db.py` |
| **M2** | `webui-t02` | `factory stop` in `factory/cli.py`; SIGTERM handling for a task run in `factory/cli.py` and `factory/pipeline.py`; the plan run's pid file and SIGTERM handling in `factory/scheduler.py`; new `tests/test_stop.py` |
| **M3** | `webui-t03` | New `factory/web/` package (`__init__.py`, `server.py`, `views.py`), `factory/web/static/app.js` and `favicon.svg`; `open_db(home, readonly=True)` in `factory/db.py`; `factory web` in `factory/cli.py`; new `tests/test_web.py` |
| **M4** | `webui-t04`, `webui-t05` | The task page, then the transcript page, in `factory/web/views.py` and `server.py`; tests in `tests/test_web.py` |
| **M5** | `webui-t06` | POST actions with the token and origin checks, the confirm page, new `factory/web/jobs.py`, the activity page and the action buttons; tests in `tests/test_web.py` |
| **M6** | `webui-t07` | The run form and the run action; the Run plan and Run again buttons; tests in `tests/test_web.py` |
| **M7** | `webui-t08` | `README.md`, `docs/reference.md`, `docs/architecture.md`, `AGENTS.md`, `factory/templates/agents-section.md`, `factory/templates/skills/factory-ops/SKILL.md`, `NEXT.md` |

```yaml
- id: webui-t01
  goal: "Several runs, `factory top` and the web page can use the board at once without `database is locked`: the board is opened in WAL mode with a 30-second busy timeout, and a heartbeat or progress write that still can't get the lock is skipped instead of ending the run"
  spec_refs:
    - "docs/plans/webui.md#the-board-lock"
    - "factory/db.py"
  depends_on: []
  non_goals:
    - "Changing the schema, the migrations or any query"
    - "Retrying or skipping any write other than heartbeat and progress"
    - "A read-only connection mode (webui-t03)"
    - "Changes outside factory/db.py, factory/pipeline.py, tests/test_db.py and this task's session log"
  acceptance:
    - "DB(path, timeout=30.0) connects with that busy timeout and runs `PRAGMA journal_mode=WAL` and `PRAGMA synchronous=NORMAL` on every open. The first open switches an existing rollback-journal board to WAL. If the switch can't get its lock, the board is left as it is for the next open to switch, and this open still succeeds"
    - "DB.heartbeat and DB.progress return True when their write committed. When the write raises sqlite3.OperationalError with `database is locked` in its message, they roll the connection back, so it isn't left inside a transaction, and return False. Every other write still raises"
    - "When DB.heartbeat or DB.progress returns False, Pipeline._event and Pipeline._progress write `board busy: skipped a heartbeat` or `board busy: skipped a progress update` to the run log, and the run carries on"
    - "Eight processes each write heartbeats and progress updates as fast as they can for 3 seconds. Meanwhile one process reads the board the way `factory top` does, and another opens and closes the board in a loop. None of them gets an OperationalError"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_db.py::test_the_board_opens_in_wal_mode_with_a_long_busy_timeout tests/test_db.py::test_a_rollback_journal_board_is_switched_to_wal_on_open tests/test_db.py::test_parallel_writers_and_readers_never_see_a_locked_board tests/test_db.py::test_a_locked_heartbeat_is_skipped_and_the_run_carries_on"
    - "uv run pytest -q tests/test_db.py tests/test_observe.py tests/test_pipeline.py"
  risk: medium

- id: webui-t02
  goal: "`factory stop TARGET` stops a running task, or a running plan and every task it started. A stopped task ends `failed` with a note saying it was stopped, its current agent run is recorded as `stopped`, and a stopped plan run starts nothing more"
  spec_refs:
    - "docs/plans/webui.md#stopping-a-run"
    - "factory/scheduler.py"
    - "factory/cli.py"
  depends_on: []
  non_goals:
    - "Pausing or resuming a run, or keeping a stopped agent's conversation"
    - "Removing the task's worktree or branch (`factory clean` does that)"
    - "Stopping runs started on another machine"
    - "Any web page (webui-t03 onwards)"
    - "Changing what `factory run` does when nothing stops it"
  acceptance:
    - "`factory run TASK` handles SIGTERM as follows. The agent run in progress ends with outcome `stopped`. The task becomes `failed` with the note `stopped by factory stop at HH:MM UTC; run it again to start over`. The run log gets a `[stage] stopped` line, and the process exits 1. The worktree and branch are kept"
    - "`factory run PLAN` writes its process id to $FACTORY_HOME/plan-runs/PLAN.pid when it starts, and removes the file when it exits, however it exits. On SIGTERM it starts no more tasks and sends SIGTERM to every task process it started that is still running. It waits for them, prints the plan summary and exits 1"
    - "`factory stop TASK [--wait SECONDS]` acts when the task is in an active status and its recorded process is alive. It sends that process SIGTERM and waits up to SECONDS (default 10) for it to exit. If it hasn't, it sends SIGKILL to the process's group when the process leads one, else to the process alone, and then sets the stopped note on the task itself. It prints what it stopped and exits 0"
    - "`factory stop PLAN` (a plan name or path) first stops the plan's run process, when its pid file names a live process, then every task of the plan that is in an active status with a live process, each the same way. With nothing running it prints `nothing to stop: PLAN has no running plan run or task` and exits 0"
    - "`factory stop` exits 1 with the reason for a target that is neither a task on the board nor a plan, and for a task that isn't running (`TASK is STATUS; nothing to stop`)"
    - "`factory stop PLAN` removes a pid file whose process is gone and otherwise ignores it"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_stop.py::test_stop_ends_a_running_task_as_failed_and_records_the_run_as_stopped tests/test_stop.py::test_stop_kills_a_task_that_ignores_sigterm tests/test_stop.py::test_a_plan_run_records_its_pid_and_stops_its_tasks_on_sigterm tests/test_stop.py::test_stop_plan_stops_the_plan_run_and_its_running_tasks tests/test_stop.py::test_stop_refuses_unknown_targets_and_idle_tasks tests/test_stop.py::test_a_stale_plan_pid_file_is_removed"
    - "uv run pytest -q tests/test_scheduler.py tests/test_pipeline.py"
  risk: high

- id: webui-t03
  goal: "`factory web` serves the board on 127.0.0.1 and opens it in the browser. The page has a sentence saying what needs you, the counts, a Needs you list with each task's next step, the running tasks with what they're doing, and every plan as a row of status squares that opens to its tasks. It updates itself every 2 seconds and looks like docs/design/webui/board.html, without that page's buttons"
  spec_refs:
    - "docs/plans/webui.md#factory-web"
    - "docs/plans/webui.md#statuses"
    - "docs/plans/webui.md#board"
    - "docs/plans/webui.md#live-pages"
    - "docs/plans/webui.md#security"
    - "docs/plans/webui.md#look"
    - "docs/design/webui/board.html"
    - "factory/observe.py"
  depends_on:
    - webui-t01
    - webui-t02
  non_goals:
    - "Buttons, forms or any request that changes something. There is no POST route yet (webui-t06, webui-t07)"
    - "The task, transcript, activity and run pages (webui-t04 to webui-t07). Task ids aren't links yet"
    - "Changing the existing rules in factory/web/static/app.css, the fonts, or the mockups in docs/design/webui/. Adding rules for elements the mockups don't show is fine"
    - "New Python dependencies, a JavaScript build step, or anything loaded from the network"
    - "Listening on any address but 127.0.0.1, or a --host option"
    - "Changing what `factory top` and `factory status` print"
  acceptance:
    - "`factory web [--port N] [--no-open]` first opens the board once with open_db(home), which migrates it as every command does. It binds 127.0.0.1 on port N (default 8765) and prints `factory web: http://127.0.0.1:N/ (Ctrl-C to stop)`. If 8765 is busy and --port wasn't given, it binds a free port and prints that one. A busy explicit --port exits 1 with `port N is in use; pick another with --port`. It opens the URL with webbrowser.open unless --no-open is given, prints nothing per request, and exits 0 on Ctrl-C"
    - "New factory/web/server.py has App(home, root), whose handle(method, path, headers, body) returns a status, headers and body without a socket. make_server(app, port) serves an App through a ThreadingHTTPServer"
    - "Each request reads through its own connection from open_db(home, readonly=True), closed when the request ends. That connection opens `file:PATH?mode=ro` as a URI and runs no schema, migration or pragma statements, so any write through it raises"
    - "GET / renders the whole board as HTML that is complete without JavaScript, using the classes and structure of docs/design/webui/board.html: the top bar, the page head with its sentence and counts, Needs you, Running, Plans with the finished plans collapsed at the end, and the footer. The top bar names the project from the config's `name`"
    - "The page head's sentence, counts, sections, row contents, status words, marks and next steps follow the plan's Statuses and Board sections. The running, ready and waiting counts and the money spent equal the numbers on the first line of observe.render_top for the same board"
    - "factory/web/static/app.js does the jobs in the plan's Live pages section, and every page loads it with `defer`. The board's <main> has data-refresh=\"2\""
    - "Requests are answered as the Security section says: GET and HEAD only, the Host check, the response headers, the fixed list of static files, the 404 page, escaping, and links only to http and https URLs"
    - "An empty board says `No tasks yet.` in the page head and `Load your plans with factory sync.` below it"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_web.py::test_board_sentence_and_counts_match_factory_top tests/test_web.py::test_needs_you_lists_each_task_waiting_on_you_with_its_next_step tests/test_web.py::test_running_tasks_show_their_step_activity_and_quiet_time tests/test_web.py::test_plans_show_one_square_per_task_and_finished_plans_collapse tests/test_web.py::test_empty_board_says_how_to_load_plans tests/test_web.py::test_board_escapes_text_from_tasks_and_agents tests/test_web.py::test_only_get_requests_for_localhost_are_answered tests/test_web.py::test_the_web_reads_the_board_read_only tests/test_web.py::test_pages_and_static_files_load_nothing_from_the_network tests/test_web.py::test_web_serves_the_board_and_its_assets_over_http tests/test_web.py::test_web_command_falls_back_to_a_free_port_and_refuses_a_busy_explicit_one"
    - "uv run pytest -q tests/test_observe.py tests/test_db.py"
  risk: medium

- id: webui-t04
  goal: "Each task has a page at /tasks/TASK, and every task id on the board links to it. It shows the task's status and next step with its full failure note, its contract with what it waits for and what needs it, every agent run newest first with its report, and the task's live log. It looks like docs/design/webui/task.html, without that page's buttons"
  spec_refs:
    - "docs/plans/webui.md#task-page"
    - "docs/plans/webui.md#statuses"
    - "docs/plans/webui.md#look"
    - "docs/design/webui/task.html"
  depends_on:
    - webui-t03
  non_goals:
    - "Transcript pages, and the `Read the transcript` links (webui-t05)"
    - "Buttons or forms (webui-t06, webui-t07)"
    - "Editing a contract from the page"
    - "Changing `factory show` or `factory logs`"
  acceptance:
    - "GET /tasks/TASK renders the task page with the classes and structure of docs/design/webui/task.html. Task ids are URL-quoted in links. An unknown task gets a 404 page that says `TASK isn't on this board` and links to the board"
    - "The page head has breadcrumbs (Board, the plan linking to its card on the board, the task id), then the id and status, then the goal as the title. The facts line shows the risk, builds, cost, branch, `built on BASE_REF at SHORT_SHA`, and the pull request as a link when there is one, each only when set"
    - "The next-step panel follows the plan's Task page section for every status. A failed, conflict, ci_failed or changes_requested task shows its full note in the panel's <pre>"
    - "The contract shows `Done when` (acceptance), `Not part of it` (non-goals), `Checked with` (each verification command with a copy button), `Waits for` (depends_on), `Needed by` (tasks whose depends_on names this task) and `Reads` (spec refs). Each dependency shows its status and links to its page"
    - "Runs are listed newest first, with the labels, outcome classes and facts described in the Task page section. Each report is in a <details> with a stable id, and only the newest run's report starts open"
    - "The log panel shows the last 200 lines of $FACTORY_HOME/logs/TASK.log, with each line's time and tag in their own spans, or `No log yet.` without one. The panel is a <pre class=\"log\" data-follow>"
    - "The page's <main> has data-refresh=\"2\""
    - "On the board, every task id in Needs you, Running and the plans links to its task page"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_web.py::test_task_page_shows_the_contract_with_what_it_waits_for_and_what_needs_it tests/test_web.py::test_task_page_lists_runs_newest_first_with_labels_outcomes_and_reports tests/test_web.py::test_task_page_next_step_follows_the_status tests/test_web.py::test_task_page_tails_the_task_log tests/test_web.py::test_unknown_task_is_a_404_that_links_back_to_the_board tests/test_web.py::test_board_links_every_task_to_its_page"
    - "uv run pytest -q tests/test_web.py"
  risk: low

- id: webui-t05
  goal: "Each agent run has a transcript page at /tasks/TASK/runs/RUN, linked from the task page. It opens with the run's model, steps, tokens, cost, time and tool mix, then shows each step's text, tool calls and results, with long results folded and refused commands flagged. It looks like docs/design/webui/transcript.html"
  spec_refs:
    - "docs/plans/webui.md#transcript-page"
    - "docs/plans/webui.md#look"
    - "docs/design/webui/transcript.html"
    - "factory/observe.py"
    - "factory/agents.py"
  depends_on:
    - webui-t04
  non_goals:
    - "Changing the transcript format or what agents record"
    - "Changing `factory transcript` or `factory trace`"
    - "Searching transcripts or comparing runs"
    - "Buttons or forms (webui-t06, webui-t07)"
  acceptance:
    - "GET /tasks/TASK/runs/RUN renders the transcript at the path in runs.transcript, with the classes and structure of docs/design/webui/transcript.html. A run id that doesn't exist, or belongs to another task, gets a 404 page linking to the task. A run with no transcript path, or whose file is missing, says `No transcript was recorded for this run.` and links to the task"
    - "The page head has breadcrumbs (Board, plan, task, the run's label), the label and outcome, and the title `What the ROLE did, step by step.` ROLE is planner, builder, reviewer or verifier for those roles, else the step name. The facts line shows the model, steps, tokens in and out, cost, model time and tool time, and the tool mix, all computed with observe.trace_rows"
    - "The system prompt and the task message are folded <details> labelled `What the agent was told (N characters)` and `The task it was given (N characters)`. Each step shows its number, model time, tool time, tokens and cost beside its text and its tool calls. Each call shows its name and arguments, without `content`, followed by its result"
    - "A result longer than 2,000 characters is a folded <details> labelled `Result, N characters`. A result that starts with `refused` has the refused class. A `stopped` event shows its reason"
    - "A last line that doesn't parse, from a transcript still being written, is skipped without an error"
    - "The page's <main> has data-refresh=\"2\" while the run has no ended_at, and none once it has one"
    - "On the task page, each run whose transcript file exists has a `Read the transcript` link to its page"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_web.py::test_transcript_page_shows_each_step_with_its_calls_and_results tests/test_web.py::test_long_results_are_folded_and_refusals_flagged tests/test_web.py::test_transcript_page_refreshes_only_while_its_run_is_running tests/test_web.py::test_a_half_written_transcript_line_is_skipped tests/test_web.py::test_a_run_of_another_task_or_without_a_transcript tests/test_web.py::test_task_page_links_runs_to_their_transcripts"
    - "uv run pytest -q tests/test_web.py tests/test_observe.py"
  risk: medium

- id: webui-t06
  goal: "The page can change the board through the same `factory` commands you'd type: Load plans, Check GitHub, Put on hold, Take off hold, Remove worktree and Stop. Each runs its command as a job you can follow on a new Activity page, Remove worktree and Stop ask for confirmation first, and only forms served by this `factory web` are accepted"
  spec_refs:
    - "docs/plans/webui.md#actions"
    - "docs/plans/webui.md#jobs"
    - "docs/plans/webui.md#activity-page"
    - "docs/plans/webui.md#security"
    - "docs/design/webui/activity.html"
    - "docs/design/webui/board.html"
    - "docs/design/webui/task.html"
  depends_on:
    - webui-t05
  non_goals:
    - "Starting a run, the run form, and the Run plan and Run again buttons (webui-t07)"
    - "Merging, closing or commenting on pull requests"
    - "Editing plans or contracts"
    - "The server writing the board itself: every change is a `factory` command"
  acceptance:
    - "Each action in the plan's Actions table is a POST form on the pages the table names, as the mockups place them. Its button's title is the command it runs. Stop and Remove worktree link to GET /confirm?action=ACTION&target=TARGET. That page says what will happen and holds the POST form, so a single click never stops a run or removes a worktree"
    - "POST /actions/ACTION validates its target against the board: the task or plan exists and the action applies to its status, as the Actions table says. If so, it starts the command as a job. Otherwise it answers 409 with a page saying why"
    - "A POST is refused with 403 when its form's `token` isn't the one this server generated at startup, when an Origin header is present and isn't this server's own `http://127.0.0.1:PORT` or `http://localhost:PORT`, when Sec-Fetch-Site is present and isn't `same-origin`, or when the Host check fails. A content type other than application/x-www-form-urlencoded gets 415, and a body over 16 KB gets 413. Every page's forms carry the token in a hidden field"
    - "New factory/web/jobs.py runs a job as the Jobs section says: the command, its output and its result in their own directory, started detached so the job survives `factory web` stopping. A job runs `python -m factory.cli …` with the interpreter the server runs under, in the repository root. App takes a launch argument so that tests can replace the process start"
    - "Load plans, Check GitHub, Put on hold, Take off hold and Remove worktree wait up to 15 seconds for their job. They then answer 303 back to the page the form came from, which must be a local path, else to /. That page shows a notice with the outcome, the command, its output's last line, and a link to the job on the activity page. Stop answers 303 to /activity at once, with a notice for its job"
    - "GET /activity renders the activity page as docs/design/webui/activity.html shows it. Its parts are a sentence counting running jobs, the notice when one is asked for, and the last 50 jobs newest first. Each job shows its command, outcome, start time and duration, and the last 200 lines of its output in a <details>, open for running and failed jobs. The page ends with the last 200 lines of every task's log, merged. Its <main> has data-refresh=\"2\". The top bar's navigation has Board and Activity on every page"
    - "Job directories beyond the newest 200 are deleted when a new job starts"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_web.py::test_each_action_runs_its_factory_command_as_a_job tests/test_web.py::test_actions_are_refused_for_tasks_they_dont_apply_to tests/test_web.py::test_posts_without_this_servers_token_or_from_another_origin_are_refused tests/test_web.py::test_stop_and_remove_worktree_ask_for_confirmation tests/test_web.py::test_quick_actions_return_to_their_page_with_a_notice tests/test_web.py::test_a_job_records_its_output_and_exit_code_and_outlives_the_server tests/test_web.py::test_activity_lists_jobs_newest_first_with_their_output tests/test_web.py::test_old_jobs_are_pruned"
    - "uv run pytest -q tests/test_web.py"
  risk: high

- id: webui-t07
  goal: "A plan or a single task can be started from the page through a run form that shows what will run, takes a required cost cap and the run's limits, previews the exact `factory run` command, and says what it may cost. The board's Run plan and Run again buttons open the form, and a started run is followed on the activity page"
  spec_refs:
    - "docs/plans/webui.md#run-form"
    - "docs/plans/webui.md#actions"
    - "docs/plans/webui.md#security"
    - "docs/design/webui/run.html"
    - "factory/scheduler.py"
  depends_on:
    - webui-t06
  non_goals:
    - "Runs that skip gates, run without the sandbox, allow network, skip the pull request or force a task"
    - "Choosing models per role from the page"
    - "Scheduling runs for later"
    - "Changing what `factory run` does"
  acceptance:
    - "GET /run?plan=PLAN and GET /run?task=TASK render the run form as docs/design/webui/run.html shows it. What will run lists each task the run would take on and what happens to it, as the Run form section says. A plan or task with nothing to run shows why instead of the form"
    - "The form has the fields from the Run form section, each with its default, limits and hint. Tasks at once appears only for a plan, and the agent flows come from the config's `flows`"
    - "The page shows the command the form will run, and app.js updates it as the fields change. Below it is the sentence `Agents call your model provider, which costs money: at most $CAP for each of N tasks, $TOTAL in all.`, then `The run keeps going if you close this page. Stop it from the board.` When missing_keys finds provider keys missing for the flow's models, the page names them and disables Start run"
    - "POST /actions/run passes the token and origin checks of webui-t06. It re-renders the form with an error beside each invalid field (400) and refuses with 409 when the target has nothing to run or the task is already running. Otherwise it starts `factory run TARGET --max-cost CAP --max-attempts N`, plus `--parallel N` for a plan, `--flow F` when F isn't the config's `flow`, and `--quiet` for a task. It does this as a job and answers 303 to /activity with the notice `Started the PLAN plan.` or `Started TASK.`"
    - "Failed, conflict, ci_failed and changes_requested tasks have a Run again button (a link to /run?task=TASK) on the board and the task page. Every plan with a task that a plan run would start now (scheduler.startable) has a Run plan button (a link to /run?plan=PLAN) on its card"
    - "The cost cap starts at the cap of the last run started from the page, else 5.00"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_web.py::test_run_form_lists_what_will_run_and_previews_the_command tests/test_web.py::test_a_run_needs_a_valid_cost_cap_and_limits tests/test_web.py::test_starting_a_run_launches_factory_run_with_the_forms_flags tests/test_web.py::test_a_run_cannot_be_started_without_the_form tests/test_web.py::test_missing_provider_keys_disable_start_run tests/test_web.py::test_run_buttons_appear_where_a_run_would_do_something"
    - "uv run pytest -q tests/test_web.py tests/test_scheduler.py"
  risk: high

- id: webui-t08
  goal: "The docs describe `factory web` and `factory stop`: the README quick start, the command reference with what each page shows and what each button runs, an architecture section on the web page and its safeguards, the AGENTS.md section and its template, the factory-ops skill, and NEXT.md item 10 marked done"
  spec_refs:
    - "docs/plans/webui.md#design"
    - "docs/reference.md#commands"
    - "docs/architecture.md#components"
  depends_on:
    - webui-t07
  non_goals:
    - "Code changes"
    - "This repository's installed skill copies under .claude/skills or .agents/skills, which `factory init --force` refreshes"
    - "Screenshots or other images"
  acceptance:
    - "README.md's quick start shows `factory web` next to `factory top`"
    - "docs/reference.md's command table has rows for `factory web [--port N] [--no-open]` and `factory stop TARGET [--wait SECONDS]`. A `### The web page` subsection lists the pages and, for each button, the command it runs"
    - "docs/architecture.md has a `## The web page` section. It says the server only reads the board and every change is a `factory` command run as a job. It covers the token and origin checks, the Host check, the response headers, 127.0.0.1 only with `ssh -L 8765:127.0.0.1:8765 HOST` to reach another machine, and the board's WAL mode. The Components table lists factory/web/"
    - "factory/templates/agents-section.md and this repository's AGENTS.md name `factory web` in their State line, identically"
    - "factory/templates/skills/factory-ops/SKILL.md says the page can show the board and run, stop or hold tasks, and names `factory stop`"
    - "NEXT.md marks item 10 done in its table, with a link to docs/architecture.md#the-web-page"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "grep -q 'factory[[:space:]]web' README.md"
    - "grep -qF 'web [--port N] [--no-open]' docs/reference.md"
    - "grep -qF 'stop TARGET [--wait SECONDS]' docs/reference.md"
    - "grep -q '^## The web page' docs/architecture.md"
    - "grep -q 'factory[[:space:]]web' factory/templates/agents-section.md"
    - "grep -q 'factory[[:space:]]web' AGENTS.md"
    - "grep -q 'factory[[:space:]]stop' factory/templates/skills/factory-ops/SKILL.md"
    - "grep -q 'architecture.md#the-web-page' NEXT.md"
    - "uv run pytest -q tests/test_templates.py"
  risk: low
```

Planned test additions:

| Task | File | Tests |
|---|---|---|
| t01 | `tests/test_db.py` | `test_the_board_opens_in_wal_mode_with_a_long_busy_timeout`, `test_a_rollback_journal_board_is_switched_to_wal_on_open`, `test_parallel_writers_and_readers_never_see_a_locked_board`, `test_a_locked_heartbeat_is_skipped_and_the_run_carries_on` |
| t02 | new `tests/test_stop.py` | `test_stop_ends_a_running_task_as_failed_and_records_the_run_as_stopped`, `test_stop_kills_a_task_that_ignores_sigterm`, `test_a_plan_run_records_its_pid_and_stops_its_tasks_on_sigterm`, `test_stop_plan_stops_the_plan_run_and_its_running_tasks`, `test_stop_refuses_unknown_targets_and_idle_tasks`, `test_a_stale_plan_pid_file_is_removed` |
| t03 | new `tests/test_web.py` | `test_board_sentence_and_counts_match_factory_top`, `test_needs_you_lists_each_task_waiting_on_you_with_its_next_step`, `test_running_tasks_show_their_step_activity_and_quiet_time`, `test_plans_show_one_square_per_task_and_finished_plans_collapse`, `test_empty_board_says_how_to_load_plans`, `test_board_escapes_text_from_tasks_and_agents`, `test_only_get_requests_for_localhost_are_answered`, `test_the_web_reads_the_board_read_only`, `test_pages_and_static_files_load_nothing_from_the_network`, `test_web_serves_the_board_and_its_assets_over_http`, `test_web_command_falls_back_to_a_free_port_and_refuses_a_busy_explicit_one` |
| t04 | `tests/test_web.py` | `test_task_page_shows_the_contract_with_what_it_waits_for_and_what_needs_it`, `test_task_page_lists_runs_newest_first_with_labels_outcomes_and_reports`, `test_task_page_next_step_follows_the_status`, `test_task_page_tails_the_task_log`, `test_unknown_task_is_a_404_that_links_back_to_the_board`, `test_board_links_every_task_to_its_page` |
| t05 | `tests/test_web.py` | `test_transcript_page_shows_each_step_with_its_calls_and_results`, `test_long_results_are_folded_and_refusals_flagged`, `test_transcript_page_refreshes_only_while_its_run_is_running`, `test_a_half_written_transcript_line_is_skipped`, `test_a_run_of_another_task_or_without_a_transcript`, `test_task_page_links_runs_to_their_transcripts` |
| t06 | `tests/test_web.py` | `test_each_action_runs_its_factory_command_as_a_job`, `test_actions_are_refused_for_tasks_they_dont_apply_to`, `test_posts_without_this_servers_token_or_from_another_origin_are_refused`, `test_stop_and_remove_worktree_ask_for_confirmation`, `test_quick_actions_return_to_their_page_with_a_notice`, `test_a_job_records_its_output_and_exit_code_and_outlives_the_server`, `test_activity_lists_jobs_newest_first_with_their_output`, `test_old_jobs_are_pruned` |
| t07 | `tests/test_web.py` | `test_run_form_lists_what_will_run_and_previews_the_command`, `test_a_run_needs_a_valid_cost_cap_and_limits`, `test_starting_a_run_launches_factory_run_with_the_forms_flags`, `test_a_run_cannot_be_started_without_the_form`, `test_missing_provider_keys_disable_start_run`, `test_run_buttons_appear_where_a_run_would_do_something` |

Each verification command names its tests, so a missing test fails the gate rather than passing with zero selected.

The project sets no `e2e`, so no task adds an e2e test. `session_log` is set, so each task adds its own `docs/sessions/<date>-<task id>.md`.

Every task changes the factory itself, and runs through `factory run` like the agent-flows and bench tasks did. The tests use the `home` and `repo` fixtures. The over-HTTP test binds port 0 on 127.0.0.1, which works in the offline sandbox because bubblewrap brings up loopback in its network namespace. No test starts a real agent: the action and run tests pass App a launch function that records the command, and the job test runs `factory sync` on the `repo` fixture.

### Risks

1. **Another website could make the browser start a paid run.** A page on any site can POST a form to `127.0.0.1:8765`. **Action:** a POST must carry the token this server generated at startup, which only its own pages contain and no other origin can read: there are no CORS headers, and the Host check stops DNS rebinding. A POST with a foreign `Origin` or `Sec-Fetch-Site` is also refused. A run additionally needs the form's cost cap. t06 and t07 test each refusal.
2. **"Pretty" can't be gated, and no agent sees the page.** **Action:** the mockups and the stylesheet are committed with this plan, and the server serves that stylesheet unchanged. Each web task's acceptance names its mockup, so the reviewer compares markup and classes, not taste. You look at the real pages against the mockups before merging t03, t04 and t07 (see Verification).
3. **No browser runs in the sandbox, so `app.js` isn't tested by the gates.** **Action:** every page is complete without JavaScript, and the tests check the server's HTML and its `data-refresh` attributes. `app.js` has only the jobs in [Live pages](#live-pages) and needs no library. You check refresh, copy and the reconnect banner by hand before merging t03.
4. **A stopped run might not exit.** A model call in flight runs in a worker thread, which can hold the process after SIGTERM. **Action:** `factory stop` waits `--wait` seconds (default 10), then kills the process group. t02 tests a process that ignores SIGTERM.
5. **WAL mode changes the live board.** The first command after t01 merges switches `factory.db` to WAL, and WAL needs a local filesystem. **Action:** the state directory is under `~/.local/share` by default, which is local. A failed switch leaves the board in rollback mode and the open still succeeds. The architecture docs (t08) say a board must not live on a network filesystem.
6. **Runs started from the page outlive it.** **Action:** that is intended, and the run form says so. Jobs are detached, and the activity page finds them again from their directories after `factory web` restarts. Old job directories beyond the newest 200 are pruned.
7. **Text written by agents goes onto the page.** Goals, notes, reports, logs and tool output can hold markup. **Action:** every value goes through one escaping helper. The CSP forbids inline scripts and styles, and the mockups need neither. t03 tests a `<script>` in a goal, a note and the activity text, and a `javascript:` PR URL.
8. **Merge conflicts with other plans.** measure, bench and strict-flow also change `factory/cli.py`, `factory/db.py`, `factory/pipeline.py` and `factory/scheduler.py`. **Action:** this plan only adds two subcommands, a constructor argument and pragmas to `DB`, a read-only mode for `open_db`, a SIGTERM handler, and a pid file. A conflicting PR goes through the factory's own conflict resolution (`factory run TASK`).

---

## Problem

The factory is driven from the terminal, and two things get in the way.

**Seeing what needs you takes several commands.**
- `factory top` (`factory/observe.py:127`) redraws a fixed-width text screen and cuts long goals and notes at the terminal width.
- `factory status`, `show`, `logs`, `trace` and `transcript` (`factory/cli.py:499`–`664`) each show one slice.
- Nothing pulls out what needs a human next: a PR to review, a failure to rerun, a dead process. Nothing is clickable either: a PR, a task's dependencies and its runs are separate commands.
- A transcript is a wall of text, in which a 20,000-character tool result looks like a one-line answer.

**Acting means remembering the right command and its flags.** Rerunning a failure, holding a task, removing a worktree, and starting a plan with a cost cap and the right parallelism are each a different command. There is no way to stop one running task at all, short of finding its process and killing it, which leaves it `building` until `status --refresh` notices.

**The board locks under load.** `DB.__init__` (`factory/db.py:75`) opens the SQLite file with the default rollback journal and a 5-second busy timeout. Every agent log line commits a heartbeat (`factory/pipeline.py`, `_event`), and every commit locks the whole file. With a few runs in parallel, `factory top` and a starting run can wait more than 5 seconds and die with `sqlite3.OperationalError: database is locked`. Reproduced on a scratch board on 2026-11-13: three saturated writers broke the 5-second limit, while WAL mode served the same load with no errors and reads under 2 ms.

## Goal

`factory web` opens a page that says in one sentence what needs you, and shows every plan and task at a glance, live. Every task opens to its contract, runs, reports and log, and every agent run opens to a readable transcript. Every common action is a button that runs the `factory` command you would have typed, and starting a run takes a form with a cost cap. Everything stays on this machine, needs no new dependencies, and looks like fractal-dev.xyz.

## Design

```
 browser ──GET──▶ factory web (127.0.0.1:8765, ThreadingHTTPServer)            factory/web/server.py
   │               │ Host check · security headers · static allowlist
   │               ├── /                     board          ◀─┐
   │               ├── /tasks/TASK           task page        │ views.py: data from a read-only
   │               ├── /tasks/TASK/runs/RUN  transcript       │ connection per request, logs and
   │               ├── /activity             jobs + logs      │ transcripts, rendered to HTML
   │               ├── /run?plan=|task=      run form         │
   │               ├── /confirm?action=…     confirm page   ◀─┘
   │               └── /static/…             app.css, app.js, favicon.svg, fonts/*.woff2
   │
   └──POST─▶ /actions/ACTION   token + Origin + Host checks → validate → jobs.py
                                   │
                                   ▼  detached: python -m factory.web.jobs DIR
                          factory sync | status --refresh | abandon | requeue | clean | stop | run …
                                   │
                                   ▼
             $FACTORY_HOME/factory.db (WAL) · logs/ · transcripts/ · web/jobs/NNNN/
```

**Principles.**
- **Every button is a factory command.** The server never writes the board. It reads it through read-only connections, and every change runs a `factory` command as a job, exactly as you would type it. Each button's tooltip shows its command, and the activity page lists every command the page ran, with its output. The page therefore teaches the CLI instead of becoming a second way to change state with its own rules.
- **Say what needs you first.** The board opens with one sentence about what needs you, then lists it with the next step for each task. Everything else (running tasks, then plans) comes after.
- **One look, from the mockups.** Pages use the classes in `app.css` exactly as the mockups do. A new element gets a new rule, and the existing rules don't change.
- **Reuse the terminal's logic.** Pages use `observe.detail`, `observe.plan_groups`, `observe.liveness`, `observe.human_secs`, `observe.trace_rows`, `db.readiness`, `db.ready` and `scheduler.startable`, so the page and `factory top` never disagree about a task.
- **Server-rendered.** Python builds each page's HTML with one escaping helper and no template library. JavaScript only refreshes, copies and formats times, and every page works without it.

### `factory web`

```
factory web [--port N] [--no-open]

$ factory web
factory web: http://127.0.0.1:8765/ (Ctrl-C to stop)
```

- The command opens the board once with `open_db(home)`, which migrates it and switches it to WAL. From then on, every request reads through its own `open_db(home, readonly=True)` connection.
- It binds `127.0.0.1:8765` by default. If 8765 is busy and `--port` wasn't given, it binds a free port and prints it, so a second project's `factory web` gets its own port. A busy explicit `--port` exits 1.
- It opens the browser with `webbrowser.open` unless `--no-open` is given. It prints nothing per request, and Ctrl-C stops it with exit 0. Runs it started keep going.
- Module layout: `factory/web/server.py` (App, routing, checks, headers, `make_server`), `factory/web/views.py` (page data and HTML), `factory/web/jobs.py` (t06), `factory/web/static/`. Static files load through `importlib.resources.files("factory.web") / "static"`. The wheel ships them because hatch packages everything under `factory/`.

### Statuses

Every page uses the same word, class and mark for a status. The class sets the hue, and the mark is a 9px shape (`<i class="mark">`) whose fill and form differ by status, so colour is never the only signal. The plan strip uses the same classes on `<i>`.

| Board status | Word | Class | Mark | In Needs you? |
|---|---|---|---|---|
| `merged` | Merged | `s-merged` | filled square, green | no |
| `pr_open` | PR open | `s-pr` | filled diamond, amber | yes |
| `conflict` | Conflict | `s-attn` | outlined diamond, amber | yes |
| `ci_failed` | CI failing | `s-attn` | outlined diamond, amber | yes |
| `changes_requested` | Changes requested | `s-attn` | outlined diamond, amber | yes |
| `planning`, `building`, `reviewing`, `verifying` | Planning, Building, Reviewing, Verifying | `s-live` | filled square, blue, breathing | no |
| `failed` | Failed | `s-failed` | crossed square, red | yes |
| active or queued, but its process is gone (`observe.liveness` is DEAD) | Process gone | `s-failed` | crossed square, red | yes |
| `queued`, ready | Ready | `s-ready` | outlined square, white | no |
| `queued`, waiting | Waiting | `s-waiting` | outlined square, grey | no |
| `abandoned` | On hold | `s-held` | dashed square, grey | no |

Needs you lists, in this order and then by task id:

| Status | Next step (the row's first line) | Second line | Buttons |
|---|---|---|---|
| Process gone | Its process is gone. Check GitHub to mark it failed. | `observe.detail` | Check GitHub (t06) |
| Failed | Read why it failed, then run it again. | the note's first line | Run again (t07), Put on hold (t06) |
| Conflict | Run it again to resolve the conflict with its base. | the note's first line | Run again (t07), Open pull request |
| CI failing | Run it again to fix the failing checks on its pull request. | the note's first line | Run again (t07), Open pull request |
| Changes requested | Run it again to address the review. | the note's first line | Run again (t07), Open pull request |
| PR open | Review and merge pull request #N. When it is stacked: Review pull request #N; merge it after DEP. | Every gate passed. Merging is your approval. | Open pull request |

`#N` is the number at the end of the PR URL. Open pull request is a link, present from t03, and the other buttons arrive with the tasks named.

### Board

The structure is `docs/design/webui/board.html`.

- **Sentence.** `N task(s) need(s) you.` or `Nothing needs you.`, followed by `R is running.` or `R are running.` when R > 0. When nothing needs you and nothing runs, the second part is `N tasks are ready to run.` if any are ready, else `Every plan is finished.` once every task is merged or on hold. An empty board says `No tasks yet.`
- **Counts** (`<dl class="tally">`): running, need you, ready, waiting, merged, on hold (only when > 0), and spent (`$` with two decimals, the sum of every task's cost).
- **Needs you:** the rows above. When the list is empty: `Nothing needs you right now.` in `.empty`.
- **Running:** one row per task in an active status: the status word, id, goal on one line (full in `title`), elapsed time, cost, and Stop (t06). A second line (`.now`) shows the step, then a `<progress>` of steps used out of the step limit, then the activity, then `quiet Ns`. The step reads like `build 1, step 14 of 120`, taken from the `step N/M` in the task's progress text, and the bar is left out when there is no such text. The section is left out when nothing runs.
- **Plans:** grouped as `factory top` groups them. Plans with a running task, an open PR or a failure come first, then plans with work left, sorted by name within each group. Each is a `<details class="plan" id="plan-NAME">`, open for the first group. Its summary shows the plan name, the strip (one square per task in dependency order, with an `aria-label` giving the counts), the counts text, the plan's cost and Run plan (t07). The counts text is `M of N merged`, then each other status with a count, in the order of the Statuses table, joined by commas. Inside are the plan's task rows: status, id, goal, `waits for …` (`db.readiness`) for a waiting task, `N build(s)` when there were any, and cost. Plans where every task is merged or on hold go last, inside a closed `<details class="finished">` titled `N finished plan(s)`.
- **Top bar:** `factory / NAME`, the navigation (Board; Activity from t06), the live indicator, and Load plans and Check GitHub (t06).
- **Footer:** the factory version, the address (`127.0.0.1:PORT, this machine only`) and the state directory.

### Task page

The structure is `docs/design/webui/task.html`.

- **Next-step panel** (`.next-step`). Its heading and paragraph depend on the task's status:
  - In Needs you: the next step from the table above, a sentence on what Run again or the other buttons will do, and the full note in `<pre>`.
  - Running: `Running: ROLE N, step S of M.` with the activity and quiet time.
  - Ready: `Ready. The next run of its plan starts it.`
  - Waiting: `Waits for DEP.`, listing the dependencies that hold it.
  - Merged: `Merged.` with the PR link.
  - On hold: `On hold. Plan runs skip it until you take it off hold.`
- **Run labels.** A run's name is its flow step, or its role when the step is unset. A build reads `build N`. A run tied to a build attempt reads `NAME, build N` (`review, build 3`, `gates, build 2`). A run with attempt 0 reads `NAME` (`plan`).
- **Outcome classes** go by the outcome's first word, so `committed (step limit)` counts as `committed`:

  | Class | Outcomes |
  |---|---|
  | `o-good` | `done`, `committed`, `APPROVE`, `pass`, `verified`, `opened` |
  | `o-bad` | `error`, `fail`, `CHANGES`, `stopped` |
  | `o-live` | the run has no `ended_at` |
  | none | anything else |

- **Run facts:** the model's last path segment (full name in `title`), steps, tokens in and out in thousands, and cost, each only when set. The run's head shows its start time, relative with the exact UTC time in `title`, and its duration (`ended_at − started_at`, or the time so far).
- **Log:** the last 200 lines of `logs/TASK.log`, each split into time, tag and text spans.

### Transcript page

The structure is `docs/design/webui/transcript.html`. The page reads the JSONL events the agent loop records (`factory/agents.py`): `system`, `human`, `ai` (`step`, `text`, `usage`, `cost_usd`, `tool_calls`), `tool` (`name`, `content`) and `stopped`. The `tool` events after an `ai` event answer its `tool_calls` in order. Step timing and the summary come from `observe.trace_rows`.

### Actions

| Button | Where | Command | Applies when | Confirm | After |
|---|---|---|---|---|---|
| Load plans | top bar; empty board | `factory sync` | always | no | back, with a notice |
| Check GitHub | top bar; Process gone rows | `factory status --refresh` | always | no | back, with a notice |
| Put on hold | Failed rows; task page | `factory abandon TASK --note "put on hold from factory web"` | `queued` or `failed`, not running | no | back, with a notice |
| Take off hold | task page | `factory requeue TASK` | `abandoned` | no | back, with a notice |
| Remove worktree | task page | `factory clean TASK` | the worktree exists and the task isn't running | yes | back, with a notice |
| Stop | Running rows; task page; a running plan job on the activity page | `factory stop TASK` or `factory stop PLAN` | the task is running; the plan has a running plan run or task | yes | the activity page |
| Run plan, Run again | plan cards; Needs you rows; task page | the run form (t07), then `factory run …` | see [Run form](#run-form) | the form is the confirmation | the activity page |

A "back" redirect goes to the form's `next` field when it is a local path (it starts with `/` and not `//`), else to `/`. The notice reads `Done: COMMAND` or `Failed: COMMAND`, with the output's last line and a link to the job on the activity page.

### Jobs

- A job is a directory `$FACTORY_HOME/web/jobs/NNNNNN/`, numbered upward. `job.json` holds the argv, the command as displayed, its kind (`run`, `stop` or `quick`), the target and the start time. `output.log` gets stdout and stderr. The job writes `result.json` (exit code and end time) when its command ends.
- The server starts `python -m factory.web.jobs DIR` with `start_new_session=True` and stdin from /dev/null, and records its pid in `job.json`. That runner starts the command in the repository root, writes `output.log` and `result.json`, and exits. Because the runner is detached, a job survives `factory web` stopping, and a restarted server finds it again by its directory.
- A job's outcome is: running (no `result.json` and its pid is alive); done (exit 0); `exit N`; or lost (no `result.json` and its pid is gone).

### Activity page

The structure is `docs/design/webui/activity.html`. It has the sentence (`N commands are running.` or `Nothing is running from this page.`), the notice for `?job=ID`, and the last 50 jobs on the run timeline. Each job shows its output in a `<details id="job-ID">`, and a running plan or task run also has Stop. The page ends with the last 200 lines of every task's log, merged by time with each line prefixed by its task id, as `factory logs --all` merges them.

### Run form

The structure is `docs/design/webui/run.html`.

- **What will run.** For a plan, each task that isn't merged, on hold, or `pr_open`, with what will happen to it:
  - Ready, or a failure, conflict, CI failure or review that will start now: `Starts now, with a fresh build.`, or `Starts now, to resolve the conflict with its base.`, `…to fix the failing checks on its pull request.`, `…to address the review.`
  - Waiting: `Starts when DEP has a pull request.`
  - Already running: `Running already; this run leaves it alone.`

  For a task, just that task and what will happen to it. When nothing would start, the page says why (for example `Every task of PLAN is merged, on hold or has a pull request.`) and shows no form.
- **Fields:**

  | Field | Name | Default | Limits | Hint |
  |---|---|---|---|---|
  | Cost cap per task, in USD | `max_cost` | the last cap used from the page, else 5.00 | required, a number above 0 and at most 1000 | A task stops once it has spent this much. |
  | Tasks at once (plans only) | `parallel` | 3 | 1–8 | Independent tasks run side by side. |
  | Builds per task | `max_attempts` | 3 | 1–5 | How often review or the gates may send it back. |
  | Agent flow | `flow` | the config's `flow` | a key of `flows` | From .factory/config.yaml. |

- **Cost line.** N is the number of tasks the run may start, counting waiting tasks that could start during it, and `$TOTAL` is N × cap.

### Live pages

`factory/web/static/app.js` is plain JavaScript with no libraries, loaded with `defer`, and it has five jobs:

1. **Refresh.** When `<main>` has `data-refresh="N"`, it fetches `location.href` (`cache: "no-store"`) every N seconds while the tab is visible, and at once when the tab becomes visible again. It swaps `<main>`'s content for the fetched page's, reopens every `<details>` the reader had open (by `id`) and closes those they'd closed, and keeps each `pre[data-follow]` scrolled to the bottom unless the reader had scrolled up. It doesn't refresh while focus is in a form field.
2. **Live indicator.** `.live-dot` reads `Live, updated HH:MM:SS` (`data-state="live"`), `Paused` while the tab is hidden (`paused`), and `Can't reach factory web` while fetches fail (`lost`). The `.banner` shows `Can't reach factory web. Retrying.` until a fetch succeeds.
3. **Copy.** Every `button.copy` copies the text of its `.cmd`'s `<code>` and reads `Copied` for 1.5 seconds. The buttons are rendered `hidden`, and the script unhides them.
4. **Times.** Each `<time datetime>` gets its `title` in the reader's local time.
5. **Run form preview.** On the run form, the `[data-preview] code` text follows the fields as they change.

### Security

| Measure | Detail |
|---|---|
| Bind | `127.0.0.1` only, with no `--host` option. To use another machine's board, tunnel: `ssh -L 8765:127.0.0.1:8765 HOST` |
| Host check | The `Host` header's name, without its port, must be `127.0.0.1` or `localhost`, or the request gets 403. This blocks DNS rebinding and lets an SSH tunnel on any local port through |
| Methods | GET and HEAD everywhere; POST only under `/actions/` (from t06). Anything else gets 405 with an `Allow` header |
| POST checks | The form's `token` must equal the server's random token (`secrets.token_urlsafe(32)`, made at startup). An `Origin` header, if present, must be this server's own origin. `Sec-Fetch-Site`, if present, must be `same-origin`. The content type must be `application/x-www-form-urlencoded` (415 otherwise), and the body at most 16 KB (413 otherwise) |
| Headers on every response | `Content-Security-Policy: default-src 'none'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self' data:; connect-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'`, plus `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer` and `Cache-Control: no-store`. There are no CORS headers |
| Board | Read through `file:PATH?mode=ro` connections only, so the server process itself can't write it |
| Files | Only `app.css`, `app.js`, `favicon.svg` and the five `fonts/*.woff2` files under `/static/`. Logs, transcripts and job output are reached through a task id, run id or job id, never a path in the URL. Every other path gets the 404 page |
| Output | One escaping helper (`html.escape(…, quote=True)`) for every value. A URL becomes an `href` only when it starts with `https://` or `http://`. There are no inline scripts, `style` attributes or event-handler attributes |

### Look

The mockups in [`docs/design/webui/`](../design/webui/) are the reference. Open them straight from the checkout, since they link the real stylesheet: `board.html`, `task.html`, `transcript.html`, `run.html`, `activity.html`. `factory/web/static/app.css` is the one stylesheet, and its fonts are in `factory/web/static/fonts/` with their SIL Open Font License texts.

- **Palette.** The site's tokens, unchanged: `--bg #0a0a0a`, `--bg-elevated #0f0f0f`, `--bg-card #141414`, `--border #242424`, `--border-accent #484848`, `--text-bright #f2f2f2`, `--text #d8d8d8`, `--text-secondary #9a9a9a`, `--text-muted #666`. The site has no hue, so four muted ones are added for status alone: `--ok #8fbf9f`, `--live #8ab4d8`, `--you #d4b06a` and `--bad #d98a80`. Against `--bg`, every colour that carries meaning has a contrast ratio of at least 7:1 (the status hues 7.4–9.6, `--text-secondary` 7.0). `--text-muted` (3.4:1) is used only for decoration. The page is dark only, like the site.
- **Type.** Instrument Serif for the one sentence at the top of each page, the task's goal and the plan names. Hanken Grotesk for body text and buttons. DM Mono for ids, numbers, commands, logs and transcripts. Numbers are tabular.
- **Layout.** Left-aligned, at most 70rem wide, with a 2.5rem gutter (1.25rem below 45rem). Content is rows separated by hairlines, not cards: the only boxed elements are the next-step panel, commands, reports, logs and form fields. Below 45rem each row stacks into lines, and below 60rem the task page's two columns stack.
- **Motion.** The live dot and a running task's mark breathe slowly. Nothing else moves on its own, and nothing moves under `prefers-reduced-motion`.
- **Focus.** A 2px `--text-bright` outline with a 2px offset on every focusable element.

### The board lock

`DB.__init__` connects with `timeout=30.0`, then runs `PRAGMA journal_mode=WAL` and `PRAGMA synchronous=NORMAL`. In WAL mode, readers never block writers and writers never block readers, and a commit appends to the WAL instead of rewriting the file under an exclusive lock. `synchronous=NORMAL` is safe in WAL mode: a power cut can lose the last commits, but it never corrupts the board.

WAL is stored in the database file, so the first open switches the board for every later process. A read-only connection works on a WAL board too (checked 2026-11-14: it reads alongside a writer in the middle of a transaction, and refuses writes).

Heartbeats and progress updates are advisory, because they only feed `factory top` and the page, so losing one is better than ending a run. Status, run and contract writes still raise.

### Stopping a run

```
factory stop TASK|PLAN [--wait SECONDS]
```

- **A task run** (`factory run TASK`) installs a SIGTERM handler that raises a `Stopped` exception in the main thread. The pipeline records the agent run in progress as `stopped`, sets the task to `failed` with the stopped note, and logs `[stage] stopped`. The sandbox's commands die with it (bubblewrap's `--die-with-parent`).
- **A plan run** (`factory run PLAN`) writes `$FACTORY_HOME/plan-runs/PLAN.pid`. On SIGTERM it stops starting tasks, sends SIGTERM to the task processes it started (each leads its own process group, since the scheduler starts them with `start_new_session=True`), waits, prints the summary and removes the pid file.
- **`factory stop`** sends SIGTERM and waits. If the process is still there after `--wait` seconds, it sends SIGKILL to the process group and writes the stopped note itself, so a stuck model call can't keep a task `building`.

## Files Changed

| File | Change |
|---|---|
| `factory/web/static/app.css`, `factory/web/static/fonts/` | Added by this plan: the stylesheet, five WOFF2 files and their OFL licences |
| `docs/design/webui/*.html` | Added by this plan: the mockups |
| `factory/db.py` | WAL, busy timeout, skippable heartbeat and progress (t01); `open_db(home, readonly=True)` (t03) |
| `factory/pipeline.py` | Run-log line for a skipped heartbeat (t01); the `stopped` run outcome and note (t02) |
| `factory/scheduler.py` | The plan run's pid file and SIGTERM handling (t02) |
| `factory/cli.py` | `factory stop` and the task run's SIGTERM handler (t02); `factory web` (t03) |
| `factory/web/__init__.py`, `server.py`, `views.py` | New: the server and the board (t03); task page (t04); transcript page (t05); actions, confirm and activity pages (t06); run form (t07) |
| `factory/web/jobs.py` | New: jobs (t06) |
| `factory/web/static/app.js`, `favicon.svg` | New (t03); the run form preview (t07) |
| `tests/test_db.py` | Lock tests (t01) |
| `tests/test_stop.py` | New (t02) |
| `tests/test_web.py` | New (t03), grown by t04–t07 |
| `README.md`, `docs/reference.md`, `docs/architecture.md`, `AGENTS.md`, `factory/templates/agents-section.md`, `factory/templates/skills/factory-ops/SKILL.md`, `NEXT.md` | Docs (t08) |
| `docs/sessions/` | Each task's session log entry |

## Test Plan

### Unit tests

The board tests seed a board through `open_db(home)` with the `home` fixture and `conftest.plan_text`, plus a second plan where needed. Most call `App.handle` directly.

- **t01** (`tests/test_db.py`)
  - `test_the_board_opens_in_wal_mode_with_a_long_busy_timeout`: `PRAGMA journal_mode` is `wal` and `PRAGMA busy_timeout` is 30000.
  - `test_a_rollback_journal_board_is_switched_to_wal_on_open`: a board created with plain `sqlite3` in `delete` mode reads `wal` after `DB(path)`. With another connection holding a write lock and a short timeout, `DB(path, timeout=0.2)` still opens.
  - `test_parallel_writers_and_readers_never_see_a_locked_board`: the eight-writer, one-reader, one-opener load from the acceptance, for 3 seconds, with no errors.
  - `test_a_locked_heartbeat_is_skipped_and_the_run_carries_on`: with another connection holding `BEGIN EXCLUSIVE`, `DB(path, timeout=0.2).heartbeat(…)` returns False and the connection isn't in a transaction. A pipeline step whose heartbeat is skipped logs `board busy: skipped a heartbeat` and finishes.
- **t02** (`tests/test_stop.py`)
  - `test_stop_ends_a_running_task_as_failed_and_records_the_run_as_stopped`: a child process claims a task, starts a run and waits inside the SIGTERM handling `factory run` installs. `factory stop TASK` ends it: the task is `failed` with the stopped note, the run's outcome is `stopped`, and the log has `[stage] stopped`.
  - `test_stop_kills_a_task_that_ignores_sigterm`: a child that ignores SIGTERM is killed after `--wait 1`, and `factory stop` sets the note itself.
  - `test_a_plan_run_records_its_pid_and_stops_its_tasks_on_sigterm`: `scheduler.run` with a fake launch writes and removes the pid file. Its SIGTERM handling terminates the launched processes and starts nothing more.
  - `test_stop_plan_stops_the_plan_run_and_its_running_tasks`: a live pid file and a running task of the plan are both stopped.
  - `test_stop_refuses_unknown_targets_and_idle_tasks`: unknown target and a queued task both exit 1 with their messages. A plan with nothing running prints the nothing-to-stop line and exits 0.
  - `test_a_stale_plan_pid_file_is_removed`: a pid file naming a dead process is removed.
- **t03** (`tests/test_web.py`)
  - `test_board_sentence_and_counts_match_factory_top`: a board with tasks in every status gives the sentence from the rules, and its running, ready and waiting counts and spend equal `observe.render_top`'s first line.
  - `test_needs_you_lists_each_task_waiting_on_you_with_its_next_step`: one task in each Needs you status, one PR stacked. The entries come in the table's order with its texts, the stacked one names its dependency, and running, queued, merged and held tasks are absent.
  - `test_running_tasks_show_their_step_activity_and_quiet_time`: a building task with progress text `build#1 step 14/120 …` shows `build 1, step 14 of 120`, a `<progress value="14" max="120">`, its activity and its quiet time. Without a `step N/M`, there is no progress bar.
  - `test_plans_show_one_square_per_task_and_finished_plans_collapse`: each plan's strip has one `<i>` per task in plan order with the status classes. The counts text follows the rule. An all-merged plan sits in the closed finished `<details>`, and the live plans' `<details>` are open.
  - `test_empty_board_says_how_to_load_plans`
  - `test_board_escapes_text_from_tasks_and_agents`: `<script>alert(1)</script>` in a goal, a note and an activity appears only escaped, and a `javascript:` PR URL is never an `href`.
  - `test_only_get_requests_for_localhost_are_answered`: POST gets 405. `Host: evil.example:8765` gets 403, while `localhost:9000` and `127.0.0.1:8765` get 200. Every response has the security headers. `/static/../db.py` and `/static/fonts/OFL-dmmono.txt` get 404.
  - `test_the_web_reads_the_board_read_only`: the request connection refuses an `UPDATE`, and serving the board leaves `factory.db`'s bytes unchanged.
  - `test_pages_and_static_files_load_nothing_from_the_network`: the HTML, `app.css` and `app.js` reference no `http://` or `https://` resource, and only PR links may be absolute URLs.
  - `test_web_serves_the_board_and_its_assets_over_http`: `make_server` on port 0 in a thread. `urllib` gets `/`, `/static/app.css` (`text/css`), `/static/app.js` (`text/javascript`), `/static/favicon.svg` and a font (`font/woff2`).
  - `test_web_command_falls_back_to_a_free_port_and_refuses_a_busy_explicit_one`: with the default port held and `serve_forever` stubbed, the command binds another port and prints it. A busy `--port` exits 1, and `webbrowser.open` runs only without `--no-open`.
- **t04–t07:** the names in the table above. Each asserts the acceptance item its name describes, against `App.handle`, and the action tests use a recording launch.

### End-to-end tests

None: the project sets no `e2e`. `test_web_serves_the_board_and_its_assets_over_http` runs the real server and a stdlib client on loopback. `test_a_job_records_its_output_and_exit_code_and_outlives_the_server` runs a real `factory sync` job.

## Verification

- `uv run pytest -q` passes after each task.
- After merging t03, t04 and again t07, reinstall the factory you run if it isn't an editable install (`uv tool install --reinstall .`), then:
  1. Run `factory web` in this repository. Put the board next to `docs/design/webui/board.html` opened from the checkout. The type, spacing, colours and layout match, and the counts match `factory top --once`.
  2. While a task runs, the board updates without a reload: its step, bar and activity change, and a plan you opened stays open.
  3. Stop `factory web`. The banner and the indicator say it can't be reached, and both clear when you start it again.
  4. Narrow the window below 45rem: rows stack and nothing scrolls sideways. Tab through the page: every control shows the focus ring.
  5. Click a copy button and paste: the command is right.
  6. After t04 and t05, open a failed task, the newest run's report and a transcript with a long tool result.
  7. After t07, start the `example` plan with a $0.50 cap from the page. Follow it on the activity page, stop it from the board, and check that the task ends `failed` with the stopped note.
- `curl -s -i -X DELETE http://127.0.0.1:8765/` gets 405. `curl -s -i -H 'Host: evil.example' http://127.0.0.1:8765/` gets 403. `curl -s -i -X POST -d 'x=1' http://127.0.0.1:8765/actions/sync` gets 403 (no token).

## Cross-Workstream Coordination

- **Depends on:** nothing. The pages read `runs.flow` and `runs.step` from [agent-flows](agent-flows.md), which are on main.
- **Required by:** [thoughts](thoughts.md). `thoughts-t03` waits for `webui-t05`: it adds each step's thoughts to the transcript page, and renames the page's model time from "thinking" to "in the model". The mockup `transcript.html` and the `.thinks` rules in `app.css` already show it.
- **Overlaps:** [measure](measure.md), [bench](bench.md) and [strict-flow](strict-flow.md) also change `factory/cli.py`, `factory/db.py`, `factory/pipeline.py` and `factory/scheduler.py`. This plan only adds to them (see Risk 8), so whichever lands second has a small conflict for the factory's conflict resolution.
- **Related:** [pr-descriptions](pr-descriptions.md). `webui-t05` failed when GitHub refused its PR body as over 65,536 characters; it runs again after `pr-descriptions-t01`, which keeps every body under the limit. Factory PRs then point to `factory show` and this plan's task page for the planner's plan and every agent's full report.
- **Later:** once measure's `factory stats` lands, a stats page can render its numbers. NEXT.md item 5 (steer a running agent) is planned in [steer](steer.md): `steer-t04` adds a box to a running task's page that runs `factory say`, and a "You said" block to the transcript page.
- **Supersedes** the unmerged `web-board` plan on branch `plan/web-board`, which was read-only and used system fonts and a different palette.

## Notes / Out of Scope

- **Merging, closing or commenting on PRs** from the page. Merging is the human gate and stays on GitHub; the page links to each PR.
- **Writing or editing plans and contracts.** Plans are written with `/plan-workstream` and live in git.
- **Choosing models per role, `--no-pr`, `--network`, `--no-sandbox`, `--skip-gates` and `--force`** from the run form. They stay terminal-only, because each one weakens a safeguard.
- **A light theme.** The page is dark, like the site.
- **More than one project per page.** Each `factory web` shows the board of the repository it was started in. One page for every board under `~/.local/share/factory/` is deferred.
- **Remote access and accounts.** There is no `--host` option and no login: tunnel over SSH. A shared board is NEXT.md item 6.
- **A JSON API, search, filters and charts.** These are deferred until a page needs them.
- **Notifications.** `factory run --notify` stays the way to be told a run ended.
