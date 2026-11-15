# Plan: Readable PR descriptions

**Status:** Planned (2026-11-15). Workstream scoped; awaiting kickoff: t01 can run now. Roadmap: [NEXT.md item 11](../../NEXT.md#11-readable-pr-descriptions).

---

## Execution Plan

### Locked Decisions

| Decision | Choice |
|---|---|
| Who writes what a human reads first | **The verifier, in a fixed shape.** It returns a title, up to 5 "what changed" bullets and a "what to check" list that includes the reviewer findings the build left unaddressed. The factory parses and bounds it, falls back to a summary it builds itself when the verifier's can't be read, and writes the rest of the body: the merge order, a one-paragraph summary of the checks, the collapsed details and a footer |
| The long material | **The planner's hand-off leaves the PR,** since it is written for the builder; `factory show` and the web task page keep it. Each reviewer's report (its last draft only) and the gate table stay in the body, collapsed and capped, and the whole body is held under GitHub's 65,536-character limit |
| Scope | **The body, the PR title and the factory's commit subjects.** The PR title becomes the task id and the verifier's title. Commit subjects are cut at a word, with the attempt moved into the commit body, since a one-commit squash merge puts that subject on the trunk. The comments the factory posts on PRs keep their wording |
| Sequencing | **Now, alongside [measure](measure.md).** t01 waits for nothing, so `webui-t05`, which failed on a body over the limit, can run again once it merges. Whichever of this plan and `measure-t01` merges second gets a conflict the factory resolves. [strict-flow](strict-flow.md), which adds blocks to the body later, waits for this plan, and its PR-body criteria follow the new layout |

### Milestones

| # | Deliverable | Exit criteria | Parallelizable with |
|---|---|---|---|
| **M1** | Every body fits, without the plan | The t01 tests in `tests/test_prbody.py`, `tests/test_gates.py` and `tests/test_pipeline.py` pass; the existing pipeline tests pass unmodified | measure-t01 (by decision) |
| **M2** | The verifier's summary | The t02 tests pass; a run whose verifier ignores the shape still opens a PR, with the fallback | — |
| **M3** | The new layout | The t03 tests pass, and the existing pipeline tests pass unmodified | — |
| **M4** | Titles and commit subjects | The t04 tests pass; only the two tests that read the attempt from a commit subject change | — |
| **M5** | Docs | Architecture, reference, NEXT.md and the factory-ops skill describe a factory PR; `tests/test_templates.py` passes | — |

**Sequence:** `M1 → M2 → M3 → M4 → M5`. Each code task changes `factory/prbody.py` and `factory/pipeline.py`, so they run one after another.

### Task Contracts

| Milestone | Task IDs | Coverage |
|---|---|---|
| **M1** | `pr-descriptions-t01` | New `factory/prbody.py` (`clean_report`, `cap`, the limits); the plan block removed and the size bound in `factory/pipeline.py`; the optional width in `factory/gates.py`'s table; new `tests/test_prbody.py`; tests in `tests/test_gates.py` and `tests/test_pipeline.py` |
| **M2** | `pr-descriptions-t02` | `factory/prompts/verifier.md`; the reviewer reports in the verify message in `factory/agents.py`; `parse_summary`, `shorten` and `fallback_summary` in `factory/prbody.py`; What changed and What to check in `factory/pipeline.py`; `tests/fake_model.py`'s VERIFIER; tests in `tests/test_prbody.py`, `tests/test_templates.py` and `tests/test_pipeline.py` |
| **M3** | `pr-descriptions-t03` | The layout, the checks paragraph, the task block, demoted headings and the footer in `factory/prbody.py` and `factory/pipeline.py`; tests in `tests/test_prbody.py` and `tests/test_pipeline.py` |
| **M4** | `pr-descriptions-t04` | The PR title and the commit messages in `factory/pipeline.py`; tests in `tests/test_pipeline.py` |
| **M5** | `pr-descriptions-t05` | `docs/architecture.md`, `docs/reference.md`, `NEXT.md`, `factory/templates/skills/factory-ops/SKILL.md` |

```yaml
- id: pr-descriptions-t01
  goal: "A factory PR's body always fits under GitHub's limit and leaves out the planner's hand-off: each agent report in it is cleaned (no preamble, a reviewer's last draft only) and capped with a pointer to the whole text, gate details are shortened, and a body that is still too long shrinks its collapsed blocks until it fits"
  spec_refs:
    - "docs/plans/pr-descriptions.md#the-limits"
    - "docs/plans/pr-descriptions.md#cleaning-agent-reports"
    - "factory/pipeline.py"
    - "factory/gates.py"
  depends_on: []
  non_goals:
    - "Changing what the verifier is asked to write, or the body's sections and their order (pr-descriptions-t02, pr-descriptions-t03)"
    - "Changing the PR title or the commit messages (pr-descriptions-t04)"
    - "Changing what `factory show`, the transcripts, the run records or the web pages hold: they keep every report in full"
    - "Editing the shipped prompts or any documentation"
  acceptance:
    - "New factory/prbody.py holds the body's text helpers as pure functions, with no git, gh or database access. prbody.BODY_LIMIT is 60000 characters and prbody.BLOCK_LIMIT is 12000"
    - "prbody.clean_report(text, first=None) returns an agent's report without what it wrote before its first markdown heading, when it has one. When `first` is given and a line equal to it occurs more than once, it keeps the text from the last of them, which is the agent's last draft. Otherwise the report is returned stripped"
    - "prbody.cap(text, limit, pointer) returns text unchanged when it fits. Otherwise it cuts at the last line break that leaves room for the note, closes a code fence the cut left open, and ends with one line giving the characters kept, the total, and `pointer`. The result is never longer than `limit`"
    - "The PR body no longer holds the planner's plan. Each reviewer report in it is clean_report(report, '## Acceptance criteria') capped at BLOCK_LIMIT, and the verifier's report is clean_report(report) capped at BLOCK_LIMIT. The pointer names the command that prints the whole report: `factory show ID --step STEP`, ID being the task id and STEP the step's name"
    - "gates.table takes an optional width. With it, each line of each gate's detail is cut to that many characters, ending with `…` when cut; the PR body's gate table uses a width of 160. Without it the table is exactly today's, so `factory gates` and the verifier's task message are unchanged"
    - "pipeline.pr_body never returns more than BODY_LIMIT characters. When the assembled body is longer, it shrinks the collapsed reviewer blocks, longest first, to 2000 characters each; then replaces each with one line naming its `factory show` command; then, as a last resort, caps the whole body"
    - "The body ends with the line: The planner's plan and every agent's full report: `factory show ID`"
    - "A run whose reviewer's final message is 100,000 characters holding three drafts opens its PR. The body is at most BODY_LIMIT characters and holds only the last draft, cut, with the pointer, and the reviewer run's report in the database is the full message"
    - "Every existing test in tests/test_pipeline.py and tests/test_gates.py passes unmodified"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_prbody.py::test_clean_report_drops_the_preamble tests/test_prbody.py::test_clean_report_keeps_the_last_draft tests/test_prbody.py::test_cap_cuts_at_a_line_closes_a_fence_and_points_to_the_rest tests/test_prbody.py::test_cap_never_exceeds_the_limit tests/test_gates.py::test_table_can_shorten_long_details"
    - "uv run pytest -q tests/test_pipeline.py::test_a_huge_review_still_opens_a_pr_that_fits tests/test_pipeline.py::test_the_pr_body_leaves_out_the_plan"
    - "uv run pytest -q tests/test_pipeline.py tests/test_gates.py"
  risk: medium

- id: pr-descriptions-t02
  goal: "The verifier writes a short summary in a fixed shape (a title, what changed, what to check) from the gates and the reviewers' reports, and the factory parses and bounds it, or builds one from the contract, the diff and the reviewers' findings when it can't. The PR body shows it as `## What changed` and `## What to check` in place of the verifier's report"
  spec_refs:
    - "docs/plans/pr-descriptions.md#the-verifiers-summary"
    - "factory/prompts/verifier.md"
    - "factory/agents.py"
  depends_on:
    - pr-descriptions-t01
  non_goals:
    - "The rest of the layout: the checks paragraph, the task block, demoted headings and the footer (pr-descriptions-t03)"
    - "Using the title for the PR or the commits (pr-descriptions-t04): this task parses it and keeps it in the pipeline's state"
    - "Asking the verifier again when its summary can't be parsed"
    - "Changing the planner, builder or reviewer prompts, or the gates"
    - "Editing documentation"
  acceptance:
    - "factory/prompts/verifier.md asks for exactly this, with nothing before or after it: a line starting `TITLE: ` with a title of at most 72 characters saying what the change does; a `## What changed` section with 1 to 5 bullets in plain language, saying what a user or maintainer of the repository would notice and naming the main files; and a `## What to check` section with 0 to 6 bullets, each something a human should look at before merging: a decision the contract left open, risky code with path:line, a reviewer finding the build didn't address (naming the reviewer step), an assumption or a follow-up. It says not to write a preamble, gate results, acceptance evidence (the reviewers' reports hold it) or a recommendation to merge. It holds one example in the shape. It still opens with `You are the VERIFIER`, and its frontmatter model and max_steps are unchanged"
    - "The verify step's task message gains a `# Reviewer reports` section after the gates: each review step's report from this attempt, cleaned and capped as in the PR body (prbody.clean_report, prbody.cap), under a `## NAME` heading, NAME being the step's name. When there are no reviewer reports to pass, the message is exactly today's"
    - "prbody.shorten(text, limit) returns the first line of text, cut after the last whole word that fits in `limit` characters with `…` when it cut, and never longer than `limit`"
    - "prbody.parse_summary(text) returns a Summary(title, changed, check) or None. It ignores text before the first part it recognizes. It takes the title from the first line starting with `TITLE:`, and recognizes each section by a markdown heading at any level, or a line in bold, reading What changed or What to check, ignoring case and a trailing colon. A bullet is a line starting with `-`, `*` or a number followed by `.` or `)`, together with the indented lines under it. It returns None when there is no What changed bullet"
    - "A parsed summary is bounded: the title is prbody.shorten(title, 72), or empty when missing. What changed keeps at most 5 bullets and What to check at most 8, each shortened to 400 characters. Bullets past the limit are replaced by one bullet giving how many more the verifier wrote and the `factory show ID --step STEP` command that prints them"
    - "prbody.fallback_summary(task, files, reviews) builds a summary without a model. Its title is the contract's goal shortened to 72 characters. What changed is the goal shortened to 400 characters, and a bullet giving the number of files changed with up to 10 of their paths. What to check is the bulleted or numbered lines under each review report's last heading containing `Findings`, each naming its step. It is bounded as above"
    - "The pipeline uses the parsed summary when there is one, and otherwise the fallback, with a log line saying why. When the verifier's summary can't be parsed, its run's outcome is `report (fallback)` instead of `report`. A flow without a verify step uses the fallback, with no verify run, as today. The summary is kept in the pipeline's state"
    - "In the PR body, `## Verifier report` is replaced by `## What changed` and `## What to check`, rendered by the factory from the summary's bullets. An empty What to check reads `Nothing flagged.`. The verifier's whole report stays in its run record, which the body's last line points to"
    - "tests/fake_model.py's VERIFIER answers in the new shape. tests/test_pipeline.py, tests/test_flows.py and tests/test_templates.py pass unmodified apart from the tests this task adds"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_prbody.py::test_shorten_cuts_at_a_word tests/test_prbody.py::test_parse_summary_reads_the_fixed_shape tests/test_prbody.py::test_parse_summary_ignores_preamble_and_accepts_other_heading_styles tests/test_prbody.py::test_a_summary_is_bounded tests/test_prbody.py::test_fallback_summary_uses_the_goal_the_diff_and_the_findings tests/test_templates.py::test_verifier_prompt_asks_for_the_fixed_shape"
    - "uv run pytest -q tests/test_pipeline.py::test_the_verifier_sees_the_reviewer_reports tests/test_pipeline.py::test_the_pr_shows_what_changed_and_what_to_check tests/test_pipeline.py::test_an_unparseable_summary_falls_back"
    - "uv run pytest -q tests/test_pipeline.py tests/test_flows.py tests/test_templates.py"
  risk: medium

- id: pr-descriptions-t03
  goal: "A factory PR's body reads top to bottom in a fixed order: why it is stacked or was updated, what changed, what to check, one paragraph on the checks, then collapsed blocks for the gate table, the task's contract and each reviewer's report, and a footer naming the task, flow, candidate, cost and where the full reports are"
  spec_refs:
    - "docs/plans/pr-descriptions.md#the-layout"
    - "factory/pipeline.py"
  depends_on:
    - pr-descriptions-t02
  non_goals:
    - "Changing the wording of the stacked, conflicts-resolved, CI-fixed and review-addressed lines, or of the comments the factory posts on PRs"
    - "The PR title and the commit messages (pr-descriptions-t04)"
    - "Changing which gates run or what they check"
    - "Editing documentation"
  acceptance:
    - "pipeline.pr_body builds, in this order and nothing else: the stacked line, the conflicts-resolved line and the rework line, each only when it applies and worded as today; `## What changed`; `## What to check`; `## Checks`; a collapsed `Gate table` block; a collapsed `The task` block; one collapsed `Reviewer report (NAME)` block per review step in flow order, NAME being the step's name; a horizontal rule; and the footer. The opening `Factory task` line, the `Candidate` and `Flow` lines at the top and the `## Gates` heading are gone"
    - "`## Checks` is one paragraph built from the gate results, which the gates node keeps in the pipeline's state next to the table. It says how many gates passed on the candidate (its first 12 characters) after how many build attempts; for each gate that runs commands (verification, unit_tests, e2e_tests), the number of commands and the tests they ran, as the gate's output counts them; the skipped gates by name; and each review step's name with its run's outcome. For example: `All 7 gates passed on 0b8369aab1d2 after 1 build attempt. verification: 2 commands, 23 tests. unit_tests: 1 command, 269 tests. Skipped: e2e_tests. Reviewed by review: APPROVE.`"
    - "`The task` holds the contract's goal, non-goals, acceptance criteria and verification commands, as lists under those labels, capped at BLOCK_LIMIT"
    - "Inside every collapsed block, markdown headings move down two levels (`##` becomes `####`, and none goes past `######`), so an agent's headings never sit at the level of the body's own. Lines inside code fences are left alone"
    - "The footer is one `<sub>` paragraph giving: `Factory task ID from PLAN`; the Flow line worded as today (bold Flow, the flow's name in code, a colon and its steps); the Candidate line worded as today (the full candidate sha, the base branch and the base's first 12 characters); the task's recorded cost, when it has one; and the `factory show ID` pointer that t01 put on the body's last line"
    - "The size bound of pr-descriptions-t01 holds for the new layout: the reviewer blocks shrink and are replaced first, then The task block, then the gate table, then the whole body is capped"
    - "Every existing test in tests/test_pipeline.py passes unmodified"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_prbody.py::test_checks_paragraph_counts_gates_tests_and_verdicts tests/test_prbody.py::test_headings_in_collapsed_blocks_move_down tests/test_prbody.py::test_fit_shrinks_blocks_in_order tests/test_pipeline.py::test_the_pr_body_reads_in_a_fixed_order tests/test_pipeline.py::test_a_stacked_pr_body_starts_with_its_merge_order"
    - "uv run pytest -q tests/test_pipeline.py tests/test_prbody.py"
  risk: medium

- id: pr-descriptions-t04
  goal: "A new factory PR is titled with the task id and the verifier's title, and the factory's commit subjects are the task id and its goal cut at a word, with the attempt and the reason for the commit in the commit body, so a one-commit squash merge puts a readable line on the trunk"
  spec_refs:
    - "docs/plans/pr-descriptions.md#titles-and-commit-messages"
    - "factory/pipeline.py"
  depends_on:
    - pr-descriptions-t03
  non_goals:
    - "Changing an open PR's title when a resolution or a rework updates it: the title is set once, when the PR is created"
    - "Rewriting commits after the gates ran: the candidate the gates passed is the commit that is pushed"
    - "Changing the repository's merge settings on GitHub: pr-descriptions-t05 documents the recommended one"
    - "Editing documentation"
  acceptance:
    - "A new PR's title is `ID: TITLE`, ID being the task id and TITLE the summary's title from pr-descriptions-t02, or, when that is empty, the contract's goal through prbody.shorten at 72 characters. `gh pr create` gets that title"
    - "Every commit the factory makes has the subject `factory(ID): GOAL`, GOAL being the contract's goal shortened so that the whole subject is at most 72 characters, then a blank line and a body saying why it was made: `Build attempt N.` for a build, `Fix CI, attempt N.` and `Address review, attempt N.` for the two reworks, and `Rebuilt on ONTO.` for a conflict resolution, ONTO being the branch it was replayed onto. N is the attempt"
    - "The rework kinds in factory/pipeline.py give their commit body in place of today's subject suffix"
    - "tests/test_pipeline.py::test_failing_ci_is_fixed_on_the_pr_branch_then_reviewed_and_gated and tests/test_pipeline.py::test_requested_changes_are_addressed_on_the_pr_branch_then_reviewed_and_gated read the attempt from the commit body (`git log --format=%B`) instead of the subject. Every other existing test passes unmodified"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_pipeline.py::test_a_new_pr_is_titled_with_the_verifiers_title tests/test_pipeline.py::test_without_a_summary_title_the_pr_is_titled_with_the_goal tests/test_pipeline.py::test_commit_subjects_fit_and_the_attempt_is_in_the_body tests/test_pipeline.py::test_failing_ci_is_fixed_on_the_pr_branch_then_reviewed_and_gated tests/test_pipeline.py::test_requested_changes_are_addressed_on_the_pr_branch_then_reviewed_and_gated"
    - "uv run pytest -q tests/test_pipeline.py tests/test_prbody.py"
  risk: low

- id: pr-descriptions-t05
  goal: "docs/architecture.md, docs/reference.md, NEXT.md and the shipped factory-ops skill describe what a factory PR shows and in what order, where each part comes from, the limits, when the summary falls back, where the full reports are, and the merge setting that puts the PR title on the trunk"
  spec_refs:
    - "docs/plans/pr-descriptions.md#design"
  depends_on:
    - pr-descriptions-t04
  non_goals:
    - "Changing code, or tests beyond what tests/test_templates.py needs for the new template text"
    - "Editing the installed skill copies under .claude/skills or .agents/skills: `factory init --force` refreshes them"
    - "Rewriting sections unrelated to PRs, or editing README.md"
  acceptance:
    - "docs/architecture.md has a `## Pull requests` section after `## Running a plan: stacked PRs`. It gives the body's parts in order, which of them the verifier writes and which the factory writes, the limits (60,000 characters for the body, 12,000 for each collapsed block, 72 for the title, the number and length of bullets), the fallback summary and the `report (fallback)` outcome, the PR title and the commit message format, and that the planner's plan and every agent's full report are in `factory show TASK` and on the web task page"
    - "docs/architecture.md's Roles table says the verifier writes the PR's title and summary (what changed, what to check), and the handover table says it gets the gate table and the reviewers' reports"
    - "The `## Pull requests` section recommends setting the repository's squash-merge default commit message to the pull request title, so the verifier's title is what lands on the trunk, and says that otherwise a one-commit PR's squash merge uses the commit subject"
    - "docs/reference.md's Troubleshooting has rows for a verify run with outcome `report (fallback)`, and for a PR body that says a report was cut, each with what to run (`factory show TASK --step STEP`)"
    - "NEXT.md marks item 11 done in its table with a link to docs/architecture.md#pull-requests"
    - "factory/templates/skills/factory-ops/SKILL.md says how a factory PR is laid out and how to read an agent's full report"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "grep -q '^## Pull requests' docs/architecture.md"
    - "grep -q 'report (fallback)' docs/architecture.md"
    - "grep -q 'report (fallback)' docs/reference.md"
    - "grep -q 'architecture.md#pull-requests' NEXT.md"
    - "grep -q 'What to check' factory/templates/skills/factory-ops/SKILL.md"
    - "uv run pytest -q tests/test_templates.py"
  risk: low
```

Planned test additions:

| Task | Test | Kind |
|---|---|---|
| t01 | `tests/test_prbody.py` (new file): `test_clean_report_drops_the_preamble`, `test_clean_report_keeps_the_last_draft`, `test_cap_cuts_at_a_line_closes_a_fence_and_points_to_the_rest`, `test_cap_never_exceeds_the_limit`; `tests/test_gates.py::test_table_can_shorten_long_details`; `tests/test_pipeline.py`: `test_a_huge_review_still_opens_a_pr_that_fits`, `test_the_pr_body_leaves_out_the_plan` | unit, CLI end to end |
| t02 | `tests/test_prbody.py`: five tests; `tests/test_templates.py::test_verifier_prompt_asks_for_the_fixed_shape`; `tests/test_pipeline.py`: three tests | unit, CLI end to end |
| t03 | `tests/test_prbody.py`: three tests; `tests/test_pipeline.py`: two tests | unit, CLI end to end |
| t04 | `tests/test_pipeline.py`: three tests; two existing tests changed to read the commit body | CLI end to end |
| t05 | none new: `tests/test_templates.py` (existing) | regression |

Every verification filter names a test the task adds, an existing test, or an existing test file, so zero selected tests fails the gate. Every task is factory-runnable on this repository: its verification runs `uv run pytest` and `grep`, offline.

Prerequisite for running `webui-t05` again: it failed when `gh pr create` refused its 63,495-character reviewer report (GitHub's limit is 65,536 characters for the whole body). Run it after `pr-descriptions-t01` merges and the main checkout is on that commit: the factory is installed editable from the checkout, so it runs whatever code the checkout holds.

### Risks

1. **The verifier doesn't keep to the shape.** Its default model is the cheapest of the four. **Action:** the parser accepts any heading level, bold labels and numbered bullets, and skips preambles; the bounds cut what's too long; a deterministic fallback always gives a body; the `report (fallback)` outcome lets [measure](measure.md)'s `factory stats` count how often it happens; and a test parses the prompt's own example.
2. **The short summary hides what the long report showed.** **Action:** the verifier gets the reviewers' reports and is told to list the findings left unaddressed; the fallback lists every reviewer's findings; the reviewer reports, the gate table and the contract stay in the body, collapsed; and every full report stays in `factory show` and on the web task page.
3. **A cut breaks the markdown.** A cut inside a table or a code fence can swallow the rest of the body. **Action:** cuts fall at line breaks, open fences are closed, and headings inside collapsed blocks move down two levels; the t01 and t03 tests check each case.
4. **A GitHub-only reader loses the plan.** Someone without access to the board can't run `factory show`. **Action:** the contract is in the body as The task block, so the change can be judged against what was asked. Putting the plan back as a capped block is a one-line change in `pipeline.pr_body` if it's missed.
5. **A model-written title misleads.** **Action:** the task id leads it, the contract and the checks are in the body, and the human can edit the title on GitHub before merging.
6. **Conflicts with measure and strict-flow.** `measure-t01` changes `factory/agents.py` and `factory/pipeline.py` at the same time as t01 to t04, and strict-flow adds blocks to the body later. **Action:** this plan's changes sit in `pr_body`, the verify step's message and the commit messages, away from where measure records prompt versions; the factory resolves the conflict on whichever PR merges second. `strict-flow-t01` waits for `pr-descriptions-t04`, `strict-flow-t09` for `pr-descriptions-t05`, and strict-flow's PR-body criteria are written against the new layout.

---

## Problem

A factory PR is the human's approval point, and its description is hard to use. Six recent factory PRs:

| PR | Task | Change | Description | The planner's hand-off |
|---|---|---|---|---|
| #23 | `bench-t01` | +685 −1, 29 files | 27,588 characters | 55% |
| #25 | `agent-flows-t04` | +835 −113, 8 files | 18,970 | 53% |
| #26 | `agent-flows-t05` | +114 −15, 5 files | 24,925 | 65% |
| #29 | `webui-t01` | +275 −20, 4 files | 22,191 | 54% |
| #30 | `webui-t02` | +410 −3, 5 files | 32,716 | 64% |
| #34 | `webui-t04` | +505 −6, 4 files | 24,812 | 53% |

- **It can fail outright.** `webui-t05` built, passed review and every gate, then ended `failed`: `gh pr create` refused the body as longer than GitHub's 65,536 characters. Its reviewer's final message alone was 63,495 characters, holding three drafts of its report ("Actually, let me reconsider…"). `pipeline.pr_body` (`factory/pipeline.py:518`) pastes every report in whole.
- **Most of it is written for an agent.** The planner's plan, which tells the builder what to do, is collapsed at the end, and it is 53% to 65% of each description above. On this board plans average 15,166 characters, up to 28,330; reviewer reports average 12,272, up to 91,516.
- **The structure is flat.** The body's own `## Verifier report` and `## Gates` sit at the same level as the verifier's `## Summary`, `## Acceptance evidence`, `## Behavioural checks` and `## Review notes` (`factory/prompts/verifier.md:14`), so nothing shows where the verifier's part ends. Seven of the last eight verifier reports open with a sentence about the verifier itself ("All evidence collected.").
- **The evidence is there twice.** The verifier's Acceptance evidence and the reviewer's Acceptance criteria table both go through every criterion.
- **The gate table holds whole commands.** The verification row ran 359 to 726 characters on #25, #26, #30 and #34, mostly a list of test names.
- **The title and the commit subject are cut mid-word.** The title is the goal's first 70 characters (`factory/pipeline.py:471`), and the commit subject is `factory(ID): ` plus the goal's first 60 characters and `(attempt N)` (`:383`, `:84`, `:102`). A one-commit squash merge puts that subject on the trunk: `factory(webui-t04): Each task has a page at /tasks/TASK, and every task id on th (attempt 1) (#34)`.

## Goal

A human can read a factory PR from the top in a minute: what it does, what to look at, and whether the checks passed, with the evidence one click away and every full report in `factory show`. No body can be refused for its length, and a one-commit squash merge puts a readable subject on the trunk.

## Design

### The layout

`webui-t04`'s PR, as it would read:

```markdown
**Stacked** on webui-t03 (https://github.com/PaddyMc/software-factory/pull/31): merge those first. This PR shows only `webui-t04`'s changes; after they merge, `factory status --refresh` moves it onto the trunk.

## What changed
- Each task has its own page at `/tasks/TASK`: status and next step, the contract with what it waits for and what needs it, every run newest first, and the live log (`factory/web/views.py`, `factory/web/server.py`).
- Every task id on the board now links to its page.

## What to check
- On a task page the Board link in the top bar is marked as the current page (`factory/web/views.py:271`), unlike the mockup. Reviewer `review` left it as minor.
- A task id containing `/` would 404. Ids can't contain one today.

## Checks
All 7 gates passed on 0b8369aab1d2 after 1 build attempt. verification: 2 commands, 23 tests. unit_tests: 1 command, 269 tests. Reviewed by review: APPROVE.

<details><summary>Gate table</summary> … </details>
<details><summary>The task</summary> goal, non-goals, acceptance criteria, verification commands </details>
<details><summary>Reviewer report (review)</summary> … </details>

---
<sub>Factory task `webui-t04` from `docs/plans/webui.md` · **Flow** `default`: plan, build, review, gates, verify · Candidate `0b8369aab1d294b273b5ac8f4dd2d9f6cd0b1eff` on base `factory/webui-t03` (`697cb5d94f95`) · $1.39 · The planner's plan and every agent's full report: `factory show webui-t04`</sub>
```

| Part | Written by | From |
|---|---|---|
| Stacked, conflicts-resolved, rework lines | The factory | Today's wording, unchanged |
| What changed, What to check | The verifier, parsed and bounded; or the fallback | The diff, the gates, the reviewers' reports |
| Checks | The factory | The gate results, the attempts, each review run's outcome |
| Gate table | The factory | `gates.table`, details cut to 160 characters per line |
| The task | The factory | The contract |
| Reviewer report blocks | The reviewers | Each report's last draft, cleaned and capped |
| Footer | The factory | The task, plan, flow, candidate, base and cost |

The stacked, conflict and rework lines keep their wording, which tests pin and which already say plainly what happened. The footer keeps the `**Flow**` and `Candidate` wording for the same reason. So t01 to t03 change no existing test.

### The limits

| What | Limit | Over it |
|---|---|---|
| The whole body | 60,000 characters (`BODY_LIMIT`; GitHub refuses over 65,536) | Shrink the collapsed blocks, then drop them, then cap the body |
| Each collapsed block, and the verifier's report until t02 | 12,000 characters (`BLOCK_LIMIT`) | Cut at a line, with `… kept N of M characters: factory show ID --step STEP` |
| A gate detail line | 160 characters | Cut, with `…` |
| The title | 72 characters | Cut at a word, with `…` |
| What changed | 5 bullets, 400 characters each | Cut at a word; one bullet counts the rest |
| What to check | 8 bullets, 400 characters each | The same |

When the body is over the limit, the blocks go in this order: the reviewer blocks shrink to 2,000 characters each, longest first, then each is replaced by its `factory show` line; then The task block; then the gate table; then the body is capped as a whole.

### Cleaning agent reports

- **The preamble.** Text before a report's first markdown heading is dropped, when it has one: `All evidence collected. The unquote on…` goes, `## Summary` stays.
- **The last draft.** When the reviewer's template opening, `## Acceptance criteria`, occurs more than once, only the text from the last one is kept.
- **Headings inside collapsed blocks** move down two levels (t03), so the body's `##` sections stay the only top-level ones.
- The run records, transcripts, `factory show` and the web task page keep every report exactly as the agent wrote it.

### The verifier's summary

What the shipped prompt asks for:

```markdown
TITLE: Task pages at /tasks/TASK, linked from the board

## What changed
- Each task has its own page at `/tasks/TASK` … (`factory/web/views.py`)
- Every task id on the board links to its page.

## What to check
- `factory/web/views.py:271`: the Board link is marked current on task pages. Reviewer `review`, minor.
```

- **Input.** The verifier's task message keeps the gate table and gains each review step's report from the attempt, cleaned and capped. With them it can say which findings the build left alone.
- **Parsing is lenient.** A preamble is skipped. A section may be `##`, `###` or `**What changed:**`, and bullets may be `-`, `*`, `1.` or `1)`.
- **The fallback.** When there's no What changed bullet, or no verify step in the flow, the factory writes one. What changed is the goal and the files changed; What to check is every reviewer's findings; the title is the goal, shortened. The verify run's outcome is `report (fallback)`, so `factory stats` can count fallbacks once measure lands.
- **No second call.** A summary that can't be parsed falls back instead of asking the verifier again.

### Titles and commit messages

| | Today | After t04 |
|---|---|---|
| PR title | `webui-t04: Each task has a page at /tasks/TASK, and every task id on the board li` | `webui-t04: Task pages at /tasks/TASK, linked from the board` |
| Build commit | `factory(webui-t04): Each task has a page at /tasks/TASK, and every task id on th (attempt 1)` | `factory(webui-t04): Each task has a page at /tasks/TASK, and every…` + body `Build attempt 1.` |
| CI fix commit | `… (fix CI, attempt 1)` | Same subject + body `Fix CI, attempt 1.` |
| Review rework commit | `… (address review, attempt 1)` | Same subject + body `Address review, attempt 1.` |
| Conflict resolution commit | `… (on main)` | Same subject + body `Rebuilt on main.` |

The verifier's title can't be the commit subject: commits are made before the verifier runs, and rewriting one afterwards would push a commit the gates never saw. GitHub's squash merge uses a one-commit PR's commit message unless the repository's default squash commit message is set to the pull request title, so t05's docs recommend that setting.

## Files Changed

| File | Change |
|---|---|
| `factory/prbody.py` | New: `BODY_LIMIT`, `BLOCK_LIMIT`, `clean_report`, `cap` (t01); `shorten`, `Summary`, `parse_summary`, `fallback_summary` (t02); the checks paragraph, the task block, demoted headings, the size bound for the layout (t03) |
| `factory/pipeline.py` | The plan block removed and the size bound (t01); the summary in the state and in the body (t02); the layout and the gate results in the state (t03); the PR title and the commit messages (t04) |
| `factory/gates.py` | `table(gates, width=None)` (t01) |
| `factory/agents.py` | The reviewer reports in the verify step's message, through a new `Ctx.reviews` (t02) |
| `factory/prompts/verifier.md` | The fixed shape (t02) |
| `tests/fake_model.py` | VERIFIER answers in the fixed shape (t02) |
| `tests/test_prbody.py` | New (t01), grown by t02 and t03 |
| `tests/test_pipeline.py`, `tests/test_gates.py`, `tests/test_templates.py` | New tests (t01–t04); two existing tests read the commit body (t04) |
| `docs/architecture.md`, `docs/reference.md`, `NEXT.md`, `factory/templates/skills/factory-ops/SKILL.md` | t05 |
| `docs/sessions/` | Every task's session log entry |

## Test Plan

### Unit tests

`tests/test_prbody.py` (new):

- `test_clean_report_drops_the_preamble` (t01): text before the first heading goes; a report without a heading is kept.
- `test_clean_report_keeps_the_last_draft` (t01): three `## Acceptance criteria` drafts leave the last.
- `test_cap_cuts_at_a_line_closes_a_fence_and_points_to_the_rest` (t01)
- `test_cap_never_exceeds_the_limit` (t01): over a range of limits and inputs, including one long line.
- `test_shorten_cuts_at_a_word` (t02)
- `test_parse_summary_reads_the_fixed_shape` (t02)
- `test_parse_summary_ignores_preamble_and_accepts_other_heading_styles` (t02): `###`, bold labels with a colon, numbered bullets, continuation lines; no What changed gives None.
- `test_a_summary_is_bounded` (t02): a long title, ten bullets, an 800-character bullet.
- `test_fallback_summary_uses_the_goal_the_diff_and_the_findings` (t02)
- `test_checks_paragraph_counts_gates_tests_and_verdicts` (t03): passed, skipped, test counts, attempts, review outcomes.
- `test_headings_in_collapsed_blocks_move_down` (t03): `##` to `####`, `#####` to `######`, nothing inside code fences.
- `test_fit_shrinks_blocks_in_order` (t03)

`tests/test_gates.py::test_table_can_shorten_long_details` (t01): with a width, lines are cut with `…`; without one, today's table.

`tests/test_templates.py::test_verifier_prompt_asks_for_the_fixed_shape` (t02): the shipped prompt names `TITLE:`, `## What changed` and `## What to check`, and `parse_summary` reads its example.

### End-to-end tests

Through the real CLI, pipeline, agents, git, bubblewrap and fake `gh`, with `ScriptedModel`, in `tests/test_pipeline.py`:

- `test_a_huge_review_still_opens_a_pr_that_fits` (t01): a 100,000-character reviewer message with three drafts; the body fits, holds the last draft, cut, and the pointer; the run record holds it all.
- `test_the_pr_body_leaves_out_the_plan` (t01)
- `test_the_verifier_sees_the_reviewer_reports` (t02): the verify transcript's task message holds the reviewer's report under its step name.
- `test_the_pr_shows_what_changed_and_what_to_check` (t02)
- `test_an_unparseable_summary_falls_back` (t02): the outcome is `report (fallback)`, and the body has the goal, the files changed and the reviewer's findings.
- `test_the_pr_body_reads_in_a_fixed_order` (t03)
- `test_a_stacked_pr_body_starts_with_its_merge_order` (t03)
- `test_a_new_pr_is_titled_with_the_verifiers_title` (t04)
- `test_without_a_summary_title_the_pr_is_titled_with_the_goal` (t04)
- `test_commit_subjects_fit_and_the_attempt_is_in_the_body` (t04)

## Verification

- Each task's verification commands, then `uv run pytest -q` (the unit gate).
- By hand, with the main checkout on the merged commit (the factory runs the checkout's code):
  1. After t01: `factory run webui-t05` opens its PR. Check the body is under 60,000 characters (`gh pr view N --json body -q '.body | length'`).
  2. After t04: read the next three factory PRs as they open. Each should say what changed and what to check in the first screen, with no `report (fallback)` in `factory show TASK --step verify`. A fallback is worth a look at the verifier's transcript.
  3. Set the repository's squash-merge default commit message to the pull request title, then check the next merge's subject on `main`.

## Cross-Workstream Coordination

- **Depends on:** nothing. It runs alongside [measure](measure.md) by decision: `measure-t01` changes `factory/agents.py` and `factory/pipeline.py` too, and the factory resolves the conflict on whichever PR merges second.
- **Required by:**
  - [strict-flow](strict-flow.md). `strict-flow-t01` depends on `pr-descriptions-t04`, the last task here to change `factory/agents.py` and `factory/pipeline.py`, and `strict-flow-t09` on `pr-descriptions-t05`, which edits the same docs. strict-flow-t04's Acceptance tests block is a collapsed block cleaned and capped like a reviewer's, and t06's `APPROVE (unproven)` outcome shows in the Checks paragraph.
  - [webui](webui.md): `webui-t05` failed on a body over GitHub's limit and runs again after t01 (see the prerequisite above). The web task page already shows every run's full report, which the PR's footer points to.
- **Related:** [measure](measure.md). The verifier's prompt changes in t02, so its prompt version changes; `report (fallback)` is a new verify outcome for `factory stats` to count.

## Notes / Out of Scope

- **The comments the factory posts on PRs** (restacks, conflict resolutions, CI fixes, review reworks) keep their wording.
- **Asking the verifier again** when its summary can't be parsed. The fallback is free and always well-formed. Revisit if `factory stats` shows fallbacks are common.
- **A PR title that follows later changes.** The title is set when the PR opens; a rework doesn't retitle it.
- **The plan as a capped block** for readers who only have GitHub. A one-line change in `pipeline.pr_body` if it's missed.
- **Changing GitHub's merge settings from the factory.** It's a repository setting you own; the docs recommend a value.
- **Diagrams or screenshots in the body,** such as a rendered page for a web change.
