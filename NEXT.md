# Factory: what's next

Gaps found by comparing the factory with similar projects (2026-10-31). This list is not backlog: executable work is a task contract in a repository's plans. Smaller known limitations (the reviewer runs before the gates, context cost, the builder re-exploring what the planner read, two boards running one task) are in the [Known limitations](docs/architecture.md#known-limitations-and-next-steps).

| # | Gap | Effort | Depends on |
|---|---|---|---|
| ✓ | Read CI on open PRs and fix failures. Done: [CI failures](docs/architecture.md#ci-failures) | — | — |
| ✓ | Act on human PR review comments. Done: [Review comments](docs/architecture.md#review-comments) | — | — |
| ✓ | The builder writes the test that judges it. Done: [The strict flow](docs/architecture.md#the-strict-flow); the without-change gate and holdout tests stay open | — | — |
| ✓ | Nothing measures the factory itself. Done: `factory stats` ([Measuring the factory](docs/architecture.md#measuring-the-factory)) and `factory bench` ([Evaluating flows](docs/architecture.md#evaluating-flows-factory-bench)) | — | — |
| 4 | Learn from feedback. Planned as a knowledge crew: [wiki](docs/plans/wiki.md) | medium | 1, 3 |
| 5 | Steer a running agent | small | — |
| 6 | Runs need this machine | large | a shared board |
| ✓ | Reshape the agent flow. Done: [Agent flows](docs/architecture.md#agent-flows) | — | — |
| ✓ | Compare flows and setups. Done: [Evaluating flows (factory bench)](docs/architecture.md#evaluating-flows-factory-bench) | — | — |
| ✓ | The steps of a flow are still the first version's. Done: [The strict flow](docs/architecture.md#the-strict-flow) | — | — |
| ✓ | Managing the factory takes many terminal commands. Done: [The web page](docs/architecture.md#the-web-page) | — | — |
| ✓ | Factory PR descriptions are long and hard to read. Done: [Pull requests](docs/architecture.md#pull-requests) | — | — |
| 12 | The models' reasoning is thrown away. Planned: [thoughts](docs/plans/thoughts.md) | small | 10 (its web task) |
| ✓ | You can't tell which factory version is running. Done: [Commands](docs/reference.md#commands) | — | — |
| 14 | A review without a verdict costs a rebuild, a task gets one build per attempt, and nothing picks the default flow from data. Planned: [flow-tuning](docs/plans/flow-tuning.md) | medium | 8, 9 |
| 15 | Specify the shipped factory for implementers. Planned in [factory-spec](docs/plans/factory-spec.md) | medium | shipped factory |
| 16 | Nothing reviews a change for security, and a builder can rewrite its reviewer's guidance. Planned: [security-review](docs/plans/security-review.md) | medium | 9, 14 |
| 17 | The bench can't rank flows: every variant solves every shipped case, and comparisons have no error bars. Planned: [evals](docs/plans/evals.md) | medium | 8, 14 |
| 18 | Agents can't look anything up: no web search or page reading, no planner shell, installed Python packages unreadable. Planned: [web-tools](docs/plans/web-tools.md) | medium | 16, 17 |

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

**Plan.** Landed: [The strict flow](docs/architecture.md#the-strict-flow), from [docs/plans/strict-flow.md](docs/plans/strict-flow.md) (tasks `strict-flow-t04` and `t05`), takes a different route from this sketch:
- A `test` step in the flow, on another model than the builder, writes the task's tests before the build, and the factory commits them.
- The red check requires at least one failing test command at that commit and rejects a command that selects no tests. The `acceptance_untouched` gate then fails a candidate that changed or removed a line the step wrote. The contract keeps its 8 keys.
- **Still open:** the `e2e_fails_without_change` gate above, which runs the tests with the change taken out of the candidate, and holdout tests kept outside the worktree.

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

**Plan.** The [measure](docs/plans/measure.md) plan (tasks `measure-t01`…`t04`, after [agent-flows](docs/plans/agent-flows.md)) landed: every agent run records a prompt version, refresh records whether the human changed a PR before merging it as a `merge` run, and `factory stats` reports those records by flow, step, model and version. See [Measuring the factory](docs/architecture.md#measuring-the-factory).

`factory bench` is built: [item 8](#8-compare-flows-and-setups). It is the controlled comparison stats can't give.

## 4. Learn from feedback

**Gap.** Reviewer findings, gate failures and human comments repeat across tasks, but nothing feeds them back into the role prompts.

**Seen in.** [oz-for-oss](https://github.com/warpdotdev/oz-for-oss) proposes skill updates from maintainer feedback.

**Sketch.** `factory learn` collects the last N runs' reviewer `CHANGES` findings, gate failures and (with item 1) human review comments. An agent proposes a diff to the role prompts, which goes out as a PR and is never applied directly. `factory bench` (item 3) shows whether it helps. Without item 3 this is guesswork, so build that first.

**Plan.** [docs/plans/wiki.md](docs/plans/wiki.md) (planned 2026-11-02, tasks `wiki-t01`…`t07`, after [measure](docs/plans/measure.md)). It follows Karpathy's [LLM wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) pattern instead of this sketch:
- A **knowledge crew**, separate from the task crew (an ingester, a linter and a wiki reviewer), keeps a wiki of the repository in `docs/wiki/`. Its pages cover modules, concepts and decisions, plus a guidance page per task role, which is where the lessons go. The role prompts are never edited.
- Sources are merged tasks (contract, change, reviewer findings, failed gates, human reviews and edits, with human signals first), code paths and docs.
- Every crew change passes a deterministic wiki check and the wiki reviewer, then lands as a commit on one standing PR that you merge. A `wiki_untouched` gate keeps tasks out of the wiki.
- Task agents get `index.md` and their role page from the base commit, and read other pages on demand.
- `factory wiki ingest` and `factory wiki lint` are run by hand. Measure's prompt versions show the effect in `factory stats`.

## 5. Steer a running agent

**Gap.** You can watch a run (`top`, `logs -f`) or stop it, but you can't redirect a builder that's heading the wrong way.

**Seen in.** [Open SWE](https://blog.langchain.com/introducing-open-swe-an-open-source-asynchronous-coding-agent) lets you interrupt and nudge a task without restarting it.

**Sketch.** `factory say TASK "…"` appends to `$FACTORY_HOME/inbox/TASK`. A `before_model` middleware in `agents.py` drains the inbox into a `HumanMessage` on the agent's next step and records it in the transcript. The message goes to whichever role is running. It's cheap to build, and it doesn't touch the pipeline.

## 6. Runs need this machine

**Gap.** Runs need this machine on. agent-orchestrator and Open SWE run in hosted workspaces.

**Sketch.** First, a shared board: state in a server database (Postgres, say) instead of the local SQLite file, so agents run on a cloud box while you watch from the laptop. Keep the offline bubblewrap sandbox. The box needs dependencies fetched ahead of time, since the sandbox is offline, and its own `gh` login. Lowest priority: local runs are a deliberate trade for the offline sandbox.

## 7. Reshape the agent flow

**Gap.** The agents a task goes through are fixed: plan, build, review, gates, verify. You can retune the four roles' models, step limits and prompts, but you can't drop the planner, add a second reviewer on another model, put the gates before review, or add a test-writing step, so you can't try different agent flows.

**Plan.** [docs/plans/agent-flows.md](docs/plans/agent-flows.md) (planned 2026-11-02, tasks `agent-flows-t01`…`t05`):
- A flow is a named list of agent steps in `.factory/config.yaml`. Each step has a kind (`plan`, `build`, `review`, `verify`) and its own prompt, model and step limit, and the gates are always in it.
- `flow:` picks the default, which is today's pipeline when unset, and `factory run --flow NAME` overrides it.
- Reworks keep their entry and run the flow's steps after it. Every run records its flow and step, for item 3 to compare.
- External agent CLIs as steps are out of scope.

## 8. Compare flows and setups

**Gap.** With [agent flows](docs/plans/agent-flows.md) you can reshape the agents, but nothing tells you whether a flow, model or prompt change made them better. Real runs aren't comparable, since every task differs, and the gates grade the builder's own tests (item 2). This is the `factory bench` half of item 3.

**Plan.** [docs/plans/bench.md](docs/plans/bench.md) (planned 2026-11-11, tasks `bench-t01`…`t06`, after agent-flows). It differs from item 3's sketch:
- It runs a suite of synthetic fixture cases shipped with the factory instead of replaying merged tasks: five small standard-library Python projects, each with a contract, hidden tests and a reference solution. `--cases DIR` runs your own cases.
- A setup is a flow, optionally with one model on every step. `factory bench run --flow A --flow B --model M --repeat N --max-cost USD` runs each case under each variant in a cell isolated from your board and checkout, with no PR.
- A cell is solved when the gates pass and then the case's hidden tests, which the agents never see, pass too. `false_pass` counts candidates the gates passed but the hidden tests failed.
- `factory bench report` and `compare` show solved rate, false passes, attempts, cost and time per variant and case, and flag any prompt, model or case that changed between two runs.

## 9. A stricter agent flow

**Gap.** [Agent flows](docs/plans/agent-flows.md) let you reorder the steps, but each step still works as it did in the first version:
- The builder's context only grows, and every retry starts a new conversation and explores the repository again.
- The builder writes the tests that judge it (item 2).
- A reviewer's `CHANGES` stands on its word: it can't run the code.

**Seen in.** LangChain raised one model from 52.8% to 66.5% on Terminal-Bench 2.0 by [changing only the harness](https://www.langchain.com/blog/improving-deep-agents-with-harness-engineering). Anthropic's [harness for long-running builds](https://www.anthropic.com/engineering/harness-design-long-running-apps) keeps a separate evaluator, and adds or removes one part at a time and measures.

**Plan.** Landed: [The strict flow](docs/architecture.md#the-strict-flow), from [docs/plans/strict-flow.md](docs/plans/strict-flow.md) (tasks `strict-flow-t01`…`t09`):
- Step options, each off unless a flow sets it. `loop: [trim, map, nudge, resume]` caps reads and clears old tool results, opens with a map of the repository, nudges a looping agent, and continues a builder's conversation across attempts. `prove: true` gives a reviewer the `run` tool and makes `CHANGES` need a reproduced failure or a scope finding.
- A `test` step kind (item 2).
- The built-in flow `strict` turns them all on: test, build, gates, a proving review, verify. `default` stays today's pipeline, and [bench](docs/plans/bench.md) compares the two.
- Parallel build candidates and a flow chosen by the contract's `risk` remain out of scope.

## 10. Manage the factory from a browser

**Gap.** Watching and steering the factory takes a dozen terminal commands. `factory top` cuts long text at the terminal width, nothing says which tasks need you next, and nothing is clickable. Acting means remembering each command's flags, and a single running task can't be stopped at all. With a few runs in parallel the board also fails with `database is locked`.

**Seen in.** [agent-orchestrator](https://github.com/ComposioHQ/agent-orchestrator) and [Open SWE](https://blog.langchain.com/introducing-open-swe-an-open-source-asynchronous-coding-agent) both put a web dashboard over their agents.

**Plan.** [docs/plans/webui.md](docs/plans/webui.md) (planned 2026-11-14, tasks `webui-t01`…`t08`, independent of the other plans):
- `factory web` serves a local page on 127.0.0.1. It shows the board, each task with its contract, runs and live log, and each agent run's transcript.
- Its buttons run the `factory` commands you'd type: load plans, check GitHub, hold, remove a worktree, stop, and start a plan or task run through a form with a cost cap. A new `factory stop` stops one task or a whole plan run.
- It needs no new dependencies, and its look is fixed by mockups committed with the plan, in fractal-dev.xyz's palette and typefaces.
- Its first task opens the board in WAL mode with a 30-second busy timeout, which fixes `database is locked`.

## 11. Readable PR descriptions

**Gap.** A factory PR is where the human approves, but its description is written for agents:
- Recent ones run 19,000 to 33,000 characters, and over half of that is the planner's hand-off to the builder.
- The verifier's sections sit at the same level as the body's own, and the acceptance evidence appears twice.
- Nothing bounds an agent's report. `webui-t05` passed every gate and then failed, because GitHub refused a body over 65,536 characters.
- The title and the commit subject are the goal cut mid-word, and a one-commit squash merge puts that subject on the trunk.

**Plan.** [docs/plans/pr-descriptions.md](docs/plans/pr-descriptions.md) (planned 2026-11-15, tasks `pr-descriptions-t01`…`t05`, alongside [measure](docs/plans/measure.md), before [strict-flow](docs/plans/strict-flow.md)):
- The verifier writes a fixed-shape summary: a title, what changed, and what to check, including the reviewer findings left unaddressed. The factory parses and bounds it, and builds one itself when it can't.
- The planner's hand-off leaves the PR. The gate table, the contract and each reviewer's last draft stay collapsed and capped, and the body is held under 60,000 characters.
- The PR title is the task id and the verifier's title. Commit subjects are cut at a word, with the attempt in the commit body.

## 12. See what the models thought

**Gap.** Every model the factory runs reasons before it answers, and the OpenRouter integration hands that reasoning to the factory with each reply. The factory records only the reply text (`factory/agents.py:329`), so transcripts, the live log and traces show what an agent did but never why. Its thinking tokens are paid for, and then thrown away.

**Plan.** [docs/plans/thoughts.md](docs/plans/thoughts.md) (planned 2026-11-15, tasks `thoughts-t01`…`t03`, alongside [measure](docs/plans/measure.md) and [pr-descriptions](docs/plans/pr-descriptions.md)):
- Each step's reasoning and thinking-token count go into its transcript, and the live log gets a short `thinks:` line per step.
- `factory transcript` prints each step's thoughts before what it said and did, and `factory trace` counts thinking tokens.
- The web transcript page shows the thoughts above what each step said, once `webui-t05` lands.
- Model requests don't change: a model that doesn't share its reasoning is shown as not sharing it.

## 13. Which factory is this?

**Gap.** Nothing says which factory version is running. `factory` has no `version` command or `--version` flag. The package version, `0.1.0` in `pyproject.toml`, stays the same until a release bumps it. An editable install runs whatever its checkout holds, and `main` is now 25 commits past `v0.1.0`, so a run's behaviour can't be tied to the code that produced it.

**Plan.** [docs/plans/version.md](docs/plans/version.md) (planned 2026-11-15, tasks `version-t01` and `t02`):
- `factory version` and `factory --version` print the installed package version. When the factory runs from its own git checkout, as an editable install does, they add that checkout's `git describe`, for example `factory 0.1.0 (v0.1.0-25-ge5f6b95-dirty)`.
- Runs, the board and PR bodies don't record the version, and the build and release process stay as they are.

## 14. Tune the agent flow

**Gap.** Three things are left once the flows run gates-first:
- A review that ends without its `VERDICT:` line counts as CHANGES and sends the build back with the reviewer's unfinished reasoning as the rejection. On this repository's board, 4 of the 7 CHANGES verdicts were that.
- A task gets one build per attempt, in one worktree.
- bench compares flows, but nothing runs the comparison and acts on it.

**Seen in.** Building several candidates and choosing one is the largest measured gain in recent work on coding agents: 70.9% to 77.6% on SWE-bench Verified for one model ([arXiv 2604.16529](https://arxiv.org/abs/2604.16529)), and 78.2% for an LLM verifier picking among three candidates whose mean was 76.1% ([arXiv 2607.05391](https://arxiv.org/abs/2607.05391)).

**Plan.** [docs/plans/flow-tuning.md](docs/plans/flow-tuning.md) (planned 2026-11-16, tasks `flow-tuning-t01`…`t06`; t01 before [strict-flow](docs/plans/strict-flow.md), the rest after it):
- A review without a verdict is asked once more in the same conversation. Still none counts as CHANGES, recorded as `CHANGES (no verdict)`, and the builder is told so.
- A build step can set `candidates: N` (2 to 5). The first attempt builds N candidates one after another in their own worktrees, the gates judge each, and a selector agent picks among those that pass, falling back to the smallest diff.
- bench records candidates, and a by-hand trial of six flows sets this repository's `flow:` by a fixed rule.

## 15. Specify the shipped factory

The architecture and reference explain how to run the factory. An implementer also needs to know the expected outcome when a dependency has an open PR, a check selects zero tests, or a human requests changes on a candidate.

The [factory-spec plan](docs/plans/factory-spec.md) covers the behavior shipped at `8bd7012` in ten plain-text chapters under `docs/spec/`. Five tasks cover the subsystems and a sixth checks the complete series and publishes its reading guide in `00-spec.txt`. No other planned workstream is a prerequisite or waits on this edition.

## 16. Nothing reviews a change for security

**Gap.** No step or gate looks at a change for security:
- The reviewer's checklist has one line on unchecked input. A custom review step can carry a security prompt, but its own `VERDICT:` line decides, so it blocks on every speculative finding or on none.
- No gate catches an added credential, or an edit to CI, `.factory/`, skills, guidance or lockfiles. After merge, those run with the repository's secrets or steer later agents.
- `_repo_guidance` (`factory/agents.py:153`) reads AGENTS.md from the task worktree, so a builder can rewrite its own reviewer's system prompt. That breaks the Policy's "settings come from the main checkout".

**Plan.** [docs/plans/security-review.md](docs/plans/security-review.md) (planned 2026-11-17, tasks `security-review-t01`…`t07`, after [strict-flow](docs/plans/strict-flow.md) and [flow-tuning](docs/plans/flow-tuning.md), before [wiki](docs/plans/wiki.md)):
- Guidance comes from the main checkout, as the config and prompt overrides do.
- `security:` in `.factory/config.yaml` turns on two gates. `secrets` fails on credential-shaped strings in added lines. `guarded_paths` fails on changes to CI, `.factory/`, skills, guidance, lockfiles and configured globs that the contract doesn't name.
- A `security` step kind ships with its own prompt, the repository's threat model, and a verdict the factory computes from its findings. Only critical or high findings with high confidence and an exploit block, and the builder gets only those. The rest go to a visible Security section in the PR.
- A built-in flow, `secure`, is gates-first plus a security step. A command that reviews any ref or PR, and a crew that audits the existing codebase, are out of scope.

## 17. Evals that rank flows

**Gap.** `factory bench` works, but its scores can't tell setups apart:
- The five shipped cases are small standard-library projects. The first real run solved all 60 of its cells across four variants, so only cost and time differed.
- `factory bench compare` prints counts with no error bars and no verdict, and run-to-run spread is several points even on large suites.
- Hidden tests are the only grade. Nothing checks that a case's tests catch a bad change, that a candidate didn't break the rest of the suite, or that it didn't edit the tests that judge it.
- There's nothing a goal loop needs: no holdout, no screening, no reusable baseline, no machine-readable verdict, no record of experiments.

**Seen in.** SWE-bench mines real merged PRs into cases, and SWE-rebench keeps mining fresh ones to stay ahead of training data. Maintainers would reject about half of SWE-bench patches that pass its tests ([METR](https://metr.org/notes/2026-03-10-many-swe-bench-passing-prs-would-not-be-merged-into-main/)), and mutation testing exposes weak tests ([SWE-ABS](https://arxiv.org/abs/2603.00520)). Anthropic's [error bars for evals](https://arxiv.org/abs/2411.00640) recommend comparing case by case with intervals. [ImpossibleBench](https://arxiv.org/abs/2510.20270) measures test gaming with tasks no honest change can pass.

**Plan.** [docs/plans/evals.md](docs/plans/evals.md) (planned 2026-11-17, tasks `evals-t01`…`t09`, after [strict-flow](docs/plans/strict-flow.md) and [flow-tuning](docs/plans/flow-tuning.md)):
- `factory bench mine` replays this repository's merged factory tasks as cases: the base without history, the contract, the merged tests as hidden tests and the merged code as the reference. `factory bench check` proves each case's tests fail before the change, pass with the reference and kill mutants of it.
- Cells are also graded `regressed` (the rest of the suite broke) and `tampered` (a protected test edited), with scope beside the reference, and three impossible cases measure gaming.
- Rates come with intervals clustered by case. Comparisons are case by case, with a verdict for solved rate and one for cost, and print as JSON.
- For a goal loop: dev and holdout splits, `--screen`, `--baseline` reuse, a ledger with notes, per-cell failure reasons, and docs/goal-loop.md with the protocol.

## 18. Agents can't look anything up

**Gap.** Agents can't consult documentation:
- No web tools. The sandbox is offline unless `--network` opens it, and then every step and gate of the task can reach any host. There is no search, no safe page reading, and no way to give one step access without the others.
- The planner has only read tools, so it can't run `git log` or ask an installed library for its own documentation.
- `dependency_sources` can't point at a Python virtualenv's `site-packages`, so installed packages, the version-exact docs, are out of reach.

How much this costs is unclear. On this repository's board, 1,092 agent commands hit the missing network once and never tried to look anything up. Elsewhere, version-specific code is where models do worst, and documentation retrieval is the usual fix. The same access lets agents find answers instead of writing them ([imec](https://aistack.imec-int.com/blog/agents-peeking)), so it has to be safe and measured.

**Plan.** [docs/plans/web-tools.md](docs/plans/web-tools.md) (planned 2026-11-18, tasks `web-tools-t01`…`t06`, after [security-review](docs/plans/security-review.md), before [wiki](docs/plans/wiki.md)):
- A plan, test or build step can set `web: true` for `web_fetch` and `web_search`, which the factory runs itself, so the sandbox stays offline. Search goes through one engine named in config (SearXNG, Brave, Exa or Tavily), so there's no provider lock-in.
- Every fetch refuses private addresses and the repository's own remote, honours allow and block lists, caps sizes, frames pages as untrusted and is recorded in the transcript.
- A plan step can set `shell: readonly`, and `dependency_sources` accepts `{root}` and globs for installed packages.
- A bench trial on the mined suite decides whether strict with web, or with the planner shell, replaces strict.
