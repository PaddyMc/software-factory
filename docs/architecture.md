# Architecture

How the factory takes a task contract to a pull request. To install and run it, see the [README](../README.md); for configuration, contracts and commands, see the [reference](reference.md).

---

## Policy

- **Merging is the approval.** Agents never merge, push, commit to your checkout, or see secrets; a passing check alone approves nothing. Branch protection is a GitHub setting you own.
- **Gates decide.** A PR is opened only when every deterministic gate passes at the exact candidate commit. The verifier agent writes the PR report; it can't override a gate.
- **Isolation.** Agent commands and gates run under bubblewrap: read-only host, empty `$HOME`, `/tmp` and `/run`, cleared environment, no network unless asked. File tools stay in the worktree (reads also reach `dependency_sources`), and never write `.git`.
- **Scope is the reviewer's call.** The builder may edit any file in the worktree; the contract's goal and non-goals bound the change, and unrelated edits are findings.
- **Settings come from the main checkout,** never from a task worktree, so an agent can't weaken its own gates or change its own prompt.

---

## Components

```mermaid
flowchart TB
  Plans["plans (config: plans)<br/>task contracts"]:::repo
  Config[".factory/config.yaml<br/>project settings"]:::repo
  CLI["factory CLI · cli.py<br/>run · top · status · trace"]:::you
  Contracts["contracts.py<br/>parse + validate"]:::core
  Sched["scheduler.py<br/>one plan, --parallel"]:::core
  Pipe["pipeline.py · outer loop (LangGraph)<br/>plan → build → review → verify → PR"]:::core
  Roles["prompts/*.md<br/>role prompts (override: .factory/agents/)"]:::core
  Agents["agents.py · inner loop (LangChain)<br/>planner · builder · reviewer · verifier"]:::core
  Gates["gates.py<br/>deterministic checks"]:::core
  Tools["tools.py<br/>read · write · run · git_diff"]:::core
  Sandbox["sandbox.py<br/>bubblewrap, offline"]:::core
  OR["OpenRouter<br/>model API"]:::ext
  GH["GitHub<br/>branch + PR"]:::ext
  WT["worktrees/TASK<br/>git worktree"]:::state
  DB[("factory.db<br/>tasks + runs")]:::state
  Files["logs/ + transcripts/"]:::state
  Obs["observe.py<br/>dashboards"]:::core
  Merge["you review + merge"]:::you

  Plans --> Contracts --> CLI
  Config --> CLI
  CLI --> Sched -->|"one child run per task"| Pipe
  CLI --> Pipe
  Roles --> Agents
  Pipe --> Agents
  Pipe --> Gates
  Agents <-->|"prompts / replies"| OR
  Agents --> Tools --> Sandbox
  Gates --> Sandbox
  Sandbox --> WT
  Pipe -->|"commit, push, gh pr"| GH --> Merge
  Pipe --> DB
  Agents -.->|"log, progress, transcript"| Files
  Merge -.->|"status --refresh<br/>(restacks dependents)"| DB
  DB --> Obs
  Files --> Obs

  classDef you fill:#fde68a,stroke:#b45309,color:#111
  classDef repo fill:#e0e7ff,stroke:#4338ca,color:#111
  classDef core fill:#dcfce7,stroke:#15803d,color:#111
  classDef state fill:#f3f4f6,stroke:#4b5563,color:#111
  classDef ext fill:#fce7f3,stroke:#be185d,color:#111
```

Colours:
- **yellow:** you;
- **blue:** your repository's inputs;
- **green:** factory code;
- **grey:** local state (`$FACTORY_HOME`);
- **pink:** external services.

Dotted lines are observability data, not control flow.

| Layer | Module | Responsibility |
|---|---|---|
| Entry | `cli.py` | Commands, pre-run checks (contract valid, factory-runnable, API keys present, dependencies merged or with open PRs), worktree setup, `status --refresh`, `init` and `config` |
| Settings | `config.py` | Load and validate `.factory/config.yaml` from the **main checkout** (never a task worktree, so an agent can't weaken its own gates) |
| Flows | `flows.py` | Parse and validate named flows from `flows:` (step kinds, names, models, step limits and order rules), hold the built-in `default` flow, and insert a gates step when one is omitted |
| Contracts | `contracts.py` | Read the fenced YAML in plans into `Task` objects (8 keys). Validate schema, IDs, dependencies across plans, command selection, placeholders |
| Scheduling | `scheduler.py` | Run one plan's tasks as child `factory run` processes, up to `--parallel`. A task starts once each dependency is merged or has an open PR |
| Stacking | `stack.py` | After a merge, rebase the PRs stacked on it onto the trunk and retarget them; edit PRs through the GitHub REST API |
| CI | `ci.py` | Read an open PR's checks at its head; the failing jobs' logs become the builder's feedback |
| Outer loop | `pipeline.py` | LangGraph state machine: plan → build → review → verify → PR / fail; resolve → review → verify for a conflicting PR; ci → build → review → verify for a PR whose CI fails. Commits the builder's work. Stops early when there is no progress |
| Inner loop | `agents.py` | One LangChain `create_agent` per role: loads the role prompt (the repository's override, else the shipped one), builds the system prompt (role + contract + project rules + repository guidance), streams steps, counts tokens and cost, records the transcript |
| Tools | `tools.py` | `read_file`, `list_dir`, `grep` (the worktree, plus `dependency_sources` read-only), `git_diff`, `write_file`/`edit_file` (anywhere in the worktree except `.git`), `run` (sandboxed; denied commands refused) |
| Checks | `gates.py`, `verification.py` | Conflict markers, plan untouched, and the configured session-log, e2e, unit and verification checks. Zero tests selected counts as failed |
| GitHub | `github.py` | Which identity: a `GH_TOKEN`/`GITHUB_TOKEN` when set (`gh` reads it; git's github.com fetches and pushes go over HTTPS with it), else the gh login and git's own credentials |
| Isolation | `sandbox.py` | bubblewrap: read-only host, empty `$HOME`/`/tmp`/`/run`, cleared environment, no network unless asked |
| State | `db.py` | SQLite `tasks` (status, branch, SHAs, PR, pid, heartbeat, activity, cost) and `runs` (every role step: outcome, report, steps, tokens, cost, refused calls, transcript path) |
| Observability | `observe.py`, `log.py`, `prices.py` | Dashboard, merged logs, traces, transcripts, liveness, OpenRouter cost |

---

## Lifecycle of one task

```mermaid
flowchart TD
  start(["factory run TASK"]) --> pre{"pre-run checks"}
  pre -->|"invalid contract, refused verification command, no API key, a dependency without a PR"| refused(["refused, nothing created"])
  pre -->|"ok"| setup["worktree factory/TASK from origin's copy of the current branch,<br/>or from the open PRs of its dependencies<br/>sandbox, log, db status queued"]
  setup --> plan["PLAN<br/>planner agent, read-only"]
  plan --> build["BUILD<br/>builder agent writes; the factory commits"]
  build --> review{"REVIEW<br/>reviewer verdict"}
  review -->|"CHANGES"| retry{"builds left and making progress?"}
  review -->|"APPROVE"| verify{"VERIFY<br/>gates at the candidate commit"}
  verify -->|"fail"| retry
  retry -->|"yes, with feedback"| build
  retry -->|"no"| failed(["failed, reason in factory show"])
  verify -->|"pass"| report["verifier agent writes the PR report"]
  report --> pr["git push + gh pr create"]
  pr --> open(["pr_open"])
  open -->|"you merge, then status --refresh"| merged(["merged; PRs stacked on it move onto the trunk"])
```

```mermaid
stateDiagram-v2
  [*] --> queued: factory sync / run
  queued --> planning
  planning --> building
  building --> reviewing
  reviewing --> building: changes requested
  reviewing --> verifying: approved
  verifying --> building: gates failed
  verifying --> pr_open: gates passed
  pr_open --> merged: you merge
  pr_open --> abandoned: PR closed
  pr_open --> conflict: status --refresh finds a conflict
  conflict --> building: factory run resolves it
  conflict --> merged: you merge
  pr_open --> ci_failed: status --refresh finds CI failing
  ci_failed --> building: factory run fixes it
  ci_failed --> pr_open: CI passes again, or a restack moves it
  ci_failed --> merged: you merge
  pr_open --> changes_requested: refresh finds a review requesting changes
  changes_requested --> pr_open: approved or dismissed, or someone else pushed
  changes_requested --> pr_open: factory run: the builder changed nothing (answered)
  changes_requested --> building: factory run addresses it
  changes_requested --> conflict: status --refresh finds a conflict (conflicts come first)
  changes_requested --> failed: the rework failed
  changes_requested --> merged: you merge
  ci_failed --> changes_requested: a review requests changes
  planning --> failed
  building --> failed
  reviewing --> failed
  verifying --> failed
  failed --> planning: factory run (plan or task) again
  merged --> [*]
```

What moves between agents is only what the pipeline hands over:

| From | To | What |
|---|---|---|
| Planner | Builder | The plan text |
| Reviewer (`VERDICT: CHANGES`) | Builder | The review, as feedback to address first |
| Gates (fail) | Builder | The failing gates' output, as feedback |
| Gates (pass) | Verifier | The gate table, for the PR report |
| CI (failing checks) | Builder | The failing checks and their jobs' logs, as feedback, on every attempt of a CI fix |

A build is retried up to `--max-attempts` times (default 3). The run stops earlier when the same gates fail with identical output twice in a row. A task that ends `failed` stays failed until you run it, or its plan, again; the rerun starts from a fresh worktree. `factory requeue TASK…` puts `failed` or `abandoned` tasks back to `queued` without running them.

---

## Merge conflicts

An open PR can stop applying to its base: another PR merged first and changed the same lines, or a stacked PR's dependency merged or moved. `factory status --refresh` finds both cases. It checks GitHub's `mergeable` for PRs on the trunk, and the restack rebase for stacked PRs. Either way the task becomes `conflict`. Running the task, or its plan, then resolves it instead of rebuilding:

```mermaid
flowchart TD
  c(["conflict"]) --> replay["worktree at the new base (origin's trunk, or the dependency's candidate)<br/>the PR's change replayed on it as one diff, uncommitted"]
  replay -->|"applies cleanly"| verify{"VERIFY: gates"}
  replay -->|"conflicts"| resolve["RESOLVE<br/>builder agent: conflicted files with diff3 markers,<br/>both sides' diffs, the task's original plan"]
  resolve --> review{"REVIEW"}
  review -->|"CHANGES"| build["BUILD with feedback"] --> review
  review -->|"APPROVE"| verify
  verify -->|"pass"| push["force-push with a lease on the old head<br/>update the same PR, comment old → new candidate"]
  verify -->|"fail"| build
  push --> open(["pr_open"])
```

- The planner doesn't run again: the builder gets the plan the PR was built from.
- A resolution is reviewed and gated like any build, and the `conflict_markers` gate fails on any `<<<<<<<`, `|||||||` or `>>>>>>>` line left in the diff. Only then is the PR updated. The push is leased on the PR's old head, so a commit someone pushed to the branch meanwhile is never overwritten.
- If the resolution fails, the PR keeps its old head and the task ends `failed`. Running it again rebuilds it from scratch on the trunk and updates the same PR. `factory run TASK --force` does the same straight away.
- Two open dependency PRs that conflict with each other are not resolved: the dependent waits until one merges (`cannot stack`).

---

## CI failures

The gates run before a PR opens. CI runs after, on every head the PR gets, including the rebased heads a restack pushes, which the gates never saw. CI can also check things the gates don't, such as formatting or lints. `factory status --refresh` reads each open PR's checks at its head (`gh pr view --json statusCheckRollup`). When a check fails on the factory's own candidate, the task becomes `ci_failed`. Running the task, or its plan, then fixes it:

```mermaid
flowchart TD
  r(["ci_failed"]) --> moved{"a stacked dependency merged or moved?"}
  moved -->|"yes"| restack["restack onto it: a new head, back to pr_open<br/>(the failure may have been the dependency's)"]
  moved -->|"no"| still{"CI still failing on the candidate?"}
  still -->|"no: re-run and passing, or running"| open(["pr_open, no agent runs"])
  still -->|"yes"| ci["CI: record the failing checks and their jobs' logs<br/>worktree = the PR's branch at the failing head"]
  ci --> build["BUILD<br/>builder: plan + failing checks + logs as feedback"]
  build --> review{"REVIEW"}
  review -->|"CHANGES"| build
  review -->|"APPROVE"| verify{"VERIFY: gates"}
  verify -->|"fail"| build
  verify -->|"pass"| push["force-push with a lease on the failing head<br/>update the same PR, comment old → new candidate"]
  push --> again(["pr_open; CI runs on the new head"])
```

- Only checks that ran on the factory's candidate count. If someone else pushed to the branch, the factory leaves the PR alone, and a `ci_failed` one goes back to `pr_open`. Cancelled, skipped and still-running checks don't count either.
- Logs come from GitHub Actions jobs, cut at the job's last `##[error]` line and capped at 8,000 characters each. Other checks only get their name and URL.
- The fix builds on the PR's head, not from scratch, so the planner doesn't run again. The gates measure the whole task diff against the PR's base, as before.
- A PR whose CI fails blocks its dependents, like a conflicting one: nothing new stacks on it until it's `pr_open` again.
- If the fix fails, the PR keeps its old head and the task ends `failed`. Running it again rebuilds it from scratch on the trunk and updates the same PR; `factory run TASK --force` does that straight away.

---

## Review comments

A human can review a factory PR on GitHub and ask for changes. `factory status --refresh` reads each open PR's reviews; a request from a reviewer with write or admin access, or any submitted review by the PR's author (on the factory's own candidate), marks the task `changes_requested`. Running the task, or its plan, then addresses the reviews on the PR's branch:

```mermaid
flowchart TD
  r(["changes_requested"]) --> restack{"a stacked dependency merged or moved?"}
  restack -->|"yes"| stack["restack onto it, keeping changes_requested<br/>the request still applies to the moved commits"]
  stack --> reread["re-read the reviews"]
  restack -->|"no"| reread
  reread --> ours{"head still the factory's candidate?"}
  ours -->|"no"| open(["pr_open; the reviews are left to whoever pushed"])
  ours -->|"yes"| left{"request still outstanding?"}
  left -->|"no"| open
  left -->|"yes"| build["BUILD<br/>builder: plan + the review brief as feedback"]
  build --> review{"REVIEW"}
  review -->|"CHANGES"| build
  review -->|"APPROVE"| verify{"VERIFY: gates"}
  verify -->|"fail"| build
  verify -->|"pass"| push["force-push with a lease on the old candidate<br/>update the same PR, comment what was addressed"]
  push --> open(["pr_open; CI runs on the new head"])
```

- **The latest review wins,** as on GitHub. Each counted reviewer's latest approval, request or dismissal decides, so an approval or a dismissal after a request clears it and returns the task to `pr_open`. Comment-only reviews from other reviewers neither request nor clear.
- **Requests are in scope, but the gates still decide.** The human is the approver, so the builder does what each review asks even where it goes beyond the plan, the goal or the non-goals, and the factory reviewer is told so. A request the gates forbid — editing the plan, failing a test — fails the rework and the human does it by hand.
- **A no-change answer.** When the builder's first attempt changes nothing, its final answer is posted on the PR as a comment, the reviews count as addressed, nothing is pushed, and the task returns to `pr_open`.
- **A failed rework** leaves the PR's old head and the task `failed`; the note says the reviews are still unaddressed. Running the task again rebuilds it from scratch and updates the same PR; `factory run TASK --force` does that straight away.
- **Someone else pushed.** A head that isn't the factory's candidate isn't the factory's to fix: the task goes back to `pr_open` and the reviews are left to whoever pushed.
- **Stacked PRs** keep `changes_requested` through a restack, so the request still applies to the moved commits, and are addressed after it — unlike a `ci_failed` head, whose restacked head goes back to `pr_open` for CI to judge.
- **Take-up.** A PR taken up from GitHub treats the reviews that existed at take-up as addressed (the watermark `reviews_addressed` starts at the latest review id), so a stale review never triggers a rework; a new one does.

---

## Running a plan: stacked PRs

`factory run <plan>` (a plan's file name without `.md`, or its path) runs every task of the plan that has no PR yet, in dependency order, up to `--parallel` at once. Each task runs as its own child `factory run <task> --quiet` process, so one crash never stops the others.

A task starts once each of its dependencies is **merged or has an open PR**. When a dependency's PR is still open, the task is **stacked** on it:

- its worktree starts from the dependency's candidate commit (several open dependencies are merged together first; if they conflict, the task waits until one merges);
- its PR targets `factory/<dependency>`, so the PR shows only the task's own changes;
- its gates measure the diff and the new e2e test against that base.

```text
main ── t01 ◆ PR #10 (base main)
          └── t02 ◆ PR #11 (base factory/t01)
                └── t03 ◆ PR #12 (base factory/t02)
       t04 ◆ PR #13 (base main, independent of the others)
```

Review and merge from the bottom of each stack up. After each merge, run `factory status --refresh`. It picks up the merge and moves every PR stacked on the merged one: the PR's own commits are rebased onto the trunk (or onto its moved dependency) and the PR is retargeted, with a comment saying which commit the gates ran on. GitHub doesn't retarget stacked PRs on its own unless the repository deletes head branches on merge, so refresh before merging the next PR in a stack.

The run ends when nothing more can start, and prints each task's outcome and the PRs in merge order. Run the plan again to continue: tasks with PRs are kept, failed tasks run again, and tasks that waited on them start once they have PRs. `abandoned` tasks (holds) are skipped. Tasks whose verification the factory refuses are reported as manual.

---

## Inside one agent: the loop

```mermaid
sequenceDiagram
  participant P as pipeline
  participant A as agent loop
  participant M as model (OpenRouter)
  participant T as tools + sandbox
  P->>A: system prompt (role file + contract + project rules + repo guidance) and task message
  loop every step, up to max_steps
    A->>M: the whole conversation so far
    M-->>A: reply
    alt reply asks for tools
      A->>T: run each tool call
      T-->>A: results, appended to the conversation
    else plain text
      A-->>P: final answer, which becomes the report
    end
  end
  Note over A,P: at max_steps the loop ends early and is logged as a step-limit stop
```

- **Context grows every step.** Each step re-sends the entire conversation. In practice 95–98% of tokens are re-read input, and output is small. `factory trace` shows the growth step by step.
- **Step limits.** Each step is 4 LangGraph nodes (call-limit hook, model, call-limit hook, tools). `ModelCallLimitMiddleware` enforces `max_steps`; the graph recursion limit (`4 × max_steps + 25`) is only a backstop.
- **Recoverable errors.** These come back to the model as results so the agent can adjust:
  - a write into `.git` or outside the worktree, or a denied command, returns `refused: …`;
  - a failing tool call returns `error: …`.

  Both are flagged with ⚠ in the log.
- **Provider errors.** Rate limits, out-of-credit and network blips are retried with backoff (about 30 s). After that the run fails with the provider's real error.

### Roles

| Role | Default model (OpenRouter) | `max_steps` | Tools | Decides |
|---|---|---|---|---|
| planner | `z-ai/glm-5.3` | 40 | read | The implementation plan |
| builder | `deepseek/deepseek-v4-pro-0813` | 120 | read, write anywhere in the worktree except `.git`, sandboxed `run` | The change, or a conflicting PR's resolution |
| reviewer | `z-ai/glm-5.3` | 60 | read, `git_diff` | `VERDICT: APPROVE` or `CHANGES` (missing verdict = CHANGES) |
| verifier | `deepseek/deepseek-v4-flash-0731` | 30 | read, `git_diff`, sandboxed `run` | Nothing: it writes the PR report; **the gates decide** |

Roles are **step kinds**: a flow step of kind `build` gets the builder's tools and default prompt whatever its name. Set models and step limits per kind with `models` and `max_steps` in `.factory/config.yaml`; `--model` overrides every step for one run. To replace a kind's whole prompt, put it in `.factory/agents/<planner|builder|reviewer|verifier>.md` (frontmatter `model` and `max_steps` optional); the config's settings still win over its frontmatter. Any `provider:model` that LangChain's `init_chat_model` supports works, with the provider's key in the environment (`OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`).

A **custom step** (a mapping step whose `name` differs from its `kind`) gets its own prompt from `.factory/agents/<name>.md` when that file exists, else its kind's prompt. Model precedence is `--model` > the step's `model` > `models[kind]` > prompt frontmatter > the default; step-limit precedence is the step's `max_steps` > `max_steps[kind]` > prompt frontmatter > 60.

The system prompt is assembled from four parts:
1. the role prompt, shipped in [`factory/prompts/`](../factory/prompts/) or overridden by the repository;
2. the contract;
3. a **Project rules** block generated from `.factory/config.yaml`, telling the agent what the gates will require (session log, e2e test, unit commands);
4. the repository's own guidance: the first file of `guidance` that exists (default `AGENTS.md`, then `CLAUDE.md`).

The shipped role prompts therefore carry no project specifics.

No agent can commit, push, call `gh`, run `factory`, or touch the database. The pipeline does those things outside the sandbox.

---

## Agent flows

A **flow** is a named, ordered list of agent steps under `flows:` in `.factory/config.yaml`; `flow:` picks the default for runs. `factory run TASK|PLAN --flow NAME` overrides it for one run, and a plan run passes it to every child. The built-in `default` flow — plan, build, review, gates, verify — is today's pipeline and can't be redefined. A step is a kind string (`plan`, `build`, `review`, `verify`, `gates`) or a mapping with `kind` required and optional `name`, `model` and `max_steps` (`gates` itself is a bare string). A step's kind fixes its tools, task message and output, as the [Roles](#roles) table describes.

```mermaid
flowchart TD
  fresh(["fresh build"]) --> plan{"plan step in the flow?"}
  plan -->|"yes, once"| p["PLAN"] --> builds
  plan -->|"no"| builds
  rework(["rework entry: resolve | ci | human_review<br/>no plan step; build on the PR's head"]) --> builds
  subgraph attempt["attempt N"]
    builds["every build step in order<br/>each commits what it leaves"] --> checks{"review steps and the gates step<br/>in flow order"}
  end
  checks -->|"first CHANGES or gate failure"| feedback["next attempt with the feedback"] --> builds
  checks -->|"all passed"| verify{"verify step in the flow?"}
  verify -->|"yes"| report["VERIFY<br/>write the PR report"] --> push["push + PR"]
  verify -->|"no"| push
```

The order rules are:

```text
[plan]?   build+   ( review | gates )*   [verify]?
  once    contiguous  any order              last
```

The effective flow has exactly one gates step: when omitted, one is inserted after the last review step, else after the last build step. Step names are unique, match `^[a-z][a-z0-9-]*$`, and aren't reserved (`resolve`, `ci`, `pr`, `human_review`, `planner`, `builder`, `reviewer`, `verifier`); a step named after a kind must have that kind.

**How attempts end.** The first review step to return `CHANGES`, or a gates failure, ends the attempt; the next starts again at the first build step with that feedback (a custom reviewer's feedback is labelled ``Reviewer `NAME` requested changes``). Later build steps also see the earlier build steps' final messages from the same attempt. A no-change attempt ends with the no-change feedback, and no review or gates run. `--max-attempts` and the stop on identical gates failures are unchanged. When the gates pass, the run continues to the next review step if the flow puts reviewers after gates (gates-first), so those reviewers only see changes that passed the gates. Review and verify steps never commit, so the candidate the gates passed is the one pushed.

**Where reworks enter.** Conflict resolution, CI fixes and human-review reworks keep their fixed entry, skip the plan step and build on the PR's head; from there they run the flow's build steps, review steps, gates and verify step. The resolve agent uses the flow's first build step's model and step limit; a clean conflict replay goes straight to the gates. CI and human-review reworks keep the brief in view on every attempt, and every review step of a human-review rework gets the review brief.

**What runs record.** `runs.role` is still the kind: the gates run is role `verify`, step `gates`, and `resolve`, `ci`, `pr` and `human_review` keep their existing roles. The `runs.flow` and `runs.step` columns hold the flow and step names. `factory show TASK --step NAME` filters runs, and `factory show` labels each run with its flow and step; `factory top`'s progress label is the step name. The PR body has one `Reviewer report (<step>)` block per review step, a Verifier report only with a verify step, a Plan block only with a plan step, and a line naming the flow and its steps in order.

---

## Gates

They run in the sandbox against the exact candidate commit, in this order. Gates marked *configured* exist only when the project sets them up:

| Gate | Passes when |
|---|---|
| `clean` | Worktree HEAD is the candidate and the worktree has no uncommitted changes |
| `diff` | The candidate changes something. Changed `lockfiles` are noted |
| `conflict_markers` | No added line opens, splits or closes a merge-conflict hunk |
| `plan_untouched` | The task's plan doc was not edited |
| `session_log` *(configured)* | A `<session_log>/*.md` entry was added |
| `e2e_written` *(configured)* | A new test was added under `e2e.dir` |
| `verification` | Every command in the contract's `verification` passes |
| `unit_tests` *(configured)* | Every `unit_tests` command passes |
| `e2e_tests` *(configured)* | The new e2e tests pass by name (`run_new`), or the whole suite (`run_all`) with `--full-e2e` or when `run_all_when` matches |

A command that selects zero tests is **inconclusive, not a pass**. `factory gates <task> --ref <ref>` runs the same gates without agents, for reviewing hand-written work; `/review-task` builds on it ([skills](reference.md#skills)).

---

## Sandbox

Agent `run` calls and gate commands execute under bubblewrap (`sandbox.py`):

- The host filesystem is read-only.
- `$HOME`, `/tmp` and `/run` are empty, so ssh keys, gh and cloud tokens, and the docker socket are invisible. Only the configured `sandbox` binds reappear.
- The environment is cleared, then set from `sandbox.env`.
- Writable: the task worktree, `$FACTORY_HOME/cache` and the `rw_binds`.
- **No network** unless `--network` is passed (or `--network-for` in the scheduler), so dependencies must already be cached.

`--no-sandbox` exists for machines without bubblewrap and is unsafe.

---

## Development

Run the tests with `uv run pytest -q tests`.

- **`tests/test_pipeline.py`** drives the **real** CLI, LangGraph pipeline, LangChain agents and tools, git, bubblewrap, a bare `origin` and a fake `gh`. Only the model is replaced: `tests/fake_model.py` is a `ScriptedModel` that reads the system prompt to know which role it's playing.
- **Other suites** cover:
  - config, init and the shipped templates and skills;
  - contracts, dependencies and paths;
  - gates (Rust and Python e2e detection, unconfigured gates);
  - the sandbox, tools and the database;
  - observability, the agent loop, plan runs, stacking, PR take-up, conflict replay and CI fixes.
- **CI:** `.github/workflows/ci.yml`.

The agent interface is a single seam: a role receives a `Ctx` with `log`, `progress` and `record` callbacks and returns an `Output`. Replacing LangChain with another runner means implementing the `Roles` protocol in `agents.py`.

---

## Known limitations and next steps

- **The default flow reviews before the gates**, so its reviewer can approve builds that then fail mechanical checks. A flow can put the gates first; see [Agent flows](#agent-flows).
- **Context cost:** whole files stay in context for every later step. Planned: capped tool output, a slimmer system prompt, summarizing old steps.
- **The builder re-explores what the planner already read.** Planned: the planner hands over exact files and line ranges.
- **Conflicts and CI failures are found on refresh, not live.** GitHub computes `mergeable` lazily, so a PR that just started conflicting may show up one `status --refresh` later.
- **Restacked PRs aren't re-gated.** After a rebase the PR comment names the commit the gates ran on. CI runs on the new one, and a refresh marks it `ci_failed` if that fails.
- **A CI fix is gated, but the gates can't run CI's own checks.** The builder is told to reproduce each failure with `run`, and CI on the new head decides. A fix that doesn't hold shows up red again on the next refresh.
- **Two boards can run the same task at once.** Nothing claims a task across boards. Planned: a draft PR as the claim.
- **A PR stacked on several dependencies is taken up as stacked on the one it targets**, since the others are merged into its branch and the PR doesn't name them.
- **A PR taken up from GitHub treats the reviews that existed at take-up as addressed**; a watermarked review before the take-up never triggers a rework.
- **Linux only**: the sandbox is bubblewrap.
- **Branch protection** on your default branch is a GitHub setting; the factory and CI report, they don't enforce merges.

Gaps compared with similar projects, and what to build next: [`NEXT.md`](../NEXT.md).
