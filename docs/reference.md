# Reference

Configuration, task contracts, skills, commands and troubleshooting. To install and run the factory, see the [README](../README.md); for how it works, see [architecture](architecture.md).

---

## `factory init`

Run it at the root of a repository (any subdirectory works; it finds the main checkout). It writes:

| File | What |
|---|---|
| `.factory/config.yaml` | Settings, every key documented in comments. `name` is the directory name, `session_log: docs/sessions` is on, and `unit_tests` is guessed from `Cargo.toml` (`cargo test --workspace`) or `pyproject.toml` (`uv run pytest -q`) |
| `.claude/skills/{plan-workstream,review-task,factory-ops}/` | The workflow skills, copied from the installed factory |
| `.agents/skills/{plan-workstream,review-task,factory-ops}` | Relative symlinks to those same skill folders, for Codex discovery |
| `docs/sessions/README.md` | The session-log convention, when the directory is new or empty |
| `docs/plans/example.md` | When the repository has no plans yet: the contract format and one valid, runnable task. Replace or delete it before `factory run` |
| `AGENTS.md` | A "Software factory" section between `<!-- factory:begin -->` and `<!-- factory:end -->`. It goes into the first `guidance` file that exists (so a `CLAUDE.md`-only repository gets it there), and `AGENTS.md` is created when there is none |

Re-running is safe: existing files are kept (`keep … (exists; --force overwrites)`), and only the text between the markers is replaced. `--force` rewrites the files, which is how skills pick up a new factory version. `--no-skills` skips the skills, `--session-log DIR` picks another log directory, and `--no-session-log` turns the requirement off.

Codex links are also added when re-running `factory init` in a repository initialized by an older version. Existing files and directories at the Codex skill paths are preserved, even with `--force`; an existing symlink to a different target is replaced only with `--force`. To refresh the skill instructions for Codex after upgrading, use `factory init --force` (this also rewrites the other scaffolded files).

---

## Configure a project

`.factory/config.yaml`. Every key is optional; `factory config` prints the effective values.

| Key | Default | Meaning |
|---|---|---|
| `name` | repo directory name | Names the state directory `~/.local/share/factory/<name>` |
| `home` | — | State directory override (`$FACTORY_HOME` wins over both) |
| `plans` | `["docs/plans/**/*.md"]` | Markdown files holding task contracts |
| `exclude` | `[]` | Globs never read as backlog (e.g. `docs/ideas/**`) |
| `guidance` | `["AGENTS.md", "CLAUDE.md"]` | Repository guidance: the first file that exists is appended to every agent's prompt |
| `session_log` | — | Directory: every task must add its own `<dir>/<today>-<task id>.md` (`session_log` gate) |
| `e2e.dir` | — | Every task must add a new test directly under this directory (`e2e_written` gate) |
| `e2e.language` | `rust` | How new tests are found: `rust` (`#[test]`, `#[tokio::test]` fns) or `python` (`def test_*`) |
| `e2e.run_new` | — | Command run per new test; `{target}` = file stem, `{name}` = function, `{path}` = repo-relative file |
| `e2e.run_all` | — | The whole suite (used with `--full-e2e`, or when `run_all_when` matches) |
| `e2e.run_all_when` | `[]` | Regexes over changed paths that run the whole suite instead of only the new tests |
| `unit_tests` | `[]` | Commands for the `unit_tests` gate |
| `lockfiles` | common lockfiles | Files the `diff` gate notes when they change |
| `dependency_sources` | cargo registry and git sources, rustup toolchains | Directories the agents' file tools may also read, by absolute path (never write) |
| `test_paths` | `[]` | Globs where a `test` step may write, in the syntax of `plans` and `exclude`; required by a flow with a test step (`factory run` refuses without it) |
| `flow` | `default` | The flow `factory run` uses: a name from `flows` (the built-ins are `default`, today's pipeline, and `strict`); `factory run --flow` overrides it per run |
| `flows` | `{default: …, strict: …}` | Named agent flows: name → ordered step list. `default` and `strict` are always present and neither can be redefined. A step is a kind string (`plan`, `test`, `build`, `review`, `verify`, `gates`) or a mapping with `kind` and optional `name`, `model`, `max_steps`, `loop` and `prove`. Exactly one gates step; one is inserted after the last review (else build) step when omitted |
| `models` | `{}` | Model per step kind (`plan`, `test`, `build`, `review`, `verify`), e.g. `{review: "anthropic:claude-…"}`; over the prompt's frontmatter |
| `max_steps` | `{}` | Model calls per agent run, per step kind (`plan`, `test`, `build`, `review`, `verify`); over the prompt's frontmatter |
| `denied_commands` | `[]` | Extra regexes the agents' `run` tool refuses (git push/commit/reset…, `sudo`, `gh`, `terraform apply/destroy` and `factory` are built in) |
| `sandbox.ro_binds` / `rw_binds` | rustup + uv read-only, `~/.cargo` writable | Host paths visible inside the sandbox (missing ones are skipped) |
| `sandbox.hide` | cargo credentials | Files masked with `/dev/null` |
| `sandbox.path` | `~/.cargo/bin`, `~/.local/bin` | Prepended to `PATH` |
| `sandbox.env` / `offline_env` | cargo/uv cache dirs / `CARGO_NET_OFFLINE`, `UV_OFFLINE` | Environment (`~` = home, `{cache}` = `$FACTORY_HOME/cache`); `offline_env` applies without `--network` |
| `sandbox.cache_dirs` | `target`, `uv` | Subdirectories of the shared cache to create |

**Agent flows:** choose one with `flow:` or `factory run --flow`; see [Agent flows](architecture.md#agent-flows) for how a flow runs.

```yaml
flow: careful
flows:
  lean:                           # no planner, gates decide, no verifier report
    - build
    - review
  careful:
    - plan
    - build
    - review
    - {name: second-review, kind: review, model: "anthropic:claude-opus-5-5"}
    - verify
  gates-first:
    - plan
    - build
    - gates                       # reviewers only see changes that pass the gates
    - review
    - verify
  default-trim: [plan, {kind: build, loop: [trim]}, review, verify]
  test-first:
    - plan
    - {name: tests, kind: build}  # prompt: .factory/agents/tests.md
    - build
    - review
```

Steps follow `[plan]? [test]? build+ (review | gates)* [verify]?`. There is at most one test step, directly before the first build step; it needs non-empty `test_paths`. In `lean`, `careful`, `default-trim` and `test-first`, a gates step is inserted after the last review; `gates-first` places it explicitly. Custom steps can set their own prompt, model and step limit as described under [Agent flows](architecture.md#agent-flows).

A step mapping also takes **`loop`**, a list containing any of `trim`, `map`, `nudge` and `resume` once each. The first three work on any agent step: `trim` caps reads and clears old tool results, `map` adds a repository map and spec references, and `nudge` warns near the step limit and about repeated edits or failures. `resume` is valid only on build steps and carries the conversation into later attempts. **`prove`** is a boolean valid only on review steps: with `prove: true`, the reviewer gets sandboxed `run`, and CHANGES needs a reproduced failure or a `[scope]` blocker or major. Kind **`test`** runs the tester once before the builds; its tests are committed, red-checked and locked.

The built-in `strict` flow combines those options and omits the planner. It is written out here for reference, not as a `flows:` entry to copy: like `default`, it cannot be redefined.

```yaml
strict:
  - {kind: test, loop: [map, trim, nudge]}
  - {kind: build, loop: [map, trim, nudge, resume]}
  - gates
  - {kind: review, prove: true, loop: [trim]}
  - verify
```

Choose it with `flow: strict` or `factory run TASK --flow strict`; see [The strict flow](architecture.md#the-strict-flow) for the red check, lock and proof rules. To price one behaviour alone, the `default-trim` example above adds only `trim` to default's build step: bench it against `default` with `factory bench run --flow default --flow default-trim --repeat 3 --max-cost USD`.

**A Rust workspace** with a dedicated e2e crate (`my-e2e`); changes to the core crates run the whole e2e suite:

```yaml
name: my-chain
exclude: ["docs/ideas/**"]
session_log: docs/sessions
e2e:
  dir: crates/e2e/tests/
  language: rust
  run_new: "cargo test -p my-e2e --test {target} {name} -- --exact"
  run_all: "cargo test -p my-e2e"
  run_all_when: ['^crates/(core|consensus|node)/']
unit_tests: ["cargo test --workspace --exclude my-e2e"]
```

**A Python project:**

```yaml
name: shop
plans: ["planning/**/*.md"]
e2e:
  dir: tests/e2e/
  language: python
  run_new: "uv run pytest {path}::{name}"
  run_all: "uv run pytest tests/e2e"
unit_tests: ["uv run pytest -q tests/unit"]
sandbox:
  ro_binds: ["~/.local/bin", "~/.local/share/uv"]
  rw_binds: []
  env: {UV_CACHE_DIR: "{cache}/uv"}
  offline_env: {UV_OFFLINE: "1"}
```

---

## Credentials

Each factory instance takes its credentials from its own environment, so two shells or services can run as different identities. They are never in the repository, and agents never see them: both sandboxes clear the environment.

| Variable | Needed | Used for |
|---|---|---|
| `OPENROUTER_API_KEY` | Yes, with the default models | The agents' model calls. `factory run` refuses to start without the key of every provider the roles use (`ANTHROPIC_API_KEY` and `OPENAI_API_KEY` for those providers) |
| `GITHUB_TOKEN` or `GH_TOKEN` | No | The GitHub identity. Unset: `gh` uses your `gh auth login`, and git fetches and pushes with the remote's own credentials (often your SSH key). Set: `gh` uses the token, and git fetches and pushes to github.com over HTTPS with it, an SSH remote rewritten for the call, so a PR and its commits come from the same account. `GH_TOKEN` wins when both are set |

`factory config` names the GitHub identity in use on its first line. git asks a credential helper for the token when it needs it, so the token is never on a command line or written to disk. Only github.com is handled; other hosts use git's own credentials.

A fine-grained token scoped to the repository needs Contents and Pull requests: read and write, Actions and Commit statuses: read (CI checks and job logs), and Workflows: read and write if a task may change `.github/workflows/`. A classic token needs `repo`, plus `workflow` for the same reason.

---

## Task contracts

A plan carries a fenced `yaml` list. Each item has **exactly** these 8 keys; status lives in the database, never in the plan:

```yaml
- id: my-workstream-t01               # workstream-prefixed, unique across plans
  goal: "One observable deliverable"
  spec_refs: ["docs/spec/api.md#orders"]
  depends_on: []                      # task ids, may be in other plans; stacks on their open PRs, or waits
  non_goals: ["What not to do"]
  acceptance: ["Observable condition proving it is done"]
  verification: ["uv run pytest tests/e2e/test_orders.py::test_refund_flow"]
  risk: low                           # low | medium | high
```

`factory validate-plan` checks:
- schema;
- dependencies, including across plans and for cycles;
- command selection;
- placeholders.

It also warns about contracts whose verification runs a command the factory refuses (`terraform apply`, `sudo`, `gh`, `denied_commands`, …), and `factory run` refuses them: those tasks are done by hand.

Contracts don't fence the builder in: it can edit any file in the worktree. The goal and the non-goals bound the change, and the reviewer treats unrelated edits as findings. Plans without a task block are not executable. `/plan-workstream` writes plans in this shape (see [Skills](#skills)).

---

## Skills

`factory init` copies three agent skills into `.claude/skills/`. Claude Code loads them there, and OpenCode reads the same directory. Relative links under `.agents/skills/` let Codex load the same files, including references and invocation policy. They read the project's `.factory/config.yaml`, so they carry no project specifics.

| Skill | Codex invocation | Use | What it does |
|---|---|---|---|
| [`/plan-workstream`](../factory/templates/skills/plan-workstream/SKILL.md) | `$plan-workstream` | Before work starts | Grounds in the config, roadmap, plans and code; locks 2–4 strategic decisions with you; writes a plan whose contracts satisfy the configured gates; validates the contracts and opens a plan PR with the roadmap changes. Tasks are synced from the target branch after merge |
| [`/review-task TASK [REF]`](../factory/templates/skills/review-task/SKILL.md) | `$review-task TASK [REF]` | Before you merge | Runs `factory gates` (cheap, then full) on the task's branch, applies the reviewer agent's checklist, and reports APPROVE or REQUEST CHANGES. It never edits or merges |
| [`factory-ops`](../factory/templates/skills/factory-ops/SKILL.md) | `$factory-ops` or automatic | While running | Loads by itself on operational questions: starting runs, what's happening, why a task failed, requeues, holds, merging stacked PRs, resetting the board |

`/plan-workstream` and `/review-task` are explicit-invocation only. The factory's own agents (planner, builder, reviewer, verifier) are role prompts, not skills, and stay in the installed package.

In Codex CLI or the IDE extension, type `$` to select a skill or select it through `/skills`. If newly installed skills do not appear, restart Codex. Codex uses `$plan-workstream` and `$review-task`; the bare slash names in the table are the Claude Code/OpenCode invocation syntax. See the [official Codex skills documentation](https://developers.openai.com/codex/skills/).

Use `factory init --no-skills` to skip the skills, and `factory init --force` to refresh them after upgrading the factory (it also rewrites the other scaffolded files, so review the diff).

---

## Commands

| Command | Purpose |
|---|---|
| `factory init [--force] [--no-skills] [--session-log DIR \| --no-session-log]` | Set the repository up: config, skills, session log, starter plan, guidance section |
| `factory config` | Print the effective project settings, the state directory and the GitHub identity |
| `factory version` / `factory --version` | Print the installed version. From a git checkout of the factory (an editable install), it also adds that checkout's `git describe` — for `v0.1.0-25-ge5f6b95-dirty`, the last release tag is `v0.1.0`, the code is 25 commits past it at commit `e5f6b95`, and `-dirty` means uncommitted edits to tracked files. A checkout that hasn't fetched its tags shows an older tag or just the commit; run `git fetch --tags` |
| `factory prompt ROLE\|STEP [--flow F]` | Print a role's or flow step's prompt as the agents get it, with its model and step limit. A step name resolves within `--flow`, defaulting to the config's `flow` |
| `factory validate-plan [PLAN…]` | Check contracts |
| `factory sync` | Load every contract from the plans into the db (statuses kept) |
| `factory status [PLAN] [--refresh] [--json]` | The board, grouped by plan with a task counter. `--refresh` picks up merged or closed PRs (a stacked PR merged into a dependency's branch counts once that branch's PR carries it to the trunk; one stranded there becomes `conflict`), takes up open or merged PRs opened from another board, moves stacked PRs whose dependencies merged, marks PRs that conflict with their base `conflict`, marks PRs a review requests changes on `changes_requested` and clears them when the request is approved or dismissed, and marks PRs whose CI fails `ci_failed`, and fails dead runs. For each task with a candidate whose PR merged, it records a `merge` run when the final head can be read: `as_built`, or `edited` with the human's commits. Conflicts come first, then requested changes, then CI |
| `factory run PLAN [--flow NAME] [--parallel N] [--network-for T1,T2] [flags]` | Every task of the plan without a PR, one PR each, dependents stacked on open dependency PRs; PRs in `conflict` get their conflicts resolved, PRs in `ci_failed` get their CI fixed, and PRs in `changes_requested` get the review addressed. `--flow NAME` runs every child under that flow instead of the config's `flow` |
| `factory run TASK [--flow NAME] [flags]` | Run one task in the foreground (stacked the same way) under `--flow NAME` instead of the config's `flow` when given. On a `conflict` task it resolves the conflicts, on a `ci_failed` task it fixes CI, and on a `changes_requested` task it addresses the review; `--force` rebuilds any of them from scratch instead |
| `factory stop TARGET [--wait SECONDS]` | Stop a running task, or a running plan and every task it started: SIGTERM, then SIGKILL after SECONDS (default 10). TARGET is a task id or a plan name/path. A stopped task ends `failed` with a note saying it was stopped; its worktree and branch are kept |
| `factory bench run\|report\|compare\|list\|cases` | Evaluate flows and models on fixture cases, in isolated cells, and read or compare the scores; see [Bench](#bench) |
| `factory top [PLAN] [--once]` | Live dashboard: each active plan with its glyph strip (✓ merged ◆ PR open ≠ PR conflicts ! CI fails ▶ running ✗ failed · queued ⊘ held) and counter, then its tasks' progress, current action, elapsed and quiet time, cost; recent events |
| `factory web [--port N] [--no-open]` | Serve the board as a page at http://127.0.0.1:8765 and open it; every button runs one of these commands. See [The web page](#the-web-page) |
| `factory logs TASK [-f] [-n N]` / `factory logs --all -f` | One task's log, or every task's log merged |
| `factory trace TASK [--role R] [--step S] [--attempt N] [--all]` | Per-step model time, tool time, context size, cached tokens, output and thinking tokens, cost, calls, largest results; `--step` filters by flow step |
| `factory transcript TASK [--role R] [--step S] [--attempt N] [--all] [--full]` | Exactly what the model saw and did, with each step's thoughts above its text and tool calls; `--step` filters by flow step |
| `factory show TASK [--role R] [--step S]` | Every step's report and stats, labelled with its flow, step, model and prompt version; `--step` filters by flow step. `--role human_review` shows the review brief a `changes_requested` rework gave the builder. `factory show TASK --role merge` shows a merged task's merge record |
| `factory stats [--since DATE] [--until DATE] [--plan P] [--json]` | How the factory is doing over a window: outcomes, attempts, cost, gate failures, reworks, human edits and per-step measurements by flow, model and prompt version. See [Measuring the factory](#measuring-the-factory) |
| `factory gates TASK [--ref R] [--base B] [--skip …]` | Deterministic gates only, in a throwaway worktree. The base defaults to the PR a stacked task is built on, else the default branch |
| `factory requeue TASK…` | Put `failed` or `abandoned` tasks back to `queued` so the next plan run picks them up (refuses running, open-PR and merged tasks) |
| `factory clean TASK` | Remove a task's worktree |
| `factory abandon TASK` | Mark a task abandoned (a hold: plan runs skip it) |
| `factory check-output --cmd C --exit N LOG` | Classify a test log (for CI) |

Useful `run` flags:

| Flag | Effect |
|---|---|
| `--base B` | Branch for the worktree and PR (default: current branch) |
| `--flow NAME` | The agent flow to run (a key of `flows`; default: the config's `flow`) |
| `--model M` | Override every step's model |
| `--max-attempts N` | Build attempts (default 3) |
| `--max-cost USD` | Abort the task above this cost |
| `--network` | Allow network in the sandbox |
| `--no-pr` | Stop after the gates pass, without pushing |
| `--skip-gates a,b` | Skip the named gates |
| `--full-e2e` | Always run the whole e2e suite |
| `--notify` | Desktop notification when the run ends |
| `--quiet` | Log to the file only |
| `--force` | Run even if the status, or a dependency without a PR, would refuse |

### The web page

`factory web [--port N] [--no-open]` binds 127.0.0.1 only. Its default port is 8765; if that is busy and `--port` wasn't given, it picks a free port, while a busy explicit `--port` exits 1. It prints `factory web: http://127.0.0.1:PORT/ (Ctrl-C to stop)` and opens the page in a browser unless `--no-open` is given. To reach another machine's board, use `ssh -L 8765:127.0.0.1:8765 HOST`.

| Page | What it shows |
|---|---|
| `/` | The board: what needs you, counts, running tasks and every plan |
| `/tasks/TASK` | The next step and note, contract, runs with their reports, and the last 200 log lines |
| `/tasks/TASK/runs/RUN` | One agent run's transcript |
| `/activity` | Commands the page ran, with output, plus every task's log merged |
| `/run?plan=…` or `/run?task=…` | The run form: what will run, the required cost cap, limits, the exact command and the cost warning |
| `/confirm` | What Stop and Remove worktree will do, so one click never acts alone |

| Button | Command it runs |
|---|---|
| Load plans | `factory sync` |
| Check GitHub | `factory status --refresh` |
| Put on hold | `factory abandon TASK --note "put on hold from factory web"` |
| Take off hold | `factory requeue TASK` |
| Remove worktree | `factory clean TASK`, after confirmation |
| Stop / Stop this run | `factory stop TASK` or `factory stop PLAN`, after confirmation |
| Run plan / Run again / Start run | Run plan and Run again open the form; Start run runs its displayed `factory run TARGET …` with the chosen limits |

The command buttons' tooltips name their commands, and the run form displays its exact command before Start run. Quick actions return to the page with a job notice; Stop and Start run go to the activity page.

Commands run as detached jobs under `$FACTORY_HOME/web/jobs/` that survive `factory web` stopping; a restart finds them, and only the newest 200 are kept. Live pages refresh every 2 seconds, and every page works without JavaScript. The page is loopback-only; its safeguards are described in [architecture](architecture.md#the-web-page).

---

## Bench

`factory bench` runs a fixed case suite under each selected setup. Cases × variants × repeats become isolated cells: each is a normal pipeline run without a PR, followed by hidden scoring when the gates pass. See [Evaluating flows](architecture.md#evaluating-flows-factory-bench) for the run diagram, outcomes, isolation, budget and recorded data.

### Commands

| Command | Flags and effect |
|---|---|
| `factory bench run [--case ID]… [--cases DIR] [--flow NAME]… [--model SPEC]… [--repeat N] [--max-cost USD] [--max-attempts N] [--parallel N] [--dry-run] [--no-sandbox]` | Run every selected case, variant and repeat. `--case` is repeatable and defaults to every case; `--cases DIR` loads that suite instead of the shipped one. `--flow` is repeatable and defaults to the config's `flow`; `--model` is repeatable and puts that model on every agent step, producing `FLOW@MODEL` variants (flows × models). `--repeat N` defaults to 1. `--max-cost USD` is the required total run budget, except with `--dry-run`. `--max-attempts N` defaults to 3 per cell. `--parallel N` defaults to 1 (sequential); larger values run up to N independent child processes. `--dry-run` prints variants, per-step models, provider key names and cells, then exits 0 without creating anything. `--no-sandbox` is unsafe, recorded in the results and flagged in reports |
| `factory bench report [RUN] [--cells]` | Report `RUN`, defaulting to the newest run: its header, per-variant summary and solved counts per case. `--cells` adds each cell's outcome, attempts, cost, minutes and directory, including `not run` cells missing from an interrupted run |
| `factory bench compare RUN_A RUN_B` | Compare shared variants and cases as A → B: solved counts, false passes, mean cost, mean attempts and mean minutes per variant, then solved counts per case. The header lists changed and one-sided cases, one-sided variants, and steps whose model, `loop`, `prove` or `prompt_sha` changed |
| `factory bench list` | List past runs newest first: id, start, case and variant counts, recorded cells of the expected total, and cost |
| `factory bench cases [--cases DIR]` | List each available case's id, kind and title. `--cases DIR` reads your suite instead of the shipped fixtures |

A variant without `--model` uses the models resolved from the invoking repository. Repeating identical `--flow` or `--model` flags does not duplicate a variant. Run from a git repository: its flows, `models`, `max_steps` and `.factory/agents/` prompt overlays configure the variants, while each cell uses the case's gates and isolated factory home.

In a report, `solved` is `solved/eligible`, where eligible cells ended `solved`, `false_pass` or `failed`. `false` counts candidates that passed their own gates but failed hidden tests. `err/stop/skip/not run` separates errors, cost-limit stops, budget-skipped cells and cells absent after an interruption. `attempts`, `cost/cell` and `min/cell` are means over cells that ran, excluding `skipped` and `not run`; `total` is all recorded spend. A comparison's per-case and per-variant solved columns are counts, not percentages.

`compare` also checks whether the two runs measured the same thing: a changed `fixture_sha` means the case files differ, and a changed step model, `loop`, `prove` or `prompt_sha` means the named variant's setup differs. Cases or variants present in only one run are named and omitted from the shared score tables. Treat small differences cautiously; use at least `--repeat 3` and compare like with like.

### A case directory

A suite is a directory containing one directory per case. A case id is its directory name and must match `^[a-z][a-z0-9-]*$`:

```text
my-cases/slugify/
  case.yaml        title, kind, requires, config, contract, hidden
  repo/            the starting tree: guidance, package and existing tests
  hidden/          files laid over the candidate to score it
  solution/        files laid over the starting tree to prove it solvable
```

`case.yaml` must have exactly these keys:

| Key | Meaning |
|---|---|
| `title` | The case's human-readable title |
| `kind` | One of `feature`, `bugfix`, `multi-file`, `refactor`, `algorithm` |
| `requires` | Non-empty command names checked with `command -v` inside the case's sandbox before a run |
| `config` | The case's `.factory/config.yaml` mapping, written into its base commit; its gates and sandbox apply in every cell |
| `contract` | One ordinary 8-key task contract, with id `<case id>-t01`, written to `docs/plans/<case id>.md` in the base commit |
| `hidden` | Non-empty test commands that score the candidate. Each must be recognized as a test command, such as pytest, `cargo … test` or `python3 -m unittest …`; zero selected tests is inconclusive, not a pass |

`repo/` is the starting tree. Materialization copies only that tree, writes `config` and `contract`, and makes one git commit with a fixed author, committer and date, so the base commit sha is deterministic across runs and machines. Neither `hidden/` nor `solution/` enters that repository.

`hidden/` must contain files and is copied over a scratch worktree of the candidate only after its gates pass. The `hidden` commands run there in the case's sandbox; their output is saved in the cell's `hidden.log`. `solution/` must also contain files: laid over the base, it demonstrates that the case is solvable. The factory's own fixture tests use it; it never enters the case repository or the candidate being scored.

For example, this is the shipped `slugify` metadata:

```yaml
title: Slugify titles for URLs
kind: feature
requires: [python3]
config:
  unit_tests: ["python3 -m unittest -q"]
  dependency_sources: []
  sandbox: {ro_binds: [], rw_binds: [], path: [], hide: []}
contract:
  id: slugify-t01
  goal: "Add textkit.slug.slugify(title, max_length=64) to turn a title into a URL slug"
  spec_refs: ["docs/plans/slugify.md"]
  depends_on: []
  non_goals: ["Changing normalize(text) or adding third-party dependencies"]
  acceptance:
    - "textkit.slug.slugify(title, max_length=64) lowercases titles, folds accents to ASCII, collapses runs of other characters to one hyphen, and trims leading and trailing hyphens"
    - "Empty and all-symbol titles return an empty string; for example, 'Café au Beurre' becomes 'cafe-au-beurre' and 'Hello, World!!!' becomes 'hello-world'"
    - "A slug longer than max_length keeps only complete hyphen-separated words that fit; if its first word is too long, that word is cut to max_length"
    - "Add visible unittest coverage in tests/test_slugify.py while preserving normalize(text) and the existing test suite"
  verification: ["python3 -m unittest -v tests.test_slugify"]
  risk: low
hidden:
  - python3 -m unittest -v bench_hidden.test_slugify
```

### Writing and checking your own cases

Put each case under a suite directory of your choosing, then check it incrementally:

```bash
factory bench cases --cases my-cases                 # load and validate every case
factory bench run --cases my-cases --dry-run         # inspect variants, models, keys and cells
factory bench run --cases my-cases --case slugify --max-cost 2
```

A malformed case is refused with its id and the problem, before any run directory or cells are created. Once the case loads, a dry run checks the expansion without spending money; a real run requires `--max-cost`. Add more cases, variants or `--repeat` after the smallest run works.

When writing one:

- Hidden tests may call only the public functions, commands and output formats named by the contract, so any solution satisfying the contract can pass.
- Prove both directions: the base tree must not already pass the hidden tests, and `solution/` laid over that base must pass every configured gate and the hidden tests. Keep a visible test command in the contract's `verification` so the production gates have something meaningful to run.
- Keep the case's `sandbox.ro_binds`, `rw_binds`, `path` and `dependency_sources` away from its own `hidden/` and `solution/` files. Preflight checks this from inside the sandbox and through the dependency sources, and refuses an exposed case.

### The shipped cases

| Case | Kind | Title | Task and what the hidden tests check |
|---|---|---|---|
| `slugify` | feature | Slugify titles for URLs | Add `slugify(title, max_length=64)` to a small text package: lowercase, fold accents, collapse punctuation to single hyphens, trim and cut at word boundaries. Hidden tests cover accents, punctuation runs, empty and all-symbol titles, and length cuts |
| `money-rounding` | bugfix | Round ledger money exactly to cents | Fix totals and balances that drift when amounts are summed as floats, including exact half-to-even cent rounding. Hidden tests cover float-drifting sums, half-cent amounts and preservation of existing behavior |
| `report-json` | multi-file | Add --format json to the report tool | Add `--format json` beside the existing table output across the argument parser, formatter and usage documentation. Hidden tests exercise the JSON shape through the real entry point and require the default table output to stay byte for byte unchanged |
| `ini-refactor` | refactor | Extract one shared settings parser | Replace two copies of a `key = value` parser with one shared parser without changing behavior. Hidden tests cover both modules, comments, blank lines, duplicate keys and preservation of the public function names |
| `rate-limiter` | algorithm | Implement the token-bucket rate limiter | Implement a token bucket with capacity, refill rate, an injectable clock and `try_acquire(n=1)`. Hidden tests cover bursts, fractional-time refills, requests larger than capacity and the capacity ceiling |

All five use only the Python standard library and declare `requires: [python3]`. Their hidden suites use `python3 -m unittest`, and their contracts require visible tests so the ordinary factory gates still apply.

---

## Measuring the factory

### `factory stats`

```text
factory stats [--since DATE] [--until DATE] [--plan P] [--json]
```

Stats reads `factory.db` only: it does not write to the database, call GitHub or call a model.

| Flag | Meaning |
|---|---|
| `--since DATE` | Select runs that started at or after this time. An ISO date means midnight UTC; an ISO datetime is also accepted, and a datetime without a zone means UTC. Omit for an open-ended start |
| `--until DATE` | Select runs that started before this time, with the same date and UTC rules. Omit for an open-ended end |
| `--plan P` | Restrict the report to one plan, named by its file name without `.md` or by its path |
| `--json` | Print one JSON object with `window`, `summary`, `gates` and `steps`, instead of the text tables |

The window is half-open: `started_at >= --since` and `started_at < --until`. A task is in the window when any of its runs is. Task-level metrics then use **all** of that task's runs, including ones outside the window; run-level metrics use only the selected runs. A step row's first-seen date spans the whole database, independently of both the window and plan filter.

An empty window prints `no runs in the window` and exits 0, including with `--json`. A rate with no denominator shows `-` in text and `null` in JSON; means and costs with no denominator do the same. A malformed date is an error with exit 2.

### Metric definitions

| Metric | Definition |
|---|---|
| Window totals | Tasks with a selected run; tasks among them with a `pr` run (`PRs`); and those whose current status is `merged` or `failed` |
| First-attempt pass rate | Tasks whose first `pr` run with outcome `opened` has attempt 1 ÷ tasks with a `build` run. Both task-level sets use all runs of the selected tasks |
| Attempts per PR | Mean attempt of each task's first `pr` run with outcome `opened`, over selected tasks that opened a PR |
| Cost per merged PR | For selected tasks now `merged`, Σ `cost_usd` over every run ÷ merged tasks with complete pricing. A merged task with any agent run whose price is unknown is excluded from that mean and counted separately as `unpriced_merged`; it is never counted as zero cost |
| Reviewer CHANGES rate | Selected `review` runs whose outcome starts `CHANGES` ÷ selected `review` runs |
| Gate failures | Per gate name, the `FAIL` rows (`| name | FAIL | … |`) in the gate tables of selected `verify` runs whose outcome is `fail` |
| Step-limit stops | Per step, selected runs whose outcome ends `(step limit)` or `(graph recursion limit)` |
| Reworks | Separately for conflict, CI and review: selected tasks with a `pr` run that also have respectively a `resolve`, `ci` or `human_review` run ÷ selected tasks with a `pr` run. These task-level checks use all runs |
| Human edits | Selected `merge` runs with outcome `edited` ÷ selected `merge` runs |

The **steps** table has one row per `(flow, step, model, prompt version)` over selected agent runs. Runs recorded before flows have flow `-` and their role as the step; an unrecorded prompt version is `-`.

| Column | Meaning |
|---|---|
| `flow`, `step`, `model`, `version` | The grouping key: flow and step names, model identifier and 12-hex prompt version |
| `runs` | Number of selected runs in the group |
| `calls` | Mean model calls per run (the run's recorded `steps`) |
| `stops` | Runs ending in either step-limit suffix above |
| `refused` | Total refused tool calls |
| `cost` | Σ recorded `cost_usd` for the group, in USD |
| `outcomes` | Count of each outcome; an unfinished run counts as `running` |
| `first seen` | UTC date of the earliest run with this grouping key anywhere in the database |

### Prompt versions

An agent run's `prompt_version` is the first 12 hex characters of the SHA-256 of its system prompt without the contract block and `Today: …` line. It covers the step's prompt as loaded (custom step override, kind override or shipped prompt), the generated project rules, the first existing repository-guidance file, and anything else added to the system prompt later. Thus identical instructions share a version, while a prompt, rules or guidance edit creates a new one. Non-agent runs have no version. `factory show TASK` prints each run's version beside its model; the full prompt remains available through `factory transcript`.

Per-version before/after deltas are confounded by the changing task mix until `factory bench` provides controlled comparisons; see [Architecture: Known limitations](architecture.md#known-limitations).

### Merge records

Refresh records at most one `merge` run per task, at attempt 0, when a task with a candidate becomes `merged`. Its SHA is the PR's final head. Refresh fetches the task branch, or `refs/pull/<number>/head` if the branch has been deleted.

| Final head | Outcome and report |
|---|---|
| Equal to the candidate | `as_built` |
| A descendant with an empty `git log --first-parent --no-merges candidate..head` | `as_built`: only base merges, such as GitHub's *Update branch*, followed the candidate |
| A descendant for which that log is non-empty | `edited`: the log with `--stat -p`, containing the human's commits and diffs |
| Not a descendant of the candidate (a force-push) | `edited`: a rewritten-head note and `git diff --stat candidate head` |
| Missing from GitHub, or the fetch fails | No merge run; the task remains merged and stderr says it cannot tell whether the PR was changed |

Reports are capped at 20,000 characters. The first-parent, no-merges walk keeps base merges out of the human's commits. A PR taken up from GitHub as already merged has no candidate and gets no merge run. Use `factory show TASK --role merge` to read one task's record.

---

## Several maintainers

Each keeps their own board; GitHub is what they share. `factory sync && factory status --refresh` (and every plan run, which starts with a refresh) takes up the factory PRs this board didn't open: a `queued` or `failed` task with an open PR on `factory/TASK` becomes `pr_open`, with its candidate, base and stack read from the PR and its branch, and one with a merged PR becomes `merged`, with a warning when that PR merged into another task's branch rather than the trunk. Closed PRs are history and are ignored; holds (`abandoned`) and running tasks are left alone. Logs, transcripts and costs stay with the board that ran the task.

---

## Troubleshooting

| Symptom | Cause, and what to do |
|---|---|
| `… which the factory refuses; run it by hand` | The contract's verification runs a denied command. Do the task by hand, or `--skip-gates verification` |
| `.factory/config.yaml: unknown key …` | A typo in the config; `factory config` shows what was understood |
| `unknown flow NAME (flows: default, …)` | The `flow` or `--flow` value matches no flow in `flows`. `factory config` prints the defined names; use one or add it under `flows:` |
| `flows.<name>.<step>: build steps come first (after any plan or test step) and are contiguous` (or `at most one plan step`, `the plan step must be first`, `at most one test step`, `the test step must be directly before the first build step`, `at most one verify step`, `the verify step must be last`, `at least one build step is required`, `at most one gates step`) | The steps must follow `[plan]? [test]? build+ (review \| gates)* [verify]?`. Reorder them; see [Agent flows](architecture.md#agent-flows) |
| `flow NAME has a test step: set test_paths in .factory/config.yaml` | A test-bearing flow needs globs where its tester may write. Set for example `test_paths: ["tests/**"]`; `factory run` refuses before any work without them |
| `the tests pass before the change` | The test step's try was not red: its tests already hold without the change. The try is discarded and the step runs again with that feedback; after two failed tries the task fails before the build |
| `The try wrote no tests.` | The tester changed nothing, but a test command fails or selects no tests before the change, so there is a test to write. When every test command already passes before the change (a documentation or spec task naming existing tests), a try that writes nothing is recorded `no tests needed` and the build starts without locked tests |
| `COMMAND selects no tests: write the tests it names` | At the test commit, COMMAND names tests that do not exist. The try is discarded and the tester runs again with the reason; zero selected tests never counts as red |
| The `acceptance_untouched` gate fails | The builder changed or removed a locked tester-written line, or deleted one of its files. The gate detail names each affected file. Lines may be added, but no line from the test commit may change or go; restore the locked content rather than weakening the test |
| A review run is recorded as `APPROVE (unproven)` | A proving reviewer reported CHANGES, but no REPRO failed again and no blocker or major was tagged `[scope]`. The verdict becomes APPROVE; the findings and `## Proof` stay in the review report and PR for the human, and the verifier receives them |
| Status `DEAD` | The `factory run` process died (killed, crashed). `factory status --refresh` marks it failed; run the task or its plan again |
| `cannot stack TASK: its open dependencies conflict` | Merge one of the dependencies' PRs, `factory status --refresh`, then run again |
| Status `conflict` | The PR no longer applies to its base. `factory run TASK` (or its plan) resolves it; see [Merge conflicts](architecture.md#merge-conflicts) |
| `TASK: merged; can't tell whether it was changed before merging (…)` | GitHub gave no final head or the fetch failed, so no `merge` run was recorded. The task is merged all the same; inspect the PR by hand if you need to know what changed |
| A conflict resolution `failed` | The PR still holds its old head. Run the task again to rebuild it from scratch on the trunk |
| Status `ci_failed` | CI fails on the PR's head. `factory show TASK --role ci` names the checks and shows the logs; `factory run TASK` (or its plan) fixes them; see [CI failures](architecture.md#ci-failures) |
| Status `changes_requested` | A review requests changes on the PR's head, which is the factory's candidate. `factory status --refresh` marks it; `factory run TASK` (or its plan) addresses the review, and `factory show TASK --role human_review` shows the brief; see [Review comments](architecture.md#review-comments) |
| A review rework `failed` | The builder couldn't address the review, or review or gates rejected the result. The PR still holds its old head and the task is `failed` | Run the task again to rebuild it from scratch, or `factory run TASK --force` to do that straight away |
| A review was answered without a change | The builder found nothing to change; its answer was posted on the PR as a comment, the reviews count as addressed, and the task is back to `pr_open` | Nothing to do |
| A verify run ends with outcome `report (fallback)` | The verifier's summary couldn't be read in the fixed shape, so the factory wrote one from the contract, the diff and the reviewers' findings; the PR is unaffected. Read the verifier's whole report with `factory show TASK --step STEP` (STEP is the verify step's name, `verify` in the default flow); see [Pull requests](architecture.md#pull-requests) |
| A PR body says `… kept N of M characters: factory show TASK --step STEP` | The block was capped to keep the body under its 60,000-character limit. Run the command it names for the whole report; `factory show TASK` has the planner's plan and every agent's full report |
| `… not the factory's candidate: someone pushed to it` | A commit the factory didn't make is on the PR branch, so its CI isn't the factory's to fix. Fix it there, or `factory run TASK --force` to rebuild |
| A CI fix `failed` | The PR still holds the failing head. Run the task again to rebuild it from scratch on the trunk |
| `⚠ stopped: step limit` in the log | The agent used `max_steps`. Raise it with `max_steps: {ROLE: N}` in `.factory/config.yaml`, or narrow the task. A review that stops there without a verdict gets one more call, without tools, for its final review (`nudge: verdict` in the log) |
| `factory prompt` or the run log prints `⚠ <step>'s prompt has no VERDICT: line; every review will count as CHANGES` | A custom review prompt without `VERDICT: APPROVE` and `VERDICT: CHANGES` lines fails safe to CHANGES, so every attempt is spent. Add the verdict lines to `.factory/agents/<step>.md` (or its kind's override) |
| Gates fail on network or dependency fetches | The sandbox is offline. Fetch dependencies first, or pass `--network` for tasks that download |
| A tool is "not found" inside the sandbox | It lives under `$HOME`, which is hidden. Add its directory to `sandbox.ro_binds` and `sandbox.path` |
| `set OPENROUTER_API_KEY first` | Export the key for the providers the roles use (`factory run` lists them) |
| A push or `gh` call fails with 403 or `Permission denied` while a token is set | The token can't do it. Give it the permissions under [Credentials](#credentials), or unset `GITHUB_TOKEN`/`GH_TOKEN` to use your gh login |
| `error: PaymentRequiredResponseError: … available credits` | OpenRouter credits ran out. Parallel runs reserve credit for their in-flight requests, so this can appear before the balance hits zero. Add credits, then run the plan again |
| `error: … ConnectError` / `name resolution` | Network outage. Model calls are retried with backoff for about 30 s before the run fails; run the plan again once it's back |
| A plan run leaves a task `queued` | A dependency has no PR (it failed, is held, or is in another plan). `factory status PLAN` shows what it waits for |
| A stacked PR shows its dependency's changes | Its dependency merged but its commits didn't rebase cleanly, so it is `conflict` and targets the trunk already. Run the task to resolve it |
| Costs show `-` | The model isn't on OpenRouter's price list, or the list couldn't be fetched |
| `CASE: hidden/solution files readable inside its sandbox: …` (or `CASE: hidden/solution files readable under its dependency_sources: …`) | The case's sandbox binds, `sandbox.path` or `dependency_sources` reach its own fixture files, so agents could read the answers. Remove that bind or source; the shipped cases bind nothing from `$HOME` |
| `CASE: required command 'X' is missing from its sandbox` | `requires` names a command not on the case sandbox's `PATH`. Add its directory to the case config's `sandbox.path` or `ro_binds`, or install the tool |
| Bench cells end `stopped` or `skipped` | The budget ran out: a `stopped` cell hit the cost limit it received when it started; a `skipped` cell never started. Raise `--max-cost`, cut variants or repeats, or preview with `--dry-run`. The command exits 1 whenever any cell ended `error`, `stopped` or `skipped` |
