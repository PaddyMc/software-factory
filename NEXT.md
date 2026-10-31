# Factory: what's next

Gaps found by comparing the factory with similar projects (2026-10-31). This list is not backlog: executable work is a task contract in a repository's plans. Smaller known limitations (the reviewer runs before the gates, context cost, the builder re-exploring what the planner read, two boards running one task) are in the [Known limitations](docs/architecture.md#known-limitations-and-next-steps).

| # | Gap | Effort | Depends on |
|---|---|---|---|
| ✓ | Read CI on open PRs and fix failures. Done: [CI failures](docs/architecture.md#ci-failures) | — | — |
| 1 | Act on human PR review comments. Planned: [pr-review-rework](docs/plans/pr-review-rework.md) | medium | — |
| 2 | The builder writes the test that judges it | small | — |
| 3 | Nothing measures the factory itself | medium | — |
| 4 | Learn from feedback | medium | 1, 3 |
| 5 | Steer a running agent | small | — |
| 6 | Runs need this machine | large | a shared board |

## 1. Act on human PR review comments

**Gap.** Once a task is `pr_open`, a human review that asks for changes has nowhere to go. You fix it by hand, or `--force` rebuilds from scratch and throws the work away.

**Seen in.** [agent-orchestrator](https://github.com/ComposioHQ/agent-orchestrator) sends review comments back to the worker that owns the branch. [oz-for-oss](https://github.com/warpdotdev/oz-for-oss) re-runs its reviewer on every push.

**Sketch.** Use the same shape as the CI fix:
- `status --refresh` reads `reviewDecision`. On `CHANGES_REQUESTED` it marks the task `changes_requested`. Count only reviews from users with write access, posted after the current head was pushed.
- The run builds on the PR's head. Its feedback is the review bodies plus the inline comments (`gh api repos/{owner}/{repo}/pulls/N/comments`, as `path:line: body`). Then review, gates, and a push leased on the old head.
- Merge `CiFix` into one `Rework(old_candidate, label, brief)` that both paths use, so the pipeline keeps a single "build on the PR head" entry point.
- Post a comment saying what was addressed. Leave resolving threads to the human.

**Plan.** [docs/plans/pr-review-rework.md](docs/plans/pr-review-rework.md) (planned 2026-10-31, tasks `pr-review-rework-t01`…`t05`). Decisions the plan locked differ from this sketch:
- Any review by the PR's author counts as a request too, since GitHub won't let the author request changes on their own PR (the factory opens PRs as you). Conversation comments, the factory's own included, never count.
- The latest review wins: an approval or a dismissal after a request cancels it.
- A per-task watermark of addressed reviews replaces "posted after the current head was pushed", so restacks and conflict resolutions keep a pending request.

## 2. The builder writes the test that judges it

**Gap.** `e2e_written` only checks that a new `#[test]` exists. Whether that test proves the acceptance criteria is the LLM reviewer's call. A test that passes without the change proves nothing.

**Seen in.** [StrongDM's software factory](https://simonwillison.net/2026/Feb/7/software-factory/) keeps its acceptance scenarios outside the codebase, where agents can't see them.

**Sketch.** Add a deterministic gate, `e2e_fails_without_change`:
- In a scratch worktree at the candidate, restore every non-test path to the base.
- Run the new e2e tests by name, as the configured `e2e` gate does. The gate passes only when they fail; a compile failure counts as failing.
- It costs one more e2e run per verify, and it fits the "gates decide" rule.

Later, holdout tests could be written at plan time by `/plan-workstream` and kept out of the worktree. That needs a contract schema change (a 9th key), so lock it as a decision first.

## 3. Nothing measures the factory itself

**Gap.** The test suite drives a `ScriptedModel`, so it checks plumbing, not prompts or models. There is no way to tell whether an edit to a role prompt (`factory/prompts/`, or a repository's `.factory/agents/` override), or a model swap, made runs better or worse.

**Seen in.** Ona publishes [daily metrics](https://ona.com/stories/building-a-software-factory-in-public) (PRs merged, coverage, CI health). Arize wrote up [a software factory that tests its own prompts](https://arize.com/blog/how-to-build-a-software-factory-that-tests-its-own-prompts.md).

**Sketch.**
- **`factory stats [--since DATE] [--plan P]`**, from `tasks` and `runs`. The data is already there for:
  - first-attempt pass rate and builds per PR;
  - cost per merged PR;
  - gate failures by gate;
  - reviewer `CHANGES` rate;
  - step-limit stops;
  - conflict and `ci_failed` rates.

  Break it down by role model. The one thing missing is whether the human changed a PR before merging it; record that at refresh by comparing the merged tree with the candidate.
- **`factory bench`**: replay a fixed set of merged tasks from their original bases with `--no-pr`, in a throwaway `FACTORY_HOME`, with a given `--model`, `models:` setting or prompt override. Compare gate results, attempts and cost against a stored baseline. Run it before merging changes to role prompts.

## 4. Learn from feedback

**Gap.** Reviewer findings, gate failures and human comments repeat across tasks, but nothing feeds them back into the role prompts.

**Seen in.** [oz-for-oss](https://github.com/warpdotdev/oz-for-oss) proposes skill updates from maintainer feedback.

**Sketch.** `factory learn` collects the last N runs' reviewer `CHANGES` findings, gate failures and (with item 1) human review comments. An agent proposes a diff to the role prompts, which goes out as a PR and is never applied directly. `factory bench` (item 3) shows whether it helps. Without item 3 this is guesswork, so build that first.

## 5. Steer a running agent

**Gap.** You can watch a run (`top`, `logs -f`) or stop it, but you can't redirect a builder that's heading the wrong way.

**Seen in.** [Open SWE](https://blog.langchain.com/introducing-open-swe-an-open-source-asynchronous-coding-agent) lets you interrupt and nudge a task without restarting it.

**Sketch.** `factory say TASK "…"` appends to `$FACTORY_HOME/inbox/TASK`. A `before_model` middleware in `agents.py` drains the inbox into a `HumanMessage` on the agent's next step and records it in the transcript. The message goes to whichever role is running. It's cheap to build, and it doesn't touch the pipeline.

## 6. Runs need this machine

**Gap.** Runs need this machine on. agent-orchestrator and Open SWE run in hosted workspaces.

**Sketch.** First, a shared board: state in a server database (Postgres, say) instead of the local SQLite file, so agents run on a cloud box while you watch from the laptop. Keep the offline bubblewrap sandbox. The box needs dependencies fetched ahead of time, since the sandbox is offline, and its own `gh` login. Lowest priority: local runs are a deliberate trade for the offline sandbox.
