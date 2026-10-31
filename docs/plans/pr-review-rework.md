# Plan: Act on human PR review comments

**Status:** Planned (2026-10-31). Workstream scoped; awaiting kickoff. Roadmap: [NEXT.md item 1](../../NEXT.md#1-act-on-human-pr-review-comments).

---

## Execution Plan

### Locked Decisions

| Decision | Choice |
|---|---|
| What marks a PR for rework | A **Request changes** review from a user with write access, or **any submitted review** by the PR's author, including a single inline comment. GitHub doesn't let an author request changes on their own PR, and the factory opens PRs as the maintainer's `gh` account. Conversation comments, including the factory's own, never count |
| What cancels it before a run | **The latest review wins**, as on GitHub. Each reviewer's latest approval, request or dismissal decides, so an approval or a dismissal after a request clears it and the task goes back to `pr_open`. Comment-only reviews from others neither request nor clear |
| A review that asks for more than the contract | **The human's ask wins.** The human is the approver: the builder does it, and the factory reviewer is told the review's requests are in scope. The gates still decide |
| Structure | **The Rework refactor comes first** (t01, no change in behavior). CI fixes and review reworks then share one "build on the PR head" path |

### Milestones

| # | Deliverable | Exit criteria | Parallelizable with |
|---|---|---|---|
| **M1** | One rework path | `pipeline.Rework` replaces `CiFix`; the four CI pipeline tests and `tests/test_ci.py` pass unmodified | — |
| **M2** | Reading reviews | `tests/test_reviews.py` passes: the trigger, the latest review wins, write access, the watermark, the brief | — |
| **M3** | The board knows | Refresh marks and clears `changes_requested`; the board, plan runs, requeue, restack and take-up handle it (refresh tests pass) | — |
| **M4** | The factory acts | `factory run` addresses the reviews on the PR branch, with review and gates, and updates the same PR (rework tests pass) | — |
| **M5** | Docs | `docs/architecture.md`, `docs/reference.md`, NEXT.md and the factory-ops skill describe it; `tests/test_templates.py` passes | — |

**Sequence:** `M1 → M2 → M3 → M4 → M5`. The tasks run one after another: every task writes the same session log, and M3 and M4 change the same parts of `cli.py` and `pipeline.py`.

### Task Contracts

| Milestone | Task IDs | Coverage |
|---|---|---|
| **M1** | `pr-review-rework-t01` | `CiFix` → `Rework` in `pipeline.py`, `cli.py` and the `ci.py` docstring; the existing CI tests are the proof |
| **M2** | `pr-review-rework-t02` | New `factory/reviews.py` (fetch, request selection, brief); the fake `gh` serves reviews; new `tests/test_reviews.py` |
| **M3** | `pr-review-rework-t03` | The `changes_requested` status and the `reviews_addressed` column; refresh precedence; observe, scheduler summary, requeue, restack, `_adopt`; refresh tests |
| **M4** | `pr-review-rework-t04` | The `human_review` rework run: run path, reviewer context, the no-change answer, PR comment and body, watermark advance, plan runs; rework tests |
| **M5** | `pr-review-rework-t05` | `docs/architecture.md` (lifecycle, a "Review comments" section, limitations), `docs/reference.md` (commands, troubleshooting), NEXT.md, the factory-ops skill template |

```yaml
- id: pr-review-rework-t01
  goal: "Fixing failing CI goes through one generic Rework of an open PR's head: pipeline.Rework replaces pipeline.CiFix, with no change in behavior"
  spec_refs:
    - "docs/plans/pr-review-rework.md#design"
    - "NEXT.md#1-act-on-human-pr-review-comments"
    - "docs/architecture.md#ci-failures"
  depends_on: []
  non_goals:
    - "Reading PR reviews, or adding any status, run role, database column or command"
    - "Changing any observable CI-fix behavior: run records (role ci, outcome failing), log lines, commit messages, PR comment and body text, task notes, printed messages"
    - "Changing conflict resolution (pipeline.Resolution, replay_worktree, the resolve node)"
    - "Editing factory/prompts/*.md or any documentation (README.md, docs/architecture.md, docs/reference.md, NEXT.md)"
  acceptance:
    - "factory/pipeline.py defines a Rework dataclass holding the rework's kind, the old candidate (where the build starts and what the push is leased on), the names of what triggered it, and the builder's brief. Options has a single `rework` field in place of `ci_fix`, and the string CiFix appears nowhere under factory/ or tests/ (the ci.py docstring included)"
    - "Every place that branched on a CI fix reads the Rework, with the kind-specific wording (commit-message suffix, no-change feedback, PR comment, PR body line, failure note, log fragment) looked up from its kind in one table. A second kind then adds a table entry rather than new branches. Those places are: cli.cmd_run_one and cli._ci_fix; Pipeline.start_sha; the graph's entry node and its run record; the build node's feedback and commit message; the pr node's push lease, comment and body"
    - "tests/test_ci.py and the four CI tests in tests/test_pipeline.py pass without being modified"
    - "docs/sessions/<today>.md has an entry for this task"
  verification:
    - "uv run pytest -q tests/test_ci.py"
    - "uv run pytest -q tests/test_pipeline.py -k 'failing_ci_is_fixed or ci_is_judged_only or failed_ci_fix or ci_failure_of_a_stacked'"
    - "! grep -rn 'CiFix' factory/ tests/"
    - "grep -q 'class Rework' factory/pipeline.py"
  risk: medium

- id: pr-review-rework-t02
  goal: "factory/reviews.py reads a factory PR's reviews through `gh api` and decides, in pure functions, which unaddressed reviews request changes and what brief the builder gets"
  spec_refs:
    - "docs/plans/pr-review-rework.md#design"
    - "NEXT.md#1-act-on-human-pr-review-comments"
    - "factory/ci.py"
  depends_on:
    - pr-review-rework-t01
  non_goals:
    - "Calling the module from status --refresh, factory run, the pipeline or the board (pr-review-rework-t03 and t04 do that)"
    - "Reading conversation (issue) comments: only reviews and their inline comments"
    - "Posting, replying to or resolving anything on GitHub"
    - "Changing factory/ci.py or the CI path"
  acceptance:
    - "fetch(root, pr_url) returns the PR's author login, its submitted reviews (id, reviewer login, state, body, commit id) and each reviewer's permission. It uses the REST endpoints in the plan's Design through `gh api` (the PR, its reviews with --paginate, collaborator permission, looked up once per reviewer per fetch), and returns None when any call fails or prints invalid JSON"
    - "requests(...) returns the unaddressed reviews (id above the task's watermark; a NULL watermark counts as 0) that request changes. Any submitted (non-PENDING) review by the PR's author counts. For other reviewers with write or admin permission, a review counts when it is their latest APPROVED, CHANGES_REQUESTED or DISMISSED review and is CHANGES_REQUESTED, so a later approval or dismissal clears an earlier request. COMMENTED reviews from others neither request nor clear, and reviewers with read, triage or no access never count"
    - "brief(...) fetches the inline comments of the reviews it covers (pulls/N/comments, --paginate) and starts with '# Address review'. It says the reviewer approves the merge, so every request is in scope even where it goes beyond the plan, the goal or the non-goals, and that a question needs an answer in the final message, not a code change. It then lists every unaddressed review by a counted reviewer (author or write access): login, state, the commit it was on, and its body. Under each review come its inline comments as `path:line: body`, replies included; an outdated comment shows its original line, marked outdated. The whole is capped like ci.BRIEF_LIMIT"
    - "The fake gh in tests/conftest.py serves the PR, reviews, review comments and permission endpoints from its state file, with no reviews and write permission by default; comment POSTs and every other existing call behave as before, and the full suite passes"
    - "docs/sessions/<today>.md has an entry for this task"
  verification:
    - "uv run pytest -q tests/test_reviews.py::test_change_requests_count_only_from_reviewers_with_write_access tests/test_reviews.py::test_any_review_by_the_pr_author_requests_changes tests/test_reviews.py::test_each_reviewers_latest_decision_wins tests/test_reviews.py::test_addressed_reviews_no_longer_count tests/test_reviews.py::test_fetch_reads_the_pr_reviews_and_permissions_through_gh_api tests/test_reviews.py::test_brief_lists_review_bodies_and_inline_comments_by_path_and_line"
  risk: low

- id: pr-review-rework-t03
  goal: "`factory status --refresh` marks an open factory PR `changes_requested` when a review requests changes on the factory's own candidate, and clears it when the request is approved or dismissed. The board, plan runs, requeue, restack and take-up all handle the new status"
  spec_refs:
    - "docs/plans/pr-review-rework.md#design"
    - "docs/architecture.md#ci-failures"
  depends_on:
    - pr-review-rework-t02
  non_goals:
    - "Addressing the reviews: `factory run` refuses a changes_requested task without --force until pr-review-rework-t04 adds the rework"
    - "Changing how conflicts or CI failures are detected, beyond the precedence in acceptance"
    - "Posting anything to GitHub"
    - "Editing factory/prompts/*.md, the documentation (README.md, docs/architecture.md, docs/reference.md, NEXT.md) or the skill templates"
  acceptance:
    - "factory/db.py has `changes_requested` in STATUSES and a tasks column `reviews_addressed` (INTEGER, the highest GitHub review id the factory has addressed), migrated into older databases"
    - "Refresh reads reviews (reviews.fetch and reviews.requests) for each pr_open, ci_failed or changes_requested task whose PR head is its candidate. When reviews request changes, the task becomes changes_requested: the note names the reviewers and `factory run TASK`, and stderr gets `TASK: changes requested by @login (`factory run TASK` addresses them)`. A changes_requested task with no request left goes back to pr_open, with stderr `TASK: no review requests changes now`"
    - "Precedence: merged or closed first, then a conflict, then requested changes, then CI. A ci_failed task with a request becomes changes_requested"
    - "A changes_requested PR whose head isn't the factory's candidate goes back to pr_open, with a note that its reviews are left to whoever pushed. When gh fails, the status stays as it is. Conversation comments, including the factory's own, never change a status"
    - "Board: `factory status` and `factory top` show changes_requested with its own glyph in the plan strip, a `changes requested` counter, and the PR URL and note in the detail line. Plan summaries list it like ci_failed. Its dependents wait (`waits for TASK (changes_requested)`), `factory requeue` leaves it alone, and `factory run TASK` refuses it without --force"
    - "stack.restack moves a stacked changes_requested PR as it moves a pr_open one, and keeps the changes_requested status: the request still applies to the moved commits"
    - "A PR taken up from GitHub (cli._adopt) records the latest review id at take-up as addressed"
    - "docs/sessions/<today>.md has an entry for this task"
  verification:
    - "uv run pytest -q tests/test_pipeline.py::test_a_review_requesting_changes_marks_the_task_on_refresh tests/test_pipeline.py::test_conflicts_come_before_requested_changes_and_requested_changes_before_ci tests/test_pipeline.py::test_reviews_on_a_head_someone_else_pushed_are_left_to_them tests/test_pipeline.py::test_a_stacked_pr_keeps_its_requested_changes_when_restacked tests/test_pipeline.py::test_a_taken_up_pr_treats_earlier_reviews_as_addressed"
    - "uv run pytest -q tests/test_scheduler.py::test_dependents_wait_while_changes_are_requested tests/test_requeue.py::test_requeue_leaves_a_pr_with_requested_changes_alone"
  risk: medium

- id: pr-review-rework-t04
  goal: "`factory run TASK` (or its plan) on a changes_requested task addresses the reviews on the PR's branch: the builder gets them as feedback, the factory reviewer judges against them, every gate runs again, and the same PR is updated with a comment saying what was addressed"
  spec_refs:
    - "docs/plans/pr-review-rework.md#design"
    - "docs/architecture.md#ci-failures"
  depends_on:
    - pr-review-rework-t03
  non_goals:
    - "Editing factory/prompts/*.md: the review-rework instructions go in the brief and in the role messages in factory/agents.py"
    - "Relaxing or skipping any gate for a review rework"
    - "Resolving review threads, replying inside threads, or requesting a re-review"
    - "Addressing failing CI in the same rework: CI is judged again on the new head"
    - "Changing what the reviewer or builder sees for CI fixes or conflict resolutions"
  acceptance:
    - "A changes_requested task without --force runs a Rework of kind human_review. Its stacked PR is restacked first when a dependency merged or moved, and the run stops if that ends in conflict. The reviews are then read again: a PR head that isn't the candidate is refused with the someone-pushed message; with no request left, the task goes to pr_open, `TASK: no review requests changes on <url>; nothing to address` is printed and no agent runs. Otherwise the build starts at the candidate on the PR's branch, and the planner doesn't run"
    - "The task's runs record a `human_review` run (outcome changes_requested, the brief as its report) before build, review, verify and pr. `factory show TASK --role human_review` shows it"
    - "The builder gets the brief as feedback on every attempt, and its commits end `(address review, attempt N)`. The reviewer's message carries the brief: the review's requests are in scope, and any request left unaddressed is a reason for VERDICT: CHANGES"
    - "When the gates pass, the push is leased on the old candidate. The PR gets the comment `Addressed review by @login on <old>: <the builder's final message>. Candidate <old> → <new>; review and gates ran on <new>.` and a `**Review addressed**` line in its body, and reviews_addressed advances to the highest review id in the brief, so a refresh with the same reviews leaves the task pr_open"
    - "When the builder's first attempt changes nothing, nothing is pushed: its final message goes on the PR as a comment (an answer), the reviews count as addressed, and the task goes back to pr_open"
    - "When the rework fails, the task is failed, the PR keeps its old head, and the note says the reviews are still unaddressed and that running the task again rebuilds it from scratch. --force on a changes_requested task rebuilds from scratch, as on any open PR"
    - "Plan runs start changes_requested tasks as they start ci_failed ones"
    - "docs/sessions/<today>.md has an entry for this task"
  verification:
    - "uv run pytest -q tests/test_pipeline.py::test_requested_changes_are_addressed_on_the_pr_branch_then_reviewed_and_gated tests/test_pipeline.py::test_a_review_that_needs_no_change_is_answered_and_the_pr_left_as_is tests/test_pipeline.py::test_review_rework_needs_an_outstanding_request_on_the_factorys_candidate tests/test_pipeline.py::test_failed_review_rework_leaves_the_pr_alone tests/test_pipeline.py::test_requested_changes_on_a_stacked_pr_are_addressed_after_the_restack"
    - "uv run pytest -q tests/test_scheduler.py::test_a_pr_with_requested_changes_runs_again_to_address_them"
  risk: high

- id: pr-review-rework-t05
  goal: "docs/architecture.md, docs/reference.md, NEXT.md and the shipped factory-ops skill describe the changes_requested status and review reworks"
  spec_refs:
    - "docs/plans/pr-review-rework.md#design"
    - "docs/architecture.md#ci-failures"
  depends_on:
    - pr-review-rework-t04
  non_goals:
    - "Changing code or tests"
    - "Editing the installed skill copies under .claude/skills or .agents/skills: `factory init --force` refreshes them"
    - "Rewriting sections unrelated to review reworks"
  acceptance:
    - "docs/architecture.md: the lifecycle state diagram has the changes_requested transitions, and a `## Review comments` section after `## CI failures` has a flowchart and bullets on what triggers a rework, the latest review winning, requests being in scope while the gates still decide, the no-change answer, a failed rework, someone else pushing, stacked PRs and take-up. Known limitations gain one bullet: take-up treats earlier reviews as addressed"
    - "docs/reference.md: the `factory run TASK`, `factory status` and `factory show` command rows mention changes_requested and `--role human_review`, and the Troubleshooting table has rows for changes_requested, a rework that failed, and a review answered without a change"
    - "NEXT.md marks item 1 done in its table with a link to docs/architecture.md#review-comments, and leaves the other items as they are"
    - "factory/templates/skills/factory-ops/SKILL.md lists changes_requested among the statuses and in its description, has a review-comments bullet under How it works, and has a row in Requests and answers. references/troubleshooting.md has rows for changes_requested, a rework that failed, and a review answered without a change"
    - "docs/sessions/<today>.md has an entry for this task"
  verification:
    - "grep -q '^## Review comments' docs/architecture.md"
    - "grep -q 'changes_requested' docs/reference.md"
    - "grep -q 'docs/architecture.md#review-comments' NEXT.md"
    - "grep -q 'changes_requested' factory/templates/skills/factory-ops/SKILL.md"
    - "grep -q 'changes_requested' factory/templates/skills/factory-ops/references/troubleshooting.md"
    - "uv run pytest -q tests/test_templates.py"
  risk: low
```

Planned test additions:

| Task | Test | Kind |
|---|---|---|
| t01 | none new: `tests/test_ci.py`, and in `tests/test_pipeline.py` `test_failing_ci_is_fixed_on_the_pr_branch_then_reviewed_and_gated`, `test_ci_is_judged_only_on_the_factorys_candidate`, `test_failed_ci_fix_leaves_the_pr_alone`, `test_ci_failure_of_a_stacked_pr_whose_dependency_merged_is_restacked_not_fixed` (all existing, unmodified) | regression |
| t02 | `tests/test_reviews.py` (new file): the six tests named in its verification | unit |
| t03 | `tests/test_pipeline.py`: the five refresh tests named in its verification; `tests/test_scheduler.py::test_dependents_wait_while_changes_are_requested`; `tests/test_requeue.py::test_requeue_leaves_a_pr_with_requested_changes_alone` | CLI end to end, unit |
| t04 | `tests/test_pipeline.py`: the five rework tests named in its verification; `tests/test_scheduler.py::test_a_pr_with_requested_changes_runs_again_to_address_them` | CLI end to end, unit |
| t05 | none new: `tests/test_templates.py` (existing) | regression |

Every verification names its tests by node id or by a `-k` expression that matches existing tests. A missing node id fails with exit 4, and a filter that selects nothing fails with exit 5.

**Prerequisites for every task** (the factory builds this plan on its own repository):

1. **Warm the sandbox's uv cache once.** The sandbox is offline, and its cache (`~/.local/share/factory/software-factory/cache/uv`) starts empty, so `uv run pytest` can't install the dependencies. Run `UV_CACHE_DIR=~/.local/share/factory/software-factory/cache/uv uv sync` in the checkout, and again whenever `uv.lock` changes. Checked on 2026-10-31: with a warm cache the whole suite (153 tests, including the nested-bwrap pipeline tests) passes inside the factory's sandbox on a fresh worktree; with the empty cache, `uv sync` fails offline on `zstandard`.
2. **Commit the factory setup, the docs reorganisation and this plan to `main` first** (`.factory/`, `docs/` including `architecture.md` and `reference.md`, the README split, `AGENTS.md`, the skills, and the NEXT.md link to this plan). Worktrees start from origin's `main`, so the agents can read the plan's Design and the docs only once they are there, and t05's doc edits would otherwise conflict with the uncommitted versions.
3. **Run the factory from the checkout:** `uv run factory …`, since it isn't installed on PATH. Keep the checkout on `main` and don't pull while a plan run is going: the running factory is this checkout's code.

### Risks

1. **The factory changes the pipeline that runs it.** A merged task changes the factory code that the next `factory run` uses. **Action:** run from the main checkout, merge bottom-up, and after each merge pull, run `uv run pytest -q`, then `uv run factory status --refresh` before running the next task.
2. **Accidental reworks from the author's own comments.** Under the locked trigger, an "LGTM" review or a thread reply by the PR author is a request. **Action:** a first attempt that changes nothing is answered with a PR comment, and the reviews count as addressed (t04). No push, no `failed` task, and no loop of plan runs paying for reworks.
3. **"The human's ask wins" stretches a task's scope.** The factory reviewer would otherwise flag requested edits as unrelated. **Action:** the brief and the reviewer's message state the requests are in scope (t04 asserts this in the reviewer's transcript), and the gates are untouched: a request that a gate forbids, such as editing the plan, fails the rework, and the human does it by hand.
4. **Watermarks are local, and a take-up loses outstanding requests.** Another board, or a board reset, doesn't know which reviews were addressed. **Action:** take-up treats earlier reviews as addressed, which is conservative: no surprise spend. t05 documents it under Known limitations; leaving a new review triggers a rework.
5. **The user's uncommitted edits to `factory/prompts/{builder,reviewer}.md`** (model swaps) would collide with any task that edits those files. **Action:** t04's non-goals keep the prompts untouched; the review-rework instructions go in `agents.py` messages and the brief.
6. **More `gh` calls on every refresh.** Each open PR now needs the PR, its reviews and per-reviewer permissions. **Action:** reviews are read only for PRs whose head is the factory's candidate, permissions are looked up once per reviewer per fetch, and inline comments are fetched only when a rework runs.

---

## Problem

Once a task is `pr_open`, a human review that asks for changes has nowhere to go. Today you fix it by hand, or `factory run TASK --force` rebuilds from scratch and throws the work away.

- `status --refresh` (`factory/cli.py:369`) reads each PR's `state`, `mergeable` and `statusCheckRollup` through `_pr_state` (`factory/cli.py:300`), and never reviews.
- The only way to build on an open PR's head is the CI fix: `pipeline.CiFix` (`factory/pipeline.py:47`), entered at the `ci` node (`factory/pipeline.py:278`), set up by `cli._ci_fix` (`factory/cli.py:274`) and branched on in `cmd_run_one` (`factory/cli.py:168`), `build`, `pr` and `pr_body`. A second kind of rework would duplicate every one of those branches.
- The factory reviewer sees only the contract and the diff (`factory/agents.py:295`). It can't tell whether a human's requests were addressed, and it would flag them as unrelated edits.
- Board statuses (`factory/db.py:16`), plan-run starts (`factory/scheduler.py:56`), restacks (`factory/stack.py:78`) and requeue (`factory/cli.py:634`) know `conflict` and `ci_failed`, but not a PR a human asked to change.
- The roadmap's sketch (NEXT.md item 1) keys on `reviewDecision == CHANGES_REQUESTED`. GitHub doesn't let a PR's author request changes on their own PR, and the factory opens PRs as the maintainer, so on a solo repository that signal never fires.

## Goal

A human reviews a factory PR on GitHub, and `factory status --refresh` marks it `changes_requested`. `factory run` (task or plan) then addresses the review on the PR's branch, with the factory's review and every gate run again, and updates the same PR with a comment saying what was addressed. Merging stays the human approval.

## Design

### Lifecycle

```text
pr_open ──refresh: a review requests changes──▶ changes_requested
   ▲                                               │  │  │
   │◀──refresh: approved or dismissed, or someone──┘  │  │
   │   else pushed to the branch                      │  │
   │◀──factory run: the builder changed nothing ──────┘  │   (answer posted, reviews addressed)
   │                                                     │
   │◀──factory run: human_review → build ⇄ review → verify → push (leased) → comment
   │
changes_requested ──refresh: conflicting──▶ conflict          (conflicts come first)
changes_requested ──factory run fails──▶ failed               (PR untouched)
ci_failed ──refresh: a review requests changes──▶ changes_requested
```

### Which reviews count (`factory/reviews.py`, t02)

| Reviewer | Review | Counts as a request? |
|---|---|---|
| The PR's author | any submitted review (COMMENTED, incl. a single inline comment) | yes |
| Write or admin permission | latest of their APPROVED, CHANGES_REQUESTED or DISMISSED reviews is CHANGES_REQUESTED | yes |
| Write or admin permission | APPROVED or DISMISSED after a request | clears the request |
| Write or admin permission | COMMENTED | no (content still goes in the brief) |
| Read, triage, none | anything | never |
| Anyone | conversation (issue) comments, including the factory's own | never read |

Only **unaddressed** reviews count: those with an id above the task's `reviews_addressed` watermark (GitHub review ids increase over time). The watermark advances when a rework pushes, or when a rework answers without a change.

Why a watermark and not "reviews on the current head": restacks and conflict resolutions push new heads that carry the same change, and the human's request still applies to them. GitHub's own `reviewDecision` stays `CHANGES_REQUESTED` after a push until the reviewer reviews again, so reading it directly would rework in a loop.

`gh api` REST endpoints, which work on Ubuntu's gh 2.4 as `ci.job_log` does:

```text
gh api repos/{owner}/{repo}/pulls/N                               → .user.login (the PR's author)
gh api --paginate 'repos/{owner}/{repo}/pulls/N/reviews?per_page=100'
      → [{id, user{login}, state, body, commit_id, submitted_at}]
gh api repos/{owner}/{repo}/collaborators/LOGIN/permission         → {permission: admin|write|read|none}
gh api --paginate 'repos/{owner}/{repo}/pulls/N/comments?per_page=100'   (brief only)
      → [{id, pull_request_review_id, path, line, original_line, body, user{login}, in_reply_to_id}]
```

`--paginate` prints one JSON array per page, back to back, so the parser must read concatenated arrays.

### Refresh precedence (t03)

For a task in `pr_open`, `ci_failed` or `changes_requested` with an open PR:

1. `MERGED` → `merged`; `CLOSED` → `abandoned` (as now).
2. GitHub reports it conflicting (a non-stacked PR) → `conflict` (as now).
3. Head ≠ candidate → leave the reviews and CI to whoever pushed; a `changes_requested` or `ci_failed` task goes back to `pr_open` with a note.
4. Reviews request changes → `changes_requested`.
5. A `changes_requested` task with no request left → `pr_open`.
6. CI, as now.

Restacks keep `changes_requested`, unlike `ci_failed`, whose new head goes back to `pr_open` for CI to judge.

### One rework path (t01, t04)

```python
@dataclass
class Rework:                     # an open PR, built on its head, then reviewed and gated again
    kind: str                     # "ci" (t01) | "human_review" (t04): the run role, and the wording below
    old_candidate: str            # the PR head: where the build starts, and what the push is leased on
    what: tuple[str, ...]         # failing checks' names, or reviewers' logins
    brief: str                    # the builder's feedback, kept in view on every attempt
    through: int | None = None    # human_review: the highest review id the brief covers
```

The kind-specific text (commit suffix, no-change feedback, PR comment, PR body line, failure note, log fragment) lives in one table keyed by `kind`. t01 must reproduce today's CI strings exactly.

### A review rework (t04)

- **Entry:** `cmd_run_one` on `changes_requested` mirrors `ci_failed`: restack if a dependency moved, then read the reviews again (`_review_fix`, next to `_ci_fix`), then a worktree at the candidate on `factory/<task>`. The planner doesn't run: the plan comes from `db.last_report(task, "plan", "done")`.
- **Builder:** the brief as feedback (`# Address review`, then each review, then `path:line: body` comments).
- **Reviewer:** `Ctx` gains the rework brief, and `LangChainRoles.review` appends it to the reviewer's message: the human review is in scope, and an unaddressed request means `VERDICT: CHANGES`. This is set for `human_review` reworks only.
- **No change on the first attempt:** it goes to a reply step instead of a retry. The builder's final message (without its `RESULT:` line) is posted as a PR comment, `reviews_addressed = through`, and the status is `pr_open`. Nothing is pushed.
- **Success:** a leased push, the comment, the body line and the watermark advance. Then `pr_open`; CI runs on the new head.

Example brief:

```text
# Address review

This task's PR (https://github.com/o/r/pull/12) is open, and its reviewer, who approves the merge, asked for
changes on 3f2a9c1e0b7d. The worktree is the PR's branch at that commit. Do what each review asks, even where
it goes beyond the plan, the task's goal or its non-goals. Where a comment asks a question, answer it in your
final message, and change code only if the answer calls for it.

## Review by @alice (CHANGES_REQUESTED, on 3f2a9c1e0b7d)

Please don't swallow the error here.

- factory/ci.py:61: return the stderr instead of ''
- factory/ci.py:58 (outdated, was line 55): nit: name this `log_tail`
```

## Files Changed

| File | Change |
|---|---|
| `factory/pipeline.py` | `Rework` replaces `CiFix` (t01); the `human_review` kind, the reply step, comment and body, reviewer context (t04) |
| `factory/cli.py` | Run path on `Rework` (t01); refresh precedence, `_adopt` watermark, run refusal (t03); `_review_fix`, the `--role human_review` choice, failure note, watermark advance (t04) |
| `factory/ci.py` | Docstring names `Rework` (t01) |
| `factory/reviews.py` | New: fetch, requests, brief (t02) |
| `factory/db.py` | `changes_requested` status, `reviews_addressed` column (t03); `human_review` in `ROLES` (t04) |
| `factory/agents.py` | `Ctx` rework brief; the reviewer's message carries it (t04) |
| `factory/observe.py` | Glyph, counter, detail line (t03) |
| `factory/scheduler.py` | Summary lists it (t03); `startable` includes it (t04) |
| `factory/stack.py` | `restack` moves `changes_requested` PRs and keeps the status (t03) |
| `tests/conftest.py` | Fake `gh`: PR, reviews, review comments, permission endpoints (t02) |
| `tests/test_reviews.py` | New (t02) |
| `tests/test_pipeline.py`, `tests/test_scheduler.py`, `tests/test_requeue.py` | New tests (t03, t04) |
| `docs/architecture.md`, `docs/reference.md`, `NEXT.md`, `factory/templates/skills/factory-ops/SKILL.md`, `factory/templates/skills/factory-ops/references/troubleshooting.md` | Docs (t05) |
| `docs/sessions/<date>.md` | An entry per task (all) |

## Test Plan

### Unit tests

`tests/test_reviews.py` (t02), driving the pure functions with review dicts and `fetch` and `brief` through the fake `gh`:

- `test_change_requests_count_only_from_reviewers_with_write_access`: CHANGES_REQUESTED from write and admin counts; from read, triage and none it doesn't.
- `test_any_review_by_the_pr_author_requests_changes`: the author's COMMENTED review (and a single inline comment) counts; PENDING doesn't.
- `test_each_reviewers_latest_decision_wins`: request then approve → none; request then dismissed → none; approve then request → one; request then a COMMENTED review → still one.
- `test_addressed_reviews_no_longer_count`: reviews at or below the watermark are ignored, and NULL counts as 0.
- `test_fetch_reads_the_pr_reviews_and_permissions_through_gh_api`: the exact `gh api` calls, one permission lookup per reviewer, pagination, and None on a gh failure.
- `test_brief_lists_review_bodies_and_inline_comments_by_path_and_line`: the heading and the in-scope sentence, each review's header and body, `path:line: body`, outdated lines, replies, the cap.

`tests/test_scheduler.py`: `test_dependents_wait_while_changes_are_requested` (t03) and `test_a_pr_with_requested_changes_runs_again_to_address_them` (t04). `tests/test_requeue.py`: `test_requeue_leaves_a_pr_with_requested_changes_alone` (t03).

### End-to-end tests

Through the real CLI, LangGraph pipeline, git, bwrap and a bare origin, with the fake `gh` and the `ScriptedModel` (`tests/test_pipeline.py`):

- t03 `test_a_review_requesting_changes_marks_the_task_on_refresh`: a teammate's request → `changes_requested`, with the stderr line, the glyph and the counter; a read-only user's request is ignored; the teammate's approval → `pr_open`; the author's comment review → `changes_requested`; the factory's own conversation comments change nothing.
- t03 `test_conflicts_come_before_requested_changes_and_requested_changes_before_ci`.
- t03 `test_reviews_on_a_head_someone_else_pushed_are_left_to_them`.
- t03 `test_a_stacked_pr_keeps_its_requested_changes_when_restacked`.
- t03 `test_a_taken_up_pr_treats_earlier_reviews_as_addressed`.
- t04 `test_requested_changes_are_addressed_on_the_pr_branch_then_reviewed_and_gated`: the runs after `pr opened` are `human_review/changes_requested, build/committed, review/APPROVE, verify/pass, verify/report, pr/opened`; no planner; the new candidate's parent is the old one; the builder's and reviewer's transcripts contain the brief and the `path:line` comment; the commit suffix, the PR comment and the body line; one `pr create`; a second refresh leaves it `pr_open`.
- t04 `test_a_review_that_needs_no_change_is_answered_and_the_pr_left_as_is`: no push, the comment holds the builder's answer, `pr_open`, and the next refresh doesn't re-mark it.
- t04 `test_review_rework_needs_an_outstanding_request_on_the_factorys_candidate`: approved between refresh and run → `pr_open` with no agent; someone pushed → refused.
- t04 `test_failed_review_rework_leaves_the_pr_alone`.
- t04 `test_requested_changes_on_a_stacked_pr_are_addressed_after_the_restack`.

## Verification

- Each task: its contract's verification commands, then the factory's gates (`uv run pytest -q`, session log, plan untouched, conflict markers).
- After t04 merges, on a scratch repository with the factory's own `gh` login: open a factory PR, leave a review with an inline comment as the PR's author, run `uv run factory status --refresh` (the task shows `changes_requested`), then `uv run factory run TASK`. The PR gets a new head, a comment naming what was addressed, and goes back to `pr_open`. Approving from a second account with write access after a request clears it on refresh.

## Cross-Workstream Coordination

- **Depends on:** the CI-failure rework (merged in #3), which t01 generalizes. No other plan exists yet.
- **Required by:** NEXT.md item 4, "Learn from feedback", which collects human review comments. It also depends on item 3, "Measure the factory". When those are planned, their plans link back here.

## Notes / Out of Scope

- **CI and review feedback in one rework.** A `changes_requested` PR whose CI also fails gets the review rework, and CI is judged again on the new head. Combining both briefs into one rework is a later optimization.
- **Resolving threads, replying in threads, requesting re-review.** Left to the human, as NEXT.md suggests.
- **Conversation (issue) comments as feedback.** Only reviews and their inline comments are read. A slash-command trigger (`/factory …`) was considered and not chosen.
- **Watermarks across boards.** Each board keeps its own. A shared record, for example a marker in the factory's PR comment, waits for NEXT.md item 6 (a shared board) or for the two-boards limitation to be addressed.
- **Changing the role prompts** (`factory/prompts/*.md`) to describe review reworks. The instructions live in the brief and the role messages until the user's uncommitted model edits to those files are settled.
