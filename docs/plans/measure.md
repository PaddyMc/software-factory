# Plan: Measure the factory

**Status:** Planned (2026-11-02). Workstream scoped; awaiting kickoff: it starts once [agent-flows](agent-flows.md) t05 has a PR. Roadmap: the `stats` half of [NEXT.md item 3](../../NEXT.md#3-nothing-measures-the-factory-itself). Sibling: [wiki](wiki.md), which depends on this plan.

---

## Execution Plan

### Locked Decisions

| Decision | Choice |
|---|---|
| Scope | **`factory stats` from the board, plus a prompt version on every agent run.** `factory bench`, which replays past tasks, gets its own plan later |
| What a prompt version covers | **Everything in an agent step's system prompt except the per-task parts** (the contract block and the date line): the step's prompt file, the project rules, the repository guidance, and the wiki pages the [wiki](wiki.md) plan injects. Neither plan has to list the other's parts, and two tasks run under the same instructions share a version |
| Human edits | **Refresh records a `merge` run** for each merged task: `as_built`, or `edited` with the commits pushed after the candidate. Merges from the base (GitHub's Update branch) don't count |
| Sequencing | **After [agent-flows](agent-flows.md).** t01 depends on `agent-flows-t05`, the end of that chain. agent-flows moves the assembly of every agent's system prompt into `LangChainRoles.step` and adds `runs.flow` and `runs.step`, which stats groups by, and its docs task edits the same docs as t04. pr-review-rework, whose `human_review` runs stats counts, is merged. [wiki](wiki.md) t01 depends on this plan's last task |

### Milestones

| # | Deliverable | Exit criteria | Parallelizable with |
|---|---|---|---|
| **M1** | Prompt versions | `tests/test_prompt_versions.py` passes: every agent run records a version; versions ignore the task, and change with the prompt file and the guidance | — |
| **M2** | Merge records | `tests/test_merges.py` passes: `as_built` or `edited` per merged task; an Update-branch merge isn't an edit; nothing is recorded when unsure | — |
| **M3** | `factory stats` | `tests/test_stats.py` passes: every metric in the Stats table, by flow, step, model and prompt version, as tables and JSON | — |
| **M4** | Docs | Architecture, reference, NEXT.md and the shipped factory-ops skill describe it; `tests/test_templates.py` passes | — |

**Sequence:** `agent-flows-t05 → M1 → M2 → M3 → M4 → wiki-t01`. The tasks run one after another: each builds on the one before (stats reads t01's versions and t02's merge runs), and they share `factory/db.py` and `factory/cli.py`.

### Task Contracts

| Milestone | Task IDs | Coverage |
|---|---|---|
| **M1** | `measure-t01` | `prompt_version` on `Output` and `runs`, computed in `LangChainRoles.step`, recorded by the pipeline, printed by `factory show`; `tests/test_prompt_versions.py` |
| **M2** | `measure-t02` | The `merge` run role; new `factory/merges.py` (the final head, the human's commits); the refresh hook; `tests/test_merges.py` |
| **M3** | `measure-t03` | New `factory/stats.py` and `factory stats`; `tests/test_stats.py` |
| **M4** | `measure-t04` | `docs/architecture.md`, `docs/reference.md`, `NEXT.md`, the factory-ops skill template |

```yaml
- id: measure-t01
  goal: "Every agent run records the prompt version it ran under: a hash of its system prompt without the per-task parts, so runs under the same instructions share a version and any change to the instructions makes a new one"
  spec_refs:
    - "docs/plans/measure.md#prompt-versions-t01"
    - "NEXT.md#3-nothing-measures-the-factory-itself"
    - "factory/agents.py"
  depends_on:
    - agent-flows-t05
  non_goals:
    - "Changing what any system prompt says: the prompts, project rules, guidance and contract block stay as they are"
    - "Changing flows, steps, or how a step's prompt, model and step limit are chosen"
    - "Storing prompt texts by version, or a command that looks a version up: each run's transcript already holds its system prompt"
    - "Merge records or stats (measure-t02, t03)"
    - "Editing documentation (README.md, docs/architecture.md, docs/reference.md, NEXT.md) or the skill templates"
  acceptance:
    - "An agent step's prompt version is the first 12 hex characters of the SHA-256 of the system prompt LangChainRoles.step builds for it, with the contract block and the `Today: …` line left out. Everything else counts: the step's prompt file as loaded (its own, its kind's override, or the shipped one), the project rules, the repository guidance, and any part added to the system prompt later"
    - "The runs table gains a `prompt_version` TEXT column, migrated into older databases. The pipeline records it for every agent run (every agent step of the task's flow, and resolve), as it records the model; runs with no agent (pr, ci, human_review, the gates step, a clean replay) leave it NULL"
    - "`factory show TASK` prints each run's prompt version next to its model"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_prompt_versions.py::test_each_agent_run_records_its_prompt_version tests/test_prompt_versions.py::test_two_tasks_under_the_same_prompts_share_a_version tests/test_prompt_versions.py::test_editing_a_role_prompt_changes_only_that_roles_version tests/test_prompt_versions.py::test_editing_the_repository_guidance_changes_every_roles_version tests/test_prompt_versions.py::test_show_prints_each_runs_prompt_version"
    - "uv run pytest -q tests/test_db.py::test_old_database_is_migrated tests/test_pipeline.py"
  risk: medium

- id: measure-t02
  goal: "`factory status --refresh` records what the human changed on a factory PR before merging it: one `merge` run per merged task, `as_built` or `edited`, with the human's commits"
  spec_refs:
    - "docs/plans/measure.md#merge-records-t02"
    - "NEXT.md#3-nothing-measures-the-factory-itself"
  depends_on:
    - measure-t01
  non_goals:
    - "Changing how refresh decides any status: merged, abandoned, conflict, changes_requested, ci_failed and restacks behave as before"
    - "Reading the merge commit on the trunk, or diffing the trunk"
    - "Recording anything for a closed PR, or for a PR taken up from GitHub as already merged (it has no candidate)"
    - "Stats (measure-t03)"
    - "Editing documentation or the skill templates"
  acceptance:
    - "db.ROLES gains `merge`. New factory/merges.py does the reading. When refresh sees a task's PR MERGED and the task has a candidate_sha, it records one `merge` run (attempt 0) as it marks the task merged. The run's sha is the PR's final head, from the `gh pr view` call refresh already makes. Its outcome is `as_built` when the human added no commits of their own (the head is the candidate, or the walk below finds no commits), else `edited`"
    - "To read the human's commits, refresh fetches the PR's branch from the remote, or `refs/pull/<number>/head` when the branch is gone. For `edited`, the report is `git log --first-parent --no-merges --stat -p <candidate>..<head>`, capped at 20,000 characters, so merging the base into the PR (GitHub's Update branch) isn't counted as the human's change. When the candidate isn't an ancestor of the head (a force-push), the outcome is `edited`, and the report says the head was rewritten and carries `git diff --stat <candidate> <head>`"
    - "When the final head can't be read (gh gives none, or the fetch fails), no merge run is recorded, the task is still marked merged, and stderr says `TASK: merged; can't tell whether it was changed before merging (<why>)`. A task gets at most one merge run"
    - "`factory show TASK --role merge` shows the merge run"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_merges.py::test_a_pr_merged_as_built_is_recorded_as_built tests/test_merges.py::test_commits_pushed_to_a_pr_before_merge_are_recorded_as_human_edits tests/test_merges.py::test_updating_a_pr_from_its_base_is_not_a_human_edit tests/test_merges.py::test_a_rewritten_pr_head_is_recorded_as_edited_with_its_diff tests/test_merges.py::test_a_merge_whose_final_head_cant_be_read_records_nothing"
  risk: medium

- id: measure-t03
  goal: "`factory stats` reports from the board how well the factory is doing: task outcomes, attempts and cost per PR, gate failures by gate, reworks and human edits, and per-step rows by flow, model and prompt version"
  spec_refs:
    - "docs/plans/measure.md#stats-t03"
    - "NEXT.md#3-nothing-measures-the-factory-itself"
  depends_on:
    - measure-t02
  non_goals:
    - "factory bench, replays, or any model call"
    - "Writing to the database or calling GitHub: stats only reads factory.db"
    - "Changing what runs record"
    - "Editing documentation or the skill templates"
  acceptance:
    - "factory/stats.py computes every metric in the plan's Stats table from factory.db alone, over a window: runs that started at or after --since and before --until (ISO dates, UTC), for the tasks of --plan when one is given. A task is in the window when any of its runs is"
    - "Summary: tasks in the window, PRs opened, merged, failed; first-attempt pass rate; attempts per PR; cost per merged PR (a merged task with an unpriced run is counted apart, never as zero); reviewer CHANGES rate; step-limit stops by step; the shares of PRs that needed a conflict resolution, a CI fix or a review rework; and the share of merges recorded as edited by the human"
    - "Gates: failed verify runs counted by gate name, read from the gate table in each failed verify run's report (rows `| name | FAIL | … |`)"
    - "Steps: one row per (flow, step, model, prompt version) over agent runs, with runs, mean model calls, step-limit stops, refused tool calls, cost, outcome counts, and the date the version was first seen. Runs recorded before flows show flow `-` and their role as the step; runs with no recorded version show `-`"
    - "`factory stats [--since DATE] [--until DATE] [--plan P] [--json]` prints the summary, gates and steps as tables, or the same data as one JSON object with `window`, `summary`, `gates` and `steps` keys. An empty window prints `no runs in the window` and exits 0. A rate whose denominator is zero shows `-` (null in JSON)"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_stats.py::test_first_attempt_pass_rate_and_attempts_per_pr tests/test_stats.py::test_cost_per_merged_pr_counts_every_run_of_merged_tasks tests/test_stats.py::test_gate_failures_are_counted_by_gate tests/test_stats.py::test_step_rows_split_by_flow_model_and_prompt_version tests/test_stats.py::test_reworks_and_human_edits_are_rates_over_prs tests/test_stats.py::test_the_window_and_plan_filters_select_runs tests/test_stats.py::test_stats_command_prints_tables_and_json"
  risk: low

- id: measure-t04
  goal: "docs/architecture.md, docs/reference.md, NEXT.md and the shipped factory-ops skill describe prompt versions, merge records and `factory stats`"
  spec_refs:
    - "docs/plans/measure.md#design"
  depends_on:
    - measure-t03
  non_goals:
    - "Changing code, or tests beyond what tests/test_templates.py needs for the new template text"
    - "Editing the installed skill copies under .claude/skills or .agents/skills: `factory init --force` refreshes them"
    - "Describing the wiki or the knowledge crew (wiki-t07)"
  acceptance:
    - "docs/architecture.md has a `Measuring the factory` section: what a prompt version covers and leaves out, the merge record and how it tells the human's commits from base merges, and what stats computes, by flow and step. Known limitations say that before/after comparisons by prompt version are confounded by the task mix until `factory bench` exists"
    - "docs/reference.md documents `factory stats` with every flag and the metric definitions, the `merge` run (`factory show TASK --role merge`), and the prompt version in `factory show`"
    - "NEXT.md item 3 says `factory stats` is done, links the architecture section, and says `factory bench` is what's left"
    - "factory/templates/skills/factory-ops/SKILL.md, and its references where they list commands, answer how to see how the factory is doing with `factory stats`"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_templates.py"
    - "grep -q 'Measuring the factory' docs/architecture.md"
    - "grep -q 'factory[[:space:]]stats' docs/reference.md"
    - "grep -q 'factory[[:space:]]stats' factory/templates/skills/factory-ops/SKILL.md"
  risk: low
```

Planned test additions:

- t01: `tests/test_prompt_versions.py` (five tests named in its verification). `tests/test_db.py::test_old_database_is_migrated` is extended to check the `prompt_version` column.
- t02: `tests/test_merges.py` (five tests).
- t03: `tests/test_stats.py` (seven tests).
- t04: none. `tests/test_templates.py` keeps passing with the new template text.

Every verification filter names its tests exactly. A filter that selects zero tests fails the gate.

Prerequisite for `measure-t01`: the agent-flows plan must be on the trunk before this plan, because `factory validate-plan` and `factory sync` resolve `agent-flows-t05` from it. Its plan PR is #17, so merge #17 first. Then t01 waits for `agent-flows-t05` to have an open or merged PR, and the factory stacks it on that PR.

### Risks

1. **Before-and-after comparisons are noisy.** Later tasks differ from earlier ones, and few runs use each prompt version. **Action:** the steps table shows run counts and first-seen dates, so small samples are visible. `factory bench`, a controlled replay, is the next plan for item 3.
2. **Versions churn on changes that don't matter.** The repository guidance is part of the version, so every AGENTS.md edit starts a new one. **Action:** this is deliberate, because the guidance changes what agents do. The first-seen date lets you group neighbouring versions, and a run's transcript shows its exact prompt.
3. **Human-edit detection misreads a GitHub merge**: a deleted branch, an Update-branch merge, a force-push. **Action:** a first-parent, no-merges walk; a fallback to `refs/pull/<number>/head`; nothing recorded when unsure. t02 tests each case.
4. **A deep stack.** t01 stacks on agent-flows' five PRs, and the wiki plan's seven stack on this one. **Action:** the factory restacks on refresh. Merge from the bottom up as PRs pass review, so later tasks start nearer the trunk.
5. **agent-flows lands differently than planned.** For example, `LangChainRoles.step` assembles prompts in another place, or the run columns are named differently. **Action:** the contracts name behavior (the system prompt a step gets, a run's flow and step), not line numbers, and each task's planner reads the code as merged.

---

## Problem

Nothing tells you whether the factory is getting better or worse (NEXT.md item 3):

- **No view across tasks.** Every run's outcome, cost, steps and report are in `runs` (`factory/db.py:37`), but they're only read for one task at a time (`factory show`, `trace`, `transcript`). There's no pass rate, cost per PR, or gate-failure count, and nothing yet compares the flows that [agent-flows](agent-flows.md) makes possible.
- **No record of what a run ran under.** A run records its model (`factory/pipeline.py:301`), but not its instructions. A change to a role prompt, an override, AGENTS.md, or (with the [wiki](wiki.md)) the knowledge pages can't be compared before and after.
- **Human edits are invisible.** Refresh marks a PR merged (`factory/cli.py:427`) without looking at what was merged. If a human fixed the PR before merging, that strong signal is lost, both to stats and to the knowledge crew that ingests merged tasks.

## Goal

`factory stats` answers "how is the factory doing, and did that change help?" from the board alone. Every agent run says which instructions it ran under, and every merged task says whether the human had to change it.

## Design

### Prompt versions (t01)

Today `LangChainRoles._run` assembles the system prompt (`factory/agents.py:194`). agent-flows moves that into `LangChainRoles.step`, once per step of a flow:

```text
step's prompt file    ─┐
contract block          │ ✗ per task
project rules           │
Today: <date> …         │ ✗ per day
repository guidance     │
(wiki: index + role page, from the wiki plan)
                       ─┴─▶ sha256(the ✓ parts joined)[:12] = prompt_version
```

The version goes on `Output` and is written to `runs.prompt_version` next to `runs.model` (`factory/pipeline.py:301`). The full text stays in the run's transcript (its `system` event), so two versions can be diffed with `factory transcript`.

### Merge records (t02)

At refresh, for a task with a candidate whose PR is `MERGED`:

| PR's final head | Outcome | Report |
|---|---|---|
| = candidate | `as_built` | — |
| candidate's descendant; `git log --first-parent --no-merges candidate..head` is empty (only Update-branch merges) | `as_built` | — |
| that log isn't empty | `edited` | that log with `--stat -p`, ≤ 20,000 chars |
| candidate isn't an ancestor (force-push) | `edited` | "head rewritten" + `git diff --stat candidate head` |
| can't be read | no run | stderr note; the task is still marked merged |

The head comes from `_pr_state` (the last of `commits`). It's fetched as `factory/<task>`, or `refs/pull/<number>/head` once GitHub deletes the branch. The [wiki](wiki.md) plan ingests `edited` reports as human signals.

### Stats (t03)

All from `factory.db`, over the window (`--since`, `--until`, `--plan`):

| Metric | Definition |
|---|---|
| First-attempt pass rate | tasks whose first `pr` run (outcome `opened`) has attempt 1 ÷ tasks with a `build` run. With several build steps in a flow, an attempt is one pass through them all |
| Attempts per PR | mean attempt of each task's first `pr` run, over tasks that opened one |
| Cost per merged PR | Σ `cost_usd` of every run of merged tasks ÷ merged tasks (a task with an unpriced run is listed apart) |
| Reviewer CHANGES rate | `review` runs whose outcome starts `CHANGES` ÷ `review` runs |
| Gate failures | per gate name: `FAIL` rows in failed `verify` runs' gate tables |
| Step-limit stops | per step: runs whose outcome ends `(step limit)` or `(graph recursion limit)` |
| Reworks | per kind: PRs (tasks with a `pr` run) with a `resolve`, `ci` or `human_review` run ÷ PRs |
| Human edits | `merge` runs with outcome `edited` ÷ `merge` runs |
| Steps | per (flow, step, model, prompt version): runs, mean model calls, stops, refused tool calls, cost, outcome counts, first seen |

```text
$ factory stats --since 2026-11-01
window: 2026-11-01 → now · 12 tasks · 11 PRs · 9 merged · 1 failed

first-attempt pass rate   58% (7/12)      reviewer CHANGES rate   31% (5/16)
attempts per PR           1.5             human edits             22% (2/9)
cost per merged PR        $0.71           reworks                 conflict 9% · ci 18% · review 27%

gate          failures
session_log   3
verification  2

flow     step    model                    version       runs  calls  stops  refused  cost   outcomes                first seen
default  build   openrouter:deepseek/…    3f2a9c1e0b7d  17    41.2   1      0        $4.10  committed 16 · …        2026-11-01
default  build   openrouter:deepseek/…    9be04d17aa21  5     33.0   0      0        $1.02  committed 5             2026-11-03
default  review  openrouter:z-ai/glm-5.3  -             16    12.4   0      0        $0.88  APPROVE 11 · CHANGES 5  2026-11-01
```

## Files Changed

| File | Change |
|---|---|
| `factory/agents.py` | `prompt_version` on `Output`, computed in `LangChainRoles.step` (t01) |
| `factory/db.py` | `runs.prompt_version` (t01), the `merge` role (t02) |
| `factory/pipeline.py` | Records `prompt_version` next to the model (t01) |
| `factory/cli.py` | Version in `show` (t01); the refresh hook and `show --role merge` (t02); `stats` (t03) |
| `factory/merges.py` | New: the PR's final head and the human's commits (t02) |
| `factory/stats.py` | New: metrics, tables, JSON (t03) |
| `tests/test_prompt_versions.py`, `test_merges.py`, `test_stats.py` | New (t01–t03) |
| `tests/test_db.py` | Migration test covers `prompt_version` (t01) |
| `docs/architecture.md`, `docs/reference.md`, `NEXT.md`, `factory/templates/skills/factory-ops/` | t04 |
| `docs/sessions/` | Every task's session log entry |

## Test Plan

### Unit tests

- `test_prompt_versions.py` (t01) runs `factory run` with `ScriptedModel`:
  - `test_each_agent_run_records_its_prompt_version`: plan, build, review and verify carry a 12-hex version, and pr and the gates run carry NULL.
  - `test_two_tasks_under_the_same_prompts_share_a_version`: demo-t01 and demo-t02 differ only in contract and get the same version per role.
  - `test_editing_a_role_prompt_changes_only_that_roles_version`: an edit to `.factory/agents/builder.md` changes build only.
  - `test_editing_the_repository_guidance_changes_every_roles_version`: an AGENTS.md edit.
  - `test_show_prints_each_runs_prompt_version`.
- `test_merges.py` (t02) uses the fake `gh` (`state: MERGED`, `commits`) and the bare origin:
  - `test_a_pr_merged_as_built_is_recorded_as_built`: also checks that a second refresh adds no run.
  - `test_commits_pushed_to_a_pr_before_merge_are_recorded_as_human_edits`: the report holds the human's diff.
  - `test_updating_a_pr_from_its_base_is_not_a_human_edit`.
  - `test_a_rewritten_pr_head_is_recorded_as_edited_with_its_diff`.
  - `test_a_merge_whose_final_head_cant_be_read_records_nothing`: stderr names why, and the status is merged.
- `test_stats.py` (t03) populates a db with `start_run`/`finish_run`/`progress`:
  - one test per metric group, named in the contract;
  - `test_stats_command_prints_tables_and_json`, which also covers an empty window and `-`/null rates.

### End-to-end tests

The repository configures no `e2e` gate. `test_prompt_versions.py` and `test_merges.py` drive the real CLI, LangGraph and git against a bare origin and the fake `gh`, as `test_pipeline.py` does.

## Verification

- Each contract's verification commands, then `uv run pytest -q` (the unit gate).
- By hand after t03 merges:
  1. Run `factory status --refresh` in this repository. pr-review-rework's merged tasks get merge runs (`factory show <task> --role merge`).
  2. `factory stats` and `factory stats --json` give plausible numbers for that plan.

## Cross-Workstream Coordination

- **Depends on:**
  - [agent-flows](agent-flows.md). `measure-t01` depends on `agent-flows-t05`, the end of that chain. t01 computes the version where `LangChainRoles.step` (agent-flows-t02) builds each step's prompt, t03 groups by the `runs.flow` and `runs.step` columns (agent-flows-t03), and t04 edits the docs agent-flows-t05 edits. agent-flows already lists "Measure the factory" under its Required by.
  - [pr-review-rework](pr-review-rework.md), merged. t02 hooks the refresh precedence its t03 set, and t03 counts the `human_review` runs its t04 records.
- **Required by:**
  - [wiki](wiki.md). `wiki-t01` depends on `measure-t04`. The knowledge crew ingests t02's `edited` merge runs as human signals, and t01's prompt version covers the wiki pages injected into task prompts, so `factory stats` shows their effect.
  - `factory bench`, the rest of NEXT.md item 3 (not yet planned). It will replay merged tasks and compare prompt versions.

## Notes / Out of Scope

- **`factory bench`.** Replaying merged tasks from their bases with `--no-pr`, in a throwaway `FACTORY_HOME`, under different prompts or models, against a stored baseline. It's the controlled comparison stats can't give. Its own plan.
- **Looking a prompt up by version.** Transcripts hold every run's system prompt. A `prompt_versions` table, or `factory prompt --version V`, waits until diffing transcripts proves too awkward.
- **Stats for the knowledge crew.** The [wiki](wiki.md) plan records the crew's runs and costs in its own table, and `factory wiki status` shows them. `factory stats` covers task runs.
- **Recording human edits for PRs taken up as merged.** They have no candidate to compare with.
- **Daily or published metrics** (as Ona does). Stats prints on demand, and a schedule or dashboard can come later.
