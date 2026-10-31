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
| `session_log` | — | Directory: every task must add `<dir>/<today>.md` (`session_log` gate) |
| `e2e.dir` | — | Every task must add a new test directly under this directory (`e2e_written` gate) |
| `e2e.language` | `rust` | How new tests are found: `rust` (`#[test]`, `#[tokio::test]` fns) or `python` (`def test_*`) |
| `e2e.run_new` | — | Command run per new test; `{target}` = file stem, `{name}` = function, `{path}` = repo-relative file |
| `e2e.run_all` | — | The whole suite (used with `--full-e2e`, or when `run_all_when` matches) |
| `e2e.run_all_when` | `[]` | Regexes over changed paths that run the whole suite instead of only the new tests |
| `unit_tests` | `[]` | Commands for the `unit_tests` gate |
| `lockfiles` | common lockfiles | Files the `diff` gate notes when they change |
| `dependency_sources` | cargo registry and git sources, rustup toolchains | Directories the agents' file tools may also read, by absolute path (never write) |
| `models` | `{}` | Model per role (`plan`, `build`, `review`, `verify`), e.g. `{review: "anthropic:claude-…"}`; over the prompt's frontmatter |
| `max_steps` | `{}` | Model calls per agent run, per role; over the prompt's frontmatter |
| `denied_commands` | `[]` | Extra regexes the agents' `run` tool refuses (git push/commit/reset…, `sudo`, `gh`, `terraform apply/destroy` and `factory` are built in) |
| `sandbox.ro_binds` / `rw_binds` | rustup + uv read-only, `~/.cargo` writable | Host paths visible inside the sandbox (missing ones are skipped) |
| `sandbox.hide` | cargo credentials | Files masked with `/dev/null` |
| `sandbox.path` | `~/.cargo/bin`, `~/.local/bin` | Prepended to `PATH` |
| `sandbox.env` / `offline_env` | cargo/uv cache dirs / `CARGO_NET_OFFLINE`, `UV_OFFLINE` | Environment (`~` = home, `{cache}` = `$FACTORY_HOME/cache`); `offline_env` applies without `--network` |
| `sandbox.cache_dirs` | `target`, `uv` | Subdirectories of the shared cache to create |

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
| [`/plan-workstream`](../factory/templates/skills/plan-workstream/SKILL.md) | `$plan-workstream` | Before work starts | Grounds in the config, roadmap, plans and code; locks 2–4 strategic decisions with you; writes a plan whose contracts satisfy the configured gates; updates the roadmap; runs `factory validate-plan` |
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
| `factory prompt ROLE` | Print a role's prompt as the agents get it (the repository's override, else the shipped one), with its model |
| `factory validate-plan [PLAN…]` | Check contracts |
| `factory sync` | Load every contract from the plans into the db (statuses kept) |
| `factory status [PLAN] [--refresh] [--json]` | The board, grouped by plan with a task counter. `--refresh` picks up merged or closed PRs, takes up open or merged PRs opened from another board, moves stacked PRs whose dependencies merged, marks PRs that conflict with their base `conflict` and PRs whose CI fails `ci_failed`, and fails dead runs |
| `factory run PLAN [--parallel N] [--network-for T1,T2] [flags]` | Every task of the plan without a PR, one PR each, dependents stacked on open dependency PRs; PRs in `conflict` get their conflicts resolved, and PRs in `ci_failed` get their CI fixed |
| `factory run TASK [flags]` | Run one task in the foreground (stacked the same way). On a `conflict` task it resolves the conflicts, and on a `ci_failed` task it fixes CI; `--force` rebuilds it instead |
| `factory top [PLAN] [--once]` | Live dashboard: each active plan with its glyph strip (✓ merged ◆ PR open ≠ PR conflicts ! CI fails ▶ running ✗ failed · queued ⊘ held) and counter, then its tasks' progress, current action, elapsed and quiet time, cost; recent events |
| `factory logs TASK [-f] [-n N]` / `factory logs --all -f` | One task's log, or every task's log merged |
| `factory trace TASK [--role R] [--attempt N] [--all]` | Per-step model time, tool time, context size, cached tokens, output, cost, calls, largest results |
| `factory transcript TASK [--role R] [--attempt N] [--all] [--full]` | Exactly what the model saw and did |
| `factory show TASK [--role R]` | Every step's report and stats |
| `factory gates TASK [--ref R] [--base B] [--skip …]` | Deterministic gates only, in a throwaway worktree. The base defaults to the PR a stacked task is built on, else the default branch |
| `factory requeue TASK…` | Put `failed` or `abandoned` tasks back to `queued` so the next plan run picks them up (refuses running, open-PR and merged tasks) |
| `factory clean TASK` | Remove a task's worktree |
| `factory abandon TASK` | Mark a task abandoned (a hold: plan runs skip it) |
| `factory check-output --cmd C --exit N LOG` | Classify a test log (for CI) |

Useful `run` flags:

| Flag | Effect |
|---|---|
| `--base B` | Branch for the worktree and PR (default: current branch) |
| `--model M` | Override every role's model |
| `--max-attempts N` | Build attempts (default 3) |
| `--max-cost USD` | Abort the task above this cost |
| `--network` | Allow network in the sandbox |
| `--no-pr` | Stop after the gates pass, without pushing |
| `--skip-gates a,b` | Skip the named gates |
| `--full-e2e` | Always run the whole e2e suite |
| `--notify` | Desktop notification when the run ends |
| `--quiet` | Log to the file only |
| `--force` | Run even if the status, or a dependency without a PR, would refuse |

---

## Several maintainers

Each keeps their own board; GitHub is what they share. `factory sync && factory status --refresh` (and every plan run, which starts with a refresh) takes up the factory PRs this board didn't open: a `queued` or `failed` task with an open PR on `factory/TASK` becomes `pr_open`, with its candidate, base and stack read from the PR and its branch, and one with a merged PR becomes `merged`. Closed PRs are history and are ignored; holds (`abandoned`) and running tasks are left alone. Logs, transcripts and costs stay with the board that ran the task.

---

## Troubleshooting

| Symptom | Cause, and what to do |
|---|---|
| `… which the factory refuses; run it by hand` | The contract's verification runs a denied command. Do the task by hand, or `--skip-gates verification` |
| `.factory/config.yaml: unknown key …` | A typo in the config; `factory config` shows what was understood |
| Status `DEAD` | The `factory run` process died (killed, crashed). `factory status --refresh` marks it failed; run the task or its plan again |
| `cannot stack TASK: its open dependencies conflict` | Merge one of the dependencies' PRs, `factory status --refresh`, then run again |
| Status `conflict` | The PR no longer applies to its base. `factory run TASK` (or its plan) resolves it; see [Merge conflicts](architecture.md#merge-conflicts) |
| A conflict resolution `failed` | The PR still holds its old head. Run the task again to rebuild it from scratch on the trunk |
| Status `ci_failed` | CI fails on the PR's head. `factory show TASK --role ci` names the checks and shows the logs; `factory run TASK` (or its plan) fixes them; see [CI failures](architecture.md#ci-failures) |
| `… not the factory's candidate: someone pushed to it` | A commit the factory didn't make is on the PR branch, so its CI isn't the factory's to fix. Fix it there, or `factory run TASK --force` to rebuild |
| A CI fix `failed` | The PR still holds the failing head. Run the task again to rebuild it from scratch on the trunk |
| `⚠ stopped: step limit` in the log | The agent used `max_steps`. Raise it with `max_steps: {ROLE: N}` in `.factory/config.yaml`, or narrow the task |
| Gates fail on network or dependency fetches | The sandbox is offline. Fetch dependencies first, or pass `--network` for tasks that download |
| A tool is "not found" inside the sandbox | It lives under `$HOME`, which is hidden. Add its directory to `sandbox.ro_binds` and `sandbox.path` |
| `set OPENROUTER_API_KEY first` | Export the key for the providers the roles use (`factory run` lists them) |
| A push or `gh` call fails with 403 or `Permission denied` while a token is set | The token can't do it. Give it the permissions under [Credentials](#credentials), or unset `GITHUB_TOKEN`/`GH_TOKEN` to use your gh login |
| `error: PaymentRequiredResponseError: … available credits` | OpenRouter credits ran out. Parallel runs reserve credit for their in-flight requests, so this can appear before the balance hits zero. Add credits, then run the plan again |
| `error: … ConnectError` / `name resolution` | Network outage. Model calls are retried with backoff for about 30 s before the run fails; run the plan again once it's back |
| A plan run leaves a task `queued` | A dependency has no PR (it failed, is held, or is in another plan). `factory status PLAN` shows what it waits for |
| A stacked PR shows its dependency's changes | Its dependency merged but its commits didn't rebase cleanly, so it is `conflict` and targets the trunk already. Run the task to resolve it |
| Costs show `-` | The model isn't on OpenRouter's price list, or the list couldn't be fetched |
