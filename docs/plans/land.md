# Plan: Land factory PRs on a dev branch (land)

**Status:** Planned (2026-11-26). Workstream scoped; awaiting kickoff: `land-t01` runs once this plan is merged and synced. Roadmap: [NEXT.md item 23](../../NEXT.md#23-land-factory-prs-on-a-dev-branch).

## Plan at a Glance

**Problem:** Every factory pull request waits for you to merge it into `main`. A stack of dependent PRs moves one merge at a time, so finished work piles up whenever you're away.

**Goal:** When this workstream is complete, factory PRs land on a `dev` branch without you. A new role, the *lander*, reviews each ready PR and either merges it into `dev` or sends it back for rework. An end-to-end test of the whole flow runs on every push to `dev`, and landing pauses while `dev` is red. `main` changes only when you merge one promotion PR, after a live run with real models that you start.

**In scope:** pointing factory PRs at `dev`; `factory land`; rework for held PRs; `factory promote`, which keeps the `dev` → `main` PR current; the end-to-end test and the live run; docs.

**Out of scope:** branch protection and the live run's API key (set by hand), merging into `main` without you, and builds started by `factory land`.

**Approach:**
1. Settings, plus a dry run that says which PRs are ready.
2. The lander's review, then landing, bottom-up through stacks.
3. Holds go back for rework; the promotion PR keeps `main` one merge away.
4. The end-to-end test on `dev`, landing only while `dev` is green, and the live run before a promotion.

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
| Confidence on `dev` | **A scripted end-to-end test on every push, plus a live smoke started by hand.** `tests/test_dev_lifecycle.py` takes a plan from `factory sync` through landing, a hold and its rework, a red `dev` and the promotion PR, using the scripted model and the fake `gh`. It runs as its own CI job on every push to `dev` and `main` and on every PR, the promotion PR included. The `live smoke` workflow runs `factory bench` on a shipped case with this repository's pinned models. You start it by hand on the promotion PR's head, and it fails unless the case is solved |
| A red `dev` | **Pauses landing.** `factory land` reviews and merges only while every check on the trunk's head has finished and passed. Red, running or missing checks stop the pass before any review, so at most one PR lands per trunk CI run, and a red `dev` points at one landing. A failed live smoke on the head is a red `dev` too |
| Branch protection | **A GitHub setting you own, set up by hand.** `main` requires a pull request, the CI checks and the `live smoke` check, so the promotion PR merges only after a live smoke passes on its head. `dev` requires the CI checks, including the end-to-end job, but no approving review, since the factory merges as the identity that opened the PR. The README gives the commands |

### Milestones

| # | Outcome | Exit criteria | Parallelizable with |
|---|---|---|---|
| **M1** | Factory PRs can target a configured trunk | The t01 tests in `tests/test_config.py`, `tests/test_pipeline.py` and `tests/test_templates.py` pass | — |
| **M2** | `factory land --dry-run` says which PRs are ready and why the others wait | The t02 tests in `tests/test_land.py` and `tests/test_ci.py` pass | M3 |
| **M3** | The lander reviews a PR head and gives a verdict | The t03 tests in `tests/test_lander.py` pass | M2 |
| **M4** | `factory land` merges ready PRs into the trunk, bottom-up through stacks | The t04 tests in `tests/test_land.py` pass, including the stack test | — |
| **M5** | A HOLD sends the PR back for rework | The t05 tests in `tests/test_land_rework.py` pass | — |
| **M6** | One promotion PR carries the trunk to the release branch | The t06 tests in `tests/test_promote.py` pass | — |
| **M7** | Landing waits for a green trunk, and an end-to-end test of the whole flow runs on every push to `dev` | `tests/test_dev_lifecycle.py::test_a_plan_reaches_the_release_branch_through_dev` and the t07 tests in `tests/test_land.py` and `tests/test_ci_workflows.py` pass | — |
| **M8** | A live smoke with real models, started by hand, fails unless its cases are solved | The t08 tests in `tests/test_bench.py` and `tests/test_ci_workflows.py` pass | — |
| **M9** | Docs | `tests/test_templates.py::test_the_docs_describe_landing_and_promotion` passes, and `tests/test_templates.py` passes | — |

**Sequence:** `M1 → (M2 ∥ M3) → M4 → M5 → M6 → M7 → M8 → M9`. t02 and t03 write different files: t02 changes `factory/land.py`, `factory/ci.py`, `factory/cli.py` and `tests/test_land.py`; t03 changes `factory/lander.py`, `factory/agents.py`, `factory/flows.py`, `factory/db.py`, `factory/prompts/lander.md` and `tests/test_lander.py`. From t04 on, every task changes `factory/cli.py`, and t07 and t08 both change `.github/workflows/` and `tests/test_ci_workflows.py`, so they run in a chain.

### Task Contracts

| Milestone | Task IDs | Coverage |
|---|---|---|
| **M1** | `land-t01` | `trunk` and `land` in `factory/config.py`, and `land` as a role for `models` and `max_steps`; the default base in `cmd_run_one`, `cmd_run_plan` and `cmd_gates` in `factory/cli.py`; `factory/templates/config.yaml`; tests in `tests/test_config.py`, `tests/test_pipeline.py` and `tests/test_templates.py` |
| **M2** | `land-t02` | New `factory/land.py` (readiness); `ci.pending` in `factory/ci.py`; `factory land --dry-run` and the refusals in `factory/cli.py`; new `tests/test_land.py`, and a test in `tests/test_ci.py` |
| **M3** | `land-t03` | New `factory/prompts/lander.md` and `factory/lander.py`; the `land` role in `factory/agents.py`, `factory/flows.py` (reserved names) and `factory/db.py` (`ROLES`); new `tests/test_lander.py` |
| **M4** | `land-t04` | Gates at the head, the review, the merge, comments, the restack after a merge, `--watch` and one land per board, in `factory/land.py` and `factory/cli.py`; tests in `tests/test_land.py` |
| **M5** | `land-t05` | Holds as rework: columns in `factory/db.py`, the refresh and `_review_fix` in `factory/cli.py`, a `land` rework kind in `factory/pipeline.py`, the hold cap in `factory/land.py`; new `tests/test_land_rework.py` |
| **M6** | `land-t06` | New `factory/promote.py`; `factory promote` and the call after a landing pass in `factory/cli.py` and `factory/land.py`; new `tests/test_promote.py` |
| **M7** | `land-t07` | The trunk's state in `factory/land.py`, read before any review or merge and printed by `factory land --dry-run` (`factory/cli.py`); CI on pushes to `dev` and the end-to-end job in `.github/workflows/ci.yml`; commit checks in `fake_gh` (`tests/conftest.py`); new `tests/test_dev_lifecycle.py` and `tests/test_ci_workflows.py`, and tests in `tests/test_land.py` |
| **M8** | `land-t08` | `factory bench run --require-solved` in `factory/bench/report.py` and `factory/cli.py`; new `.github/workflows/live-smoke.yml`; tests in `tests/test_bench.py` and `tests/test_ci_workflows.py` |
| **M9** | `land-t09` | `docs/architecture.md`, `docs/reference.md`, `README.md`, `NEXT.md`, the AGENTS section (template and this repository's `AGENTS.md`) and the factory-ops skill (template and installed copy); a new test in `tests/test_templates.py` |

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
    - "The fake gh in tests/conftest.py answers the merge call as GitHub does. It merges the PR's head into its base in the test's bare origin with the given method and marks the PR merged with that mergeCommit, and it refuses with GitHub's message when sha isn't the PR's head"
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
    - "When origin/RELEASE has commits that origin/TRUNK lacks, not counting merge commits (a promotion merged with a merge commit leaves one on RELEASE, as expected), promote prints, and puts at the top of the body, `RELEASE has N commits TRUNK lacks: merge RELEASE into TRUNK so the promotion stays a clean merge`"
    - "With nothing to promote it prints `nothing to promote: RELEASE has everything on TRUNK`, exits 0 and opens nothing. `factory promote --dry-run` prints the title and body it would write and changes nothing on GitHub. Without land: configured it exits 1 with the message factory land gives"
    - "After a factory land pass that merged at least one PR, factory land runs promote and logs the promotion PR's URL. A promote failure is logged and doesn't stop the pass or --watch"
    - "The promotion PR's head is the trunk, not a factory/ branch, so refresh and adoption ignore it"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_promote.py::test_promote_opens_one_pr_listing_the_tasks_the_release_branch_lacks tests/test_promote.py::test_promote_updates_the_open_promotion_pr tests/test_promote.py::test_the_body_says_how_each_task_landed_and_lists_other_commits tests/test_promote.py::test_release_commits_missing_from_the_trunk_are_reported tests/test_promote.py::test_nothing_to_promote_opens_nothing tests/test_promote.py::test_dry_run_prints_the_pr_and_changes_nothing tests/test_promote.py::test_land_updates_the_promotion_pr_after_a_merge tests/test_promote.py::test_promote_refuses_without_land_config"
    - "uv run pytest -q tests/test_promote.py tests/test_land.py tests/test_prbody.py tests/test_stack.py"
  risk: medium

- id: land-t07
  goal: "factory land reviews and merges only while the trunk is green, meaning every check on the head of origin/TRUNK has finished and passed. CI runs on every push to dev. A new end-to-end test, run in CI as its own job, takes a plan from `factory sync` to the release branch through dev: stacked landings, a hold and its rework, a red dev that pauses landing, a human-only PR that never lands, and the promotion PR"
  spec_refs:
    - "docs/plans/land.md#a-green-trunk"
    - "docs/plans/land.md#the-end-to-end-test-on-dev"
    - "docs/plans/land.md#a-land-pass"
    - "factory/land.py"
    - "factory/ci.py"
    - "factory/cli.py"
    - ".github/workflows/ci.yml"
    - "tests/conftest.py"
  depends_on:
    - land-t06
  non_goals:
    - "The live smoke workflow and `factory bench run --require-solved` (land-t08)"
    - "Telling anyone that the trunk went red, or reverting the landing that turned it red"
    - "Showing the trunk's state in `factory status`, `factory top` or the web page"
    - "Branch protection, the dev branch or this repository's .factory/config.yaml"
  acceptance:
    - "New `land.trunk_state(...)` reads the checks on the head commit of origin/TRUNK through gh api, from `repos/{owner}/{repo}/commits/SHA/check-runs` (GitHub's newest run of each check) and `repos/{owner}/{repo}/commits/SHA/status`. It returns green; red with the failed checks' names; running with N of M checks pending; or none when the head has no checks. With land.require_checks false, a head with no checks is green"
    - "A factory land pass reads the trunk state after its refresh and before any review, gates or merge. When the trunk isn't green, the pass reviews, gates and merges nothing. When the state changes, it logs one of these: `TRUNK is red at SHA (NAMES failed): factory land merges nothing until it is green`, `TRUNK's checks are running at SHA (N of M pending): factory land waits for them`, or `TRUNK has no checks at SHA yet: factory land waits (CI must run on pushes to TRUNK)`. After a merge, the pass reads the trunk state again before the next PR, so one pass lands at most one PR per trunk CI run"
    - "`factory land --dry-run` first prints `trunk TRUNK at SHA: green` (or `red (NAMES failed)`, `checks running (N of M pending)`, `no checks yet`), then the PR lines of land-t02"
    - "The fake gh in tests/conftest.py answers the commit check-runs and status calls from its state file, so a test sets each trunk head's checks as it sets a PR's"
    - ".github/workflows/ci.yml runs on pushes to main and dev, on pull requests and on workflow_call. A new job named `end-to-end: a plan to the release branch through dev` runs `uv run --locked pytest -q -rs tests/test_dev_lifecycle.py` after installing bubblewrap as the test job does. The package job also runs `factory prompt land` from the installed wheel in the repository it initialises, and fails unless the output contains `VERDICT: MERGE`"
    - "New tests/test_dev_lifecycle.py has test_a_plan_reaches_the_release_branch_through_dev. It uses a real git repository whose bare origin has main and dev, a config with `trunk: dev` and a land: block, the fake gh, and scripted models for every role including the lander. It goes only through the real entry points: `factory sync`, `factory run PLAN`, `factory land`, `factory run TASK`, `factory promote` and `factory status`. Its plan has four tasks: demo-t01; demo-t02, which depends on demo-t01; demo-t03, which the lander holds once; and demo-t04, with risk: high"
    - "The test checks this order. `factory run PLAN` opens four PRs: demo-t02's targets factory/demo-t01 and the others target dev. With dev and every PR head green, a pass merges demo-t01 and nothing else, because dev's new head has no checks yet, and restacks demo-t02 onto dev. With dev green again, the next pass gates demo-t02's restacked head and merges it. With dev green again, the pass after that holds demo-t03, which becomes changes_requested, and comments `a human merges it` on demo-t04, which stays open"
    - "The test then continues. `factory run demo-t03` reworks the hold and pushes a new head. With dev's head red, a pass reviews and merges nothing, and the scripted lander isn't called. With dev green, a pass merges demo-t03's new head. There is exactly one PR from dev to main. After the last landing, its body lists demo-t01, demo-t02 and demo-t03 as landed by factory land and doesn't list demo-t04"
    - "Last, the test merges the promotion PR into main in the bare origin with a merge commit, as a human would. `factory promote` then prints `nothing to promote` and no RELEASE-has-commits warning, and `factory status` shows demo-t01 to demo-t03 merged and demo-t04 pr_open. Every merge call the fake gh received carried the head sha the lander reviewed and targeted dev, and none targeted main"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_land.py::test_trunk_state_reads_the_checks_on_the_trunk_head tests/test_land.py::test_land_reviews_and_merges_nothing_while_the_trunk_is_not_green tests/test_land.py::test_one_pass_lands_one_pr_per_trunk_ci_run tests/test_land.py::test_dry_run_starts_with_the_trunk_state tests/test_ci_workflows.py::test_ci_runs_on_pushes_to_dev_with_the_end_to_end_job tests/test_ci_workflows.py::test_the_package_job_checks_the_lander_prompt_ships tests/test_dev_lifecycle.py::test_a_plan_reaches_the_release_branch_through_dev"
    - "uv run pytest -q tests/test_land.py tests/test_land_rework.py tests/test_promote.py tests/test_dev_lifecycle.py tests/test_ci_workflows.py"
  risk: medium

- id: land-t08
  goal: "`factory bench run --require-solved` fails unless every cell solved its case. A GitHub Actions workflow named `live smoke`, started only by hand, runs it with this repository's pinned models on shipped bench cases at the ref it is started on. So a promotion can be checked with real models before a human merges it"
  spec_refs:
    - "docs/plans/land.md#the-live-smoke"
    - "factory/bench/report.py"
    - "factory/bench/run.py"
    - "factory/cli.py"
    - ".github/workflows/ci.yml"
  depends_on:
    - land-t07
  non_goals:
    - "Running the live smoke on pushes, pull requests or a schedule"
    - "Adding the OPENROUTER_API_KEY secret or changing branch protection (both done by hand)"
    - "Running the lander or factory land with a real model"
    - "New bench cases, or changing how cells are scored"
  acceptance:
    - "`factory bench run` takes `--require-solved`. With it, the command exits 1 unless every cell's outcome is `solved`, and prints `not solved: CASE (OUTCOME)` for each other cell after the summary. Without it, the exit code is as today"
    - "New .github/workflows/live-smoke.yml is named `live smoke` and runs only on workflow_dispatch. Its inputs are `cases` (space-separated case ids, default `slugify`) and `max_cost` (USD, default `5`). Its one job is named `live smoke`. It checks out the ref the workflow was started on, installs bubblewrap as ci.yml does, sets up uv, and sets FACTORY_HOME to a directory under runner.temp"
    - "The job's bench step runs `uv run --locked factory bench run`, with one `--case ID` per id in `cases`, `--max-cost MAX_COST` and `--require-solved`. The inputs reach the script through env variables and are never written into the script with `${{ }}`. OPENROUTER_API_KEY comes from the repository secret of that name, in that step's env only"
    - "After the bench step, also when it fails, the job appends the output of `factory bench report --cells` to the job summary and uploads FACTORY_HOME's bench directory as an artifact named `live-smoke-bench`. The workflow's permissions are `contents: read`"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_bench.py::test_require_solved_fails_unless_every_cell_is_solved tests/test_ci_workflows.py::test_the_live_smoke_runs_by_hand_on_the_pinned_models tests/test_ci_workflows.py::test_the_live_smoke_keeps_its_inputs_and_secret_out_of_scripts"
    - "uv run pytest -q tests/test_bench.py tests/test_ci_workflows.py"
  risk: medium

- id: land-t09
  goal: "The docs describe the trunk and release branches, the lander, factory land, holds, the green-trunk rule, factory promote, the end-to-end test on dev and the live smoke. The policy says the factory merges into the trunk and a human merges into the release branch. The README says how to set up a dev branch with its branch protection, and NEXT.md marks item 23 done"
  spec_refs:
    - "docs/plans/land.md#branches"
    - "docs/plans/land.md#a-green-trunk"
    - "docs/plans/land.md#the-live-smoke"
    - "docs/plans/land.md#turning-it-on-here"
    - "docs/architecture.md"
    - "docs/reference.md"
    - "README.md"
    - "NEXT.md"
    - "factory/templates/agents-section.md"
    - "factory/templates/skills/factory-ops/SKILL.md"
  depends_on:
    - land-t08
  non_goals:
    - "Changing behaviour or workflows"
    - "Changing this repository's .factory/config.yaml, creating the dev branch, adding secrets or changing branch protection"
    - "The factory specification chapters in docs/spec/"
  acceptance:
    - "docs/architecture.md's Policy says that merging into the release branch is the human approval, and that with land: configured the factory's own code merges a factory PR into the trunk after the lander's MERGE, pinned to the reviewed head. It also says agents still never merge, push or call gh"
    - "docs/architecture.md has a new section headed `## Landing on the trunk`. It covers the branches, readiness and its reasons, human-only PRs, the green-trunk rule and its one landing per trunk CI run, gates at the head, the lander's review, the merge, holds and their cap, `--watch`, one land per board, and the promotion PR. It also covers what gives confidence in the trunk: the end-to-end test that runs on every push to dev and on every PR, and the live smoke run by hand before a promotion is merged. The Roles table has a lander row. The known limitation `Restacked PRs aren't re-gated` says that factory land gates a head before landing it"
    - "docs/reference.md describes `trunk` and `land` with the other config keys. It lists `factory land` and `factory promote` with every flag and default, `factory bench run --require-solved`, and `land` in the roles for models and max_steps. It has troubleshooting rows for `land: is not configured`, `land.release must differ from trunk`, `factory land is already running on this board`, `held N times by the lander`, `TRUNK is red at SHA`, `TRUNK has no checks at SHA yet` and the RELEASE-has-commits warning"
    - "README.md has a section headed `## Land on a dev branch`. It covers creating the branch (`git push origin main:dev`), the `trunk:` and `land:` settings, keeping the checkout on the trunk, and running CI on pushes to the trunk. It covers the branch protection: main requires a pull request, the CI checks and the `live smoke` check; dev requires the CI checks and no approving review. It gives the gh api commands for both"
    - "The same README section covers running `factory land --watch`, what a red dev does to landing and how to re-run a failed check, and running factory land with GH_TOKEN for a separate GitHub identity. It also covers merging the promotion PR with a merge commit after starting the live smoke on its head (`gh workflow run live-smoke.yml --ref dev`), with the OPENROUTER_API_KEY repository secret it needs. It points at this repository's .github/workflows/live-smoke.yml as an example for other projects"
    - "NEXT.md's item 23 row and section say landing is done and link docs/architecture.md#landing-on-the-trunk"
    - "factory/templates/agents-section.md and the Software factory section of this repository's AGENTS.md, which stay identical, say that with land: configured `factory land` merges ready PRs into the trunk while it is green, and that merging the promotion PR is the human approval"
    - "The factory-ops skill has request rows for landing ready PRs (`factory land`, `--watch`, `--dry-run`), why a PR isn't landing (including a red trunk), a held PR, promoting the trunk (`factory promote`) and running the live smoke. They are in factory/templates/skills/factory-ops/SKILL.md and .claude/skills/factory-ops/SKILL.md, which stay identical"
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
- **`land-t07`:** four tests added to `tests/test_land.py`; a new `tests/test_ci_workflows.py` with two tests; and the new end-to-end `tests/test_dev_lifecycle.py::test_a_plan_reaches_the_release_branch_through_dev`.
- **`land-t08`:** `tests/test_bench.py::test_require_solved_fails_unless_every_cell_is_solved`, and two tests added to `tests/test_ci_workflows.py`.
- **`land-t09`:** `tests/test_templates.py::test_the_docs_describe_landing_and_promotion`.

Every contract names at least one test that doesn't exist yet, so each fits this repository's `strict` flow. The end-to-end test goes in land-t07 rather than a task of its own because it needs the green-trunk rule: without that rule, its red-`dev` pass would merge, so the test fails before the build. The tests drive `gh` through the `fake_gh` fixture in `tests/conftest.py`, which t02, t04, t06 and t07 extend for the calls they add: pull request files, issue comments, the merge call, `mergeCommit` and commit checks. `tests/test_ci_workflows.py` reads the workflow files with PyYAML, already a dependency, and runs nothing on GitHub. Each verification filter must select its tests; zero matching tests is not a pass.

These tasks change the factory itself and run on this repository's own board, as earlier factory plans did. They land through human merges into `main`. This repository switches to a dev branch only after land-t09, by hand (see [Turning it on here](#turning-it-on-here)).

### Risks

1. **An unattended merge the human would have refused.** The lander is one model's judgment, and a merge into the trunk feeds every later task built on it. **Action:** the gates must pass at the exact head, CI must be green on the PR and on the trunk's head, and the merge is pinned to the reviewed sha. The end-to-end test runs on every PR and on `dev` after every landing. `risk: high` contracts and changes to `.factory/`, `.github/` or guidance files wait for a human. The release branch moves only by a human merge of the promotion PR, which lists how each task landed.
2. **The factory weakens its own checks through the trunk.** Settings and guidance come from the main checkout, which sits on the trunk once landing is on. So a landed change to `.factory/config.yaml`, CI or `AGENTS.md` would steer every later run. **Action:** those paths are human-only in land-t02. When [security-review](security-review.md)'s `guarded_paths` lands, its list can replace this one (see Notes).
3. **Builder and lander loop on the same PR.** A HOLD sends the PR back, the rework is reviewed again, and it can be held again. **Action:** `land.max_holds` (default 2) caps reworks per fresh build, after which the PR waits for a human. Each head is reviewed once, and a missing verdict is retried at most twice per head.
4. **Squash merges split the trunk from the release branch.** A promotion PR merged with a squash gives `main` a commit that `dev` lacks, and every later promotion conflicts. **Action:** the promotion PR's body says to use a merge commit, and promote reports when the release branch has commits the trunk lacks. The README tells you to allow merge commits on `main`.
5. **Mixed trunks while switching.** PRs opened before the switch target `main` and keep `main` as their trunk, and a task stacked on one inherits it. **Action:** `factory land` never merges a PR off the configured trunk, and dry-run lists it as `targets main, not the trunk dev`. Switch when no stacks are open, or merge those PRs by hand.
6. **Races with GitHub and with other runs.** A push, a restack or a conflict can land between the review and the merge. **Action:** the merge call carries `sha=`, so GitHub refuses a head that moved. One land runs per board, and a task in a run isn't `pr_open`, so land skips it.
7. **Spend.** Each review is a model call that `--watch` makes unattended. **Action:** the lander runs only on ready heads (CI green, gates passed) while the trunk is green, once per head, with `max_steps: 40`. Its runs carry cost like every role, so `factory stats` and `factory show` count them.
8. **A flaky check stalls landing.** Every check on the trunk's head counts, so a flaky job or a failed live smoke pauses every landing until the head is green. **Action:** GitHub reports the newest run of each check, so re-running the failed job (`gh run rerun --failed`) turns the head green, and the README says so. The pause is logged once per state, and `factory land --dry-run` prints it on its first line.
9. **The live smoke costs money and depends on an outside provider.** **Action:** it runs only when you start it, `--max-cost` caps it (default $5), and only its bench step sees the API key. Provider failures are `error` cells, so `factory bench report --cells` in the job summary tells them apart from a case that wasn't solved.
10. **One long end-to-end test breaks for many reasons.** **Action:** it asserts board states, PR bases, merge calls and the promotion PR's task lines, never log wording. Each step it walks through also has narrower tests in `tests/test_land.py`, `tests/test_land_rework.py` and `tests/test_promote.py`, which point at the failing part.
11. **The scripted test can't catch a model or prompt regression.** **Action:** the live smoke covers real models on the build roles before each promotion. The lander's own model is exercised only by real land passes, whose `land` runs and outcomes `factory show` records (see Notes).

---

## Background and Evidence

- **The trunk is whatever branch a run starts on.** `cmd_run_one` sets `trunk = a.base or git rev-parse --abbrev-ref HEAD` (`factory/cli.py:239`), and records it on the task. Restacks and the stranded-PR check use `row["trunk"] or "main"` (`factory/stack.py`, `factory/cli.py:491`). No config key sets it, and `factory gates` defaults to `main` (`factory/cli.py:828`).
- **Only humans merge.** The Policy in `docs/architecture.md` says "Merging is the approval. Agents never merge, push, commit to your checkout, or see secrets". After a merge, `_refresh` marks the task merged (`_merged`), records what changed after the factory's candidate (`factory/merges.py`), and restacks the PRs stacked on it (`stack.restack`).
- **Refresh already reads every signal a merge needs, one at a time.** `_pr_state` (`factory/cli.py`) returns state, mergeability, head and checks; `ci.red` finds failed checks on the factory's own head; `reviews.requests` finds unaddressed review requests; a head other than `candidate_sha` means someone else pushed. Nothing combines them into "ready to merge", and nothing reads pending checks.
- **Restacked heads aren't re-gated.** The architecture's known limitations say so: after a rebase, only CI checks the new head. Gate runs are recorded as role `verify`, step `gates`, with outcome `pass`/`fail` and the sha they ran on (`factory/pipeline.py:735`). So the newest passing gates sha tells whether a head was gated. `factory gates TASK --ref` (`cmd_gates`) already runs the gates on any commit in a throwaway worktree.
- **Roles outside a flow exist.** The selector ships as `factory/prompts/selector.md`, maps in `agents.ROLE_FILES`, is configured with `models.select`, and runs through `LangChainRoles.step(flows.Step("select", "select"), …)`. The lander follows the same pattern. The run role `merge` is taken by merge records (`db.ROLES`), so the new role is `land`.
- **Reworks have one entry point.** `cmd_run_one` handles `changes_requested` through `_review_fix`, which builds a `Rework` whose kind (`factory/pipeline.py` `KINDS`: `ci`, `human_review`) supplies the log line, commit body, PR comment and failure note. The scheduler already starts `changes_requested` tasks (`factory/scheduler.py:63`).
- **The repository today.** There is no `dev` branch on origin, and `main` has no branch protection (`gh api …/branches/main/protection` returns 404). CI runs on every `pull_request` and on pushes to `main` (`.github/workflows/ci.yml`), so PRs into `dev` get checks, but `dev`'s own head would get none. The repository has no CI secrets.
- **End-to-end tests already use a scripted model.** `tests/fake_model.py` plays each role from its system prompt, so the real agents, tools and graph run. `tests/test_pipeline.py` drives `main([...])` against a real repository with a bare origin and the `fake_gh` fixture, from `factory init` to an open PR (`test_an_initialised_repo_runs_its_starter_plan_with_the_shipped_prompts`). No test yet goes past an open PR.
- **`factory bench` runs real models, but a failed case still exits 0.** A bench cell is a normal pipeline run without a PR, scored by the case's hidden tests: `solved`, `false_pass` or `failed` (`factory/bench/run.py`). `report.exit_code` fails only for `error`, `stopped` and `skipped` cells (`factory/bench/report.py:335`). Runs are stored under `$FACTORY_HOME/bench/<run>`. The shipped cases are in `factory/bench/fixtures/` (`ini-refactor`, `money-rounding`, `rate-limiter`, `report-json`, `slugify`).

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
       trunk not green (t07) ──► log the state if changed, end the pass              │
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
            │                 · read the trunk again: not green ──► end the pass     │
       merged anything? ──► factory promote (t06)                                    │
     --watch: sleep --poll, repeat ──────────────────────────────────────────────────┘
```

A stack lands bottom-up across passes. The bottom PR merges, and the refresh after it rebases the next PR onto the trunk and retargets it. CI then runs on that new head, which is a new candidate the gates haven't seen, and on the trunk's new head. A later pass finds both green, gates the PR's head, reviews it and merges it.

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

### A green trunk

```text
$ factory land --dry-run
trunk dev at 3f2a9c1: red (end-to-end: a plan to the release branch through dev failed)
land-t04   ready                                              https://github.com/o/r/pull/122
```

`factory land` merges only onto a trunk that is known to work. After its refresh, a pass reads the checks on `origin/TRUNK`'s head (GitHub's newest run of each, from `commits/SHA/check-runs` and `commits/SHA/status`):

| Trunk head | The pass |
|---|---|
| Every check finished and passed | reviews and merges as above |
| A check failed | reviews and merges nothing: `dev is red at SHA (NAMES failed)` |
| Checks still running | waits: `dev's checks are running at SHA (N of M pending)` |
| No checks | waits: `dev has no checks at SHA yet`, unless `land.require_checks: false` |

A merge moves the trunk's head, so the pass reads the trunk again before the next PR. Its new head has no checks yet, so one pass lands one PR. The next lands after CI has passed on the trunk with the first in it. Landing is slower than merging everything that is ready at once. In exchange, each landing is tested on `dev` on its own, and a red `dev` names the PR that turned it red. Every check on the head counts, including a live smoke started on it.

### The end-to-end test on `dev`

`tests/test_dev_lifecycle.py::test_a_plan_reaches_the_release_branch_through_dev` is one test of the whole flow, run through the real entry points. It uses the scripted model for every role, the fake `gh`, and a bare origin whose merges really happen in git:

```text
factory sync ─► factory run PLAN ─► 4 PRs (t02 stacked on t01; t04 risk: high)
dev green   ─► factory land: merges t01, restacks t02 · dev's new head has no checks: stop
dev green   ─► factory land: gates t02's restacked head, merges it
dev green   ─► factory land: HOLD t03 → changes_requested · t04: "a human merges it"
              factory run t03 ─► rework pushes a new head
dev red     ─► factory land: no review, no merge
dev green   ─► factory land: merges t03 · the one promotion PR lists t01, t02, t03, not t04
human merges the promotion PR into main (merge commit) ─► factory promote: nothing to promote
factory status: t01–t03 merged, t04 pr_open · every merge call: dev, at the reviewed sha
```

CI runs it as its own job, `end-to-end: a plan to the release branch through dev`, on every push to `main` and `dev` and on every pull request. So it runs on each factory PR before it lands, on `dev` after each landing, and on the promotion PR. The `test` job runs it too, as part of the whole suite. `dev` and `main` both require the job.

### The live smoke

The scripted test proves the plumbing, but not that the real models still produce working changes with the prompts and tools on `dev`. The `live smoke` workflow (`.github/workflows/live-smoke.yml`, started only by hand) does that before you approve a promotion:

```bash
gh workflow run live-smoke.yml --ref dev                       # slugify, at most $5
gh workflow run live-smoke.yml --ref dev -f cases="slugify rate-limiter" -f max_cost=10
```

It runs `factory bench run --case … --max-cost … --require-solved` with this repository's pinned models, at `dev`'s head. `--require-solved` makes the bench fail unless every case's hidden tests pass. The job summary carries `factory bench report --cells`, and the bench directory is uploaded as `live-smoke-bench`. Its check lands on `dev`'s head, which is the promotion PR's head. `main` requires it, so the promotion PR merges only after a live smoke passed on the exact commit you are merging. Until one has, GitHub shows the required check as waiting. Each landing moves the head, so you start the live smoke when you are ready to merge. A run in progress holds landing like any running check, and a failed run pauses landing until it is re-run green or a fix lands.

The key is the `OPENROUTER_API_KEY` repository secret, visible only to the bench step. Only people who can write to the repository can start the workflow.

### Turning it on here

This is done by hand once land-t09 has merged into `main`, and is not a contract:

1. `git push origin main:dev`.
2. Add the `OPENROUTER_API_KEY` repository secret, and run `gh workflow run live-smoke.yml --ref dev` once to see it pass.
3. Branch protection (README section): `main` requires a pull request, the `ci` checks (including `end-to-end: a plan to the release branch through dev`) and `live smoke`, and allows merge commits. `dev` requires the `ci` checks and no approving review.
4. In `.factory/config.yaml` on `dev`, add `trunk: dev`, the `land:` block and `models.land`. Merge `dev` into `main` once so both branches carry them, and switch the main checkout to `dev`.
5. Let the open stacks that target `main` finish, or merge them by hand. Then run `factory land --watch` (or `--dry-run` first).

## Files Changed

| File | Change |
|---|---|
| `factory/config.py` | `trunk`, `LandConfig` and their validation; `land` in `ROLES` (t01) |
| `factory/cli.py` | Default base from `trunk` (t01); `factory land` (t02, t04); holds in `_refresh`, `_review_fix` and `cmd_run_one` (t05); `factory promote` (t06); the trunk line in `--dry-run` (t07); `factory bench run --require-solved` (t08) |
| `factory/templates/config.yaml` | Commented `trunk:` and `land:` (t01) |
| `factory/land.py` | New: readiness (t02); the pass, gates at the head, the merge, comments, `--watch`, the pid file (t04); the hold cap (t05); calling promote (t06); `trunk_state` and the green-trunk rule (t07) |
| `factory/ci.py` | `pending` (t02) |
| `factory/bench/report.py` | The `--require-solved` exit code and its `not solved` lines (t08) |
| `.github/workflows/ci.yml` | Runs on pushes to `dev`; the end-to-end job; the package job checks `factory prompt land` (t07) |
| `.github/workflows/live-smoke.yml` | New: the live smoke, started by hand (t08) |
| `factory/prompts/lander.md` | New lander prompt (t03) |
| `factory/lander.py` | New: the lander's message, review and run record (t03) |
| `factory/agents.py` | `land` in `ROLE_FILES`, the `MERGE`/`HOLD` verdict and the `land` kit (t03) |
| `factory/flows.py` | `land` and `lander` reserved (t03) |
| `factory/db.py` | `land` in `ROLES` (t03); `land_hold` and `land_holds` columns (t05) |
| `factory/pipeline.py` | The `land` rework kind (t05) |
| `factory/promote.py` | New: tasks to promote, the PR body, open or update (t06) |
| `tests/conftest.py` | `fake_gh` learns PR files, issue comments, the merge call (merging in the bare origin), `mergeCommit` and commit checks (t02, t04, t06, t07) |
| `tests/test_land.py`, `tests/test_lander.py`, `tests/test_land_rework.py`, `tests/test_promote.py` | New tests (t02–t07) |
| `tests/test_dev_lifecycle.py`, `tests/test_ci_workflows.py` | New: the end-to-end test on `dev` (t07); the workflow tests (t07, t08) |
| `tests/test_config.py`, `tests/test_pipeline.py`, `tests/test_ci.py`, `tests/test_bench.py`, `tests/test_templates.py` | New tests (t01, t02, t08, t09) |
| `docs/architecture.md`, `docs/reference.md`, `README.md`, `NEXT.md`, `AGENTS.md`, `factory/templates/agents-section.md`, factory-ops skill (template and installed copy) | Docs (t09) |

## Test Plan

### Unit tests

- **t01:** `trunk`/`land` defaults and every validation message; `land` accepted in `models` and `max_steps`; a run without `--base` builds on and targets `trunk`, and `--base` wins; `factory gates` measures against `trunk`; the config template mentions both.
- **t02:** each readiness rule and its exact reason. Ready on green checks. Stacked waits. Pending, failed or missing checks and UNKNOWN mergeability wait. A pushed head or a PR on another base is human. `risk: high` and `.factory/`/`.github/`/guidance paths are human. `--dry-run` prints one line per PR and leaves the board and fake gh state unchanged. Refused without `land:`. Also `ci.pending` for check runs and status contexts.
- **t03:** the prompt's last line matches the parser. `models.land`, the override and `factory prompt land`. The message carries each input and `(none)` for empty ones. The kit has read tools and `git_diff` only. The last verdict wins and a missing one is asked for once. The run record has role `land`, step `review` and the head sha.
- **t04:** merge at the reviewed head with `sha=` and the method. A head without passing gates is gated first, and failing gates hold it. A HOLD comments and doesn't merge. One review per head. A refused merge is retried without a new review. Human-only PRs get one comment per head and are never merged. Never off the trunk or into the release branch. `--watch` repeats the pass, and a second land is refused.
- **t05:** a hold sets `changes_requested`, `land_hold` and `land_holds`. Refresh keeps it. The rework feedback carries the findings and human requests. A rework clears the hold and the new head is reviewed. The cap leaves it for a human. A fresh build resets the count. A plan run starts held tasks.
- **t06:** one PR opened, then updated. The body lists tasks by plan, how each landed, edited merges and other commits. Release-only commits are reported, but the merge commit a promotion leaves on the release branch isn't. Nothing to promote opens nothing. `--dry-run` changes nothing. Land calls promote after a merge. Refused without `land:`.
- **t07:** `trunk_state` reads check runs and status contexts on the trunk's head: green, red with names, running with counts, none, and none counting as green with `require_checks: false`. A pass on a red, running or check-less trunk calls no model and merges nothing, and logs each state once. After a merge, the pass stops when the trunk's new head has no checks, so two ready PRs land on two passes. `--dry-run` prints the trunk line first. `ci.yml` runs on pushes to `dev`, has the end-to-end job, and its package job checks `factory prompt land`.
- **t08:** `--require-solved` exits 1 for `failed`, `false_pass`, `error`, `stopped` and `skipped` cells and prints each, and 0 when all are solved; without it the exit code is unchanged. `live-smoke.yml` runs only on `workflow_dispatch`, with the `cases` and `max_cost` inputs, `--require-solved`, `contents: read`, the secret in the bench step's env only, inputs passed through env, and the summary and artifact steps running on failure.
- **t09:** the docs name the commands, settings, messages and branch protection above.

### End-to-end tests

- **t04:** `tests/test_land.py::test_land_takes_a_stack_to_the_trunk_bottom_up` runs the real `factory land` entry point on a real git repository with a `dev` trunk. It uses the fake `gh` and a scripted lander over two stacked task PRs. Pass 1 merges the bottom PR and restacks the top one onto `dev`. With the top PR's checks pending, pass 2 waits. Once they are green, pass 3 gates the restacked head, reviews it and merges it. The board ends with both tasks merged, and the merge calls carry the reviewed shas.
- **t07:** `tests/test_dev_lifecycle.py::test_a_plan_reaches_the_release_branch_through_dev` walks the whole flow on `dev`, as in [The end-to-end test on dev](#the-end-to-end-test-on-dev): sync, four PRs, stacked landings one per trunk CI run, a hold and its rework, a red `dev` that pauses landing, a `risk: high` PR that never lands, one promotion PR, and the human merge into `main`. CI runs it as its own job on every push to `dev` and `main` and on every PR.
- **t08 (live, by hand):** the `live smoke` workflow runs `factory bench run --require-solved` on shipped cases with the pinned models. It isn't run by the factory or by pytest.

## Verification

```bash
uv run pytest -q tests/test_land.py tests/test_lander.py tests/test_land_rework.py tests/test_promote.py
uv run pytest -q tests/test_dev_lifecycle.py tests/test_ci_workflows.py
uv run pytest -q
```

By hand, after [Turning it on here](#turning-it-on-here):
- `factory land --dry-run` prints `dev`'s state first, then the open PRs with reasons.
- `factory land` merges a ready low-risk PR into `dev`, and the promotion PR to `main` lists it. A `risk: high` PR gets the lander's comment and stays open.
- The end-to-end job passes on `dev`'s new head, and the next pass lands the next ready PR only after it has.
- `gh workflow run live-smoke.yml --ref dev` passes, and its check shows on the promotion PR, which can then be merged.

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
- **A live run of the lander.** The live smoke runs the build roles through `factory bench`, which has no landing step. The lander's model is first exercised by real land passes. A bench case that lands its result would cover it.
- **Telling you `dev` went red, or reverting the landing that did it.** GitHub's own failure notifications and the dry run's first line cover it. A revert, by hand or by a later task, is a normal PR into `dev`.
- **Starting the live smoke from `factory promote`.** It stays a hand step, since it spends money. The factory doesn't call `gh workflow run`.
- **Cross-board claims.** Two boards each running `factory land` on one repository could both review a PR; the `sha=` pin keeps the merge safe, but the double review isn't prevented (NEXT.md item 6).
