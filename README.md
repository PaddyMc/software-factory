# Software factory

`factory run <plan>` turns each **task contract** in a plan into a **pull request** for you to review and merge. For every task, four AI agents (planner, builder, reviewer, verifier) work in a sandboxed git worktree, and a PR opens only when every deterministic check passes. Agents never push, merge or see secrets: you merging the PR is the approval.

- [Architecture](docs/architecture.md): how a task goes from contract to PR, stacked PRs, conflicts, CI fixes, gates and the sandbox.
- [Reference](docs/reference.md): configuration, task contracts, skills, every command and flag, troubleshooting.

## Install

Prerequisites (Linux only): `uv`, `git`, `gh` (authenticated), bubblewrap (`bwrap`), and your project's toolchain.

```bash
uv tool install git+https://github.com/PaddyMc/software-factory
uv tool upgrade software-factory     # later, to update
```

To work on the factory itself, install from a checkout so your edits apply straight away:

```bash
uv tool install --editable /path/to/software-factory
```

## Set up a repository

```bash
cd your-repo
factory init                    # .factory/config.yaml, skills, a starter plan, an AGENTS.md section
$EDITOR .factory/config.yaml    # where plans live, test commands, models, sandbox
factory config                  # the effective settings, and where the state lives
```

Re-running `factory init` is safe: it keeps existing files, and `--force` overwrites them. See [what it writes](docs/reference.md#factory-init) and [every config key](docs/reference.md#configure-a-project).

## Run tasks

A task is a fenced YAML contract in a plan, by default under `docs/plans/` ([format](docs/reference.md#task-contracts)). `/plan-workstream` in Claude Code or OpenCode (`$plan-workstream` in Codex) writes plans with you. Credentials come from the environment, so each shell or service is its own instance: see [credentials](docs/reference.md#credentials).

```bash
export OPENROUTER_API_KEY=sk-or-...
export GITHUB_TOKEN=github_pat_...  # optional: this instance's GitHub identity, instead of your gh login
uv sync                         # or cargo fetch, npm ci, …: the sandbox is offline, so fetch dependencies first

factory validate-plan           # check the contracts
factory sync                    # load them into the db
factory status                  # the board: ready / waiting / running / PR open / failed

factory run <plan>              # every task in a plan, one PR each (a plan's file name or path)
factory run <task-id>           # one task, in the foreground
factory top                     # live dashboard, in another terminal
```

A task whose dependency isn't merged yet is built on top of the dependency's open PR, so one run covers the whole plan. Merge from the bottom of each stack up, and after each merge run:

```bash
factory status --refresh        # records the merge, moves the PRs stacked on it, flags conflicts and failing CI
```

If a task fails, `factory show <task-id>` shows each step's report and `factory logs <task-id> -f` follows its log. Run the task or its plan again to retry. More in [troubleshooting](docs/reference.md#troubleshooting).

## Where things live

The state is local to your machine, in `$FACTORY_HOME`. That defaults to `~/.local/share/factory/<name>`, where `<name>` is `name` in `.factory/config.yaml` (the repository's directory name by default).

| Path | Contents |
|---|---|
| `$FACTORY_HOME/factory.db` | The SQLite database: every task's status, branch, PR and cost, and every agent run (older schemas migrate in place) |
| `$FACTORY_HOME/worktrees/<task>/` | The task's git worktree, on branch `factory/<task>` |
| `$FACTORY_HOME/logs/<task>.log` | Stage changes, agent messages, tool calls, gate results |
| `$FACTORY_HOME/transcripts/<task>/NNNNN-ROLE-ATTEMPT.jsonl` | A full transcript per role step: system prompt, messages, tool calls and results, usage, cost |
| `$FACTORY_HOME/cache/` | Shared build caches, and the OpenRouter price list (refreshed daily) |

To keep a separate board, for example for experiments, set `FACTORY_HOME` or `home:` in the config. Inside the repository, the factory's only files are the ones [`factory init` writes](docs/reference.md#factory-init) and your plans.

## Development

```bash
uv run pytest -q tests
```

How the tests are put together: [architecture](docs/architecture.md#development). What's planned next: [known limitations](docs/architecture.md#known-limitations-and-next-steps) and [`NEXT.md`](NEXT.md).

---

Extracted from the Cleartree project's factory, which keeps its own project-specific copy.
