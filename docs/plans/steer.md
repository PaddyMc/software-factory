# Plan: Steer a running agent

**Status:** Planned (2026-11-18). Workstream scoped; awaiting kickoff: `steer-t01` runs once this plan is merged and synced and `flow-tuning-t04` has a PR. Roadmap: [NEXT.md item 5](../../NEXT.md#5-steer-a-running-agent).

---

## Execution Plan

### Locked Decisions

| Decision | Choice |
|---|---|
| Reach | **This run.** The running agent gets a message before its next model call, and the message stays in that conversation, including a resumed build's. Every later agent in the same run gets the run's earlier messages in its task message, so a fresh build after a review, or the reviewer, knows what you said. Messages end with the run |
| Authority | **Guidance only.** The contract still decides scope. The reviewer and the verifier see the messages, and the PR body lists them, so you judge any drift when you merge. A reviewer reports work that a message asked for outside the contract, but doesn't block on it |
| A task that isn't running | **Refused,** as `factory stop` refuses one. A message sent while the gates run waits for the run's next agent, and one that no agent got before the run ended is logged as not delivered |
| Surfaces | **`factory say TASK MESSAGE` and a box on a running task's web page.** The box runs `factory say` as a job, like every other button. The box and the "You said" transcript block are fixed by mockups committed with this plan |
| Sequencing | **After `flow-tuning-t04`.** Like `security-review-t01` and `t02`, this plan waits for flow-tuning's code tasks and then runs alongside security-review. The factory's conflict resolution handles the small overlap in `agents.py`, `pipeline.py`, `db.py` and `cli.py` |

### Milestones

| # | Deliverable | Exit criteria | Parallelizable with |
|---|---|---|---|
| **M1** | `factory say` and the board's messages | The t01 tests in `tests/test_steer.py` pass | — |
| **M2** | The running agent gets the message | The t02 tests in `tests/test_steer.py` pass, and `tests/test_agent_loop.py` and `tests/test_pipeline.py` pass unmodified | — |
| **M3** | The rest of the run knows | The t03 tests in `tests/test_steer.py` pass: later agents, the reviewer's guidance, the PR body, messages left at the end of a run | M4 |
| **M4** | The box on the task page | The t04 tests in `tests/test_web.py` pass, and a running task's page and a transcript look like `task-running.html` and `transcript.html` | M3 |
| **M5** | Docs | `tests/test_templates.py::test_the_docs_describe_steering` passes, and `tests/test_templates.py` passes | — |

**Sequence:** `[flow-tuning-t04 →] M1 → M2 → (M3 ∥ M4) → M5`. t01 and t02 share `factory/db.py` and `factory/cli.py`. t02 and t03 share `factory/agents.py` and `factory/pipeline.py`. t04 changes only `factory/web/`, `factory/web/static/app.js` and `tests/test_web.py`, so it runs beside t03.

### Task Contracts

| Milestone | Task IDs | Coverage |
|---|---|---|
| **M1** | `steer-t01` | The `messages` table and its methods in `factory/db.py`; `factory say` and the messages in `factory show` in `factory/cli.py`; new `tests/test_steer.py` |
| **M2** | `steer-t02` | `Ctx.inbox` and the delivery middleware in `factory/agents.py`; the board wiring, the transcript event and the log line in `factory/pipeline.py`; `said` events in `factory transcript` (`factory/observe.py`); tests in `tests/test_steer.py` |
| **M3** | `steer-t03` | The run's messages in later agents' task messages, with the reviewer's and verifier's lines, in `factory/agents.py` and `factory/pipeline.py`; the PR body block in `factory/pipeline.py`; messages left at the end of a run in `factory/cli.py`; tests in `tests/test_steer.py` |
| **M4** | `steer-t04` | The message box and the run's messages on the task page, the `say` action, and the "You said" block on the transcript page in `factory/web/views.py` and `factory/web/server.py`; drafts kept across refreshes in `factory/web/static/app.js`; tests in `tests/test_web.py` |
| **M5** | `steer-t05` | `docs/reference.md`, `docs/architecture.md`, the factory-ops skill (template and installed copy) and `NEXT.md`; a new test in `tests/test_templates.py` |

```yaml
- id: steer-t01
  goal: "`factory say TASK MESSAGE` stores a message on the board for the run of TASK that is going on now, and refuses a task that isn't running. `factory show TASK` lists the latest run's messages and what became of each. Nothing delivers them yet"
  spec_refs:
    - "docs/plans/steer.md#the-board"
    - "docs/plans/steer.md#factory-say"
    - "factory/db.py"
    - "factory/cli.py"
  depends_on:
    - flow-tuning-t04
  non_goals:
    - "Delivering messages to an agent (steer-t02)"
    - "The web page (steer-t04)"
    - "Messages for a task that isn't running, or for a whole plan"
    - "Editing or deleting a message once it is sent"
  acceptance:
    - "Every board opened with open_db has a `messages` table with the columns id INTEGER PRIMARY KEY, task_id TEXT NOT NULL, run_started TEXT NOT NULL, text TEXT NOT NULL, sent_at TEXT NOT NULL, run_id INTEGER, before_step INTEGER, delivered_at TEXT and dropped_at TEXT. That includes a board created before this change. No existing table changes"
    - "`DB.add_message(task_id, text)` stores a message for the task's current run, meaning run_started is the task's `started_at`. It sets sent_at to the current UTC time and returns the new id. `DB.run_messages(task_id)` returns the messages of the task's current run, oldest first"
    - "`factory say TASK MESSAGE...` joins its words with single spaces, and `factory say TASK -` reads the message from stdin. Leading and trailing whitespace is stripped. When the task's status is one of db.ACTIVE and its recorded process is alive, the command stores the message, prints `sent to TASK: the agent gets it before its next model call` and exits 0"
    - "It exits 1 and stores nothing in these cases, printing the reason: `TASK isn't on the board` for an unknown task; `TASK isn't running (STATUS); there's nothing to tell` for a task whose status isn't active or whose process is gone; `the message is empty` for an empty message; and `the message is N characters; the limit is 4,000` for a message over 4,000 characters"
    - "A message belongs to the run it was sent to. After the task is claimed again, with a new started_at, run_messages returns only the messages sent since"
    - "`factory show TASK` prints a `## Messages this run` section after the task's fields and before its runs, when the latest run has any messages. Each line is the sent time (HH:MM:SS UTC), its fate and the text. The fate is `waiting`, or `LABEL got it before step S` (LABEL is the receiving run's step name, or its role when unset, then `#` and its attempt), or `not delivered: the run ended first` when dropped_at is set"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_steer.py::test_say_stores_a_message_for_the_running_task tests/test_steer.py::test_say_reads_the_message_from_stdin tests/test_steer.py::test_say_refuses_a_task_that_isnt_running tests/test_steer.py::test_say_refuses_empty_and_oversized_messages tests/test_steer.py::test_messages_belong_to_the_run_they_were_sent_to tests/test_steer.py::test_show_lists_this_runs_messages_and_their_fate"
    - "uv run pytest -q tests/test_db.py tests/test_stop.py"
  risk: low

- id: steer-t02
  goal: "A message sent with `factory say` reaches the task's running agent before its next model call, as a human message that stays in that agent's conversation. It works in every step kind and every flow. The transcript records it as a `said` event, the run log shows it, and `factory transcript` prints it. A message sent while no agent can take it waits for the run's next agent"
  spec_refs:
    - "docs/plans/steer.md#delivery"
    - "docs/plans/steer.md#what-the-agent-reads"
    - "factory/agents.py"
    - "factory/pipeline.py"
  depends_on:
    - steer-t01
  non_goals:
    - "The run's earlier messages in later agents' task messages, the reviewer's and verifier's lines, the PR body block and messages left at the end of a run (steer-t03)"
    - "Interrupting a model call or a tool call that is in progress"
    - "Changing what an agent sees, records or logs in a run that gets no message"
    - "The web page (steer-t04)"
  acceptance:
    - "Ctx has an `inbox` field: a callable that takes the number of the model call about to be made. It returns the run's waiting messages as (sent_at, text) pairs, oldest first, and marks them delivered. The default returns an empty list"
    - "Every agent step, of every kind and in every flow, runs a middleware placed after ModelCallLimitMiddleware. Before each model call, it asks ctx.inbox for waiting messages. It adds each one to the agent's conversation state as a HumanMessage: the heading `# A message from the person running the factory`, a blank line, the text, a blank line, then `It is guidance: your task's contract still decides what is in scope.` That model call and every later one in the conversation see it, and a resumed build carries it into its next attempt"
    - "Pipeline wires ctx.inbox to the board. A waiting message belongs to the task's current run and has neither delivered_at nor dropped_at. Delivering one sets delivered_at, run_id (the runs row of the agent that got it) and before_step"
    - "Each delivered message is recorded in the agent's transcript as {\"type\": \"said\", \"text\": ..., \"sent_at\": ..., \"before_step\": ...}. It is logged under the agent's tag as `you said: ` followed by the text, clipped to 240 characters"
    - "When ModelCallLimitMiddleware ends an agent at its step limit, no waiting message is marked delivered to it. A message sent while the gates run, or after an agent's last model call, stays waiting and goes to the first model call of the run's next agent"
    - "A message stored by another process during an agent's run reaches the agent's next model call. A test shows this with a scripted model that calls DB.add_message through a second board connection at step 2: the model's messages at step 3 include the human message"
    - "With no message, an agent's conversation, transcript and log are what they are today. tests/test_agent_loop.py and tests/test_pipeline.py pass unmodified"
    - "`factory transcript` prints a said event as `HH:MM:SS [you said, before step S]` followed by its text"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_steer.py::test_a_message_reaches_the_running_agent_before_its_next_model_call tests/test_steer.py::test_a_delivered_message_stays_in_the_conversation tests/test_steer.py::test_a_message_sent_while_no_agent_runs_goes_to_the_next_agent tests/test_steer.py::test_an_agent_at_its_step_limit_leaves_messages_for_the_next tests/test_steer.py::test_without_messages_the_agent_runs_as_before tests/test_steer.py::test_said_events_show_in_the_transcript_and_the_log"
    - "uv run pytest -q tests/test_steer.py tests/test_agent_loop.py tests/test_pipeline.py"
  risk: medium

- id: steer-t03
  goal: "The rest of the run knows what you said. Every later agent in the run gets the run's earlier messages in its task message as guidance. The reviewer reports work that a message asked for outside the contract without blocking on it, and the verifier mentions it. The PR body lists the run's messages, and a message no agent got before the run ended is marked and logged as not delivered"
  spec_refs:
    - "docs/plans/steer.md#the-rest-of-the-run"
    - "docs/plans/steer.md#what-the-agent-reads"
    - "factory/agents.py"
    - "factory/pipeline.py"
  depends_on:
    - steer-t02
  non_goals:
    - "Messages reaching a later run of the task"
    - "Treating a message as part of the contract: no gate reads messages, and the contract and acceptance tests are unchanged"
    - "The web page (steer-t04)"
  acceptance:
    - "When an agent step starts in a run with delivered messages, its task message ends with a section headed `# Messages from the person running the factory`. Under the sentence `They were sent to earlier agents in this run. They are guidance: the contract still decides what is in scope.`, the section lists each delivered message oldest first as `- HH:MM UTC, to LABEL: TEXT`, where LABEL is as `factory show` gives it. A resumed build's message has the section too. A run with no delivered message adds no section"
    - "A review step's section ends with: `If the change does something outside the contract because a message asked for it, report it as a [minor] finding that names the message. It is not on its own a reason for VERDICT: CHANGES.`"
    - "A verify step's section ends with: `Mention under What to check any part of the change that a message asked for.`"
    - "When the run has messages, the PR body has a `<details><summary>Messages during the run (N)</summary>` block after the task block. It lists each message's sent time, its fate (as `factory show` gives it) and its text as a quotation, capped at prbody.BLOCK_LIMIT with the pointer `factory show TASK`. When the body is over GitHub's limit, the block becomes `Messages during the run (N): factory show TASK` (in code) before the task block is replaced"
    - "When `factory run TASK` ends, whether done, failed, stopped by SIGTERM or after an exception, every message of the run that no agent got is given a dropped_at time. Each is logged under the tag `run` as `not delivered, the run ended first: ` followed by the text, clipped to 240 characters"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_steer.py::test_later_agents_get_the_runs_earlier_messages tests/test_steer.py::test_the_reviewer_is_told_messages_are_guidance_not_scope tests/test_steer.py::test_the_pr_body_lists_the_runs_messages tests/test_steer.py::test_messages_left_at_the_end_of_a_run_are_dropped_and_logged"
    - "uv run pytest -q tests/test_steer.py tests/test_pipeline.py tests/test_prbody.py"
  risk: medium

- id: steer-t04
  goal: "A running task's web page has a box that runs `factory say` as a job, and lists this run's messages with what became of each. A transcript page shows each message you sent as a \"You said\" block where the agent got it. The pages look like docs/design/webui/task-running.html and transcript.html"
  spec_refs:
    - "docs/plans/steer.md#the-web-page"
    - "docs/design/webui/task-running.html"
    - "docs/design/webui/transcript.html"
    - "docs/plans/webui.md#security"
  depends_on:
    - steer-t02
  non_goals:
    - "Sending messages from the board, the activity page or a transcript page"
    - "The server writing the board: the box runs `factory say` as a job"
    - "Changing existing rules in factory/web/static/app.css or the mockups"
    - "Changes outside factory/web/, tests/test_web.py and this task's session log"
  acceptance:
    - "The page of a running task (status in db.ACTIVE, process alive) has the form.say and the ol.messages from docs/design/webui/task-running.html inside its next-step panel, after the Stop button. The form's label is `Tell the ROLE`, where ROLE is the role word the transcript page uses for the step of the task's newest run without an ended_at, or `Tell the agent` when there is none. The textarea has id `say-TASK`, name `message`, maxlength 4000 and `required`. A task that isn't running has neither"
    - "The message list shows each message of the current run, oldest first, with its sent time in a <time>, its text and its fate: `waiting for the next model call` (class is-waiting), `LABEL got it before step S` with LABEL as the task page names runs, or `not delivered: the run ended first`. With no messages the list is left out"
    - "POST /actions/say passes the existing token, origin, Host, content-type and size checks. It needs `target` and `message`. When the task is running and the message is 1 to 4,000 characters after stripping, it starts the quick job `factory say TASK MESSAGE` with the message as a single argument and never through a shell. The job's displayed command shell-quotes the message and clips it to 80 characters. The request answers 303 back to the task page with the job's notice. A task that isn't running gets 409, and an empty or oversized message gets 400. Each refusal is a page that says why and links back to the task"
    - "On a transcript page, each said event renders as a div.step.said before the step it arrived before. It shows `You said`, `before step S` and the delivery time, the text in p.says, and `Sent at HH:MM:SS with factory say TASK.` in p.said-via, as docs/design/webui/transcript.html shows"
    - "app.js keeps the text of every textarea with an id across a refresh, so a draft survives the task page's 2-second refresh even when focus has left the box"
    - "A message holding `<script>` or HTML shows as text on the task page, the transcript page and the activity page"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_web.py::test_a_running_task_page_has_the_message_box_and_this_runs_messages tests/test_web.py::test_the_message_box_runs_factory_say_as_a_job tests/test_web.py::test_say_is_refused_for_a_task_that_isnt_running_or_a_bad_message tests/test_web.py::test_the_transcript_shows_what_you_said_where_it_arrived tests/test_web.py::test_messages_are_escaped_on_every_page"
    - "uv run pytest -q tests/test_web.py"
  risk: medium

- id: steer-t05
  goal: "The docs describe steering. The command reference has `factory say` and the task page's message box, and the architecture has a section on how a message reaches the agent and what it may change. The factory-ops skill says how to steer a running task, and NEXT.md marks item 5 done"
  spec_refs:
    - "docs/plans/steer.md#design"
    - "docs/reference.md#commands"
    - "docs/architecture.md#the-web-page"
  depends_on:
    - steer-t03
    - steer-t04
  non_goals:
    - "Code changes"
    - "Rewriting docs that steering doesn't change"
  acceptance:
    - "docs/reference.md's command table has a row for `factory say TASK MESSAGE` (or `-` for stdin). Its web page section names the message box on a running task's page and the command it runs"
    - "docs/architecture.md has a `## Steering a run` section. It covers the messages table, delivery before the next model call as a message that stays in the conversation, the section later agents in the run get, guidance-only scope with the reviewer's rule, the PR body block, and messages that are refused or not delivered"
    - "factory/templates/skills/factory-ops/SKILL.md tells an operator to steer a running task with `factory say TASK \"…\"` or the box on its web page, rather than stopping and rerunning it. .claude/skills/factory-ops/SKILL.md is the same file, as tests/test_templates.py::test_this_repository_uses_the_factory_it_ships requires"
    - "NEXT.md marks item 5 done in its table, with a link to docs/architecture.md#steering-a-run"
    - "A new test, tests/test_templates.py::test_the_docs_describe_steering, checks those four statements. It looks for `say TASK` in docs/reference.md, `## Steering a run` in docs/architecture.md, `factory say` in the factory-ops template, and `architecture.md#steering-a-run` on NEXT.md's item 5 row"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_templates.py::test_the_docs_describe_steering"
    - "uv run pytest -q tests/test_templates.py"
  risk: low
```

Planned test additions:

| Task | File | Tests |
|---|---|---|
| t01 | new `tests/test_steer.py` | `test_say_stores_a_message_for_the_running_task`, `test_say_reads_the_message_from_stdin`, `test_say_refuses_a_task_that_isnt_running`, `test_say_refuses_empty_and_oversized_messages`, `test_messages_belong_to_the_run_they_were_sent_to`, `test_show_lists_this_runs_messages_and_their_fate` |
| t02 | `tests/test_steer.py` | `test_a_message_reaches_the_running_agent_before_its_next_model_call`, `test_a_delivered_message_stays_in_the_conversation`, `test_a_message_sent_while_no_agent_runs_goes_to_the_next_agent`, `test_an_agent_at_its_step_limit_leaves_messages_for_the_next`, `test_without_messages_the_agent_runs_as_before`, `test_said_events_show_in_the_transcript_and_the_log` |
| t03 | `tests/test_steer.py` | `test_later_agents_get_the_runs_earlier_messages`, `test_the_reviewer_is_told_messages_are_guidance_not_scope`, `test_the_pr_body_lists_the_runs_messages`, `test_messages_left_at_the_end_of_a_run_are_dropped_and_logged` |
| t04 | `tests/test_web.py` | `test_a_running_task_page_has_the_message_box_and_this_runs_messages`, `test_the_message_box_runs_factory_say_as_a_job`, `test_say_is_refused_for_a_task_that_isnt_running_or_a_bad_message`, `test_the_transcript_shows_what_you_said_where_it_arrived`, `test_messages_are_escaped_on_every_page` |
| t05 | `tests/test_templates.py` | `test_the_docs_describe_steering` |

Each verification command names its tests, so a missing test fails the gate rather than passing with zero selected. Every task has at least one new test that fails before its change, as the strict flow's test step requires. That includes the docs task, t05.

The project sets no `e2e`, so no task adds an e2e test. `session_log` is set, so each task adds its own `docs/sessions/<date>-<task id>.md`.

Every task changes the factory itself, and runs through `factory run` like the webui and plan-pages tasks. The tests use the `home` and `repo` fixtures and the `ScriptedModel` in `tests/fake_model.py`. A "running" task is a board row in an active status whose pid is the test process. A message sent "during" a run is a scripted model step that calls `DB.add_message` through a second board connection. No test needs the network or a browser.

Prerequisite for `steer-t01`: `flow-tuning-t04` must be merged or have an open PR, as `depends_on` says. This plan's PR must also merge before `factory sync` loads its tasks.

### Risks

1. **A bug in the delivery middleware breaks every run, not just steered ones.** It runs in every agent step. **Action:** with no waiting message, the middleware returns nothing, and t02 tests that an unsteered agent's conversation, transcript and log are unchanged. `tests/test_agent_loop.py` and `tests/test_pipeline.py` must pass unmodified.
2. **The middleware reads the board from inside the agent graph.** **Action:** the trim and nudge middlewares already log through `ctx.log`, which writes a heartbeat to the board from the same place, so the graph runs middleware hooks on the calling thread. t02's tests run the real graph with a real board, and a second connection writes the message, as `factory say` does.
3. **A message lands where nothing sees it.** That could happen at the step limit, between agents, during the gates or after the last model call. **Action:** delivery sits after the call limit, so an agent ending at its limit takes nothing. A waiting message goes to the run's next agent. One left when the run ends is marked and logged. The task page and `factory show` say what became of every message.
4. **A message pulls the work outside the contract, and the reviewer and the human disagree about it.** **Action:** every message says it is guidance and that the contract decides scope. The reviewer reports such work as a minor finding naming the message, and doesn't block on it. The verifier mentions it, and the PR body lists the messages, so the merge decision sees all of it.
5. **A message is an instruction to an agent that can run commands.** **Action:** only someone at this machine can send one. `factory say` writes the local board, and the web box passes the token, Origin and Host checks of every other action. The agent's tools, sandbox and denied commands don't change, and the job runs `factory say` with the message as a single argument, never through a shell.
6. **The task page refreshes every 2 seconds and could throw away a draft.** **Action:** `app.js` already pauses refreshes while focus is in the box, and t04 makes it keep each textarea's text across a refresh. No browser runs in the sandbox, so you check a long draft by hand before merging t04.
7. **Merge conflicts with flow-tuning, security-review and plan-pages.** flow-tuning and security-review change `agents.py`, `pipeline.py`, `db.py` and `cli.py`, and plan-pages and `security-review-t05` change `factory/web/views.py`. **Action:** this plan waits for `flow-tuning-t04`. Its changes are additions: a table, a subcommand, a middleware, a Ctx field, a PR body block and a form. A conflicting PR goes through the factory's conflict resolution (`factory run TASK`).

---

## Problem

The only levers on a running task are watching it and stopping it.

- `factory top`, `factory logs -f` and the web task and transcript pages show a builder heading the wrong way: editing the same file over and over, trying to `git commit`, or reading the whole repository.
- `factory stop` (`factory/cli.py:900`) ends the run. The rerun starts a fresh build and throws away the agent's work and context, and the next build can make the same mistake, because nothing tells it otherwise.
- The factory's own nudges (`NudgeMiddleware`, `factory/agents.py:432`) catch budgets and repeated edits or failures. They can't carry what only you know: which file is the real cause, that a test is wrong, or that a contract line means something narrower.

## Goal

While a task runs, `factory say TASK "…"` or the box on its web page gets a message to the running agent before its next model call. The rest of the run keeps it, the PR shows what you said, and the contract stays the judge of scope. Nothing about a run that gets no message changes.

## Design

```
 factory say TASK "…"  ──or──  task page box ─POST /actions/say─► job: factory say TASK MESSAGE
          │                                                                │
          └──────────────► board: messages (task_id, run_started, text, sent_at, …) ◄──┘
                                               │
   factory run TASK (its own process)          │  waiting = this run's, not delivered, not dropped
   ┌───────────────────────────────────────────┼──────────────────────────────────────────────┐
   │ agent step: [call limit] → [deliver] → model → tools → [call limit] → [deliver] → model … │
   │                                 │                                                         │
   │        ctx.inbox(step) ─────────┘  HumanMessage added to the conversation state;          │
   │                                    transcript {"type": "said"}; log "you said: …"         │
   │ next agent step: task message ends with "# Messages from the person running the factory"  │
   │ PR body: <details> Messages during the run (N)                                            │
   │ run ends: waiting messages → dropped_at, "not delivered" in the log                       │
   └──────────────────────────────────────────────────────────────────────────────────────────┘
```

### The board

```sql
CREATE TABLE IF NOT EXISTS messages (
    id           INTEGER PRIMARY KEY,
    task_id      TEXT NOT NULL,
    run_started  TEXT NOT NULL,   -- the task's started_at when it was sent: which run it belongs to
    text         TEXT NOT NULL,
    sent_at      TEXT NOT NULL,
    run_id       INTEGER,         -- the agent run (runs.id) that got it
    before_step  INTEGER,         -- the model call it arrived before
    delivered_at TEXT,
    dropped_at   TEXT             -- the run ended before any agent got it
);
```

- A run is identified by the task's `started_at`, which `DB.claim` sets when `factory run TASK` starts. Messages of an earlier run never reach a later one.
- The board is the one place for factory state, so `factory show`, the web page and the PR body all read this table. The agent process reads it through `Ctx.inbox`, so `agents.py` never touches the board.

### `factory say`

```
factory say TASK MESSAGE...
factory say TASK -              # the message from stdin

$ factory say bench-t04 "Don't commit: the factory commits for you."
sent to bench-t04: the agent gets it before its next model call
```

| Case | Output | Exit |
|---|---|---|
| Running (status in `db.ACTIVE`, process alive) | `sent to TASK: the agent gets it before its next model call` | 0 |
| Unknown task | `TASK isn't on the board` | 1 |
| Not running, or its process is gone | `TASK isn't running (STATUS); there's nothing to tell` | 1 |
| Empty after stripping | `the message is empty` | 1 |
| Over 4,000 characters | `the message is N characters; the limit is 4,000` | 1 |

`factory show TASK` gains a `## Messages this run` section with each message's time, fate and text.

### Delivery

- A middleware in every agent step, after `ModelCallLimitMiddleware`, asks `ctx.inbox(step)` before each model call. The pipeline answers from the board and marks what it returns as delivered to the current agent run before that step.
- Each message is added to the conversation **state**, not just the outgoing request as `NudgeMiddleware` does. The model sees it on this call and every later one, and a resumed build carries it.
- Placed after the call limit, the middleware never hands a message to an agent that the limit is ending. That message waits for the run's next agent.
- A model call or a tool call in progress isn't interrupted. A message sent during a 5-minute test run arrives before the next model call after it.

### What the agent reads

Delivered during the agent's run, as a human message:

```markdown
# A message from the person running the factory

Don't commit: the factory commits for you. Fix the compare header first.

It is guidance: your task's contract still decides what is in scope.
```

At the start of every later agent step in the run, at the end of its task message (t03):

```markdown
# Messages from the person running the factory

They were sent to earlier agents in this run. They are guidance: the contract still decides what is in scope.

- 21:38 UTC, to build#1: Don't commit: the factory commits for you. Fix the compare header first.
```

The reviewer's section adds: `If the change does something outside the contract because a message asked for it, report it as a [minor] finding that names the message. It is not on its own a reason for VERDICT: CHANGES.` The verifier's adds: `Mention under What to check any part of the change that a message asked for.`

### The rest of the run

- **Later agents** get the section above. A resumed build gets it too, even though its conversation already holds the messages.
- **The PR body** gets `<details><summary>Messages during the run (N)</summary>` after the task block. Each message is listed with its time, fate and text as a quotation. Under the body limit, the block is replaced by a pointer to `factory show TASK` before the task block is.
- **The end of the run**, however it ends short of SIGKILL, gives every message still waiting a `dropped_at` time and logs it as not delivered.

### The web page

The structure is [`docs/design/webui/task-running.html`](../design/webui/task-running.html) for a running task and [`transcript.html`](../design/webui/transcript.html) for the "You said" block.

- **Box:** in the next-step panel of a running task, after Stop: `Tell the builder` (or the running step's role), a textarea, and Send, which runs `factory say TASK MESSAGE` as a quick job and comes back to the task page with the notice. The POST goes through the webui [Security](webui.md#security) checks. A task that isn't running gets 409, and an empty or oversized message gets 400.
- **Messages:** this run's messages under the box, oldest first, each with its time, text and fate: `waiting for the next model call`, `build 1 got it before step 9`, or `not delivered: the run ended first`.
- **Transcript:** a `said` event is a `div.step.said` before the step it arrived before, ruled in the brightest text colour.
- **Drafts:** `app.js` keeps a textarea's text across the 2-second refresh. It already skips refreshes while the box has focus.
- **Look:** the rules `.say`, `.say-end`, `.messages`, `.said` and `.said-via` are in `app.css`, committed with this plan. No existing rule changes.

## Files Changed

| File | Change |
|---|---|
| `factory/db.py` | The `messages` table, `add_message`, `run_messages`, delivery and drop updates (t01, t02, t03) |
| `factory/cli.py` | `factory say`, messages in `factory show` (t01); waiting messages dropped at the end of a run (t03) |
| `factory/agents.py` | `Ctx.inbox` and the delivery middleware (t02); the run's messages in the task message, with the review and verify lines (t03) |
| `factory/pipeline.py` | The board wiring, the `said` event and the log line (t02); earlier messages for later agents and the PR body block (t03) |
| `factory/observe.py` | `said` events in `factory transcript` (t02) |
| `factory/web/server.py`, `factory/web/views.py` | The `say` action, the box and the messages on the task page, and "You said" on the transcript page (t04) |
| `factory/web/static/app.js` | Textarea drafts kept across refreshes (t04) |
| `factory/web/static/app.css` | `.say`, `.say-end`, `.messages`, `.said`, `.said-via` (with this plan) |
| `docs/design/webui/task-running.html`, `transcript.html`, `README.md` | The new mockup, the "You said" block, and the README row (with this plan) |
| `tests/test_steer.py` | New (t01, t02, t03) |
| `tests/test_web.py` | The web tests (t04) |
| `docs/reference.md`, `docs/architecture.md`, `NEXT.md`, the factory-ops skill and its installed copy, `tests/test_templates.py` | Docs and their test (t05) |

## Test Plan

### Unit tests

- **t01, `tests/test_steer.py`:**
  - `test_say_stores_a_message_for_the_running_task`: the row, its run, the output.
  - `test_say_reads_the_message_from_stdin`.
  - `test_say_refuses_a_task_that_isnt_running`: an unknown task, a queued, failed or merged task, and an active task whose process is gone.
  - `test_say_refuses_empty_and_oversized_messages`: nothing stored.
  - `test_messages_belong_to_the_run_they_were_sent_to`: a second claim starts a new run.
  - `test_show_lists_this_runs_messages_and_their_fate`: waiting, delivered, dropped.
- **t02, `tests/test_steer.py`:**
  - `test_a_message_reaches_the_running_agent_before_its_next_model_call`: a scripted builder whose step 2 stores a message; step 3's request holds it.
  - `test_a_delivered_message_stays_in_the_conversation`: steps 4 and later still see it, and a resumed build's carried messages hold it.
  - `test_a_message_sent_while_no_agent_runs_goes_to_the_next_agent`: a message stored during the gates reaches the reviewer's first model call.
  - `test_an_agent_at_its_step_limit_leaves_messages_for_the_next`.
  - `test_without_messages_the_agent_runs_as_before`: the same model requests, transcript and log as without the middleware.
  - `test_said_events_show_in_the_transcript_and_the_log`: the event, the log line, `factory transcript`.
- **t03, `tests/test_steer.py`:**
  - `test_later_agents_get_the_runs_earlier_messages`: a fresh build after CHANGES, and a resumed build.
  - `test_the_reviewer_is_told_messages_are_guidance_not_scope`: the review and verify lines.
  - `test_the_pr_body_lists_the_runs_messages`: the block, its cap, its replacement under the limit.
  - `test_messages_left_at_the_end_of_a_run_are_dropped_and_logged`: a run that ends done, failed and stopped.
- **t04, `tests/test_web.py`:** the five tests in its contract, through `App.handle` with a launch function that records the job.
- **t05, `tests/test_templates.py`:** `test_the_docs_describe_steering`.

### End-to-end tests

The project configures no `e2e` gate. The t02 and t03 tests are the end-to-end path. They run `Pipeline` with the real LangChain agent graph, the scripted model and a real board. A second connection sends the message, as `factory say` would from another process.

## Verification

- `uv run pytest -q` passes after each task.
- After t02, on a real task: start `factory run TASK`. While it builds, `factory say TASK "…"`. Then check the run log's `you said:` line, the agent's next steps in `factory transcript`, and `factory show TASK`.
- After t04, send a message from a running task's page. Watch its fate change from waiting to delivered, then open the transcript and find the "You said" block. Type a long draft, click elsewhere, and check that a refresh keeps it.

## Cross-Workstream Coordination

- **Depends on:** [flow-tuning](flow-tuning.md) (`flow-tuning-t04`, sequencing only: both change `agents.py`, `pipeline.py`, `db.py` and `cli.py`) and [webui](webui.md), merged. Its task page, actions, jobs and security checks carry the box.
- **Required by:** nothing yet. [wiki](wiki.md) could later take human messages as a learning signal, beside reviews and gate failures.
- **Overlaps:**
  - [security-review](security-review.md) runs alongside this plan and changes `agents.py`, `pipeline.py`, `db.py`, `cli.py` and `factory/web/views.py`.
  - [plan-pages](plan-pages.md), in plan PR #82, changes `factory/web/views.py`, `server.py`, `tests/test_web.py`, `app.css` and the mockups' navigation. `task-running.html` follows `main`'s navigation; once plan-pages lands, add its Plans item there too.

  See Risk 7.

## Notes / Out of Scope

- **Messages that last beyond a run.** Standing guidance for a task belongs in its contract, which you edit in the plan and sync.
- **Messages to a whole plan** or to every running task at once.
- **Interrupting** a model call or tool call in progress, or pausing an agent until you answer.
- **The agent asking you a question.** That would need a reply channel and a way to wait for it.
- **Editing or withdrawing** a sent message.
- **Sending from the board or a transcript page.** The box is on the task page only.
