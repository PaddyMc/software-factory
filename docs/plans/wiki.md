# Plan: A repository wiki kept by a knowledge crew

**Status:** Planned (2026-11-02). Workstream scoped; awaiting kickoff: it starts once [measure](measure.md) t04 and [strict-flow](strict-flow.md) t08 have PRs. Roadmap: [NEXT.md item 4](../../NEXT.md#4-learn-from-feedback). Sibling: [measure](measure.md), which this plan depends on. Pattern: Karpathy's [LLM wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f).

---

## Execution Plan

### Locked Decisions

| Decision | Choice |
|---|---|
| What the wiki is | **A knowledge base of the repository**, after Karpathy's LLM wiki. It has overview, module, concept, decision and role pages, plus `index.md` and `log.md`. The lessons for the task crew are its role pages, `roles/<role>.md` |
| Who writes it | **A knowledge crew, separate from the task crew**: an ingester, a linter and a wiki reviewer, with their own prompts, models and step limits. Only the crew writes the wiki: a `wiki_untouched` gate fails any task that changes it |
| Where it lives, and approval | **In the repository**, under the directory that `wiki:` in `.factory/config.yaml` names (opt-in; `docs/wiki` here). The crew adds one commit per ingest or lint to **one standing PR** from the `factory-wiki` branch, and merging it publishes the wiki. After that PR merges or closes, the next run starts the branch again from the trunk |
| Sources | **A merged task** (its contract, change, reviewer findings, failed gates, human reviews and edits), **a code path, or a doc.** The first pages come from ingesting the main modules and docs |
| How task agents use it | **Each task agent step's system prompt gets `index.md` and the role page for its kind**, read from the task's base commit. Other pages are read on demand with the existing read tools. Where the wiki and the code disagree, the code wins |
| Review | **Every crew change passes the deterministic wiki check, then the wiki reviewer**, before it is committed. The human merges the PR |
| Cadence | **Manual**: `factory wiki ingest` and `factory wiki lint`. Nothing starts the crew automatically |
| Sequencing | **After [measure](measure.md) and [strict-flow](strict-flow.md).** t01 depends on `measure-t04` and on `strict-flow-t08`, the last code task of the plan that changes the task crew's loop, and t07 depends on `strict-flow-t09`, which edits the same docs. t04's briefs use measure's merge records, and measure's prompt version covers the wiki pages injected into task prompts, so `factory stats` shows their effect |

### Milestones

| # | Deliverable | Exit criteria | Parallelizable with |
|---|---|---|---|
| **M1** | Wiki format and check | `tests/test_wiki_check.py` passes: structure errors, stale pages, caps, `factory init --wiki`, `factory wiki check` | — |
| **M2** | Task agents read the wiki | `tests/test_wiki_reading.py` passes: index and role page from the base commit; no change without a wiki; the `wiki_untouched` gate | — |
| **M3** | The crew's ingest loop | `tests/test_wiki_ingest.py` passes: path ingests, standing branch and PR, write scope, check retries | — |
| **M4** | Ingesting merged tasks | `tests/test_wiki_sources.py` passes: task briefs with human signals first, pending from the log, `factory wiki status` | — |
| **M5** | The wiki reviewer | `tests/test_wiki_review.py` passes: approve, changes back to the ingester, rejection | — |
| **M6** | Lint | `tests/test_wiki_lint.py` passes: stale pages re-verified, check errors fixed, reviewed, committed | — |
| **M7** | Docs | Architecture, reference, README, NEXT.md and the shipped templates describe it; `tests/test_templates.py` passes | — |

**Sequence:** `(measure-t04 ∥ strict-flow-t08) → M1 → M2 → M3 → M4 → M5 → M6 → [strict-flow-t09 →] M7`. The tasks run one after another: each builds on the one before, and the code tasks share `factory/wiki.py`, `factory/cli.py` and `factory/agents.py`.

### Task Contracts

| Milestone | Task IDs | Coverage |
|---|---|---|
| **M1** | `wiki-t01` | The `wiki` config key; templates for the schema, index and log; `factory init --wiki`; page parsing and `wiki.check` in new `factory/wiki.py`; `factory wiki check`; `tests/test_wiki_check.py` |
| **M2** | `wiki-t02` | The wiki block in task roles' system prompts (from the base commit); the `wiki_untouched` gate and project rule; `tests/test_wiki_reading.py` |
| **M3** | `wiki-t03` | `factory/prompts/ingester.md`, the `ingest` role, the `wiki_runs` table, the standing branch, `factory wiki ingest PATH…`, the push and the standing PR; the fake model's INGESTER; `tests/test_wiki_ingest.py` |
| **M4** | `wiki-t04` | Task source briefs, pending tasks from `log.md`, `factory wiki ingest` with no source, `factory wiki status`; `tests/test_wiki_sources.py` |
| **M5** | `wiki-t05` | `factory/prompts/wiki-reviewer.md`, the `wiki_review` role, the review step and its retries; the fake model's WIKI REVIEWER; `tests/test_wiki_review.py` |
| **M6** | `wiki-t06` | `factory/prompts/linter.md`, the `lint` role, `factory wiki lint`; the fake model's LINTER; `tests/test_wiki_lint.py` |
| **M7** | `wiki-t07` | `docs/architecture.md`, `docs/reference.md`, `README.md`, `NEXT.md`, the factory-ops skill and AGENTS.md section templates |

```yaml
- id: wiki-t01
  goal: "A wiki format the factory checks without a model: `wiki:` in .factory/config.yaml names the directory, `factory init --wiki DIR` writes its schema, index and log, and `factory wiki check` reports structure errors and stale pages"
  spec_refs:
    - "docs/plans/wiki.md#the-wiki-t01"
    - "https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f"
  depends_on:
    - measure-t04
    - strict-flow-t08
  non_goals:
    - "Any agent, ingest or lint run (wiki-t03 to t06)"
    - "Putting the wiki into task prompts, or the wiki_untouched gate (wiki-t02)"
    - "Turning the wiki on for this repository: its .factory/config.yaml stays as it is"
    - "Editing documentation (README.md, docs/architecture.md, docs/reference.md, NEXT.md) or the skill templates"
  acceptance:
    - "config.py accepts an optional `wiki` key: a repository-relative directory, unset (off) by default. The shipped config template carries it commented out (`# wiki: docs/wiki`). `factory init --wiki DIR` writes DIR/SCHEMA.md, DIR/index.md and DIR/log.md from new templates under factory/templates/wiki/, keeping existing files unless --force, as init does. It sets `wiki: DIR` in the config it writes, and appends that line to an existing config that has no `wiki` key"
    - "factory/wiki.py parses pages: every .md file under the wiki directory except SCHEMA.md, index.md and log.md. Each starts with YAML frontmatter: `title`; `kind` (overview, module, concept, decision or role); `sources`, a non-empty list of repository-relative paths or `task:<id>`; and `verified`, a commit. Role pages are roles/planner.md, roles/builder.md, roles/reviewer.md and roles/verifier.md"
    - "wiki.check(root, cfg, ref) returns errors and stale pages from git and the files alone. Errors: a page with missing or invalid frontmatter; a page that index.md doesn't link to, or links to more than once; a link in index.md or a page that resolves to neither a wiki page nor a file in the repository; a `sources` path that doesn't exist at ref; a `task:` source that isn't a task in the plans; a `verified` commit that doesn't exist; index.md over 8,000 characters, a role page over 3,000, or any other page over 20,000; a log.md heading not of the form `## [YYYY-MM-DD] ingest | …` or `## [YYYY-MM-DD] lint | …`. A page is stale when a commit after its `verified` commit, up to ref, changed one of its `sources` paths"
    - "`factory wiki check [--ref REF]` (default ref HEAD) prints each error, and each stale page with the commits that made it stale. It exits 1 on any error and 0 otherwise, since stale pages alone don't fail. With no `wiki` configured, it says so and exits 2"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_wiki_check.py::test_a_well_formed_wiki_passes_the_check tests/test_wiki_check.py::test_pages_missing_from_the_index_and_broken_links_are_errors tests/test_wiki_check.py::test_bad_frontmatter_and_missing_sources_are_errors tests/test_wiki_check.py::test_pages_whose_sources_changed_since_verified_are_stale tests/test_wiki_check.py::test_size_caps_and_log_heading_format tests/test_wiki_check.py::test_init_with_wiki_writes_the_schema_index_log_and_config tests/test_wiki_check.py::test_wiki_check_command_exit_codes"
    - "uv run pytest -q tests/test_config.py tests/test_templates.py"
  risk: low

- id: wiki-t02
  goal: "Task agents read the wiki and can't change it: with `wiki` configured, each task role's system prompt carries index.md and its role page from the task's base commit, and the wiki_untouched gate fails any task that edits the wiki"
  spec_refs:
    - "docs/plans/wiki.md#how-task-agents-read-it-t02"
  depends_on:
    - wiki-t01
  non_goals:
    - "Writing the wiki: any crew agent or command (wiki-t03 onward)"
    - "Choosing other pages for a task (retrieval): agents read them on demand"
    - "Changing any system prompt or gate when no wiki is configured"
    - "Editing factory/prompts/*.md, documentation or the skill templates"
  acceptance:
    - "When `wiki` is configured, LangChainRoles.step adds a block to the system prompt of every agent step of a task's flow, and of resolve, right after the step's instructions. The block starts with the heading `# Repository wiki (<dir>/, at the base commit)` and one paragraph: the knowledge crew keeps this wiki; read other pages with read_file when the task touches their area; where the wiki and the code disagree, the code wins. Then come index.md, and the page for the step's kind under `## Guidance for the <kind> (<dir>/roles/<file>)`: roles/planner.md for plan steps, roles/builder.md for build steps and resolve, roles/reviewer.md for review steps, roles/verifier.md for verify steps. Both files are read with git from the task's base commit (Ctx.base_sha), never from the worktree. A missing file is left out, and with neither the block is left out"
    - "With no `wiki` configured, every system prompt is byte-for-byte what it was before this task"
    - "factory/gates.py adds `wiki_untouched` right after plan_untouched when `wiki` is configured. It fails when the candidate changes any file under the wiki directory, and names those files. `factory gates` runs it too. project_rules tells every role not to edit the wiki directory, because the knowledge crew keeps it and the wiki_untouched gate fails otherwise, and to name in its final report anything there the change makes untrue"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_wiki_reading.py::test_task_roles_get_the_index_and_their_role_page tests/test_wiki_reading.py::test_the_wiki_is_read_from_the_base_commit_not_the_worktree tests/test_wiki_reading.py::test_without_a_wiki_system_prompts_are_unchanged tests/test_wiki_reading.py::test_the_wiki_untouched_gate_fails_a_task_that_edits_the_wiki tests/test_wiki_reading.py::test_project_rules_name_the_wiki_gate"
    - "uv run pytest -q tests/test_gates.py tests/test_pipeline.py"
  risk: medium

- id: wiki-t03
  goal: "`factory wiki ingest PATH…` runs the knowledge crew's ingester on code paths and docs. It edits only the wiki, on the standing `factory-wiki` branch, and every change that passes the wiki check is committed and pushed to one standing PR"
  spec_refs:
    - "docs/plans/wiki.md#the-crews-run-loop-t03"
    - "docs/plans/wiki.md#ingester"
  depends_on:
    - wiki-t02
  non_goals:
    - "Task sources, the pending list and `factory wiki status` (wiki-t04)"
    - "The wiki reviewer (wiki-t05): this task commits what passes the check"
    - "Lint (wiki-t06)"
    - "Running the crew automatically"
    - "Changing `factory run`, its flows and steps, or their models and provider keys"
    - "Editing documentation or the skill templates"
  acceptance:
    - "An ingester role ships as factory/prompts/ingester.md (`You are the INGESTER`, with the rules in the plan's Ingester section), and .factory/agents/ingester.md overrides it. config ROLES gains `ingest` for `models` and `max_steps`, and `factory prompt ingest` prints the prompt. `factory run`'s model and provider-key checks still cover only its flow's steps"
    - "factory/db.py has a `wiki_runs` table (id, op, source, started_at, ended_at, outcome, attempts, sha, branch, pr_url, report, steps, tokens_in, tokens_out, cost_usd), created in older databases on open"
    - "`factory wiki ingest [--base B] [--model M] [--no-pr] PATH…` exits 2 when no `wiki` is configured, and refuses before any agent runs when a PATH doesn't exist at the base's tip. Otherwise it first prepares the standing branch at $FACTORY_HOME/worktrees/factory-wiki. When `factory-wiki` has an open PR, the branch is rebased onto the tip of the base (default: the current branch, as for `factory run`) and pushed with a lease on its old head. When it has none, or its PR merged or closed, the branch starts again at the base's tip. A rebase that conflicts stops the run, names the files and changes nothing"
    - "Each PATH is one ingest, in the order given, with one wiki_runs row. The ingester gets read tools over the worktree, write tools that refuse any path outside the wiki directory and SCHEMA.md inside it, and no run tool. SCHEMA.md and index.md are in its system prompt, and its message names the source and the base's tip. The result must pass wiki.check, plus four more conditions: only files under the wiki directory changed; log.md kept every earlier entry and gained exactly one `## [<today>] ingest | <path>`; every page it changed has `verified` set to the base's tip; and the source is in each new page's `sources`. A pass is committed as `wiki: ingest <path>`. A failure goes back to the ingester with the errors, for at most 3 attempts in all; after that the ingest is recorded `refused` with the errors, and nothing is committed. No change is recorded `no_change`"
    - "After the last ingest, new commits are pushed to `factory-wiki`, and the standing PR is opened against the base, or updated if it is already open. Its title is `factory wiki: <n> updates`. Its body lists every commit on the branch (op, source and the first line of the agent's final message), the check's stale pages, and that merging publishes the wiki to task agents. --no-pr commits locally and pushes nothing. Each wiki_runs row records its outcome, sha, PR and cost. Transcripts go to $FACTORY_HOME/transcripts/wiki/ and the log to $FACTORY_HOME/logs/wiki.log, and the worktree is removed at the end"
    - "tests/fake_model.py's ScriptedModel plays INGESTER scripts, and the full suite passes"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_wiki_ingest.py::test_ingesting_a_path_commits_wiki_pages_and_opens_the_standing_pr tests/test_wiki_ingest.py::test_a_second_ingest_adds_a_commit_to_the_open_standing_pr tests/test_wiki_ingest.py::test_after_the_standing_pr_merges_the_branch_starts_again_from_the_base tests/test_wiki_ingest.py::test_the_standing_branch_is_rebased_onto_the_base_first tests/test_wiki_ingest.py::test_the_ingester_cannot_write_outside_the_wiki_or_edit_the_schema tests/test_wiki_ingest.py::test_an_ingest_that_keeps_failing_the_check_is_refused_and_not_committed tests/test_wiki_ingest.py::test_the_ingester_prompt_ships_and_can_be_configured"
    - "uv run pytest -q tests/test_templates.py tests/test_config.py"
  risk: high

- id: wiki-t04
  goal: "The knowledge crew ingests merged tasks: `factory wiki ingest task:<id>` gives the ingester the task's contract, change and feedback from the board, and `factory wiki ingest` with no source ingests every merged task the wiki's log doesn't list yet"
  spec_refs:
    - "docs/plans/wiki.md#task-sources-t04"
    - "docs/plans/measure.md#merge-records-t02"
  depends_on:
    - wiki-t03
  non_goals:
    - "Calling GitHub to build a brief: it comes from factory.db and git"
    - "The wiki reviewer and lint (wiki-t05, t06)"
    - "Changing what task runs record"
    - "Editing documentation or the skill templates"
  acceptance:
    - "factory/wiki.py builds a task source brief from the board and git. It holds the contract (goal, non-goals, acceptance), the plan file and the PR URL; the change (`git diff --stat` and the patch of base_sha..candidate_sha, the patch capped at 20,000 characters); then the task's feedback, human signals first and newest first within each kind: human_review briefs, the merge run's report when it is `edited`, review runs with outcome CHANGES, the failed rows of failed verify runs' gate tables, failure notes, step-limit stops and refused tool calls; then the last verifier report. The brief is capped at 60,000 characters: whole items are left out from the end, and a final line says how many"
    - "`factory wiki ingest task:<id>` refuses a task that isn't merged. With no source, ingest takes every merged task on the board that no log.md heading names as `task:<id>` (on the standing branch, or on the base when no standing PR is open), oldest merge first (by its merge run, else by when the board marked it merged), at most --limit (default 10). With none pending it prints `nothing to ingest` and runs no agent"
    - "For a task source, the ingester's message is its brief, and the log heading is `## [<today>] ingest | task:<id>`. Path sources behave as in wiki-t03, and both kinds can be mixed in one command"
    - "`factory wiki status` prints the standing PR (or none), the merged tasks pending ingest, the check's stale page count, and the last 10 wiki runs with their outcomes and costs"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_wiki_sources.py::test_a_task_brief_has_the_contract_change_and_feedback_humans_first tests/test_wiki_sources.py::test_the_task_brief_is_capped_and_says_what_it_left_out tests/test_wiki_sources.py::test_ingest_with_no_source_takes_merged_tasks_missing_from_the_log tests/test_wiki_sources.py::test_ingesting_an_unmerged_task_is_refused tests/test_wiki_sources.py::test_nothing_pending_runs_no_agent tests/test_wiki_sources.py::test_wiki_status_shows_the_standing_pr_pending_tasks_and_runs"
  risk: medium

- id: wiki-t05
  goal: "A wiki reviewer judges every change the knowledge crew makes before it is committed. Once the wiki check passes, it reads the diff and the sources and gives VERDICT: APPROVE or CHANGES, and CHANGES goes back to the crew agent with its findings"
  spec_refs:
    - "docs/plans/wiki.md#wiki-reviewer"
    - "docs/plans/wiki.md#the-crews-run-loop-t03"
  depends_on:
    - wiki-t04
  non_goals:
    - "Relaxing or skipping the wiki check"
    - "Lint (wiki-t06), beyond lint reusing this review step"
    - "Changing how task PRs are reviewed: the task reviewer and its prompt are unchanged"
    - "Editing documentation or the skill templates"
  acceptance:
    - "A wiki reviewer role ships as factory/prompts/wiki-reviewer.md (`You are the WIKI REVIEWER`, with the rules in the plan's Wiki reviewer section), and .factory/agents/wiki-reviewer.md overrides it. config ROLES gains `wiki_review`, and `factory prompt wiki_review` prints the prompt"
    - "In each ingest, a change that passes the check goes to the wiki reviewer. It gets read tools over the worktree, a diff tool against the commit the ingest started from, SCHEMA.md in its system prompt, and the same source message the ingester got. Its verdict is read with parse_verdict, so a missing verdict counts as CHANGES. APPROVE commits the change. CHANGES sends the reviewer's report back to the ingester as feedback for another attempt, within the same 3-attempt limit as check failures. An ingest still unapproved after its last attempt is recorded `rejected` with the reviewer's report, its changes are dropped, and the next source starts from the last commit"
    - "The standing PR's body entry for each commit includes the first line of the wiki reviewer's report"
    - "tests/fake_model.py plays WIKI REVIEWER scripts, kept apart from the task REVIEWER's, and the full suite passes"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_wiki_review.py::test_an_approved_ingest_is_committed tests/test_wiki_review.py::test_reviewer_changes_go_back_to_the_ingester_as_feedback tests/test_wiki_review.py::test_an_ingest_never_approved_is_rejected_and_dropped tests/test_wiki_review.py::test_the_wiki_reviewer_gets_the_diff_and_the_sources tests/test_wiki_review.py::test_the_wiki_reviewer_prompt_ships_and_can_be_configured"
    - "uv run pytest -q tests/test_wiki_ingest.py tests/test_pipeline.py"
  risk: medium

- id: wiki-t06
  goal: "`factory wiki lint` keeps the wiki true to the code. It gives the linter the wiki check's errors and stale pages; the linter re-checks them against the code, fixes or removes what no longer holds and marks them verified; and the change goes through the check and the wiki reviewer onto the standing PR"
  spec_refs:
    - "docs/plans/wiki.md#linter"
    - "docs/plans/wiki.md#the-crews-run-loop-t03"
  depends_on:
    - wiki-t05
  non_goals:
    - "Searching the web or reading outside the repository"
    - "Ingesting new sources"
    - "Running lint automatically"
    - "Editing documentation or the skill templates"
  acceptance:
    - "A linter role ships as factory/prompts/linter.md (`You are the LINTER`, with the rules in the plan's Linter section), and .factory/agents/linter.md overrides it. config ROLES gains `lint`, and `factory prompt lint` prints the prompt"
    - "`factory wiki lint [--base B] [--model M] [--no-pr] [--max-pages N]` prepares the standing branch as ingest does, then runs wiki.check. With no errors and no stale pages, it prints `the wiki is clean` and runs no agent. Otherwise one lint run's message holds the errors and up to --max-pages stale pages (default 15), stalest first, each with the commits and diffs to its sources since its `verified` commit, capped at 40,000 characters in all"
    - "The linter has the ingester's tools and write scope. Its result must pass the check, plus four more conditions: only wiki files changed; log.md kept every earlier entry and gained exactly one `## [<today>] lint | <n> pages`; every page it changed or re-checked has `verified` set to the base's tip; and none of the errors it was given remain. The wiki reviewer then judges it as in wiki-t05, within 3 attempts. An approved lint is committed as `wiki: lint <n> pages`, pushed, and added to the standing PR, and its wiki_runs row has op `lint`"
    - "tests/fake_model.py plays LINTER scripts, and the full suite passes"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_wiki_lint.py::test_lint_gives_the_linter_the_errors_and_the_stale_pages_with_their_diffs tests/test_wiki_lint.py::test_a_lint_marks_the_pages_it_rechecked_as_verified_at_the_base tests/test_wiki_lint.py::test_a_clean_wiki_runs_no_agent tests/test_wiki_lint.py::test_a_lint_goes_through_the_check_and_the_wiki_reviewer tests/test_wiki_lint.py::test_the_linter_prompt_ships_and_can_be_configured"
  risk: medium

- id: wiki-t07
  goal: "docs/architecture.md, docs/reference.md, README.md, NEXT.md, the shipped factory-ops skill and the AGENTS.md section template describe the repository wiki and the knowledge crew"
  spec_refs:
    - "docs/plans/wiki.md#design"
  depends_on:
    - wiki-t06
    - strict-flow-t09
  non_goals:
    - "Changing code, or tests beyond what tests/test_templates.py needs for the new template text"
    - "Editing the installed skill copies under .claude/skills or .agents/skills, or this repository's AGENTS.md: `factory init --force` refreshes them"
    - "Turning the wiki on for this repository, or writing any page under docs/wiki/"
    - "Editing factory/prompts/*.md"
  acceptance:
    - "docs/architecture.md has a `The knowledge crew` section covering: the three layers (sources, the wiki, the schema); the ingester, the linter and the wiki reviewer; the wiki check; the standing PR; how task agents read the wiki (from the base commit, index and role page); and the wiki_untouched gate. Its Components and Roles mention them. Known limitations say the wiki lags the code until a lint runs and the standing PR merges, and that the injected pages cost tokens on every step"
    - "docs/reference.md documents: the `wiki` config key; `factory init --wiki`; `factory wiki check`, `ingest`, `lint` and `status`, with every flag; the page format and its caps; the `ingest`, `lint` and `wiki_review` keys for `models` and `max_steps`; `factory prompt` for the crew's roles; wiki_untouched in the gate list; and troubleshooting for a refused or rejected ingest, a rebase conflict on the standing branch, and a task that fails wiki_untouched. README.md's `Where things live` lists worktrees/factory-wiki, transcripts/wiki/ and logs/wiki.log"
    - "NEXT.md marks item 4 done through the knowledge crew, with a link to the architecture section"
    - "factory/templates/skills/factory-ops/SKILL.md, and its references where they list commands, answer how to start and maintain the wiki (`factory init --wiki`, `factory wiki ingest`, `lint`, `status`) and how to review the standing PR. factory/templates/agents-section.md says the knowledge crew keeps the wiki, and that tasks can't edit it"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_templates.py"
    - "grep -q 'The knowledge crew' docs/architecture.md"
    - "grep -q 'wiki_untouched' docs/reference.md"
    - "grep -q 'wiki[[:space:]]ingest' docs/reference.md"
    - "grep -q 'wiki[[:space:]]lint' factory/templates/skills/factory-ops/SKILL.md"
    - "grep -q 'knowledge crew' factory/templates/agents-section.md"
  risk: low
```

Planned test additions:

- t01: `tests/test_wiki_check.py` (seven tests named in its verification).
- t02: `tests/test_wiki_reading.py` (five tests).
- t03: `tests/test_wiki_ingest.py` (seven tests).
- t04: `tests/test_wiki_sources.py` (six tests).
- t05: `tests/test_wiki_review.py` (five tests).
- t06: `tests/test_wiki_lint.py` (five tests).
- t07: none. `tests/test_templates.py` keeps passing with the new template text.

Every verification filter names its tests exactly. A filter that selects zero tests fails the gate.

Prerequisite for `wiki-t01`: none outside the board. It waits for `measure-t04` to have an open or merged PR, and the factory stacks it on that PR.

After `wiki-t06` merges, turning the wiki on for this repository is the maintainer's job, not a factory task. It needs a model key and a `gh` login:
1. `factory init --wiki docs/wiki`.
2. Seed it: `factory wiki ingest factory/ docs/architecture.md docs/reference.md`, then `factory wiki ingest` for the merged tasks.
3. Review the standing PR and merge it.

From then on, this repository's tasks get the `wiki_untouched` gate.

### Risks

1. **A wrong page misleads every later run.** **Action:** every claim cites code or a task. The deterministic check, then the wiki reviewer, run before any commit. Task prompts say the code wins. Lint re-verifies pages whose sources changed. The human merges the PR.
2. **Context cost.** `index.md` and the role page are in every step of every task run. **Action:** caps of 8,000 and 3,000 characters, and provider prompt caching. Measure's prompt versions mean `factory stats` shows cost and steps per PR before and after the wiki, so a wiki that costs more than it saves shows up.
3. **Role pages overfit or lower the bar.** **Action:** the ingester's bar for a rule: the source shows the problem, and it recurs or a human raised it, with a citation. The wiki reviewer checks the same, nothing may relax a gate or the task reviewer, and the role-page cap applies.
4. **The standing PR becomes a large review.** **Action:** one commit per source, each listed in the PR body with the reviewer's summary. Rejected ingests never reach it, and you merge whenever you choose.
5. **The standing branch drifts from the trunk.** **Action:** every run starts by rebasing it onto the base's tip, pushed with a lease. The gate keeps tasks out of the wiki, so a rebase conflicts only if someone edited the wiki outside the crew; the run then stops and names the files.
6. **`verified` commits vanish with a squash merge.** **Action:** `verified` is always the base's tip, a trunk commit, never a commit on the standing branch.
7. **Crew cost.** **Action:** the crew runs only by hand, with `--limit` and capped briefs, and `factory wiki status` shows each run's cost.
8. **A deep stack.** This plan's seven tasks stack on measure's four, which stack on agent-flows' five. **Action:** merge from the bottom up as PRs pass review. The factory restacks the rest on refresh.

---

## Problem

The factory doesn't accumulate what it learns about a repository:

- **Every run starts cold.** The planner explores the code from scratch each time, and the builder explores it again (Known limitations, "The builder re-explores what the planner already read", `docs/architecture.md`). The only repository-specific knowledge an agent gets is the guidance file (`factory/agents.py:197`), which humans write and which covers every role at once.
- **Feedback doesn't flow back** (NEXT.md item 4). Reviewer findings, failed gates, human reviews (pr-review-rework) and human edits ([measure](measure.md) t02) are all on the board, but no later run sees them.
- **The only per-repository lever is a fork.** Steering a role means replacing its whole prompt with `.factory/agents/<role>.md` (`factory/agents.py:81`). From then on, that repository stops getting the factory's prompt updates.
- **Docs drift.** `docs/architecture.md` and similar files stay current only if someone keeps them current. The maintenance cost is what makes people abandon a wiki, which is the gap Karpathy's pattern fills with an LLM.

## Goal

A knowledge crew keeps a wiki of the repository in the repository, from its code, docs and merged tasks: what the modules do, why they're built that way, and how the task crew should work here. The wiki is reviewed like code and published by merging one standing PR. Every task agent starts from the wiki's index and its role's guidance, and `factory stats` shows whether runs got better.

## Design

### The three layers

| Layer | Here | Who changes it |
|---|---|---|
| Raw sources | the code, docs, plans; each merged task's contract, change and feedback on the board | humans and task PRs; the crew only reads |
| The wiki | `<wiki>/` pages, `index.md`, `log.md` | the knowledge crew only (`wiki_untouched` gate) |
| The schema | `<wiki>/SCHEMA.md` | humans; the crew suggests changes in its PR body |

### The wiki (t01)

```text
docs/wiki/
  SCHEMA.md               conventions for the crew (shipped template; human-owned)
  index.md                catalog by kind, one line per page; task agents read it first
  log.md                  append-only: ## [2026-11-05] ingest | task:pr-review-rework-t02
  overview.md
  modules/<name>.md       e.g. modules/pipeline.md
  concepts/<name>.md      e.g. concepts/stacked-prs.md
  decisions/<name>.md     e.g. decisions/one-rework-path.md
  roles/planner.md  roles/builder.md  roles/reviewer.md  roles/verifier.md
```

A page:

```markdown
---
title: Pipeline
kind: module
sources: [factory/pipeline.py, factory/agents.py, task:pr-review-rework-t01]
verified: 3f2a9c1e0b7d4a…        # a trunk commit: the base's tip when the page was last written or checked
---
One task runs plan → build → review → verify → PR as a LangGraph (`factory/pipeline.py:418`). Review
CHANGES and failed gates loop back to build with feedback, up to `max_attempts` …
```

An `index.md` line: `- [Pipeline](modules/pipeline.md): one task from plan to PR; the rework entry points`.

The check (`wiki.check`, `factory wiki check`) uses git and files only:

| Finding | Kind |
|---|---|
| Frontmatter missing or invalid; `kind` unknown; `sources` empty | error |
| Page not in `index.md`, or listed twice; a broken link | error |
| A `sources` path missing at the ref; a `task:` id not in the plans; a `verified` commit that doesn't exist | error |
| `index.md` > 8,000 chars; a role page > 3,000; another page > 20,000 | error |
| A `log.md` heading not `## [YYYY-MM-DD] ingest\|lint \| …` | error |
| A source path changed after `verified` (`git log verified..ref -- path`) | stale |

### How task agents read it (t02)

```text
<step instructions>
# Repository wiki (docs/wiki/, at the base commit)
The knowledge crew keeps this wiki. Read other pages with read_file when the task touches their
area. Where the wiki and the code disagree, the code wins.
<index.md>
## Guidance for the builder (docs/wiki/roles/builder.md)
<roles/builder.md>
# Task `…`               (contract block, as today)
# Project rules          (+ don't edit docs/wiki/: the wiki_untouched gate)
Today: …
# Repository guidance    (AGENTS.md, as today)
```

The two files come from `git show <base_sha>:<wiki>/…`, so a task can't change what it or a later role reads. Measure's prompt version covers the block, because only the contract and the date are left out of the hash.

### The crew's run loop (t03)

```text
factory wiki ingest [SOURCE…]            factory wiki lint
        │                                       │
        ▼                                       ▼
prepare factory-wiki: open PR → rebase onto the base's tip (leased push)
                      none, merged or closed → start again at the base's tip
        │
        ▼  for each source (lint: one run)
ingester / linter ──▶ wiki check + only wiki files + one log entry + verified = base tip
      ▲                       │ fail
      └──── errors ───────────┘
                              │ pass
                              ▼
                       wiki reviewer (t05) ──CHANGES──▶ back to the agent    (≤ 3 attempts in all)
                              │ APPROVE
                              ▼
                     commit "wiki: ingest <source>" / "wiki: lint <n> pages"
        │
        ▼
push factory-wiki (leased) → open or update the standing PR → you merge → task agents read it
```

The branch is `factory-wiki`, kept out of the `factory/<task>` namespace that refresh and take-up read. The crew's agents never commit or push; the factory process does, as it does for tasks. Each agent run's transcript goes to `$FACTORY_HOME/transcripts/wiki/`.

### Task sources (t04)

A `task:<id>` brief, at most 60,000 characters, with whole items dropped from the end when it's longer:

| # | Part | From |
|---|---|---|
| 1 | Contract: goal, non-goals, acceptance; the plan file; the PR | `tasks.contract`, `tasks.pr_url` |
| 2 | The change: `--stat`, and the patch (≤ 20,000 chars) | `git diff base_sha..candidate_sha` |
| 3 | Human reviews | `human_review` runs (pr-review-rework) |
| 4 | Human edits before merge | `merge` runs with outcome `edited` ([measure](measure.md) t02) |
| 5 | Reviewer findings | `review` runs, outcome `CHANGES…` |
| 6 | Failed gates | the `FAIL` rows of failed `verify` runs |
| 7 | Failures, step-limit stops, refused tool calls | task notes, run outcomes, `runs.refused` |
| 8 | The final verifier report | the last `verify` run with outcome `report` |

A task is pending until a `log.md` heading names it, so the wiki itself records what's been ingested. That record is shared by every board and survives a board reset.

### Ingester

The rules (the body of `factory/prompts/ingester.md`):

1. Read `index.md` first, and existing pages before writing new ones. Update rather than duplicate.
2. From the source, file what a future planner, builder, reviewer or verifier of this repository needs:
   - what modules do and how they connect (module pages);
   - ideas that cut across them (concept pages);
   - why things are as they are (decision pages);
   - how the task crew should work here (role pages).
3. Ground every claim in code you read (cite `path:line`, and list the path in `sources`) or in the task source (list `task:<id>`). Write nothing you didn't read.
4. A role-page rule needs four things:
   - the source shows the problem (a reviewer finding, a failed gate, a human review or edit);
   - it isn't already a project rule or in the role's prompt;
   - it happened in more than one task (check the log and the pages), unless a human raised it;
   - it ends `(from: task:<id>, …)`.

   Never relax a gate or the reviewer's checks.
5. Set `verified` to the base commit your message names on every page you write or re-check.
6. Keep `index.md` to one line per page, and append one `log.md` entry that lists the pages you touched.
7. Don't edit `SCHEMA.md`. Suggest schema changes in your final message instead.
8. Stay within the caps. Split or condense pages as they grow.
9. Final message: a one-line summary, then the pages created and changed, then `RESULT: DONE` or `RESULT: NOTHING`.

### Wiki reviewer

The rules (the body of `factory/prompts/wiki-reviewer.md`):

1. Every added or changed claim is supported by what it cites. Open the cited code, and check the source message.
2. Nothing from one task becomes a convention. Role rules meet the ingester's bar.
3. Nothing relaxes a gate or the task reviewer's checks, or contradicts the role prompts, the project rules or `SCHEMA.md`.
4. `index.md` and `log.md` match the change, and nothing changes that the source doesn't justify.
5. Output: a one-line summary; findings as `[blocker|major|minor] path — what, why, fix`; then `VERDICT: APPROVE` or `VERDICT: CHANGES`.

### Linter

The rules (the body of `factory/prompts/linter.md`):

1. For each stale page, read its sources' changes and re-read the code. Fix the claims that no longer hold, delete the ones that can't be grounded, and set `verified` to the base's tip.
2. Fix every check error you're given.
3. Look for contradictions between the pages you touch and the pages they link to, for concepts several pages mention that have no page, and for pages missing from the index.
4. The ingester's citation rules, caps and final message apply. The log entry is `## [<today>] lint | <n> pages`.

## Files Changed

| File | Change |
|---|---|
| `factory/config.py` | The `wiki` key (t01); `ingest`, `wiki_review` and `lint` in `ROLES` (t03, t05, t06) |
| `factory/wiki.py` | New: pages, `check` (t01); the crew's run loop and standing branch (t03); task briefs and pending tasks (t04); review step (t05); lint (t06) |
| `factory/scaffold.py`, `factory/templates/config.yaml`, `factory/templates/wiki/` | `factory init --wiki`, and the schema, index and log templates (t01) |
| `factory/agents.py` | The wiki block in every task step's prompt, in `LangChainRoles.step` (t02); the crew's roles and write scope (t03, t05, t06) |
| `factory/gates.py` | `wiki_untouched` (t02) |
| `factory/tools.py` | `PathGuard` with writable prefixes and denied paths (t03) |
| `factory/db.py` | The `wiki_runs` table (t03) |
| `factory/cli.py` | `factory wiki check` (t01); `ingest` (t03, t04); `status` (t04); `lint` (t06) |
| `factory/prompts/ingester.md`, `wiki-reviewer.md`, `linter.md` | New (t03, t05, t06) |
| `tests/fake_model.py` | Plays INGESTER, WIKI REVIEWER and LINTER (t03, t05, t06) |
| `tests/test_wiki_check.py`, `test_wiki_reading.py`, `test_wiki_ingest.py`, `test_wiki_sources.py`, `test_wiki_review.py`, `test_wiki_lint.py` | New (t01–t06) |
| `docs/architecture.md`, `docs/reference.md`, `README.md`, `NEXT.md`, `factory/templates/skills/factory-ops/`, `factory/templates/agents-section.md` | t07 |
| `docs/sessions/` | Every task's session log entry |

## Test Plan

### Unit tests

- `test_wiki_check.py` (t01) builds wikis in a throwaway repository:
  - a well-formed one passes;
  - each error kind is reported;
  - a source edited after `verified` makes its page stale, but not an error;
  - the caps and the log heading format;
  - `factory init --wiki` on a fresh repository and on an existing config;
  - `factory wiki check` exits 0, 1 or 2.
- `test_wiki_reading.py` (t02) runs `factory run` with `ScriptedModel` and reads the transcripts' system events:
  - the builder's prompt has the index and `roles/builder.md`, and the reviewer's has `roles/reviewer.md`;
  - a builder edit to `docs/wiki/roles/reviewer.md` doesn't reach the reviewer;
  - without `wiki`, prompts are byte-identical to a run on the base;
  - `wiki_untouched` fails a task that edits the wiki;
  - the project rules name the gate.
- `test_wiki_ingest.py` (t03) runs `factory wiki ingest factory/x.py` with INGESTER scripts against a bare origin and the fake `gh`:
  - one commit, and the PR opened;
  - a second run adds a commit to the same PR;
  - after the PR merges, the branch is reset to the base;
  - the branch is rebased when the base moved;
  - a write to `AGENTS.md` or `SCHEMA.md` is refused;
  - three failed checks mean `refused` and no commit;
  - the prompt ships, and `models.ingest` validates.
- `test_wiki_sources.py` (t04) puts board rows (human_review, merge `edited`, review `CHANGES`, failed verify) behind a merged demo task:
  - brief order and cap;
  - pending tasks from `log.md`;
  - an unmerged task is refused;
  - nothing pending means no agent;
  - `factory wiki status`.
- `test_wiki_review.py` (t05) uses WIKI REVIEWER scripts:
  - APPROVE commits;
  - CHANGES, then APPROVE, takes two ingester attempts, the second with the findings;
  - three CHANGES mean `rejected` with nothing committed;
  - the reviewer's message has the diff tool and the source;
  - the prompt ships.
- `test_wiki_lint.py` (t06):
  - the stale pages' diffs are in the linter's message;
  - re-checked pages get `verified` set to the base;
  - a clean wiki means no agent;
  - a lint is checked, reviewed and committed;
  - the prompt ships.

### End-to-end tests

The repository configures no `e2e` gate. `test_wiki_reading.py`, `test_wiki_ingest.py`, `test_wiki_review.py` and `test_wiki_lint.py` drive the real CLI, LangChain agents and tools, and git against a bare origin and the fake `gh`, as `test_pipeline.py` does.

## Verification

- Each contract's verification commands, then `uv run pytest -q` (the unit gate).
- By hand after t06 merges: turn the wiki on and seed it in this repository, as in the prose after the contracts. Then:
  1. Run a few tasks and check, in `factory transcript <task> --role build`, that the builder got the index and its role page.
  2. Edit a cited source file and run `factory wiki check`: the page shows stale. Run `factory wiki lint` to re-verify it.
  3. `factory stats --since <wiki merge date>`: the steps table shows the new prompt versions beside the old.

## Cross-Workstream Coordination

- **Depends on:**
  - [measure](measure.md). `wiki-t01` depends on `measure-t04`, the end of that chain, because both plans change `agents.py`, `db.py`, `cli.py` and the same docs. t04's briefs read measure-t02's `merge` runs. Measure-t01's prompt version covers the wiki block, so `factory stats` compares runs with and without the wiki.
  - [strict-flow](strict-flow.md). `wiki-t01` depends on `strict-flow-t08` and `wiki-t07` on `strict-flow-t09`: that plan changes the same `agents.py`, `gates.py`, `tools.py` and docs, and the role pages should describe the loop the task crew then runs. It adds a `test` step kind, which gets a role page only if the wiki has one for it, and write tools limited to path globs, which wiki-t03's `PathGuard` change builds on.
  - [agent-flows](agent-flows.md), through measure. wiki-t02 adds its block where `LangChainRoles.step` builds each step's prompt, and picks the role page by the step's kind.
  - [pr-review-rework](pr-review-rework.md), merged. t04's briefs read the `human_review` runs from its t04.
- **Required by:** nothing planned. `factory bench` (NEXT.md item 3), when it's planned, could replay tasks with and without the wiki.

## Notes / Out of Scope

- **`factory ask`**: you query the wiki, and good answers are filed back as pages (Karpathy's query operation). Task agents already query it by reading pages. A human-facing command comes after the crew proves itself.
- **Automatic runs**: ingesting on `status --refresh` after a merge, or linting on a schedule. Revisit once manual runs show what they cost and how good the pages are.
- **Retrieval and search.** Picking pages for a task beyond the index and the role page, or a search tool (the gist mentions qmd), once the wiki outgrows its 8,000-character index.
- **The crew editing `SCHEMA.md`.** It suggests changes in its PR body, and a human makes them.
- **Web search during lint** (the gist's "data gaps"). The sandbox is offline, and the crew reads only the repository and the board.
- **Images and assets** in pages.
- **The crew's costs in `factory stats`.** They're in `wiki_runs` and `factory wiki status` for now.
- **Promoting role pages into the shipped prompts.** In the factory repository, a rule that holds for every project moves into `factory/prompts/` by hand.
- **Two boards running the crew at once.** Leased pushes make the second fail rather than overwrite. A shared claim waits for NEXT.md item 6.
- **Knowledge across repositories.** Each wiki is one repository's.
