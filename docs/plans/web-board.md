# Plan: A board you can open in a browser

**Status:** Planned (2026-11-03). Workstream scoped; awaiting kickoff. Roadmap: [NEXT.md item 8](../../NEXT.md#8-watch-the-board-in-a-browser).

---

## Execution Plan

### Locked Decisions

| Decision | Choice |
|---|---|
| Form | **A live page served from this machine.** `factory web` starts a small server on `127.0.0.1`, opens the browser, and the page updates itself every few seconds while runs progress. It uses only the Python standard library and has no JavaScript build step, so no new dependencies |
| Actions | **Read-only.** The page only shows the board; you act in the terminal. The server answers only `GET` and `HEAD`, and it reads the database through a read-only connection, so no browser request can change state, start a run or spend money |
| Pages | **The board, plus a page per task.** The board shows every plan and task, and lists what needs you. Each task page shows its contract, runs, reports and live log. Each agent run has a readable transcript page. No charts or dependency graphs |
| Sequencing | **Starts now, independent of other plans.** Runs are labelled by role and attempt (`build #2`). Showing agent-flows' step names, and measure's stats, are later follow-ups |

### Milestones

| # | Deliverable | Exit criteria | Parallelizable with |
|---|---|---|---|
| **M1** | The board in a browser | The t01 tests in `tests/test_web.py` pass; `factory web` opens a live board | agent-flows, measure, wiki |
| **M2** | Task pages | The t02 tests in `tests/test_web.py` pass; every task id on the board opens its page | agent-flows, measure, wiki |
| **M3** | Transcript pages | The t03 tests in `tests/test_web.py` pass; every agent run with a transcript opens a readable view of it | agent-flows, measure, wiki |
| **M4** | Docs | README, reference, architecture, the AGENTS.md section and the factory-ops skill template name `factory web`; `tests/test_templates.py` passes | — |

**Sequence:** `M1 → M2 → M3 → M4`. Every task changes `factory/web.py`, `factory/static/` and `tests/test_web.py`, so they run one after another. None of them depends on another plan.

### Task Contracts

| Milestone | Task IDs | Coverage |
|---|---|---|
| **M1** | `web-board-t01` | New `factory/web.py` (the app, server, routes, security headers, board data and HTML); new `factory/static/web.css`, `web.js`, `favicon.svg`; `open_db(home, readonly=True)` in `factory/db.py`; `factory web` in `factory/cli.py`; new `tests/test_web.py` |
| **M2** | `web-board-t02` | The task page and `/api/tasks/TASK` in `factory/web.py`; board links; styles in `web.css`; tests in `tests/test_web.py` |
| **M3** | `web-board-t03` | The transcript page in `factory/web.py`; links from the task page; styles in `web.css`; tests in `tests/test_web.py` |
| **M4** | `web-board-t04` | `README.md`, `docs/reference.md`, `docs/architecture.md`, `AGENTS.md`, `factory/templates/agents-section.md`, `factory/templates/skills/factory-ops/SKILL.md`, `NEXT.md` |

```yaml
- id: web-board-t01
  goal: "`factory web` serves a live, read-only board page on 127.0.0.1 and opens it in the browser. The page has a summary of the board, a Needs you list with each task's next step, and a card per plan with its tasks in dependency order"
  spec_refs:
    - "docs/plans/web-board.md#design"
    - "docs/plans/web-board.md#board-page"
    - "docs/plans/web-board.md#live-refresh"
    - "docs/plans/web-board.md#security"
    - "docs/plans/web-board.md#visual-design"
    - "factory/observe.py"
  depends_on: []
  non_goals:
    - "Task pages, transcript pages or log views (web-board-t02, web-board-t03); board task ids aren't links yet"
    - "Any request that changes state: no POST handler and no buttons that run, requeue, hold or refresh a task"
    - "Listening on any address but 127.0.0.1, or a --host option"
    - "New Python dependencies, a JavaScript build step, or anything loaded from the network (web fonts, CDNs)"
    - "Changing what `factory top` and `factory status` print, or the observe.py helpers they share"
    - "Docs (web-board-t04)"
  acceptance:
    - "`factory web [--port N] [--no-open]` migrates the database once, as every command does. It binds 127.0.0.1 on port N (default 8765) and prints `factory web: http://127.0.0.1:N/ (read-only; Ctrl-C to stop)`. It opens that URL with webbrowser.open unless --no-open is given, and exits 0 on Ctrl-C"
    - "Without --port, a busy 8765 makes it bind a free port and print that one. With an explicit --port that's busy, it exits 1 with `port N is in use; pick another with --port`"
    - "New factory/web.py has an App whose handle(method, path, headers) returns a status, headers and body without a socket. make_server(app, port) wraps the App in a ThreadingHTTPServer that logs nothing per request"
    - "GET / renders the board as complete HTML, readable without JavaScript. GET /api/board returns the same content as JSON with the keys project, generated_at, summary, needs_you and plans. The page title and header name the project from the `name:` setting"
    - "summary has running, pr_open, failed, ready, waiting, done and spent_usd, counted exactly as the first line of `factory top` counts them, plus needs_you"
    - "needs_you lists every task that is DEAD, failed, conflict, ci_failed, changes_requested or pr_open, in that order and then by id. Each entry has its status, its observe.detail line and the next step from the Board page table. That function is the one web-board-t02 reuses"
    - "Plans come in three groups. First, plans with a running task, an open PR or a failure (the rule `factory top` uses). Then other plans with work left. Last, plans whose every task is merged or held, in a Finished plans <details> that starts collapsed. Each card shows the plan name, a progress bar segmented by status group, the observe.counts text and the cost. A card with a ready task and nothing running also shows `factory run PLAN` as its next step"
    - "Each task row, in plan order (observe.plan_groups), shows a status badge (glyph and word, never colour alone) and the id. It shows the goal on one line, with the full goal on hover, then observe.detail, builds and cost. A running task also shows its elapsed time, quiet time and current activity"
    - "Every command on the page is visible text with a copy button. The button appears only when JavaScript runs"
    - "An empty board says `No tasks yet. Load your plans with factory sync.`, with that command copyable"
    - "factory/static/web.css implements the Visual design section: the light and dark palettes through prefers-color-scheme, the status colours, the narrow layout under 720px, and no animation under prefers-reduced-motion"
    - "factory/static/web.js re-fetches a page whose <main> carries data-refresh, at that many seconds, while the tab is visible. It swaps <main> and keeps open <details> open. While a fetch fails it shows a reconnecting banner. The board's <main> has data-refresh=\"3\""
    - "Only GET and HEAD are answered; anything else gets 405 with Allow: GET, HEAD. A Host header whose name isn't 127.0.0.1 or localhost gets 403. From factory/static only /static/web.css, /static/web.js and /static/favicon.svg are served, and any other path gets a friendly 404 page"
    - "Every response carries the headers in the Security section. Every value from the database or a file is HTML-escaped. A PR URL becomes a link only when it starts with https:// or http://"
    - "Each request reads through its own read-only SQLite connection, opened and closed per request: open_db(home, readonly=True) connects with mode=ro and runs no schema or migration statements"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_web.py::test_board_shows_every_plan_and_its_tasks_in_dependency_order tests/test_web.py::test_board_summary_matches_factory_top tests/test_web.py::test_needs_you_lists_each_task_waiting_on_a_human_with_its_next_step tests/test_web.py::test_finished_plans_collapse_and_plans_with_ready_tasks_say_how_to_run_them tests/test_web.py::test_board_escapes_text_from_tasks_and_agents tests/test_web.py::test_only_get_requests_for_localhost_are_answered tests/test_web.py::test_the_board_reads_the_database_read_only tests/test_web.py::test_web_serves_the_board_its_json_and_its_assets_over_http tests/test_web.py::test_web_command_falls_back_to_a_free_port_and_refuses_a_busy_explicit_one tests/test_web.py::test_empty_board_says_how_to_load_plans tests/test_web.py::test_pages_load_nothing_from_the_network"
    - "uv run pytest -q tests/test_observe.py tests/test_db.py"
  risk: medium

- id: web-board-t02
  goal: "Each task has its own page at /tasks/TASK, and the board links every task to it. The page shows where the task is and what to do next, its contract, and the tasks it waits for and that wait on it. It lists every run with its outcome and report, and tails the task's live log"
  spec_refs:
    - "docs/plans/web-board.md#task-page"
    - "docs/plans/web-board.md#visual-design"
    - "factory/cli.py"
  depends_on: [web-board-t01]
  non_goals:
    - "Rendering transcripts, or linking runs to them (web-board-t03)"
    - "Any action on the task, or editing its contract"
    - "Changing `factory show` or `factory logs`"
    - "Docs (web-board-t04)"
  acceptance:
    - "GET /tasks/TASK renders the task page. GET /api/tasks/TASK returns the same content as JSON with the keys task, next_step, contract, depends_on, needed_by, runs and log. Task ids are URL-quoted in links"
    - "The header has a breadcrumb back to the board and the plan, then the id, the status badge, and the goal as the title. It shows the risk, builds, cost and branch, and a button to the PR when there is one"
    - "The next step comes from the same function as the board's Needs you list. A running task shows its progress, activity, elapsed time and quiet time. A DEAD one says its `factory run` process is gone. A failed, conflict, ci_failed or changes_requested task shows its full note"
    - "The contract section shows acceptance, non-goals, verification commands (each copyable), spec refs and risk. Depends on and Needed by (tasks whose depends_on names this one) list each task with its badge and a link to its page"
    - "Runs are listed newest first. Each shows its role and attempt (`build #2`) and an outcome badge, classed by the outcome's first word as in the Task page section. It also shows the model, start time (relative, exact on hover), duration, steps, tokens in and out, cost and refused tool calls. Each report is in a <details>; the newest run's starts open"
    - "The log panel shows the last 200 lines of $FACTORY_HOME/logs/TASK.log, or `No log yet` without one. It stays scrolled to the bottom across refreshes unless the reader has scrolled up"
    - "The page's <main> has data-refresh=\"3\""
    - "An unknown task gets a 404 page that says the task isn't on this board and links to the board. /api/tasks/TASK for an unknown task is a 404 with a JSON error"
    - "Every task id on the board, in the Needs you list, and under Depends on and Needed by links to its task page"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_web.py::test_task_page_shows_the_contract_with_dependencies_and_dependents tests/test_web.py::test_task_page_lists_runs_newest_first_with_outcomes_and_reports tests/test_web.py::test_task_page_shows_the_next_step_the_running_state_and_the_failure_note tests/test_web.py::test_task_page_tails_the_task_log tests/test_web.py::test_unknown_task_is_a_404_that_links_back_to_the_board tests/test_web.py::test_board_links_every_task_to_its_page"
    - "uv run pytest -q tests/test_web.py"
  risk: low

- id: web-board-t03
  goal: "Each agent run has a readable transcript page at /tasks/TASK/runs/RUN, and the task page links every run that has a transcript. The page opens with a summary of time, tokens, cost and tools, then shows each step's text, tool calls and results, with long results collapsed and refusals flagged"
  spec_refs:
    - "docs/plans/web-board.md#transcript-page"
    - "docs/plans/web-board.md#visual-design"
    - "factory/observe.py"
    - "factory/agents.py"
  depends_on: [web-board-t02]
  non_goals:
    - "Changing the transcript format or what agents record"
    - "Changing `factory transcript` or `factory trace`"
    - "Searching transcripts, or comparing runs"
    - "Docs (web-board-t04)"
  acceptance:
    - "GET /tasks/TASK/runs/RUN renders the transcript of run RUN, read from the path in runs.transcript. A run id that doesn't exist, or belongs to another task, gets a 404 page linking to the task. A run whose transcript is unset or missing says `No transcript was recorded for this run` and links to the task"
    - "The header has a breadcrumb (board, plan, task, `role #attempt`), the outcome badge, model, steps, tokens, cost and refused count. A summary, computed with observe.trace_rows, gives model time and tool time, tokens in, cached and out, cost, and the tool mix"
    - "The system prompt and the task message are collapsed <details> labelled with their sizes. Each agent step shows its number, model and tool time, tokens and cost, and its text. Each tool call shows its name and main argument, with the full arguments collapsed, and is followed by its result"
    - "A result longer than 2,000 characters is collapsed behind a label giving its size. A result that starts with `refused` is flagged. A stopped event shows its reason"
    - "A trailing line that doesn't parse, from a transcript still being written, is skipped without an error"
    - "The page's <main> has data-refresh=\"3\" while the run has no ended_at, and no data-refresh once it has one"
    - "On the task page, each run whose transcript file exists links to its transcript page"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_web.py::test_transcript_page_shows_each_step_with_its_tool_calls_and_results tests/test_web.py::test_long_results_are_collapsed_and_refusals_flagged tests/test_web.py::test_transcript_page_refreshes_only_while_its_run_is_running tests/test_web.py::test_a_half_written_transcript_line_is_skipped tests/test_web.py::test_a_run_of_another_task_or_without_a_transcript tests/test_web.py::test_task_page_links_runs_to_their_transcripts"
    - "uv run pytest -q tests/test_web.py tests/test_observe.py"
  risk: medium

- id: web-board-t04
  goal: "The docs describe `factory web`. This covers the README quick start, the command reference, an architecture section on watching from a browser, the AGENTS.md section and its template, and the factory-ops skill template. NEXT.md item 8 is marked done"
  spec_refs:
    - "docs/plans/web-board.md#design"
    - "docs/reference.md#commands"
    - "docs/architecture.md#components"
  depends_on: [web-board-t03]
  non_goals:
    - "Code changes"
    - "This repository's installed factory-ops skill under .claude/skills, which `factory init --force` refreshes"
    - "Screenshots or other images"
  acceptance:
    - "README.md's quick start shows `factory web` next to `factory top`"
    - "docs/reference.md's command table has a `factory web [--port N] [--no-open]` row. It says what the board, task and transcript pages show, that the page is read-only and local, the default port 8765 and the free-port fallback"
    - "docs/architecture.md has a `## Watching from a browser` section. It covers the pages, live refresh, the read-only database connection, 127.0.0.1 and the Host check, the security headers, and viewing another machine's board through `ssh -L 8765:127.0.0.1:8765` to it. Components lists web.py and factory/static"
    - "factory/templates/agents-section.md and this repository's AGENTS.md name `factory web` in their State line, identically"
    - "factory/templates/skills/factory-ops/SKILL.md names `factory web` in its What's happening row and among the read-only commands"
    - "NEXT.md row 8 is marked ✓ and links docs/architecture.md#watching-from-a-browser"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "grep -q 'factory[[:space:]]web' README.md"
    - "grep -qF 'web [--port N] [--no-open]' docs/reference.md"
    - "grep -q '^## Watching from a browser' docs/architecture.md"
    - "grep -q 'factory[[:space:]]web' factory/templates/agents-section.md"
    - "grep -q 'factory[[:space:]]web' AGENTS.md"
    - "grep -q 'factory[[:space:]]web' factory/templates/skills/factory-ops/SKILL.md"
    - "grep -q 'architecture.md#watching-from-a-browser' NEXT.md"
    - "uv run pytest -q tests/test_templates.py"
  risk: low
```

Planned test additions are all in a new `tests/test_web.py`:

- **web-board-t01:**
  - `test_board_shows_every_plan_and_its_tasks_in_dependency_order`
  - `test_board_summary_matches_factory_top`
  - `test_needs_you_lists_each_task_waiting_on_a_human_with_its_next_step`
  - `test_finished_plans_collapse_and_plans_with_ready_tasks_say_how_to_run_them`
  - `test_board_escapes_text_from_tasks_and_agents`
  - `test_only_get_requests_for_localhost_are_answered`
  - `test_the_board_reads_the_database_read_only`
  - `test_web_serves_the_board_its_json_and_its_assets_over_http`
  - `test_web_command_falls_back_to_a_free_port_and_refuses_a_busy_explicit_one`
  - `test_empty_board_says_how_to_load_plans`
  - `test_pages_load_nothing_from_the_network`
- **web-board-t02:**
  - `test_task_page_shows_the_contract_with_dependencies_and_dependents`
  - `test_task_page_lists_runs_newest_first_with_outcomes_and_reports`
  - `test_task_page_shows_the_next_step_the_running_state_and_the_failure_note`
  - `test_task_page_tails_the_task_log`
  - `test_unknown_task_is_a_404_that_links_back_to_the_board`
  - `test_board_links_every_task_to_its_page`
- **web-board-t03:**
  - `test_transcript_page_shows_each_step_with_its_tool_calls_and_results`
  - `test_long_results_are_collapsed_and_refusals_flagged`
  - `test_transcript_page_refreshes_only_while_its_run_is_running`
  - `test_a_half_written_transcript_line_is_skipped`
  - `test_a_run_of_another_task_or_without_a_transcript`
  - `test_task_page_links_runs_to_their_transcripts`

Each verification filter names its tests, so a missing test fails the gate rather than passing with zero selected.

The project has no `e2e` setting, so no task needs an e2e test. `session_log` is set, so each task adds its own `docs/sessions/<date>-<task id>.md`.

Every task changes the factory itself. They run through `factory run` like the agent-flows tasks did: the tests use the `home` fixture and a temporary board, and the over-HTTP test binds port 0 on 127.0.0.1, which works inside the offline sandbox because bubblewrap brings up loopback in its network namespace.

### Risks

1. **The sandbox has no browser, so no test runs `web.js`.** Live refresh, the reconnecting banner and the copy buttons go untested by the gates. **Action:** keep `web.js` small, dependency-free and limited to the three jobs in Live refresh. The tests check that the server renders complete pages without JavaScript and sets `data-refresh` correctly, and the human checks the live behaviour by eye before merging t01 (see Verification).
2. **"Looks good" can't be gated, and the reviewer agent can't see the page.** **Action:** the Visual design section fixes the palette, type, spacing and layout, so the reviewer checks `web.css` against stated values rather than taste. The human looks at the board in light and dark mode, and in a narrow window, before merging t01.
3. **A local server exposes transcripts, which contain the repository's code, to other pages in the browser.** A malicious site could try DNS rebinding to read `127.0.0.1:8765`. **Action:** the server binds 127.0.0.1 only and answers only `GET` and `HEAD` with a localhost `Host`. It sends no CORS headers and a strict CSP (see Security). t01 tests the 403 and 405 paths.
4. **Reading while runs write.** A read that holds SQLite's shared lock delays a writer's commit. **Action:** each request opens a read-only connection, makes a few short reads in one go and closes it, and a page refreshes at most every 3 seconds. Writers keep Python's default 5-second busy timeout.
5. **Merge conflicts with other plans.** agent-flows-t04, measure and wiki also change `factory/cli.py` and `factory/db.py`. **Action:** this plan only adds the `web` subparser and `cmd_web`, plus an optional `readonly` argument to `open_db`, so conflicts stay small. A PR that conflicts goes through the factory's own conflict resolution (`factory run TASK`).
6. **Untrusted text on the page.** Goals, notes, reports, logs and tool output can contain markup, including text written by agents. **Action:** everything is escaped through one helper, the CSP forbids inline scripts, and t01 tests a `<script>` in a goal, a note and a report.

---

## Problem

The only ways to see the board are terminal commands:

- `factory top` (`factory/observe.py:127`, `factory/cli.py:510`) redraws a fixed-width text screen every 2 seconds.
- `factory status` (`factory/cli.py:491`) prints one line per task.
- `factory show`, `trace`, `transcript` and `logs` (`factory/cli.py:527`–`645`) print one task at a time.

That works while you're at a terminal, but it's hard to scan, and these problems follow:

- Long goals and notes are cut to the terminal width.
- Nothing is clickable: a PR URL, a task's dependencies and its runs are separate commands.
- A transcript is a wall of text where a 50,000-character tool result looks the same as a one-line answer.
- The terminal never pulls out what needs a human next (an open PR to review, a failure to rerun, a dead process).

All the state is already local: the `tasks` and `runs` tables in `$FACTORY_HOME/factory.db` (`factory/db.py:22`), `logs/TASK.log`, and one JSONL transcript per agent run.

## Goal

`factory web` opens a page in the browser that shows the whole board at a glance, says what needs you next, and updates live. Every task opens to its contract, runs, reports and log, and every agent run opens to a readable transcript. Everything stays local and read-only, and needs no new dependencies.

## Design

```
 browser ──GET──▶ factory web (127.0.0.1:8765, ThreadingHTTPServer, factory/web.py)
                    │ App.handle(method, path, headers)
                    │   Host check · GET/HEAD only · security headers
                    ├── /                      board HTML      ◀── board_data(db, home)
                    ├── /api/board             board JSON      ◀── board_data(db, home)
                    ├── /tasks/TASK            task HTML       ◀── task_data(db, home, id)       (t02)
                    ├── /api/tasks/TASK        task JSON       ◀── task_data(db, home, id)       (t02)
                    ├── /tasks/TASK/runs/RUN   transcript HTML ◀── transcript_data(db, id, run)  (t03)
                    └── /static/web.css|web.js|favicon.svg     (factory/static, fixed list)
                          │
                          ▼ per request: open_db(home, readonly=True)  (sqlite mode=ro)
                    $FACTORY_HOME/factory.db · logs/TASK.log · transcripts/*.jsonl
```

- **One renderer, server-side.** Python builds a plain dict for each page (`board_data`, `task_data`, `transcript_data`). The JSON routes return it, and the HTML renderers format it. There is no client-side templating: JavaScript only re-fetches and swaps the server's HTML. The tests can then assert on the data and on the HTML without a browser.
- **Reuse the terminal's logic.** The pages use `observe.detail`, `observe.counts`, `observe.plan_groups`, `observe.liveness`, `observe.human_secs` and `observe.trace_rows`, and `db.readiness` and `db.ready`. The web page and `factory top` therefore never disagree about a task, and t01 tests that the summary matches top's header line.
- **Static files** live in `factory/static/` and load through `importlib.resources.files("factory") / "static"`, as the role prompts do. The wheel ships them because hatch packages everything under `factory/`.
- **Times.** The database stores UTC ISO times. Pages show relative times ("4m ago", via `observe.human_secs`), with the exact UTC time in `title` and a `<time datetime>` element.

### `factory web`

```
factory web [--port N] [--no-open]

$ factory web
factory web: http://127.0.0.1:8765/ (read-only; Ctrl-C to stop)
```

- The command opens the board once with `open_db(home)`, which migrates the database, as every command does. After that every request uses its own `open_db(home, readonly=True)` connection.
- It binds `127.0.0.1:8765` by default. If 8765 is busy and `--port` wasn't given, it binds a free port and prints it; a busy explicit `--port` exits 1. A second project's `factory web` therefore just gets another port.
- It opens the browser with `webbrowser.open(url)` unless `--no-open` is given. A headless machine just prints the URL.
- It prints nothing per request. Ctrl-C stops it and exits 0.

### Board page

```
┌───────────────────────────────────────────────────────────────────────────────────────────┐
│ software-factory                ▶ 1 running  ◆ 3 PR open  ✗ 1 failed  · 1 ready  · 1 waiting │
│ board                           ✓ 5 done  $9.80                     ● live · updated 12:03:04 │
└───────────────────────────────────────────────────────────────────────────────────────────┘

  Needs you · 4
  ┌─────────────────────────────────────────────────────────────────────────────────────────┐
  │ ✗ failed     agent-flows-t04   Reworks run the flow's steps…   Read why it failed, then    │
  │                                                                rerun  factory run agent-flows-t04 ⧉ │
  │ ◆ PR open    agent-flows-t01   `.factory/config.yaml` can…     Review and merge PR #19 ↗   │
  │ ◆ PR open    agent-flows-t02   Every agent runs through…       Review PR #20; merge it     │
  │                                                                after agent-flows-t01 ↗     │
  └─────────────────────────────────────────────────────────────────────────────────────────┘

  agent-flows                                                   0/5 merged · 3 PR open · …  $7.21
  [██████████████████████████████▓▓▓▓▓▓▓▓░░░░░░]
    ◆ PR open    agent-flows-t01   `.factory/config.yaml` can define named…   PR #19 ↗   1 build  $0.66
    ◆ PR open    agent-flows-t02   Every agent runs through one…  stacked on t01 ↗    1 build  $1.13
    ▶ building   agent-flows-t04   Reworks run the flow's steps…  build#2 step 31/150  2 builds $2.80
                 ↳ [build#2] → run(command=uv run pytest -q tests/test_pipeline.py)   12m04s · quiet 8s
    · waiting    agent-flows-t05   Docs…                          waits for agent-flows-t04

  example                                                                    0/1 merged · 1 ready
    · ready      example-t01       Add the greeting module                   ready
    Run next  factory run example ⧉

  ▸ Finished plans (1)
```

- **Header.** It shows the project name and the summary chips. Their counts are exactly those on the first line of `factory top`: running is the active statuses; PR open is pr_open, conflict, ci_failed and changes_requested; failed; ready; waiting; done is merged plus held; and spent. A live dot shows "updated HH:MM:SS"; it turns grey with "paused" while the tab is hidden and red with "reconnecting" while fetches fail. The header stays at the top as the page scrolls.
- **Needs you** lists the tasks whose next step is a human's, most urgent first. When it's empty it shows one muted line, "✓ Nothing needs you right now". The order and each next step are:

  | Shown status | Next step |
  |---|---|
  | DEAD (active or queued, but its process is gone) | "Its `factory run` process is gone; mark it failed" `factory status --refresh` |
  | failed | "Read why it failed, then rerun" `factory run TASK` |
  | conflict | "Resolve the conflict with its base" `factory run TASK` |
  | ci_failed | "Fix the failing CI" `factory run TASK` |
  | changes_requested | "Address the review" `factory run TASK` |
  | pr_open | "Review and merge" plus a link to the PR. When `stacked_on` is set: "Review; merge it after STACKED_ON" |

  The board's other states need nobody: running, queued (ready or waiting), merged and held. A ready task is the plan card's "Run next" instead.
- **Plan cards** come in the groups and order of `factory top`. First, plans with a running task, an open PR or a failure. Then the rest with work left. Last, the plans where everything is merged or held, inside a collapsed `<details>` "Finished plans (N)". Within each group, plans are sorted by name, as `observe.plan_groups` does.

  A card's progress bar has one segment per status group, sized by its count. The segments run, in order: merged, PR open, running, attention (conflict, ci_failed, changes_requested), failed (including DEAD), ready, waiting, held. The bar carries `role="img"` and an `aria-label` with the counts text.
- **Task rows** follow plan order and have these columns: badge, id, goal (one line with an ellipsis; the full goal in `title`), detail (`observe.detail`, with the PR URL as a link), builds and cost. A running row adds a second line with `↳ activity`, the elapsed time and "quiet Ns". Below 720px the columns stack into three lines: badge and id, then the goal, then detail, builds and cost.
- **Badges** use the CLI's glyph and a word: `✓ merged`, `◆ PR open`, `≠ conflict`, `! CI failing`, `↺ changes requested`, `▶ planning|building|reviewing|verifying`, `✗ failed`, `✗ dead`, `· ready`, `· waiting`, `⊘ held`.
- **Commands** are `<code>` text with a copy button (⧉). The button is rendered `hidden`, and `web.js` unhides it and copies with `navigator.clipboard`; 127.0.0.1 counts as a secure context, so the clipboard API works there. After a copy the button reads "Copied" for 1.5 seconds.
- **Empty board:** "No tasks yet. Load your plans with `factory sync`." with the command copyable.

`/api/board`:

```json
{"project": "software-factory", "generated_at": "2026-11-03T12:03:04+00:00",
 "summary": {"running": 1, "pr_open": 3, "failed": 1, "ready": 1, "waiting": 1, "done": 5,
             "spent_usd": 9.8, "needs_you": 4},
 "needs_you": [{"task": "agent-flows-t04", "plan": "agent-flows", "status": "failed", "detail": "…",
                "next": {"text": "Read why it failed, then rerun", "command": "factory run agent-flows-t04",
                         "url": null}}],
 "plans": [{"name": "agent-flows", "group": "live", "counts": "0/5 merged · 3 PR open · …",
            "cost_usd": 7.21, "segments": {"merged": 0, "pr": 3, "running": 1, "...": 0},
            "run_next": null,
            "tasks": [{"id": "agent-flows-t01", "status": "pr_open", "shown": "pr_open",
                       "goal": "…", "risk": "medium", "detail": "…", "builds": 1, "cost_usd": 0.66,
                       "pr_url": "https://github.com/…/pull/19", "elapsed": null, "quiet": null,
                       "activity": null}]}]}
```

`group` is `live`, `open` or `finished`. `shown` is the status with DEAD applied.

### Task page

```
  Board › agent-flows › agent-flows-t04

  agent-flows-t04   ✗ failed                                          [ Open PR ↗ ]
  Reworks run the flow's steps after their entry
  risk medium · 2 builds · $2.80 · branch factory/agent-flows-t04

  ┌ Next ───────────────────────────────────────────────────────────────────────┐
  │ Read why it failed, then rerun   factory run agent-flows-t04 ⧉               │
  │ error: PaymentRequiredResponseError: This request requires more credits…     │
  └──────────────────────────────────────────────────────────────────────────────┘

  Contract                                  │  Runs (newest first)
   Acceptance  • …                          │   build #2  ✗ error   glm-5.3 · 4m ago · 3m12s
   Non-goals   • …                          │             41 steps · 812k in / 9k out · $1.94
   Verification  uv run pytest … ⧉          │             ▾ report …
   Spec refs   docs/plans/agent-flows.md…   │   review #1 ✗ CHANGES  …
   Depends on  ◆ agent-flows-t03            │   build #1  ✓ committed …
   Needed by   · agent-flows-t05            │   plan #0   ✓ done …
                                            │
  Log (last 200 lines)                                                    live ●
  ┌──────────────────────────────────────────────────────────────────────────────┐
  │ 11:58:02 [stage] building (build #2)                                         │
  │ …                                                                            │
  └──────────────────────────────────────────────────────────────────────────────┘
```

- On wide screens the contract and the runs sit side by side (the contract takes 5 of 12 columns), with the log full-width below. Below 960px they stack.
- **Outcome badges** go by the outcome's first word, so `committed (step limit)` counts as `committed`:

  | Class | Outcomes |
  |---|---|
  | good | `done`, `committed`, `APPROVE`, `pass`, `verified`, `opened` |
  | bad | `error`, `fail`, `CHANGES` |
  | running | the run has no `ended_at` |
  | neutral | anything else (`report`, `failing`, `changes_requested`, …) |

- **Duration** is `ended_at − started_at`, or the time so far for a running run.
- **Log:** the last 200 lines, monospace, in a panel 28 lines tall. `web.js` keeps it pinned to the bottom across refreshes unless the reader has scrolled up.
- **Needed by** is computed from every task's contract on the board: the tasks whose `depends_on` contains this id.

### Transcript page

```
  Board › agent-flows › agent-flows-t04 › build #2

  build #2  ✗ error · openrouter:z-ai/glm-5.3 · 41 steps · 812k in / 9k out · $1.94 · 0 refused
  Model 2m40s · tools 32s · 640k cached · run ×22, read_file ×12, write_file ×6, final answer ×1

  ▸ System prompt (14,212 chars)
  ▸ Task message (6,031 chars)

  Step 1 · model 4.1s · tools 0.3s · 18k in / 210 out · $0.004
    I'll start by reading the pipeline…
    → read_file(path=factory/pipeline.py)        ▸ arguments
      ▸ result · 21,904 chars
  Step 2 …
    → run(command=uv run pytest -q tests/…)
      ⚠ refused: git push is not allowed
  …
  ■ Stopped: step limit (150)
```

- The page parses the JSONL events the agent loop records (`factory/agents.py`): `system`, `human`, `ai` with `step`, `text`, `usage`, `cost_usd` and `tool_calls`, `tool` with `name` and `content`, and `stopped`. Results pair with calls in order: the `tool` events after an `ai` event answer its `tool_calls` one by one.
- A result up to 2,000 characters shows inline in a monospace block; a longer one is a collapsed `<details>` labelled "result · N chars". A result that starts with `refused` gets the warning style and the ⚠ glyph.
- A trailing line that doesn't parse is skipped, because a running agent may be halfway through writing it.
- `data-refresh="3"` only while the run has no `ended_at`, so a finished transcript isn't re-fetched.

### Live refresh

`factory/static/web.js` is plain JavaScript loaded with `defer`. It uses no libraries and has three jobs:

1. **Refresh.** When `<main>` carries `data-refresh="N"`, it fetches `location.href` (with `cache: "no-store"`) every N seconds while `document.visibilityState` is `visible`, and immediately when the tab becomes visible again. It parses the response with `DOMParser` and replaces `<main>`'s content, then reopens every `<details>` the reader had open (by `id`; the server gives every `<details>` a stable id) and keeps the log panel pinned as described above. It updates the header's "updated" time and live dot. While a fetch fails, it shows the banner "Can't reach factory web. Retrying…" and keeps trying on the same interval.
2. **Copy.** It unhides every `button.copy[data-copy]` and copies that text on click.
3. **Times.** It rewrites each `<time datetime>` element's `title` to the reader's local time.

A page without `data-refresh` never re-fetches.

### Security

| Measure | Detail |
|---|---|
| Bind | `127.0.0.1` only; there is no `--host` option. To see another machine's board, tunnel: `ssh -L 8765:127.0.0.1:8765 HOST` |
| Host check | The `Host` header's name (without the port) must be `127.0.0.1` or `localhost`, or the request gets 403. This blocks DNS rebinding while letting an SSH tunnel on any local port through |
| Methods | `GET` and `HEAD` only; anything else gets 405 with `Allow: GET, HEAD` |
| Headers on every response | `Content-Security-Policy: default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'`, plus `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer` and `Cache-Control: no-store`. There are no CORS headers |
| Database | Opened read-only per request (`file:…/factory.db?mode=ro`, `uri=True`), with no schema or migration statements, so a write raises `attempt to write a readonly database` |
| Files | Only the three named files under `factory/static/`. Logs and transcripts are reached only through a task id and run id looked up in the database, never through a path in the URL |
| Output | Every value goes through one escaping helper (`html.escape(..., quote=True)`). A URL becomes an `href` only when it starts with `https://` or `http://`. There are no inline scripts, `style` attributes or event-handler attributes |

### Visual design

The look is calm and information-dense, with colour reserved for status. Everything uses system fonts and stays readable in light and dark mode.

- **Type.** Text uses `system-ui, -apple-system, "Segoe UI", Roboto, sans-serif` at 15px with line-height 1.5. Ids, commands, logs and transcripts use `ui-monospace, "SF Mono", "Cascadia Code", Menlo, Consolas, monospace` at 13px. Headings are weight 600 (page title 22px, card titles 16px). Numbers use `font-variant-numeric: tabular-nums`. No web fonts.
- **Layout.** Content is at most 1,180px wide, centred, with 24px gutters (16px below 720px), on an 8px spacing scale. Cards have a 12px radius, a 1px border and a shadow of `0 1px 2px rgb(0 0 0 / 6%)`. The header is sticky and blurs what scrolls under it.
- **Colour.** CSS custom properties hold the colours, and `@media (prefers-color-scheme: dark)` swaps them. Text tokens meet 4.5:1 contrast on their background.

  | Token | Light | Dark |
  |---|---|---|
  | `--bg` | `#f6f7f9` | `#0f1115` |
  | `--surface` | `#ffffff` | `#171a20` |
  | `--surface-2` | `#f0f2f5` | `#1e222a` |
  | `--border` | `#e1e4e8` | `#2a2f38` |
  | `--text` | `#1b1f24` | `#e7e9ee` |
  | `--muted` | `#5b6470` | `#9aa3af` |
  | `--accent` (links, focus) | `#3b5bdb` | `#8ea8ff` |

  Status colours, text on tint:

  | Group | Light fg / bg | Dark fg / bg |
  |---|---|---|
  | merged | `#1f7a3d` / `#e3f4e8` | `#5fd38a` / `#15301f` |
  | PR open | `#2459c9` / `#e5edfd` | `#7ea8ff` / `#172440` |
  | running | `#9a5b00` / `#fdf0d9` | `#f2b54a` / `#33260e` |
  | attention (conflict, CI failing, changes requested) | `#b4480b` / `#fde8dc` | `#ff9a5c` / `#3a2113` |
  | failed, dead | `#c22a2a` / `#fce4e4` | `#ff7b7b` / `#3b1719` |
  | ready | `#3d4a5c` / `#e8ecf1` | `#c3cbd6` / `#232833` |
  | waiting, held, neutral | `#6b7380` / `#f0f2f5` | `#8b95a3` / `#1e222a` |

- **Badges** are pills (999px radius, 2px by 8px padding, 12px weight 600) holding the glyph and the word. Colour is never the only signal.
- **Progress bars** are 8px tall with a 4px radius. Each segment is filled with its group's foreground colour. The running segment has a slow moving stripe.
- **Motion.** The live dot pulses every 1.6 seconds and the running segment's stripe moves. Both stop under `@media (prefers-reduced-motion: reduce)`.
- **Focus and links.** Focus rings are 2px `--accent` with a 2px offset. Links are `--accent`, underlined on hover, and an external link (a PR) ends in ↗.
- **Favicon.** `factory/static/favicon.svg` is a 32px rounded square in `--accent` holding a white ◆.

## Files Changed

| File | Change |
|---|---|
| `factory/web.py` | New: `App`, `make_server`, routing, the Host check, security headers, escaping; `board_data` and the board page (t01); `task_data` and the task page (t02); `transcript_data` and the transcript page (t03) |
| `factory/static/web.css`, `web.js`, `favicon.svg` | New (t01); task page styles (t02); transcript styles (t03) |
| `factory/db.py` | `open_db(home, readonly=False)`: a read-only connection that skips schema and migrations (t01) |
| `factory/cli.py` | `factory web [--port] [--no-open]` (t01) |
| `tests/test_web.py` | New (t01), grown by t02 and t03 |
| `README.md`, `docs/reference.md`, `docs/architecture.md`, `AGENTS.md`, `factory/templates/agents-section.md`, `factory/templates/skills/factory-ops/SKILL.md`, `NEXT.md` | Docs (t04) |
| `docs/sessions/` | Every task's session log entry |

## Test Plan

### Unit tests

All of these are in `tests/test_web.py`. They seed a board through `open_db(home)` with the `home` fixture and `conftest.plan_text`, and most call `App.handle` directly.

- **t01:**
  - `test_board_shows_every_plan_and_its_tasks_in_dependency_order`: two plans; the board JSON and HTML list each plan's tasks in `observe.plan_groups` order with their badges, goals, detail, builds and cost.
  - `test_board_summary_matches_factory_top`: a board with running, PR open, failed, ready, waiting and merged tasks; `summary`'s counts and spend equal the numbers in `observe.render_top`'s first line.
  - `test_needs_you_lists_each_task_waiting_on_a_human_with_its_next_step`: one task in each of DEAD (a dead pid), failed, conflict, ci_failed, changes_requested and pr_open, one of them stacked. The entries come in that order with the commands and texts from the table, and the stacked one says to merge it after its dependency. A queued, running, merged or held task isn't listed.
  - `test_finished_plans_collapse_and_plans_with_ready_tasks_say_how_to_run_them`: an all-merged plan sits in a closed Finished plans `<details>`; a plan with a ready task and nothing running shows `factory run PLAN`; one with a running task doesn't.
  - `test_board_escapes_text_from_tasks_and_agents`: a goal, note and activity holding `<script>alert(1)</script>`, and a `pr_url` of `javascript:alert(1)`. The HTML contains only the escaped form and no `href="javascript:`.
  - `test_only_get_requests_for_localhost_are_answered`: POST gets 405 with `Allow: GET, HEAD`. `Host: evil.example:8765` gets 403, while `Host: localhost:9000` and `127.0.0.1:8765` get 200. Every response has the CSP, `nosniff`, `no-referrer` and `no-store` headers. `/static/../db.py` and `/static/other.css` get 404.
  - `test_the_board_reads_the_database_read_only`: the connection the app reads through raises `sqlite3.OperationalError` on an `UPDATE`, and serving the board doesn't change the database file's bytes.
  - `test_web_serves_the_board_its_json_and_its_assets_over_http`: `make_server` on port 0 in a thread. `urllib` gets `/` (HTML naming the project), `/api/board` (JSON), `/static/web.css` (`text/css`), `/static/web.js` (`text/javascript`) and `/static/favicon.svg`. Then the server shuts down.
  - `test_web_command_falls_back_to_a_free_port_and_refuses_a_busy_explicit_one`: with a socket holding the default port (patched to one the test owns) and `--no-open`, the command binds another port and prints it. The test stubs `serve_forever` so it returns. A busy `--port` exits 1 with the message, and `webbrowser.open` is called only without `--no-open`.
  - `test_empty_board_says_how_to_load_plans`: no tasks; the page shows the `factory sync` hint and `summary` is all zeros.
  - `test_pages_load_nothing_from_the_network`: the board HTML and the three static files reference no `http://` or `https://` resource. The only such URLs allowed are PR links in `href`.
- **t02:**
  - `test_task_page_shows_the_contract_with_dependencies_and_dependents`: `demo-t02`'s page lists acceptance, non-goals, verification and spec refs, and Depends on `demo-t01` with its badge and link. `demo-t01`'s page lists Needed by `demo-t02`.
  - `test_task_page_lists_runs_newest_first_with_outcomes_and_reports`: plan, build, review (CHANGES), build, review (APPROVE) and verify runs come newest first with the classes good, bad and running. Only the newest run's report `<details>` is open. Duration, steps, tokens, cost and refused show.
  - `test_task_page_shows_the_next_step_the_running_state_and_the_failure_note`: a failed task shows its full note and `factory run TASK`. A building task shows its progress, activity, elapsed and quiet times. A dead one shows its gone-process message.
  - `test_task_page_tails_the_task_log`: a 500-line log shows only the last 200 lines; with no log the page says `No log yet`. The page's `<main>` has `data-refresh="3"`.
  - `test_unknown_task_is_a_404_that_links_back_to_the_board`: the page gets 404 and links to `/`; the JSON route gets 404 with an `error` key.
  - `test_board_links_every_task_to_its_page`: every task id on the board and in Needs you is an `href` to `/tasks/<quoted id>`.
- **t03:**
  - `test_transcript_page_shows_each_step_with_its_tool_calls_and_results`: a recorded transcript with system, human, two ai steps and their tool results. The summary carries `observe.trace_rows`' totals, the system prompt and task message are collapsed with their sizes, and each call is followed by its result.
  - `test_long_results_are_collapsed_and_refusals_flagged`: a 5,000-character result is collapsed behind "5,000 chars", a 100-character one is inline, a `refused: …` result is flagged, and a `stopped` event shows its reason.
  - `test_transcript_page_refreshes_only_while_its_run_is_running`: there is a `data-refresh` with no `ended_at`, and none after `finish_run`.
  - `test_a_half_written_transcript_line_is_skipped`: a transcript whose last line is a cut-off JSON object renders every complete event with status 200.
  - `test_a_run_of_another_task_or_without_a_transcript`: another task's run id gets 404 with a link to the task. A `pr` run with no transcript says `No transcript was recorded for this run`.
  - `test_task_page_links_runs_to_their_transcripts`: runs whose transcript file exists link to `/tasks/TASK/runs/RUN`, and the others don't.

### End-to-end tests

None: the project sets no `e2e` requirement. The over-HTTP test in t01 runs the real server and stdlib client on loopback.

## Verification

- `uv run pytest -q` passes after each task.
- After merging t01, and again after t03, check by hand that the factory version you run is the new one (for example with `uv tool install --reinstall .`):
  1. Run `factory web` in this repository. The board opens and matches `factory top --once`.
  2. Start a task (`factory run example-t01 --no-pr`). The board shows it running and updates without a reload. Its activity line changes, and an open `<details>` stays open.
  3. Stop `factory web`. The page shows the reconnecting banner, which clears when you start it again.
  4. Switch the OS between light and dark mode, then narrow the window below 720px. Both palettes read well, and the task rows stack.
  5. Click a copy button and paste. The command is right.
  6. After t02 and t03, open a task, its newest run's report and a transcript with a long tool result.
- Run `curl -s -X POST -i http://127.0.0.1:8765/` and check it gets 405. Run `curl -s -i -H 'Host: evil.example' http://127.0.0.1:8765/` and check it gets 403.

## Cross-Workstream Coordination

- **Depends on:** nothing.
- **Required by:** nothing.
- **Overlaps:** [agent-flows](agent-flows.md) t04, and [measure](https://github.com/PaddyMc/software-factory/pull/18) and wiki (planned in PR #18), also change `factory/cli.py` and `factory/db.py`. This plan only adds the `web` subcommand and a `readonly` argument to `open_db`, so whichever lands second has a small conflict for the factory's conflict resolution.

## Notes / Out of Scope

- **Actions from the page** (refresh from GitHub, requeue, hold, run) are out: the page is read-only by decision. Adding them later needs a POST route with CSRF protection and a process model for runs.
- **Flow and step names.** Once agent-flows-t03 records `runs.flow` and `runs.step`, a follow-up can label runs by step (`review-glm #1`) instead of role. The page reads only `role` and `attempt`, so nothing breaks before then.
- **Stats.** Once measure-t03 ships `factory/stats.py`, a stats page can render its JSON. Charts and plan dependency graphs are deferred with it.
- **More than one project per page.** Each `factory web` shows one board (`$FACTORY_HOME`). Showing every board under `~/.local/share/factory/` on one page is deferred.
- **Search and filters** on the board are deferred until boards get big enough to need them.
- **Remote viewing** is an SSH tunnel; there is no `--host` option and no auth. A shared board is NEXT.md item 6.
