# Plan: Land factory PRs on a dev branch (land)

**Status:** Planned (2026-11-26). Workstream scoped; awaiting kickoff: `land-t01` runs once this plan is merged and synced. Roadmap: [NEXT.md item 23](../../NEXT.md#23-land-factory-prs-on-a-dev-branch).

## Plan at a Glance

**Problem:** Every factory pull request waits for you to merge it into `main`. A stack of dependent PRs (each built on top of the one before it) moves forward one merge and one refresh at a time, so finished work piles up whenever you're away.

**Goal:** When this workstream is complete, factory PRs land on a `dev` branch without you. A new merge role, the *lander*, checks each ready PR, reviews it, and either merges it into `dev` or sends it back for rework. `main` changes only when you merge one promotion PR that lists everything `dev` has added.

**In scope:** a setting that points factory PRs at `dev`; `factory land`, which finds ready PRs, checks them again, has the lander review them, and merges them; rework for held PRs; `factory promote`, which keeps the `dev` → `main` PR current; docs.

**Out of scope:** setting up GitHub branch protection (you do that by hand), merging into `main` without you, and builds started by `factory land`.

**Approach:**
1. Settings, plus a dry run that says which PRs are ready and what the others wait for.
2. The lander's review, then landing: check again, review, merge, move the next PR in the stack onto `dev`.
3. Holds go back for rework, and the promotion PR keeps `main` one merge away.

**First task:** `land-t01` — the `trunk:` and `land:` settings, since every later task reads them.

> **Reading guide:** Start here for the purpose and scope. Read **Execution Plan** for sequencing and review boundaries, **Task Contracts** for factory-executable work, and **Design** plus the remaining sections for implementation detail.

---

## Execution Plan

### Locked Decisions

| Decision | Choice |
|---|---|
| Where the merge role runs | **A `factory land` command.** One pass by default; `--watch` repeats a pass every `--poll` seconds until stopped. It doesn't depend on the [devbox](devbox.md) worker; the worker can run a pass on each poll later |
| What lands without a human | **Every ready factory PR into the trunk, except human-only ones.** A contract with `risk: high` is the human's judgment, so the lander reviews and comments on it but never merges it. So is a PR that changes `.factory/`, `.github/` or a guidance file, since those steer the factory's own later runs. Neither ever goes into the release branch |
| A HOLD | **Sends the PR back for rework**, as a human's request for changes does: the task becomes `changes_requested`, and its next run addresses the lander's findings. A task is reworked for at most `land.max_holds` holds (default 2) per fresh build; the next HOLD leaves the PR for a human |
| `dev` → `main` | **The factory keeps one promotion PR.** `factory promote` opens or updates a single PR from the trunk to the release branch, listing every task it carries. `factory land` updates it after each pass that merged something. You merge it, and that merge is the approval |
| Who merges | **The factory's own code, after the lander's verdict.** The lander has read-only tools and ends with `VERDICT: MERGE` or `VERDICT: HOLD`. The factory then merges through GitHub's API, pinned to the head commit the lander reviewed. Agents still never call `gh`, push or merge |
| Turning it on | **`trunk:` and `land:` in `.factory/config.yaml`.** `trunk:` sets the branch factory PRs target (default: the checkout's current branch, as today). Without `land:`, `factory land` and `factory promote` refuse to run. A `land.release` equal to the trunk is rejected when the config loads |
| Branch protection | **A GitHub setting you own, set up by hand.** `main` requires a pull request. `dev` requires the CI checks but no approving review, since the factory merges as the identity that opened the PR. The README gives the commands |

### Milestones

| # | Outcome | Exit criteria | Parallelizable with |
|---|---|---|---|
| **M1** | Factory PRs can target a configured trunk | The t01 tests in `tests/test_config.py`, `tests/test_pipeline.py` and `tests/test_templates.py` pass | — |
| **M2** | `factory land --dry-run` says which PRs are ready and why the others wait | The t02 tests in `tests/test_land.py` and `tests/test_ci.py` pass | M3 |
| **M3** | The lander reviews a PR head and gives a verdict | The t03 tests in `tests/test_lander.py` pass | M2 |
| **M4** | `factory land` merges ready PRs into the trunk, bottom-up through stacks | The t04 tests in `tests/test_land.py` pass, including the stack test | — |
| **M5** | A HOLD sends the PR back for rework | The t05 tests in `tests/test_land_rework.py` pass | — |
| **M6** | One promotion PR carries the trunk to the release branch | The t06 tests in `tests/test_promote.py` pass | — |
| **M7** | Docs | `tests/test_templates.py::test_the_docs_describe_landing_and_promotion` passes, and `tests/test_templates.py` passes | — |

**Sequence:** `M1 → (M2 ∥ M3) → M4 → M5 → M6 → M7`. t02 and t03 write different files: t02 changes `factory/land.py`, `factory/ci.py`, `factory/cli.py` and `tests/test_land.py`; t03 changes `factory/lander.py`, `factory/agents.py`, `factory/flows.py`, `factory/db.py`, `factory/prompts/lander.md` and `tests/test_lander.py`. From t04 on, every task changes `factory/land.py` and `factory/cli.py`, so they run in a chain.

### Task Contracts

| Milestone | Task IDs | Coverage |
|---|---|---|
| **M1** | `land-t01` | `trunk` and `land` in `factory/config.py`, and `land` as a role for `models` and `max_steps`; the default base in `cmd_run_one`, `cmd_run_plan` and `cmd_gates` in `factory/cli.py`; `factory/templates/config.yaml`; tests in `tests/test_config.py`, `tests/test_pipeline.py` and `tests/test_templates.py` |
| **M2** | `land-t02` | New `factory/land.py` (readiness); `ci.pending` in `factory/ci.py`; `factory land --dry-run` and the refusals in `factory/cli.py`; new `tests/test_land.py`, and a test in `tests/test_ci.py` |
| **M3** | `land-t03` | New `factory/prompts/lander.md` and `factory/lander.py`; the `land` role in `factory/agents.py`, `factory/flows.py` (reserved names) and `factory/db.py` (`ROLES`); new `tests/test_lander.py` |
| **M4** | `land-t04` | Gates at the head, the review, the merge, comments, the restack after a merge, `--watch` and one land per board, in `factory/land.py` and `factory/cli.py`; tests in `tests/test_land.py` |
| **M5** | `land-t05` | Holds as rework: columns in `factory/db.py`, the refresh and `_review_fix` in `factory/cli.py`, a `land` rework kind in `factory/pipeline.py`, the hold cap in `factory/land.py`; new `tests/test_land_rework.py` |
| **M6** | `land-t06` | New `factory/promote.py`; `factory promote` and the call after a landing pass in `factory/cli.py` and `factory/land.py`; new `tests/test_promote.py` |
| **M7** | `land-t07` | `docs/architecture.md`, `docs/reference.md`, `README.md`, `NEXT.md`, the AGENTS section (template and this repository's `AGENTS.md`) and the factory-ops skill (template and installed copy); a new test in `tests/test_templates.py` |

```yaml
- id: land-t01
  goal: "`trunk:` in .factory/config.yaml names the branch factory PRs build on and target, and `land:` configures landing (release branch, merge method, hold cap, required checks). `factory run TASK`, `factory run PLAN` and `factory gates` default to the trunk when it is set, and `land` is a role that `models` and `max_steps` accept"
  spec_refs:
    - "docs/plans/land.md#settings"
    - "docs/plans/land.md#branches"
    - "factory/config.py"
    - "factory/cli.py"
    - "factory/templates/config.yaml"
  depends_on: []
  non_goals:
    - "`factory land`, `factory promote` or the lander agent (land-t02 to land-t06)"
    - "Creating the dev branch or setting branch protection on GitHub"
    - "Changing this repository's .factory/config.yaml"
    - "Moving open PRs or tasks that already have a trunk recorded"
  acceptance:
    - "Config has `trunk`, a branch name or None (the default), and `land`, None by default or a LandConfig with `release` (default `main`), `method` (`squash` by default; `merge` or `rebase`), `max_holds` (integer of at least 0, default 2) and `require_checks` (boolean, default true)"
    - "Loading a config whose `land` is set without `trunk` raises ConfigError `land needs trunk: the branch factory PRs target and factory land merges into`. A `land.release` equal to `trunk` raises ConfigError `land.release must differ from trunk (BRANCH): landing would merge into the release branch unattended`, naming the branch. An unknown method raises ConfigError `land.method must be squash, merge or rebase`. A `land` key that is unknown, a `max_holds` that isn't a non-negative integer, or a `require_checks` that isn't a boolean raises a ConfigError naming the key"
    - "`land` joins the roles that `models` and `max_steps` accept, so `models: {land: openrouter:z-ai/glm-5.3}` loads, and an unknown role still raises the existing `unknown role(s)` error with `land` in its list"
    - "`factory run TASK` without `--base` builds a task with no open dependency on the configured trunk, as origin has it, and opens its PR against the trunk. It records the trunk as the task's trunk. `--base` still overrides it, and without `trunk` the checkout's current branch is used, as today. A task stacked on an open dependency keeps the dependency's trunk, as today. `factory run PLAN` gives every task it starts the same default"
    - "`factory gates TASK` without `--base` measures an unstacked task against the configured trunk instead of `main`; without `trunk` it uses `main`, as today"
    - "`factory config` shows `trunk` and `land`. factory/templates/config.yaml documents both, commented out, with one line each on what they do, and says that land.release is where the promotion PR goes and that a human merges it"
    - "A config without `trunk` and `land` behaves as today, and the existing tests pass unmodified"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_config.py::test_trunk_and_land_are_read_with_their_defaults tests/test_config.py::test_land_needs_a_trunk_that_is_not_the_release_branch tests/test_config.py::test_land_is_a_role_for_models_and_max_steps tests/test_pipeline.py::test_runs_build_on_and_target_the_configured_trunk tests/test_pipeline.py::test_gates_default_to_the_configured_trunk tests/test_templates.py::test_the_config_template_documents_trunk_and_land"
    - "uv run pytest -q tests/test_config.py tests/test_pipeline.py tests/test_templates.py tests/test_scheduler.py"
  risk: low

- id: land-t02
  goal: "`factory land --dry-run` reads the board and GitHub and prints every open factory PR of the selected plans with whether it is ready to land on the trunk, and if not, what it waits for. It changes nothing on the board or GitHub. `factory land` refuses to run without `land:` in the config"
  spec_refs:
    - "docs/plans/land.md#ready-to-land"
    - "docs/plans/land.md#a-land-pass"
    - "factory/ci.py"
    - "factory/cli.py"
    - "factory/stack.py"
  depends_on:
    - land-t01
  non_goals:
    - "Reviewing, gating or merging a PR (land-t03, land-t04)"
    - "A refresh: the dry run neither pushes restacks nor comments"
    - "Holds and their cap (land-t04, land-t05)"
    - "Showing readiness in `factory status`, `factory top` or the web page"
  acceptance:
    - "New factory/land.py has `readiness(...)`, which returns for one task either ready, `waits` with a reason (the factory will act later), or `human` with a reason (only a person can move it). It is computed from the task's board row, its contract and the PR as `gh pr view` reports it (state, mergeability, head, checks, base, changed files), with no model call"
    - "A task is ready when all of these hold: its status is pr_open; the PR is open and its base is the configured trunk; the PR's head is the task's candidate_sha; GitHub reports it MERGEABLE; and its head has at least one check, all completed, none failed. With `land.require_checks: false`, a head with no checks also counts"
    - "Otherwise the reason is the first that applies, in this order: a status other than pr_open waits with `STATUS: ` and the board's note; a PR stacked on an open dependency waits with `stacked on DEP`; a PR whose base is neither the trunk nor a factory branch is `human` with `targets BASE, not the trunk TRUNK`; a head other than the candidate is `human` with `someone else pushed to it`; UNKNOWN mergeability waits with `GitHub hasn't computed mergeability yet`; CONFLICTING waits with `conflicts with TRUNK`; pending checks wait with `CI running (N of M checks pending)`; failed checks wait with `CI failed (NAMES)`; no checks while they are required waits with `no CI checks on its head yet`"
    - "A task that is otherwise ready is `human` with `risk: high` when its contract's risk is high, and `human` with `changes PATH` when the PR changes a path under .factory/ or .github/ or a file the config's `guidance` lists, naming the first such path"
    - "New `ci.pending(rollup)` returns the checks in a statusCheckRollup that haven't completed: a check run whose status isn't COMPLETED, or a status context whose state is PENDING or EXPECTED"
    - "`factory land` takes `--dry-run`, `--plan NAME` (repeatable; default every plan) and `--no-sandbox`. `factory land --dry-run` prints one line per open factory PR of the selected plans, in plan order: the task id, `ready` or the reason (`waits: …` or `waits for a human: …`), and the PR URL. It doesn't refresh, comment, merge or call a model, and it leaves the board unchanged. With no open factory PR it prints `no open factory PRs`"
    - "Without `land:` in .factory/config.yaml, `factory land` exits 1 with `land: is not configured in .factory/config.yaml: factory land merges only into a configured trunk`. An unknown `--plan` exits 1 with `NAME is not a plan (a plan's file name without .md)`"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_land.py::test_a_pr_on_the_trunk_with_green_checks_is_ready tests/test_land.py::test_stacked_prs_wait_for_their_dependency tests/test_land.py::test_pending_failed_or_missing_checks_and_unknown_mergeability_wait tests/test_land.py::test_a_pushed_head_or_a_pr_on_another_base_waits_for_a_human tests/test_land.py::test_risk_high_and_steering_paths_wait_for_a_human tests/test_land.py::test_dry_run_prints_each_open_pr_and_changes_nothing tests/test_land.py::test_land_refuses_without_land_config tests/test_ci.py::test_pending_lists_checks_still_running"
    - "uv run pytest -q tests/test_land.py tests/test_ci.py tests/test_stack.py tests/test_reviews.py"
  risk: medium

- id: land-t03
  goal: "The lander is a new read-only agent role that reviews one factory PR at its head against the trunk and ends with `VERDICT: MERGE` or `VERDICT: HOLD`. Its prompt ships as factory/prompts/lander.md, `models.land` and `max_steps.land` configure it, and every review is recorded as a `land` run with the head it judged"
  spec_refs:
    - "docs/plans/land.md#the-lander"
    - "factory/agents.py"
    - "factory/prompts/reviewer.md"
    - "factory/prompts/selector.md"
    - "factory/flows.py"
    - "factory/db.py"
  depends_on:
    - land-t01
  non_goals:
    - "Fetching the PR, its comments or its checks from GitHub, or running gates (land-t04 passes them in)"
    - "Merging, commenting or changing a task's status (land-t04, land-t05)"
    - "A `land` step kind in flows: the lander runs only from factory land"
    - "Changing the reviewer, selector or any other role's prompt"
  acceptance:
    - "factory/prompts/lander.md ships with frontmatter `model: openrouter:z-ai/glm-5.3` and `max_steps: 40`. It tells the lander that it judges whether this PR, at this head, can go into the trunk without a human. It checks that every acceptance criterion and non-goal of the contract still holds at this head, that the PR's 'What to check' items hold, that comments asking for something are answered, and that the diff has no unrelated edits or weakened tests. It ends with exactly one line, `VERDICT: MERGE` or `VERDICT: HOLD`. Before a HOLD it lists each finding with a file and line and what to change, since the builder receives them as feedback"
    - "`land` maps to lander.md in agents.ROLE_FILES. A repository's .factory/agents/lander.md overrides it. `factory prompt land` shows the prompt in effect, and the model resolves as `--model` > `models.land` > the prompt's frontmatter > the default. `land` and `lander` are reserved step names in flows. db.ROLES includes `land`"
    - "New factory/lander.py has `message(...)`, which builds the lander's task message from what it is given: the PR's URL, title and body, the trunk, the head sha, the gate table at the head, the CI checks with their conclusions, the build reviewer's last report, the PR's conversation and inline comments (each with its author), and the lander's earlier findings on this task. A section is marked `(none)` when it has nothing"
    - "`lander.review(...)` runs the role in a given worktree at the PR head with the read tools and `git_diff` against the merge base with the trunk, and no write or run tools. It returns a decision, MERGE, HOLD or no verdict, with the report. The last VERDICT line decides. When the lander stops at its step limit without a verdict it gets one more call without tools, and a verdict still missing is asked for once more in the same conversation, as for the reviewer; still missing, the decision is no verdict"
    - "Each review is recorded as a run with role `land`, step `review`, outcome `merge`, `hold` or `no_verdict`, sha set to the head it judged, and its report, model, prompt version, tokens and cost, as other roles' runs are"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_lander.py::test_lander_prompt_matches_land_verdict_parser tests/test_lander.py::test_the_land_role_can_be_configured_overridden_and_printed tests/test_lander.py::test_the_message_holds_the_pr_gates_checks_comments_and_earlier_findings tests/test_lander.py::test_the_lander_gets_read_tools_and_the_diff_against_the_trunk_only tests/test_lander.py::test_the_last_verdict_decides_and_a_missing_one_is_asked_for_once tests/test_lander.py::test_each_review_is_recorded_as_a_land_run_on_its_head"
    - "uv run pytest -q tests/test_lander.py tests/test_templates.py tests/test_agent_loop.py tests/test_flows.py tests/test_prompt_versions.py"
  risk: medium

- id: land-t04
  goal: "`factory land` refreshes the board, then lands each ready, non-human PR. It runs the gates at the head when they haven't passed there, has the lander review it, and on MERGE merges it into the trunk through GitHub's API, pinned to the reviewed head. It then comments, records the merge and restacks the PRs that were stacked on it. A HOLD comments its findings and doesn't merge. A human-only PR gets one review comment per head. `--watch` repeats the pass until stopped"
  spec_refs:
    - "docs/plans/land.md#a-land-pass"
    - "docs/plans/land.md#ready-to-land"
    - "docs/plans/land.md#the-lander"
    - "factory/cli.py"
    - "factory/stack.py"
    - "factory/merges.py"
    - "factory/gates.py"
  depends_on:
    - land-t02
    - land-t03
  non_goals:
    - "Sending a held PR back for rework, and the hold cap (land-t05)"
    - "The promotion PR (land-t06)"
    - "Starting builds or reworks: factory land never runs factory run"
    - "Merging into any branch other than the configured trunk, or merging a PR that isn't a factory PR on the board"
    - "Approving PRs as a GitHub review, or changing branch protection"
  acceptance:
    - "A pass first runs the refresh that `factory status --refresh` runs. It then takes the selected plans' open factory PRs in plan order and judges each with land.readiness. A PR is reviewed at most once per head: when a land review run on its current head already exists, its decision stands, except that a no-verdict run is retried on the next pass, at most twice per head"
    - "For a ready PR whose head isn't the sha of the task's newest passing gates run, the pass first runs the gates at the head, in a throwaway detached worktree and against the merge base with the trunk, as `factory gates` does. It records them as a run with role `land`, step `gates`, outcome `pass` or `fail` and the head sha. Failing gates are a HOLD whose findings are the failing gates' output, with no model call"
    - "The lander reviews the PR (land-t03) in a throwaway worktree at the head. Its message holds the PR's title and body, the gate table at the head, the checks, the build reviewer's last report, the PR's conversation and inline comments read through gh api, and the lander's earlier findings on the task. Both worktrees are removed afterwards"
    - "On MERGE, factory land calls `gh api -X PUT repos/{owner}/{repo}/pulls/NUMBER/merge` with merge_method set to land.method and sha set to the reviewed head. On success it posts a PR comment that starts `Landed on TRUNK by factory land` and includes the lander's report, capped. It records a run with role `land`, step `merge`, outcome `merged` and the head sha. It then runs the refresh again, which marks the task merged, records its merge record and restacks the PRs stacked on it onto the trunk. When GitHub refuses the merge, the pass logs GitHub's message, changes no status, and on a later pass merges the same head again without a new review"
    - "On HOLD, factory land posts a PR comment that starts `The lander holds this PR at SHA` with the findings, and leaves the PR open with its status unchanged and a board note saying the lander holds it. In this task, a held head is not reviewed or merged again; land-t05 sends it back for rework"
    - "A PR that is `human` for `risk: high` or a steering path is reviewed once per head like any other, and the lander's report is posted as a comment that starts `factory land won't merge this PR (REASON): a human merges it`. It is never merged. Other `human` and `waits` PRs are logged with their reason only when the reason changes"
    - "Without `--dry-run`, factory land never merges a PR whose base isn't the configured trunk, and never merges into land.release, even when a PR targets it"
    - "`factory land --watch [--poll SECONDS]` (default 120) repeats the pass until it gets SIGTERM or Ctrl-C, logging one timestamped line per event. A review in progress when it stops is recorded as stopped, and nothing is merged. Only one factory land at a time runs on a board: a second exits 1 with `factory land is already running on this board (pid PID)`. A pid file in $FACTORY_HOME records the running one and is removed on exit"
    - "`factory land` also takes `--model`, which overrides the lander's model, and exits 0 after a pass (or after --watch stops) unless it was refused"
    - "An end-to-end test runs factory land on a real git repository with the fake gh and a scripted lander over a stack of two PRs. It merges the bottom PR, restacks the top one onto the trunk, and merges the top one on a later pass once its checks pass"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_land.py::test_land_merges_a_ready_pr_at_the_reviewed_head tests/test_land.py::test_a_head_without_passing_gates_is_gated_first_and_failing_gates_hold_it tests/test_land.py::test_a_hold_comments_its_findings_and_does_not_merge tests/test_land.py::test_each_head_is_reviewed_once tests/test_land.py::test_a_merge_github_refuses_is_retried_without_a_new_review tests/test_land.py::test_human_only_prs_get_one_comment_per_head_and_are_never_merged tests/test_land.py::test_land_never_merges_off_the_trunk tests/test_land.py::test_watch_repeats_the_pass_and_one_land_runs_per_board tests/test_land.py::test_land_takes_a_stack_to_the_trunk_bottom_up"
    - "uv run pytest -q tests/test_land.py tests/test_lander.py tests/test_stack.py tests/test_merges.py tests/test_gates.py"
  risk: high

- id: land-t05
  goal: "A HOLD sends the PR back for rework, as a human's request for changes does. The task becomes changes_requested, refresh keeps it there, and its next `factory run` has the builder address the lander's findings on the PR's branch. After land.max_holds holds since the task's last fresh build, the next HOLD leaves the PR for a human instead"
  spec_refs:
    - "docs/plans/land.md#holds-and-rework"
    - "docs/plans/pr-review-rework.md"
    - "factory/cli.py"
    - "factory/pipeline.py"
    - "factory/db.py"
    - "factory/reviews.py"
  depends_on:
    - land-t04
  non_goals:
    - "factory land starting the rework itself: a plan run, factory run TASK or the devbox worker runs it"
    - "Posting the lander's findings as a GitHub review"
    - "Changing how human reviews are counted"
    - "The promotion PR (land-t06)"
  acceptance:
    - "The tasks table gains `land_hold` (the id of the newest land review or gates run that held the task and hasn't been addressed) and `land_holds` (how many holds since the task's last fresh build), added to older databases by the existing migrations"
    - "When the lander, or failing gates at the head, holds a PR and the task's land_holds is below land.max_holds, factory land sets status changes_requested, land_hold to that run and land_holds one higher. The note is `the lander holds it at SHA: factory run TASK addresses it`. It also posts the hold comment of land-t04"
    - "When land_holds has reached land.max_holds, a HOLD instead leaves the task pr_open with the note `held N times by the lander: merge it, close it, or factory run TASK --force to rebuild` and posts the same text as a comment. factory land readiness then reports it as `human` with `held N times by the lander` until the task is built from scratch"
    - "The refresh treats an unaddressed land_hold as a request for changes. A changes_requested task with one stays changes_requested even when no GitHub review requests changes. When someone else pushes to the PR, land_hold is cleared with the same note as for reviews"
    - "`factory run TASK` on a changes_requested task with an unaddressed land_hold reworks the PR's branch at its candidate. The builder's feedback holds the lander's findings from that run's report, followed by any unaddressed human review requests. The rework uses a new `land` rework kind, whose log line, commit body, PR comment and failure note name the lander. When the rework updates the PR, land_hold is cleared and land_holds is kept. factory land then reviews the new head on a later pass"
    - "A fresh build (a task run from queued or failed, or with --force) resets land_holds to 0 and clears land_hold"
    - "A plan run and the scheduler start a held task like any changes_requested task"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_land_rework.py::test_a_hold_marks_the_task_changes_requested_with_the_landers_note tests/test_land_rework.py::test_refresh_keeps_an_unaddressed_hold tests/test_land_rework.py::test_the_rework_feedback_holds_the_landers_findings_and_human_requests tests/test_land_rework.py::test_a_rework_clears_the_hold_and_land_reviews_the_new_head tests/test_land_rework.py::test_after_max_holds_the_pr_waits_for_a_human tests/test_land_rework.py::test_a_fresh_build_resets_the_hold_count tests/test_land_rework.py::test_a_plan_run_starts_a_held_task"
    - "uv run pytest -q tests/test_land_rework.py tests/test_land.py tests/test_reviews.py tests/test_ci.py tests/test_scheduler.py tests/test_db.py tests/test_pipeline.py"
  risk: medium

- id: land-t06
  goal: "`factory promote` opens or updates one PR from the trunk to land.release. It lists, by plan, every task that landed on the trunk but isn't on the release branch yet, plus the trunk's other commits. `factory land` runs it after every pass that merged a PR, so the human merge into the release branch is always one PR away"
  spec_refs:
    - "docs/plans/land.md#promotion"
    - "factory/cli.py"
    - "factory/stack.py"
    - "factory/prbody.py"
  depends_on:
    - land-t05
  non_goals:
    - "Merging the promotion PR, or merging anything into the release branch"
    - "Merging the release branch back into the trunk: promote only reports when it is needed"
    - "Tags, releases or changelog files"
    - "Showing promotion in `factory status`, `factory top` or the web page"
  acceptance:
    - "New factory/promote.py finds the tasks to promote: board tasks that are merged and whose PR's merge commit (GitHub's mergeCommit, read in one gh pr list call) is on origin/TRUNK and not an ancestor of origin/RELEASE, oldest merge first. It also finds the trunk's other commits: those in RELEASE..TRUNK that are no task's merge commit"
    - "`factory promote` fetches both branches. With tasks or other commits to promote, it opens a PR with head the trunk and base land.release, titled `Promote TRUNK to RELEASE: N tasks`. When an open PR with that head and base exists, it updates that PR's title and body through the REST API instead, so there is only ever one. It prints the PR URL"
    - "The body groups the tasks by plan. Each line gives the task id, the first sentence of its goal, its PR link, its contract's risk, and whether it was landed by factory land (a land run with outcome merged) or merged by a human. A task whose merge record is `edited` is marked so. Other commits are listed by subject under `Other commits`. The body ends with `Merge this PR with a merge commit, not a squash or rebase, so TRUNK and RELEASE keep one history.`"
    - "When origin/RELEASE has commits that origin/TRUNK lacks, promote prints, and puts at the top of the body, `RELEASE has N commits TRUNK lacks: merge RELEASE into TRUNK so the promotion stays a clean merge`"
    - "With nothing to promote it prints `nothing to promote: RELEASE has everything on TRUNK`, exits 0 and opens nothing. `factory promote --dry-run` prints the title and body it would write and changes nothing on GitHub. Without land: configured it exits 1 with the message factory land gives"
    - "After a factory land pass that merged at least one PR, factory land runs promote and logs the promotion PR's URL. A promote failure is logged and doesn't stop the pass or --watch"
    - "The promotion PR's head is the trunk, not a factory/ branch, so refresh and adoption ignore it"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_promote.py::test_promote_opens_one_pr_listing_the_tasks_the_release_branch_lacks tests/test_promote.py::test_promote_updates_the_open_promotion_pr tests/test_promote.py::test_the_body_says_how_each_task_landed_and_lists_other_commits tests/test_promote.py::test_release_commits_missing_from_the_trunk_are_reported tests/test_promote.py::test_nothing_to_promote_opens_nothing tests/test_promote.py::test_dry_run_prints_the_pr_and_changes_nothing tests/test_promote.py::test_land_updates_the_promotion_pr_after_a_merge tests/test_promote.py::test_promote_refuses_without_land_config"
    - "uv run pytest -q tests/test_promote.py tests/test_land.py tests/test_prbody.py tests/test_stack.py"
  risk: medium

- id: land-t07
  goal: "The docs describe the trunk and release branches, the lander, factory land, holds and factory promote. The policy says the factory merges into the trunk and a human merges into the release branch. The README says how to set up a dev branch with its branch protection, and NEXT.md marks item 23 done"
  spec_refs:
    - "docs/plans/land.md#branches"
    - "docs/plans/land.md#turning-it-on-here"
    - "docs/architecture.md"
    - "docs/reference.md"
    - "README.md"
    - "NEXT.md"
    - "factory/templates/agents-section.md"
    - "factory/templates/skills/factory-ops/SKILL.md"
  depends_on:
    - land-t06
  non_goals:
    - "Changing behaviour"
    - "Changing this repository's .factory/config.yaml, creating the dev branch or changing branch protection"
    - "The factory specification chapters in docs/spec/"
  acceptance:
    - "docs/architecture.md's Policy says that merging into the release branch is the human approval, and that with land: configured the factory's own code merges a factory PR into the trunk after the lander's MERGE, pinned to the reviewed head. It also says agents still never merge, push or call gh. A new section headed `## Landing on the trunk` covers the branches, readiness and its reasons, human-only PRs, gates at the head, the lander's review, the merge, holds and their cap, `--watch`, one land per board, and the promotion PR. The Roles table has a lander row. The known limitation `Restacked PRs aren't re-gated` says that factory land gates a head before landing it"
    - "docs/reference.md describes `trunk` and `land` with the other config keys, lists `factory land` and `factory promote` with every flag and default, lists `land` in the roles for models and max_steps, and has troubleshooting rows for `land: is not configured`, `land.release must differ from trunk`, `factory land is already running on this board`, `held N times by the lander` and the RELEASE-has-commits warning"
    - "README.md has a section headed `## Land on a dev branch`. It covers creating the branch (`git push origin main:dev`), the `trunk:` and `land:` settings, keeping the checkout on the trunk, and the branch protection: main requires a pull request and the CI checks; dev requires the CI checks and no approving review. It gives the gh api commands for both. It also covers running `factory land --watch`, merging the promotion PR with a merge commit, and running factory land with GH_TOKEN for a separate GitHub identity"
    - "NEXT.md's item 23 row and section say landing is done and link docs/architecture.md#landing-on-the-trunk"
    - "factory/templates/agents-section.md and the Software factory section of this repository's AGENTS.md, which stay identical, say that with land: configured `factory land` merges ready PRs into the trunk and that merging the promotion PR is the human approval"
    - "The factory-ops skill has request rows for landing ready PRs (`factory land`, `--watch`, `--dry-run`), why a PR isn't landing, a held PR, and promoting the trunk (`factory promote`). They are in factory/templates/skills/factory-ops/SKILL.md and .claude/skills/factory-ops/SKILL.md, which stay identical"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_templates.py::test_the_docs_describe_landing_and_promotion"
    - "uv run pytest -q tests/test_templates.py"
  risk: low
```

Planned test additions, all new:
- **`land-t01`:** `test_trunk_and_land_are_read_with_their_defaults`, `test_land_needs_a_trunk_that_is_not_the_release_branch` and `test_land_is_a_role_for_models_and_max_steps` in `tests/test_config.py`; `test_runs_build_on_and_target_the_configured_trunk` and `test_gates_default_to_the_configured_trunk` in `tests/test_pipeline.py`; `tests/test_templates.py::test_the_config_template_documents_trunk_and_land`.
- **`land-t02`:** a new `tests/test_land.py` with seven tests, plus `tests/test_ci.py::test_pending_lists_checks_still_running`.
- **`land-t03`:** a new `tests/test_lander.py` with six tests.
- **`land-t04`:** nine tests added to `tests/test_land.py`, including the end-to-end `test_land_takes_a_stack_to_the_trunk_bottom_up`.
- **`land-t05`:** a new `tests/test_land_rework.py` with seven tests.
- **`land-t06`:** a new `tests/test_promote.py` with eight tests.
- **`land-t07`:** `tests/test_templates.py::test_the_docs_describe_landing_and_promotion`.

Every contract names at least one test that doesn't exist yet, so each fits this repository's `strict` flow. The tests drive `gh` through the `fake_gh` fixture in `tests/conftest.py`, which t02, t04 and t06 extend for the calls they add: pull request files, issue comments, the merge call and `mergeCommit`. Each verification filter must select its tests; zero matching tests is not a pass.

These tasks change the factory itself and run on this repository's own board, as earlier factory plans did. They land through human merges into `main`. This repository switches to a dev branch only after land-t07, by hand (see [Turning it on here](#turning-it-on-here)).

### Risks

1. **An unattended merge the human would have refused.** The lander is one model's judgment, and a merge into the trunk feeds every later task built on it. **Action:** the gates must pass at the exact head, CI must be green, and the merge is pinned to the reviewed sha. `risk: high` contracts and changes to `.factory/`, `.github/` or guidance files wait for a human. The release branch moves only by a human merge of the promotion PR, which lists how each task landed.
2. **The factory weakens its own checks through the trunk.** Settings and guidance come from the main checkout, which sits on the trunk once landing is on. So a landed change to `.factory/config.yaml`, CI or `AGENTS.md` would steer every later run. **Action:** those paths are human-only in land-t02. When [security-review](security-review.md)'s `guarded_paths` lands, its list can replace this one (see Notes).
3. **Builder and lander loop on the same PR.** A HOLD sends the PR back, the rework is reviewed again, and it can be held again. **Action:** `land.max_holds` (default 2) caps reworks per fresh build, after which the PR waits for a human. Each head is reviewed once, and a missing verdict is retried at most twice per head.
4. **Squash merges split the trunk from the release branch.** A promotion PR merged with a squash gives `main` a commit that `dev` lacks, and every later promotion conflicts. **Action:** the promotion PR's body says to use a merge commit, and promote reports when the release branch has commits the trunk lacks. The README tells you to allow merge commits on `main`.
5. **Mixed trunks while switching.** PRs opened before the switch target `main` and keep `main` as their trunk, and a task stacked on one inherits it. **Action:** `factory land` never merges a PR off the configured trunk, and dry-run lists it as `targets main, not the trunk dev`. Switch when no stacks are open, or merge those PRs by hand.
6. **Races with GitHub and with other runs.** A push, a restack or a conflict can land between the review and the merge. **Action:** the merge call carries `sha=`, so GitHub refuses a head that moved. One land runs per board, and a task in a run isn't `pr_open`, so land skips it.
7. **Spend.** Each review is a model call that `--watch` makes unattended. **Action:** the lander runs only on ready heads (CI green, gates passed), once per head, with `max_steps: 40`. Its runs carry cost like every role, so `factory stats` and `factory show` count them.

---

## Background and Evidence

- **The trunk is whatever branch a run starts on.** `cmd_run_one` sets `trunk = a.base or git rev-parse --abbrev-ref HEAD` (`factory/cli.py:239`), and records it on the task. Restacks and the stranded-PR check use `row["trunk"] or "main"` (`factory/stack.py`, `factory/cli.py:491`). No config key sets it, and `factory gates` defaults to `main` (`factory/cli.py:828`).
- **Only humans merge.** The Policy in `docs/architecture.md` says "Merging is the approval. Agents never merge, push, commit to your checkout, or see secrets". After a merge, `_refresh` marks the task merged (`_merged`), records what changed after the factory's candidate (`factory/merges.py`), and restacks the PRs stacked on it (`stack.restack`).
- **Refresh already reads every signal a merge needs, one at a time.** `_pr_state` (`factory/cli.py`) returns state, mergeability, head and checks; `ci.red` finds failed checks on the factory's own head; `reviews.requests` finds unaddressed review requests; a head other than `candidate_sha` means someone else pushed. Nothing combines them into "ready to merge", and nothing reads pending checks.
- **Restacked heads aren't re-gated.** The architecture's known limitations say so: after a rebase, only CI checks the new head. Gate runs are recorded as role `verify`, step `gates`, with outcome `pass`/`fail` and the sha they ran on (`factory/pipeline.py:735`). So the newest passing gates sha tells whether a head was gated. `factory gates TASK --ref` (`cmd_gates`) already runs the gates on any commit in a throwaway worktree.
- **Roles outside a flow exist.** The selector ships as `factory/prompts/selector.md`, maps in `agents.ROLE_FILES`, is configured with `models.select`, and runs through `LangChainRoles.step(flows.Step("select", "select"), …)`. The lander follows the same pattern. The run role `merge` is taken by merge records (`db.ROLES`), so the new role is `land`.
- **Reworks have one entry point.** `cmd_run_one` handles `changes_requested` through `_review_fix`, which builds a `Rework` whose kind (`factory/pipeline.py` `KINDS`: `ci`, `human_review`) supplies the log line, commit body, PR comment and failure note. The scheduler already starts `changes_requested` tasks (`factory/scheduler.py:63`).
- **The repository today.** There is no `dev` branch on origin, and `main` has no branch protection (`gh api …/branches/main/protection` returns 404). CI runs on every `pull_request` and on pushes to `main` (`.github/workflows/ci.yml`), so PRs into `dev` get checks.

## Design

### Branches

```text
factory/<task> ──PR──► dev (trunk) ──── promotion PR ────► main (release)
                   │                                    │
          factory land merges ready PRs        a human merges it: the approval
          (lander MERGE, gates, CI green)      (with a merge commit)
```

- **Trunk:** the branch factory PRs target and stacks end on. `trunk:` sets it; without it, today's rule applies.
- **Release branch:** `land.release`, where the promotion PR goes. Only a human merges into it.
- Plan PRs, hand-done work and anything not on a `factory/<task>` branch are never landed. They reach the trunk by a human merge, and the promotion PR lists them under *Other commits*.

### Settings

```yaml
trunk: dev                  # factory PRs build on and target this branch (default: the checkout's branch)
land:                       # factory land and factory promote; absent, neither runs
  release: main             # the promotion PR's base; only a human merges into it
  method: squash            # how factory land merges into the trunk: squash | merge | rebase
  max_holds: 2              # HOLDs sent back for rework per fresh build; the next one waits for a human
  require_checks: true      # a head needs at least one finished, passing CI check
models:
  land: openrouter:z-ai/glm-5.3
```

### Ready to land

A pass judges each open factory PR of the selected plans with no model call, in this order:

| Check | Not met |
|---|---|
| Task is `pr_open` | waits: `STATUS: note` (conflict, ci_failed, changes_requested… are fixed by a run) |
| Not stacked on an open dependency | waits: `stacked on DEP` |
| PR base is the trunk | human: `targets BASE, not the trunk TRUNK` |
| PR head is the factory's candidate | human: `someone else pushed to it` |
| GitHub says MERGEABLE | waits: `GitHub hasn't computed mergeability yet` / `conflicts with TRUNK` |
| Checks on the head: at least one, all finished, none failed | waits: `CI running (N of M checks pending)` / `CI failed (NAMES)` / `no CI checks on its head yet` |
| Contract risk isn't high | human: `risk: high` (reviewed and commented, never merged) |
| No change under `.factory/`, `.github/` or a guidance file | human: `changes PATH` (reviewed and commented, never merged) |
| Fewer than `max_holds` holds (t05) | human: `held N times by the lander` |

```text
$ factory land --dry-run
land-t02   ready                                              https://github.com/o/r/pull/120
land-t03   waits: stacked on land-t02                         https://github.com/o/r/pull/121
evals-t04  waits: CI running (2 of 3 checks pending)          https://github.com/o/r/pull/118
steer-t02  waits for a human: risk: high                      https://github.com/o/r/pull/119
```

### The lander

- **Input** (`lander.message`): the contract (in the system prompt, as for every role), then the PR's URL, title and body (the verifier's *What changed* and *What to check*), the trunk and head, the gate table at the head, the CI checks, the build reviewer's last report, the PR's conversation and inline comments with their authors, and its own earlier findings on the task.
- **Tools:** read tools on a throwaway worktree at the head, and `git_diff` against the merge base with the trunk. No write or `run` tools.
- **Judgement:** whether this head can go into the trunk without a human. Every acceptance criterion and non-goal still holds after restacks and reworks. *What to check* holds. Comments asking for something are answered. There are no unrelated edits and no weakened or deleted tests.
- **Output:** a report ending in `VERDICT: MERGE` or `VERDICT: HOLD`. A HOLD lists its findings as `file:line: what to change`, since they become the builder's feedback. A missing verdict is handled as for the reviewer (a call without tools, then one more ask), and is then "no verdict".
- **Records:** a `land` run, step `review`, outcome `merge`/`hold`/`no_verdict`, `sha` = the head, with cost and tokens.

### A land pass

```text
factory land [--plan P]... [--watch [--poll 120]] [--dry-run] [--model M] [--no-sandbox]
  │
  ├─ refuse: no land: in config · another factory land on this board (pid file)
  │
  └─ pass ───────────────────────────────────────────────────────────────────────────┐
       refresh (as status --refresh: merges, CI, reviews, conflicts, restack)        │
       for each open factory PR, in plan order:                                      │
         readiness ── waits / human (no review needed) ──► log reason if changed     │
            │ ready, or human-only and not yet reviewed on this head                 │
         a land decision on this head already? ── MERGE: merge again · HOLD: skip    │
         head ≠ newest passing gates sha ──► gates at head ── fail ──► HOLD          │
         lander review ── no verdict ──► retry next pass (≤ 2 per head)             │
            │ HOLD ──► comment findings (t05: changes_requested, or a human at cap)  │
            │ MERGE, human-only ──► comment "a human merges it"                      │
            │ MERGE ──► PUT pulls/N/merge (method, sha=head) ── refused ──► log      │
            │             └─► comment · land run merged · refresh (mark merged,      │
            │                 record the merge, restack dependents onto the trunk)   │
       merged anything? ──► factory promote (t06)                                    │
     --watch: sleep --poll, repeat ──────────────────────────────────────────────────┘
```

A stack lands bottom-up across passes. The bottom PR merges, and the refresh after it rebases the next PR onto the trunk and retargets it. CI then runs on that new head, which is a new candidate the gates haven't seen. A later pass finds the checks green, gates the head, reviews it and merges it.

### Holds and rework

```text
HOLD on head H (lander, or failing gates at H)
  ├─ land_holds < max_holds ─► status changes_requested · land_hold = run · land_holds += 1
  │                             comment the findings
  │                             next factory run TASK (plan run, worker) ─► Rework(kind="land")
  │                               feedback: the findings (+ any human review requests)
  │                               review + gates + push ─► land_hold cleared ─► new head H'
  │                             factory land reviews H' once its CI is green
  └─ land_holds = max_holds ─► stays pr_open · note + comment "held N times by the lander: merge it,
                                close it, or factory run TASK --force to rebuild" · readiness: human
```

A HOLD isn't posted as a GitHub review. The factory opens PRs as you, and the refresh counts any review by the PR's author as a request for changes (`factory/reviews.py`), so the hold lives on the board instead. The refresh treats an unaddressed `land_hold` like an unaddressed review request.

### Promotion

```text
$ factory promote
https://github.com/o/r/pull/130   Promote dev to main: 5 tasks
```

The body of PR #130:

```markdown
## land
- `land-t02` — `factory land --dry-run` reads the board and GitHub… — #120 · risk medium · landed by factory land
- `land-t03` — The lander is a new read-only agent role… — #121 · risk medium · merged by a human · edited before merge
## steer
- `steer-t02` — … — #119 · risk high · merged by a human

### Other commits
- Plan: web and local tools for agents (web-tools) (#85)

Merge this PR with a merge commit, not a squash or rebase, so dev and main keep one history.
```

A task is on the release branch when its PR's merge commit is an ancestor of `origin/RELEASE`, so tasks merged before landing was switched on count as promoted. `factory land` runs promote after every pass that merged something, so the PR is current whenever you look.

### Turning it on here

This is done by hand once land-t07 has merged into `main`, and is not a contract:

1. `git push origin main:dev`.
2. Branch protection (README section): `main` requires a pull request and the `ci` checks, and allows merge commits. `dev` requires the `ci` checks and no approving review.
3. In `.factory/config.yaml` on `dev`, add `trunk: dev`, the `land:` block and `models.land`. Merge `dev` into `main` once so both branches carry them, and switch the main checkout to `dev`.
4. Let the open stacks that target `main` finish, or merge them by hand. Then run `factory land --watch` (or `--dry-run` first).

## Files Changed

| File | Change |
|---|---|
| `factory/config.py` | `trunk`, `LandConfig` and their validation; `land` in `ROLES` (t01) |
| `factory/cli.py` | Default base from `trunk` (t01); `factory land` (t02, t04); holds in `_refresh`, `_review_fix` and `cmd_run_one` (t05); `factory promote` (t06) |
| `factory/templates/config.yaml` | Commented `trunk:` and `land:` (t01) |
| `factory/land.py` | New: readiness (t02); the pass, gates at the head, the merge, comments, `--watch`, the pid file (t04); the hold cap (t05); calling promote (t06) |
| `factory/ci.py` | `pending` (t02) |
| `factory/prompts/lander.md` | New lander prompt (t03) |
| `factory/lander.py` | New: the lander's message, review and run record (t03) |
| `factory/agents.py` | `land` in `ROLE_FILES`, the `MERGE`/`HOLD` verdict and the `land` kit (t03) |
| `factory/flows.py` | `land` and `lander` reserved (t03) |
| `factory/db.py` | `land` in `ROLES` (t03); `land_hold` and `land_holds` columns (t05) |
| `factory/pipeline.py` | The `land` rework kind (t05) |
| `factory/promote.py` | New: tasks to promote, the PR body, open or update (t06) |
| `tests/conftest.py` | `fake_gh` learns PR files, issue comments, the merge call and `mergeCommit` (t02, t04, t06) |
| `tests/test_land.py`, `tests/test_lander.py`, `tests/test_land_rework.py`, `tests/test_promote.py` | New tests (t02–t06) |
| `tests/test_config.py`, `tests/test_pipeline.py`, `tests/test_ci.py`, `tests/test_templates.py` | New tests (t01, t02, t07) |
| `docs/architecture.md`, `docs/reference.md`, `README.md`, `NEXT.md`, `AGENTS.md`, `factory/templates/agents-section.md`, factory-ops skill (template and installed copy) | Docs (t07) |

## Test Plan

### Unit tests

- **t01:** `trunk`/`land` defaults and every validation message; `land` accepted in `models` and `max_steps`; a run without `--base` builds on and targets `trunk`, and `--base` wins; `factory gates` measures against `trunk`; the config template mentions both.
- **t02:** each readiness rule and its exact reason. Ready on green checks. Stacked waits. Pending, failed or missing checks and UNKNOWN mergeability wait. A pushed head or a PR on another base is human. `risk: high` and `.factory/`/`.github/`/guidance paths are human. `--dry-run` prints one line per PR and leaves the board and fake gh state unchanged. Refused without `land:`. Also `ci.pending` for check runs and status contexts.
- **t03:** the prompt's last line matches the parser. `models.land`, the override and `factory prompt land`. The message carries each input and `(none)` for empty ones. The kit has read tools and `git_diff` only. The last verdict wins and a missing one is asked for once. The run record has role `land`, step `review` and the head sha.
- **t04:** merge at the reviewed head with `sha=` and the method. A head without passing gates is gated first, and failing gates hold it. A HOLD comments and doesn't merge. One review per head. A refused merge is retried without a new review. Human-only PRs get one comment per head and are never merged. Never off the trunk or into the release branch. `--watch` repeats the pass, and a second land is refused.
- **t05:** a hold sets `changes_requested`, `land_hold` and `land_holds`. Refresh keeps it. The rework feedback carries the findings and human requests. A rework clears the hold and the new head is reviewed. The cap leaves it for a human. A fresh build resets the count. A plan run starts held tasks.
- **t06:** one PR opened, then updated. The body lists tasks by plan, how each landed, edited merges and other commits. Release-only commits are reported. Nothing to promote opens nothing. `--dry-run` changes nothing. Land calls promote after a merge. Refused without `land:`.

### End-to-end tests

- **t04:** `tests/test_land.py::test_land_takes_a_stack_to_the_trunk_bottom_up` runs the real `factory land` entry point on a real git repository with a `dev` trunk. It uses the fake `gh` and a scripted lander over two stacked task PRs. Pass 1 merges the bottom PR and restacks the top one onto `dev`. With the top PR's checks pending, pass 2 waits. Once they are green, pass 3 gates the restacked head, reviews it and merges it. The board ends with both tasks merged, and the merge calls carry the reviewed shas.

## Verification

```bash
uv run pytest -q tests/test_land.py tests/test_lander.py tests/test_land_rework.py tests/test_promote.py
uv run pytest -q
```

By hand, after [Turning it on here](#turning-it-on-here): `factory land --dry-run` lists the open PRs with reasons; `factory land` merges a ready low-risk PR into `dev` and the promotion PR to `main` lists it; a `risk: high` PR gets the lander's comment and stays open.

## Cross-Workstream Coordination

- **Depends on:** none. `land-t01` can run once this plan is merged and synced.
- **Required by:** none.
- **Related:**
  - [devbox](devbox.md): its worker starts `changes_requested` tasks, so it picks up the lander's holds. Its checkout updater (devbox-t04) fast-forwards the trunk, which is `trunk:` once land-t01 has merged. Running a land pass on each worker poll is deferred (Notes).
  - [security-review](security-review.md): its `guarded_paths` gate covers the same steering files that land-t02 makes human-only. When it lands, the two lists should become one (Notes).
  - [pr-review-rework](pr-review-rework.md) (done): land-t05 reuses its `changes_requested` rework path and leaves how human reviews are counted unchanged.
- **Overlaps, with no ordering:** `devbox-t01`, `devbox-t02`, `steer-t01` and `security-review-t06` change `factory/cli.py`; `devbox-t01` and `security-review-t02` change `factory/config.py`; `steer-t01` and `devbox-t02` change `factory/db.py`; flow-tuning and security-review tasks change `factory/agents.py` and `factory/pipeline.py`. The factory's conflict resolution handles these, as it did for earlier plans.

## Notes / Out of Scope

- **A land pass inside the devbox worker.** `factory start` could run one pass per poll once both plans have landed; until then, run `factory land --watch` beside it.
- **Starting reworks from `factory land`.** It reviews and merges only; a plan run, `factory run TASK` or the worker builds the rework.
- **One list of steering paths.** land-t02 hard-codes `.factory/`, `.github/` and the guidance files. Replacing them with security-review's `guarded_paths` (and its rule that a contract naming a path authorises it) is a follow-up once that plan lands.
- **Readiness on the board.** `factory status`, `factory top` and the web page don't show readiness or the promotion PR; `factory land --dry-run` and `factory promote --dry-run` do.
- **`factory stats` for landing.** Land runs carry cost and outcomes, but stats doesn't yet report land merge and hold rates.
- **The specification chapters** (`docs/spec/`) aren't updated here; [factory-spec](factory-spec.md) owns them.
- **Merging into the release branch unattended, tags and releases.** The promotion PR stays a human merge.
- **Cross-board claims.** Two boards each running `factory land` on one repository could both review a PR; the `sha=` pin keeps the merge safe, but the double review isn't prevented (NEXT.md item 6).
