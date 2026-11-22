# Plan: Follow a task’s agent thoughts

**Planned 2026-11-22.** Workstream 20 builds on the shipped transcript and web views. [Roadmap](../../NEXT.md#20-follow-a-tasks-agent-thoughts)

## Execution Plan

### Locked Decisions

| Decision | Choice |
|---|---|
| What opens first | A task-wide timeline across agents and retries. Both interfaces can narrow it by role, named flow step and attempt. |
| What each entry shows | The thought the model shared, then the tool names from that reply or a short reply excerpt. The full transcript is reachable from the entry. |
| When to use it | Both during and after a task. The CLI follows on request. The web view updates automatically while the task runs. Each update follows a recorded model reply. |

### Milestones

| Milestone | Deliverable | Exit criteria |
|---|---|---|
| M1 | Review a task from the terminal | One command shows a tester, a builder retry and a reviewer in order. Its transcript hint opens the exact run even when two attempts have the same labels. |
| M2 | Follow the task in the terminal | A follower sees a newly completed reply once and continues into the next agent or retry. |
| M3 | Read and follow from the web UI | One link on the task page opens the same entries. Filters, expanded thoughts and transcript links work as new replies arrive. |

The sequence is **M1 → M2 → M3**. M1 and M2 share the reader and CLI. M3 uses the same reader and documents the web workflow beside the CLI in the reference.

### Task Contracts

| Milestone | Task ID | Coverage |
|---|---|---|
| M1 | `thought-timeline-t01` | Shared transcript reader, CLI snapshot and exact-run transcript selection |
| M2 | `thought-timeline-t02` | Incremental CLI follow across runs and retries |
| M3 | `thought-timeline-t03` | Discoverable web timeline, live updates, filters and links to the matching transcript turn |

```yaml
- id: thought-timeline-t01
  goal: "Add factory thoughts TASK and an exact-run transcript hint using a shared task-scoped reader in factory/observe.py and the parser in factory/cli.py."
  spec_refs:
    - "docs/plans/thought-timeline.md#reading-the-timeline"
    - "docs/plans/thought-timeline.md#terminal"
    - "docs/plans/thoughts.md#recording"
  depends_on: [thoughts-t02]
  non_goals: ["Live follow", "Web UI", "Changes to agent requests, the transcript writer, logs or the database schema"]
  acceptance:
    - "The default command shows all recorded thought entries for one task in run ID then transcript order. Label the run ID, role, flow step, attempt (including zero), reply number and recorded time when available. Each entry shows the full saved thought or the positive thinking-token count with an explanation when text was unavailable."
    - "Include tool names in recorded order when present, otherwise a one-line reply excerpt capped at 160 characters including any ellipsis. Omit an empty action. Keep prompts, call arguments and tool results out of this view."
    - "Support intersecting --role, --step and --attempt filters including test, named flow steps and attempt zero. Handle historical runs without a step name, missing transcript files and partially written records as specified in Reading the timeline. Distinguish an unknown task (nonzero) from a known task with no matching thoughts (clear message and success)."
    - "A copyable factory transcript TASK --run-id ID --full hint for each displayed run selects that exact run through the normal CLI, including while its transcript has an unfinished last record. Reject a foreign or missing run ID without opening its file. Preserve the existing latest, --all and filtering behavior for invocations without --run-id."
    - "Document both commands in docs/reference.md. Add the named tests under tests/test_observe.py and a dated docs/sessions entry ending in -thought-timeline-t01.md."
  verification:
    - "uv run --offline pytest -q tests/test_observe.py::test_thoughts_cli_orders_and_filters_runs tests/test_observe.py::test_thoughts_cli_handles_old_missing_and_partial_records tests/test_observe.py::test_thoughts_hint_opens_exact_transcript"
    - "uv run --offline pytest -q tests/test_observe.py::test_transcripts_without_thoughts_print_as_before"
  risk: medium
- id: thought-timeline-t02
  goal: "Let factory thoughts TASK --follow print the snapshot once, then emit matching replies as they arrive across agent and attempt changes."
  spec_refs:
    - "docs/plans/thought-timeline.md#reading-the-timeline"
    - "docs/plans/thought-timeline.md#following-a-task"
  depends_on: [thought-timeline-t01]
  non_goals: ["Web polling", "Token-by-token model streaming", "Changes to board state, model calls or transcript files"]
  acceptance:
    - "Expose -f and --follow in factory/cli.py. Reuse the snapshot format and filters, flush entries promptly, and continue observing the task through quiet intervals, run handoffs, new retries and a started run whose file appears later."
    - "In factory/observe.py, resume from the last consumed record per run. Retain or reread an incomplete trailing line and emit its reply once after completion. A reply appended at the snapshot-to-follow boundary is delivered once. Idle polls do not reread completed transcript history."
    - "For a queued task, wait for a run. After the task finishes or an active worker is recorded dead, drain complete matching records and exit. Following an already finished task emits its snapshot and returns promptly. Ctrl-C exits cleanly and has no effect on the worker."
    - "Document follow behavior in docs/reference.md. Add deterministic follow tests under tests/test_observe.py and a dated docs/sessions entry ending in -thought-timeline-t02.md."
  verification:
    - "uv run --offline pytest -q tests/test_observe.py::test_thoughts_follow_emits_split_reply_and_next_attempt_once tests/test_observe.py::test_thoughts_follow_waits_drains_and_stops"
  risk: medium
- id: thought-timeline-t03
  goal: "Give every task page a Thoughts link opening a filterable task-wide timeline with live updates and a link from each thought to its source turn."
  spec_refs:
    - "docs/plans/thought-timeline.md#reading-the-timeline"
    - "docs/plans/thought-timeline.md#web-page"
    - "docs/plans/webui.md#live-pages"
  depends_on: [thought-timeline-t02, thoughts-t03]
  non_goals: ["A board-wide feed", "Changes to agent prompts, storage or capture", "New frontend dependencies or write endpoints"]
  acceptance:
    - "Place a visible Thoughts link near the task heading in factory/web/views.py. Serve GET /tasks/TASK/thoughts via factory/web/server.py with the shared reader, a read-only board connection and the existing page layout. A known task with no matching entries has an empty state. An unknown task gets 404."
    - "Render the same entries, labels and action context as the CLI in chronological run order. Provide labeled GET filters for role, flow step and attempt that combine and survive refresh, plus a way to clear them. All controls and transcript links work with ordinary HTML navigation."
    - "Give each entry a link to the matching run and turn anchor on the existing transcript page. Preserve its existing folds. Show a readable opening for long thoughts and make the complete saved text available. Escape model text and labels, encode links, and keep stored paths, prompts, tool arguments and results out of the timeline."
    - "While the task is running, refresh at the existing two-second cadence through agent handoffs. Preserve an expanded thought across refreshes, including two runs with the same reply number. After completion show the final entries and stop polling. Opening a finished task starts no timer."
    - "Update README.md and docs/reference.md with the CLI and web entry points, and docs/architecture.md with the page route. Add the named request tests in tests/test_web.py and a dated docs/sessions entry ending in -thought-timeline-t03.md."
  verification:
    - "uv run --offline pytest -q tests/test_web.py::test_task_links_to_filterable_thought_timeline tests/test_web.py::test_thought_links_open_the_exact_turn_and_escape_text tests/test_web.py::test_thought_timeline_refreshes_across_runs_and_stops"
    - "uv run --offline pytest -q tests/test_web.py::test_long_thoughts_fold_after_their_opening tests/test_web.py::test_a_half_written_transcript_line_is_skipped"
  risk: medium
```

The planned additions are the three t01, two t02 and three t03 tests named in the first verification command of each contract. The other named tests already exist. A verification command must select and run its named tests. Each task adds its own `docs/sessions/YYYY-MM-DD-<task-id>.md` using the implementation date.

The implementation prerequisites on the earlier plans have merged. After the plan PR merges, run `factory sync` from an up-to-date `main` to load the three contracts.

### Risks

1. **A retry looks like a duplicate.** Keep the database run ID and the turn’s position in its file. Role, attempt, reply number and timestamp can all repeat across runs.
2. **A follower drops the last reply.** Discover runs and consume complete records again after observing task completion. Exercise the startup race and a split write with a controlled writer in tests.
3. **An old or unavailable transcript gives a misleading blank page.** Distinguish token counts without text from a task with no recorded thoughts. Surface a missing referenced file without losing other runs’ entries.
4. **Long tool results overwhelm refreshes.** Apply run filters before opening files and stream through JSONL one record at a time. Keep only timeline data for rendering. Opening the ordinary task page costs one link and reads no additional transcripts.

## Problem

The factory already records reasoning supplied by a model, its reported thinking-token count and tool calls together for each reply. Its log preview clips the reasoning at 240 characters (`factory/agents.py:735`). The terminal transcript defaults to the latest matching run and mixes reasoning with prompts, calls and results (`factory/cli.py:672`, `factory/observe.py:197`). The web task page links to a separate transcript under each run (`factory/web/views.py:778`). Following a tester, a builder retry and the final review currently means piecing those runs together.

## Goal

One command or one click from a task should answer “What were its agents considering, and what did they do next?” The same view should work for a task that finished yesterday and one whose next reply is still being written.

## Design

### Reading the timeline

Read only the selected task’s board runs and their recorded transcript paths. `DB.runs` supplies stable run ID order (`factory/db.py:223`). Within a run, preserve append order. For each `ai` record with nonblank `reasoning`, use the saved text, preserving paragraphs. A positive `usage.reasoning` count can also stand alone, as in “121 thinking tokens. The model didn’t share text for this reply.” Skip replies with neither. An absent or zero count still permits a thought with text.

The run supplies its ID, role, flow step (fall back to role for old rows) and attempt. The event supplies the turn number (`ai.step`) and optional time. Keep the flow step and turn number separately labeled. A turn calling tools shows the tool names in order. Otherwise show a whitespace-collapsed excerpt from its reply, capped at 160 characters. Preserve the full recorded thought independently of that cap.

Select runs before reading their files. A row with no transcript path contributes no entries. If a referenced file is missing, identify the run as unavailable, keep reading other runs and retry an active file on the next poll. Skip malformed complete lines and unrelated event types. Wait for a newline before consuming an active file’s last record. Accept a complete final JSON record without a newline in a finished file. Filter roles and flow steps by their stored labels so custom step names and the strict flow’s tester are both accessible. Absence of a named step uses the same fallback for display and filtering.

### Terminal

```sh
factory thoughts example-t01
factory thoughts example-t01 --role build --step implement --attempt 2
factory thoughts example-t01 --follow
factory transcript example-t01 --run-id 42 --full
```

For example, a builder’s entry could read like this:

```text
Run 42 · build · flow step implement · attempt 2
09:15:17 UTC · turn 3
The failing assertion expects an empty list. I’ll check the parser’s empty-input branch.
Tools: read_file, grep
Full transcript: factory transcript example-t01 --run-id 42 --full
```

Group entries by run and print the transcript command once per group, with the actual task and run ID. Exact selection matters when restarting a task creates a second “build, attempt 1”. Scope that lookup to the task before reading a transcript. If exact selection is combined with another selection that excludes the run, report no match. A snapshot of a known empty task or an empty selection explains the result and exits successfully.

### Following a task

The pipeline appends one timestamped JSON object per line and gives each role run its own file (`factory/pipeline.py:315`, `factory/pipeline.py:341`). Acquire follow positions while reading the snapshot so a write between initial display and the first poll is visible. Poll the board for newly created runs as well as the open file for new replies. Keep the same filters across handoffs. For example, a follower filtered to review waits while the builder works and starts printing when the reviewer returns a thought. Use task liveness and status for exit, then do a final read. Tests can inject a write and a state change between polls without wall-clock sleeps.

### Web page

The task heading links directly to **Thoughts**, including for tasks that have yet to record one. Put the three filters above the entries. The submitted URL carries the filter values, so a bookmark and live refresh restore the same selection. Populate filter choices from the task’s run metadata. An entry links to `/tasks/TASK/runs/RUN#turn-N`. Add that anchor to the corresponding turn in the existing transcript. Task-level fold IDs include both the run and turn, allowing the existing refresh code to restore the correct expanded thought.

Use the existing thought typography, long-text folds, and server-rendered page. Keep paragraph breaks legible. Reuse `app.js` for refresh and apply the newly fetched page’s refresh setting when rescheduling. Today it keeps the interval from the initial page, so a task that finishes while open needs explicit coverage. When scripting is disabled, the same URL renders the complete snapshot and can be refreshed manually.

## Files Changed

| Paths in implementation PRs | Purpose |
|---|---|
| `factory/observe.py`, `factory/cli.py`, `tests/test_observe.py` | Shared reader, CLI snapshot and follow, exact transcript selection |
| `factory/web/server.py`, `factory/web/views.py`, `factory/web/static/app.js`, `tests/test_web.py` | Route, links, filters, folds and refresh lifecycle |
| `docs/reference.md`, `README.md`, `docs/architecture.md` | Command examples, entry point and route |
| `docs/sessions/` | One implementation entry per task |

## Test Plan

**Unit coverage.** Use synthetic JSONL with multiline thoughts, multiple calls, a long reply, tokens without text, and a legacy reply with neither. Include a missing file, a partial record and identical turn numbers in different runs. Assert the absence of sentinel prompt, tool-argument and result strings in both interfaces.

**End-to-end coverage.** Drive the real CLI parser against a temporary board and follow through an append, file creation, agent handoff, retry and terminal state. Exercise web requests through `App.handle` on the same kind of fixture. Follow the task link, apply and clear combined filters, resolve a turn anchor and request the page before and after a run transition. The project’s tests live under `tests/` and run offline.

## Verification

Run the exact pytest node IDs in each contract and the configured `uv run pytest -q` gate. At web review, open a filtered live task, expand a long thought, let another reply arrive and follow its transcript link. Verify the first thought stays expanded and the browser stops polling after the task ends. This browser check supplements the offline request tests.

## Cross-Workstream Coordination

- **Depends on** [thoughts](thoughts.md). Its merged `thoughts-t02` provides the terminal transcript and `thoughts-t03` the web presentation. The latter builds on [webui](webui.md)’s `webui-t05` transcript route.
- **Required by** no current workstream. The timeline reads saved events and can be delivered independently of changes to agent flows.

## Notes / Out of Scope

Model configuration, prompts, new reasoning capture, token streaming during generation, persistent indexes and cross-task search are outside this workstream. The timeline can surface only what was recorded. Source material stays in the local factory home.
