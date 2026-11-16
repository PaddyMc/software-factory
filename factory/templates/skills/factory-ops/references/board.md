# The board

Read before changing factory state: the database or the worktrees.

## Before anything: is a run active?

```bash
pgrep -af "factory run" | grep -v pgrep
```

Plan runs and task runs live outside your session. While any is active, don't switch the main checkout's branch (new tasks start from its current branch), don't reset the database, and don't remove worktrees.

## How is the factory doing?

```bash
factory stats [--since DATE] [--until DATE] [--plan P] [--json]
```

This is read-only: it reads the board and summarises outcomes, attempts, costs, gate failures, reworks and human edits over the window. Its per-step rows are split by flow, model and prompt version. `--since` is inclusive, `--until` exclusive, and either can be omitted; `--plan` takes a plan name or path. `factory show TASK --role merge` shows whether one task merged `as_built` or was `edited`, with the human's commits when available.

## Reset the board ("clean the db and start all tasks again")

Archive rather than delete, and keep the build cache warm. `factory config` prints the board's directory:

```bash
H=<the board directory from `factory config`>
A=$H/archive-$(date -u +%Y%m%dT%H%M%SZ); mkdir -p $A
mv $H/factory.db $H/logs $H/transcripts $A/          # keep $H/cache (build caches)
git worktree list | awk -v h="$H/worktrees/" 'index($1, h) == 1 {print $1}' | xargs -r -n1 git worktree remove --force
git worktree prune
factory sync                                         # every contract back to queued
factory status --refresh                             # takes up the open and merged factory PRs again
```

- Old `factory/*` branches on GitHub are overwritten when each task pushes again. Closed PRs stay closed, and reruns open new ones.
- Holds are lost on reset; reapply them with `factory abandon TASK --note "hold: <why>"`.
- A `factory top` that is already open keeps watching the old database. Restart it.
