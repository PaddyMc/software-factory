"""`factory` CLI."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from . import config as C
from . import contracts, factory_home, repo_root
from . import gates as G
from . import sandbox as S
from . import observe
from .db import ACTIVE, open_db, pid_alive
from .log import RunLog, log_path
from .verification import PASS, classify, tests_run


def _db():
    return open_db(factory_home())


def cmd_validate_plan(a) -> int:
    root = repo_root()
    try:
        cfg = C.load(root)
    except C.ConfigError as e:
        print(f"FAIL {C.CONFIG_PATH}: {e}")
        return 1
    plans = [root / p for p in a.plans] if a.plans else contracts.discover_plans(root, cfg)
    try:
        known = contracts.load_all(root)
    except contracts.ContractError as e:
        print(f"FAIL {e}")
        return 1
    bad = 0
    for p in plans:
        if a.plans or contracts.parse_plan(p, root):
            tasks, errs = contracts.validate_plan(p, root)
            if tasks:  # resolve depends_on against every plan: cross-plan dependencies are allowed
                errs = contracts.validate_tasks(tasks, known)
            print(f"{'FAIL' if errs else 'ok  '} {p.relative_to(root)} ({len(tasks)} tasks)")
            for e in errs:
                print(f"     {e}")
            for t in tasks:
                if not G.e2e_writable(t, cfg):
                    print(f"     warn: {t.id} is not factory-runnable: no allowed path can hold a new test "
                          f"under {cfg.e2e.dir} (the e2e_written gate would always fail)")
            bad += bool(errs)
    return 1 if bad else 0


def cmd_run(a) -> int:
    if a.ready or len(a.task_ids) > 1:
        return cmd_run_many(a)
    if not a.task_ids:
        print("give a task id, several task ids, or --ready", file=sys.stderr)
        return 2
    a.task_id = a.task_ids[0]
    return cmd_run_one(a)


def _child_args(a) -> list[str]:
    """Flags a scheduled child `factory run` inherits from the scheduler's command line."""
    out = []
    for flag, value in (("--base", a.base), ("--model", a.model), ("--skip-gates", a.skip_gates or None),
                        ("--max-cost", a.max_cost)):
        if value is not None:
            out += [flag, str(value)]
    out += ["--max-attempts", str(a.max_attempts)]
    for flag, on in (("--network", a.network), ("--no-sandbox", a.no_sandbox), ("--no-pr", a.no_pr),
                     ("--full-e2e", a.full_e2e), ("--notify", a.notify)):
        if on:
            out.append(flag)
    return out


def cmd_run_many(a) -> int:
    import os

    from . import scheduler
    from .agents import missing_keys, role_models

    root = repo_root()
    models = role_models(root, a.model)
    missing = missing_keys(models, os.environ)
    if missing:
        print(f"set {', '.join(missing)} first", file=sys.stderr)
        return 1
    try:
        tasks = contracts.load_all(root)
    except contracts.ContractError as e:
        print(f"FAIL {e}", file=sys.stderr)
        return 1
    unknown = [t for t in a.task_ids if t not in tasks]
    if unknown:
        print(f"unknown task(s): {', '.join(unknown)}", file=sys.stderr)
        return 1
    db = _db()
    db.sync(tasks)  # the scheduler works from the db; make sure it has the current contracts
    not_queued = [f"{t} ({db.task(t)['status']})" for t in a.task_ids if db.task(t)["status"] != "queued"]
    if not_queued:
        print(f"skipping {', '.join(not_queued)}: only queued tasks start (`factory retry` requeues failed ones)",
              file=sys.stderr)
    plan = scheduler.Plan(tasks=list(a.task_ids), ready=a.ready, parallel=a.parallel, watch=a.watch,
                          budget=a.budget, network_for=tuple(x for x in (a.network_for or "").split(",") if x),
                          child_args=_child_args(a))
    results = scheduler.run(db, plan, scheduler.default_launch(root), _refresh)
    print(scheduler.summary(db, results))
    return 0 if all(s in ("pr_open", "merged", "verifying") for s in results.values()) else 1


def cmd_run_one(a) -> int:
    import os

    from .agents import LangChainRoles, missing_keys, role_models
    from .pipeline import Options, Pipeline, PipelineError, create_worktree, git

    root = repo_root()
    home = factory_home()
    cfg = C.load(root)
    task = contracts.find_task(root, a.task_id)
    errs = contracts.validate_tasks([task], contracts.load_all(root))
    if errs:
        print("contract invalid:\n  " + "\n  ".join(errs), file=sys.stderr)
        return 1
    if not G.e2e_writable(task, cfg) and "e2e_written" not in a.skip_gates:
        print(f"{task.id} cannot pass the e2e_written gate: none of its allowed_paths can hold a new test under "
              f"{cfg.e2e.dir}. Fix the contract (add e.g. {cfg.e2e.dir}<name>{cfg.e2e.suffix}), or run it by hand.",
              file=sys.stderr)
        return 1
    models = role_models(root, a.model)
    missing = missing_keys(models, os.environ)
    if missing:
        print(f"set {', '.join(missing)} first (models: {', '.join(f'{r}={m}' for r, m in models.items())})",
              file=sys.stderr)
        return 1
    db = _db()
    db.upsert_task(task)
    row = db.task(task.id)
    if row["status"] in ACTIVE + ("pr_open", "merged") and not a.force:
        print(f"{task.id} is {row['status']}; use --force to run again", file=sys.stderr)
        return 1
    unmet = db.deps_unmet(task)
    if unmet and not a.force:
        print(f"{task.id} depends on unmerged tasks: {', '.join(unmet)} (use --force to override)", file=sys.stderr)
        return 1
    base_ref = a.base or git(root, "rev-parse", "--abbrev-ref", "HEAD")
    try:
        wt, base_sha = create_worktree(root, home, task.id, base_ref)
    except PipelineError as e:
        print(e, file=sys.stderr)
        return 1
    db.update(task.id, status="queued", branch=f"factory/{task.id}", base_ref=base_ref, base_sha=base_sha,
              candidate_sha=None, pr_url=None, attempts=0, note=None, progress=None)
    db.claim(task.id, os.getpid())
    sbx = S.make(wt, home / "cache", sandbox=not a.no_sandbox, network=a.network, cfg=cfg.sandbox)
    opts = Options(base_ref=base_ref, max_attempts=a.max_attempts, open_pr=not a.no_pr,
                   skip_gates=tuple(x for x in a.skip_gates.split(",") if x), full_e2e=a.full_e2e,
                   max_cost=a.max_cost, config=cfg)
    log = RunLog(log_path(home, task.id), echo=not a.quiet)
    log("run", f"=== {task.id}: worktree {wt} on factory/{task.id} from {base_ref} ({base_sha[:12]}); "
               f"models {', '.join(f'{r}={m}' for r, m in models.items())}")
    print(f"log: {log.path}  (follow elsewhere: factory logs {task.id} -f)", flush=True)
    try:
        result = Pipeline(db, LangChainRoles(root, a.model, cfg=cfg), task, wt, base_sha, sbx, opts, log=log,
                          transcript_dir=home / "transcripts" / task.id).run()
    finally:
        log.close()
    row = db.task(task.id)
    summary = (f"{task.id}: {row['status']} after {row['attempts']} build(s)"
               + (f" — {row['pr_url']}" if row["pr_url"] else "")
               + (f" — ${row['cost_usd']:.2f}" if row["cost_usd"] is not None else ""))
    print(summary + (f"\n{row['note']}" if row["note"] else ""))
    if a.notify:
        _notify(f"factory: {task.id} {row['status']}", row["pr_url"] or observe.failing_summary(row["note"]))
    return 0 if result.get("outcome") in ("pr_open", "verified") else 1


def _notify(title: str, body: str) -> None:
    import shutil
    if shutil.which("notify-send"):
        subprocess.run(["notify-send", title, body or ""], capture_output=True)


def _refresh(db) -> None:
    for row in db.tasks():
        if row["status"] in ACTIVE and row["pid"] and not pid_alive(row["pid"]):
            db.update(row["id"], status="failed", progress=None,
                      note=f"process {row['pid']} exited mid-run (killed or crashed); `factory clean` then rerun")
        if row["status"] == "pr_open" and row["pr_url"]:
            p = subprocess.run(["gh", "pr", "view", row["pr_url"], "--json", "state", "-q", ".state"],
                               capture_output=True, text=True)
            state = p.stdout.strip()
            if state == "MERGED":
                db.update(row["id"], status="merged")
            elif state == "CLOSED":
                db.update(row["id"], status="abandoned", note="PR closed without merge")


def _detail(db, r) -> str:
    return observe.detail(db, r)


def cmd_status(a) -> int:
    db = _db()
    if a.refresh:
        _refresh(db)
    rows = db.tasks()
    if a.json:
        print(json.dumps([dict(r) | {"detail": _detail(db, r)} for r in rows], indent=2))
        return 0
    if not rows:
        print("no tasks yet — `factory sync` loads every contract from the plans")
    for r in rows:
        cost = f"${r['cost_usd']:.2f}" if r["cost_usd"] is not None else ""
        status = "DEAD" if observe.liveness(r) else r["status"]
        print(f"{r['id']:<31} {status:<10} builds={r['attempts']:<2} {cost:>6} {_detail(db, r)}")
    return 0


def cmd_top(a) -> int:
    import time
    home = factory_home()
    db = _db()
    try:
        while True:
            screen = observe.render_top(db, home, events=a.events)
            if a.once:
                print(screen)
                return 0
            sys.stdout.write("\033[H\033[2J" + screen + f"\n\n(refreshing every {a.interval}s · Ctrl-C to exit)\n")
            sys.stdout.flush()
            time.sleep(a.interval)
    except KeyboardInterrupt:
        return 0


def cmd_trace(a) -> int:
    db = _db()
    runs = [r for r in db.runs(a.task_id) if r["transcript"]
            and (not a.role or r["role"] == a.role) and (a.attempt is None or r["attempt"] == a.attempt)]
    if not runs:
        print(f"no transcripts for {a.task_id}" + (f" role={a.role}" if a.role else ""), file=sys.stderr)
        return 1
    for r in (runs if a.all else runs[-1:]):
        print(f"=== {a.task_id} · {r['role']} #{r['attempt']} — {r['outcome'] or 'running'} ===")
        if Path(r["transcript"]).is_file():
            print(observe.render_trace(Path(r["transcript"])))
        print()
    return 0


def cmd_transcript(a) -> int:
    db = _db()
    runs = [r for r in db.runs(a.task_id) if r["transcript"]
            and (not a.role or r["role"] == a.role) and (a.attempt is None or r["attempt"] == a.attempt)]
    if not runs:
        print(f"no transcripts for {a.task_id}" + (f" role={a.role}" if a.role else ""), file=sys.stderr)
        return 1
    if not a.all:
        runs = runs[-1:]
    for r in runs:
        path = Path(r["transcript"])
        cost = f", ${r['cost_usd']:.4f}" if r["cost_usd"] is not None else ""
        print(f"=== {r['role']} #{r['attempt']} — {r['outcome'] or 'running'} ({r['model'] or '-'}, "
              f"{r['steps']} steps, {r['tokens_in']} in / {r['tokens_out']} out{cost}, {r['refused']} refused) ===")
        print(f"    {path}")
        if path.is_file():
            print(observe.render_transcript(path, full=a.full))
        print()
    return 0


def cmd_sync(a) -> int:
    root = repo_root()
    try:
        tasks = contracts.load_all(root)
    except contracts.ContractError as e:
        print(f"FAIL {e}", file=sys.stderr)
        return 1
    errs = contracts.validate_tasks(list(tasks.values()))
    if errs:
        print("contracts invalid (fix, then sync):\n  " + "\n  ".join(errs), file=sys.stderr)
        return 1
    db = _db()
    added, updated, orphaned = db.sync(tasks)
    print(f"synced {len(tasks)} tasks from the plans: {len(added)} added, {len(updated)} updated")
    for t in orphaned:
        print(f"  note: {t} is in the db but no longer in any plan")
    ready = [r["id"] for r in db.tasks() if r["status"] == "queued" and db.readiness(r["id"]) == "ready"]
    print("ready to run: " + (", ".join(ready) if ready else "none"))
    return 0


def cmd_logs(a) -> int:
    import time

    if a.all or not a.task_id:
        try:
            observe.follow_all(factory_home(), a.lines, a.follow)
        except KeyboardInterrupt:
            pass
        return 0
    path = log_path(factory_home(), a.task_id)
    if not path.exists():
        print(f"no log yet for {a.task_id} ({path})", file=sys.stderr)
        return 1
    db = _db()
    with path.open() as f:
        lines = f.readlines()
        sys.stdout.writelines(lines[-a.lines:] if a.lines else lines)
        sys.stdout.flush()
        if not a.follow:
            return 0
        idle = 0.0
        while True:
            line = f.readline()
            if line:
                sys.stdout.write(line)
                sys.stdout.flush()
                idle = 0.0
                continue
            time.sleep(0.5)
            idle += 0.5
            row = db.task(a.task_id)
            if idle >= 2 and (row is None or row["status"] not in ACTIVE + ("queued",)):
                print(f"-- {a.task_id} is {row['status'] if row else 'gone'}; stopped following --")
                return 0


def cmd_show(a) -> int:
    db = _db()
    row = db.task(a.task_id)
    if row is None:
        print(f"{a.task_id} is not in the factory", file=sys.stderr)
        return 1
    print(f"# {row['id']} — {row['status']}\n")
    for k in ("plan", "branch", "base_ref", "base_sha", "candidate_sha", "pr_url", "attempts", "note"):
        print(f"- {k}: {row[k]}")
    if row["cost_usd"] is not None:
        print(f"- cost: ${row['cost_usd']:.4f}")
    if row["status"] in ACTIVE:
        print(f"- process: {row['pid']} ({'alive' if pid_alive(row['pid']) else 'GONE'}), now: {row['activity']}")
    for r in db.runs(a.task_id):
        if a.role and r["role"] != a.role:
            continue
        stats = f"{r['steps']} steps, {r['tokens_in']} in / {r['tokens_out']} out"
        stats += f", ${r['cost_usd']:.4f}" if r["cost_usd"] is not None else ""
        stats += f", {r['refused']} tool calls refused" if r["refused"] else ""
        print(f"\n## {r['role']} #{r['attempt']} — {r['outcome']} ({r['model'] or '-'}, {r['started_at']}; {stats})")
        if r["transcript"]:
            print(f"transcript: factory transcript {a.task_id} --role {r['role']} --attempt {r['attempt']}")
        print()
        print(r["report"] or "")
    return 0


def cmd_gates(a) -> int:
    """Gates for a ref, in a throwaway detached worktree (for reviewing hand-written work)."""
    from .pipeline import git

    root = repo_root()
    home = factory_home()
    cfg = C.load(root)
    task = contracts.find_task(root, a.task_id)
    sha = git(root, "rev-parse", "--verify", f"{a.ref}^{{commit}}")
    base = git(root, "merge-base", a.base, sha)
    wt = home / "review" / f"{task.id}-{sha[:12]}"
    if not wt.exists():
        git(root, "worktree", "add", "-q", "--detach", str(wt), sha)
    try:
        sbx = S.make(wt, home / "cache", sandbox=not a.no_sandbox, cfg=cfg.sandbox)
        gs = G.run_gates(task, wt, base, sha, sbx, cfg, skip=tuple(x for x in a.skip.split(",") if x),
                         full_e2e=a.full_e2e)
    finally:
        git(root, "worktree", "remove", "--force", str(wt), check=False)
    print(f"# Gates · {task.id} · {a.ref} ({sha[:12]}) vs {a.base} (merge-base {base[:12]})\n")
    print(G.table(gs))
    print(f"\n{'PASS' if G.passed(gs) else 'FAIL'}")
    return 0 if G.passed(gs) else 1


def cmd_clean(a) -> int:
    from .pipeline import git

    root = repo_root()
    wt = factory_home() / "worktrees" / a.task_id
    if wt.exists():
        git(root, "worktree", "remove", "--force", str(wt))
        print(f"removed {wt}")
    db = _db()
    if db.task(a.task_id) and db.task(a.task_id)["status"] in ACTIVE + ("queued",):
        db.update(a.task_id, status="failed", note="cleaned while in progress")
    return 0


def cmd_retry(a) -> int:
    """Requeue failed tasks (all of them, or the ones named): remove the leftover worktree and set them back
    to queued. A scheduler then starts them again, including one already running with --watch."""
    from .pipeline import git

    root = repo_root()
    db = _db()
    targets = [(t, db.task(t)) for t in a.task_ids] if a.task_ids else \
        [(r["id"], r) for r in db.tasks()
         if r["status"] == "failed" or (r["status"] in ACTIVE and observe.liveness(r) == "DEAD")]
    requeued = []
    for tid, row in targets:
        if row is None:
            print(f"{tid} is not in the factory (`factory sync`?)", file=sys.stderr)
            continue
        if row["status"] in ACTIVE and pid_alive(row["pid"]):
            print(f"{tid} is running ({row['status']}); leaving it", file=sys.stderr)
            continue
        if row["status"] in ("queued", "pr_open", "merged"):
            hint = "" if row["status"] == "queued" else f" (`factory run {tid} --force` redoes it)"
            print(f"{tid} is {row['status']}; nothing to retry{hint}", file=sys.stderr)
            continue
        wt = factory_home() / "worktrees" / tid
        if wt.exists():
            git(root, "worktree", "remove", "--force", str(wt))
        db.update(tid, status="queued", progress=None, note=None)
        requeued.append(tid)
    if not requeued:
        print("nothing to retry")
        return 1 if a.task_ids else 0
    print(f"requeued {len(requeued)}: {', '.join(requeued)}")
    print("a scheduler running with --watch starts them; otherwise `factory run --ready --parallel N`")
    return 0


def cmd_abandon(a) -> int:
    _db().update(a.task_id, status="abandoned", note=a.note)
    return 0


def cmd_init(a) -> int:
    """Scaffold .factory/config.yaml and the four role prompts in the current repository."""
    from importlib import resources

    root = repo_root()
    templates = resources.files("factory") / "templates"
    files = {C.CONFIG_PATH: templates / "config.yaml"}
    files |= {f".factory/agents/{name}": templates / "agents" / name
              for name in ("planner.md", "builder.md", "reviewer.md", "verifier.md")}
    for rel, src in files.items():
        dest = root / rel
        if dest.exists() and not a.force:
            print(f"keep   {rel} (exists; --force overwrites)")
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        text = src.read_text()
        if rel == C.CONFIG_PATH:
            text = text.replace("name: my-project", f"name: {root.name}", 1)
        dest.write_text(text)
        print(f"wrote  {rel}")
    print("next: edit .factory/config.yaml, add task contracts under docs/plans/, then `factory validate-plan` "
          "and `factory sync`")
    return 0


def cmd_config(a) -> int:
    """The effective project settings (defaults filled in)."""
    import dataclasses

    import yaml
    root = repo_root()
    try:
        cfg = C.load(root)
    except C.ConfigError as e:
        print(f"{C.CONFIG_PATH}: {e}", file=sys.stderr)
        return 1

    def plain(v):
        if dataclasses.is_dataclass(v):
            return {k: plain(x) for k, x in dataclasses.asdict(v).items()}
        if isinstance(v, (list, tuple)):
            return [plain(x) for x in v]
        if isinstance(v, dict):
            return {k: plain(x) for k, x in v.items()}
        return v

    source = C.CONFIG_PATH if (root / C.CONFIG_PATH).is_file() else "defaults (no config file)"
    print(f"# {source}; state in {factory_home()}")
    print(yaml.safe_dump(plain(cfg), sort_keys=False).rstrip())
    return 0


def cmd_check_output(a) -> int:
    out = Path(a.log).read_text(errors="replace")
    outcome = classify(a.cmd, a.exit, out)
    print(f"{outcome}: {a.cmd} (tests run: {tests_run(out)})")
    return 0 if outcome == PASS else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="factory", description="plan -> build -> review -> verify -> PR, per task")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="scaffold .factory/config.yaml and the four role prompts here")
    s.add_argument("--force", action="store_true", help="overwrite existing files")
    s.set_defaults(fn=cmd_init)

    s = sub.add_parser("config", help="print the effective project settings")
    s.set_defaults(fn=cmd_config)

    s = sub.add_parser("validate-plan", help="validate task contracts (never edits the plan)")
    s.add_argument("plans", nargs="*")
    s.set_defaults(fn=cmd_validate_plan)

    s = sub.add_parser("run", help="run tasks through the four agents and open PRs (one, several, or --ready)")
    s.add_argument("task_ids", nargs="*", metavar="task_id")
    s.add_argument("--ready", action="store_true", help="run every ready task (scheduler mode)")
    s.add_argument("--parallel", type=int, default=3, help="scheduler: max tasks running at once")
    s.add_argument("--watch", action="store_true",
                   help="scheduler: keep running; poll GitHub for merged PRs and start newly ready tasks")
    s.add_argument("--budget", type=float, help="scheduler: stop starting tasks once this many USD are spent")
    s.add_argument("--max-cost", type=float, help="abort a task once it has cost this many USD")
    s.add_argument("--network-for", help="scheduler: comma list of task ids that get --network")
    s.add_argument("--base", help="base branch for the worktree and PR (default: current branch)")
    s.add_argument("--model", help="override every role's model, e.g. openrouter:z-ai/glm-5.3")
    s.add_argument("--max-attempts", type=int, default=3, help="max build attempts (review/gate loops)")
    s.add_argument("--network", action="store_true", help="allow network inside the sandbox")
    s.add_argument("--no-sandbox", action="store_true", help="run commands without bubblewrap (unsafe)")
    s.add_argument("--no-pr", action="store_true", help="stop after gates pass; do not push or open a PR")
    s.add_argument("--skip-gates", default="", help="comma list, e.g. e2e_tests (recorded in the PR body)")
    s.add_argument("--full-e2e", action="store_true", help="run the whole e2e suite (e2e.run_all)")
    s.add_argument("--force", action="store_true", help="run despite status or unmerged dependencies")
    s.add_argument("--quiet", action="store_true", help="log to file only (no terminal echo)")
    s.add_argument("--notify", action="store_true", help="desktop notification (notify-send) when the run ends")
    s.set_defaults(fn=cmd_run)

    s = sub.add_parser("top", help="live dashboard: every running/failed/open/ready task + recent events")
    s.add_argument("--interval", type=float, default=2.0)
    s.add_argument("--events", type=int, default=12, help="recent log lines to show (0 = none)")
    s.add_argument("--once", action="store_true", help="print one frame and exit")
    s.set_defaults(fn=cmd_top)

    s = sub.add_parser("trace", help="per-step timing, context size, tokens, cost and tool calls of an agent loop")
    s.add_argument("task_id")
    s.add_argument("--role", choices=("plan", "build", "review", "verify"))
    s.add_argument("--attempt", type=int)
    s.add_argument("--all", action="store_true", help="every matching run, not just the latest")
    s.set_defaults(fn=cmd_trace)

    s = sub.add_parser("transcript", help="full agent transcript (every message, tool call and result)")
    s.add_argument("task_id")
    s.add_argument("--role", choices=("plan", "build", "review", "verify"))
    s.add_argument("--attempt", type=int)
    s.add_argument("--all", action="store_true", help="every matching run, not just the latest")
    s.add_argument("--full", action="store_true", help="do not truncate long messages / tool output")
    s.set_defaults(fn=cmd_transcript)

    s = sub.add_parser("sync", help="load every contract from the plans into the db (status kept)")
    s.set_defaults(fn=cmd_sync)

    s = sub.add_parser("logs", help="a task's live log, or every task's merged (--all)")
    s.add_argument("task_id", nargs="?")
    s.add_argument("--all", action="store_true", help="merge every task's log, prefixed with the task id")
    s.add_argument("-f", "--follow", action="store_true", help="keep printing until the run ends")
    s.add_argument("-n", "--lines", type=int, default=0, help="only the last N lines first")
    s.set_defaults(fn=cmd_logs)

    s = sub.add_parser("status", help="task board from the local database")
    s.add_argument("--refresh", action="store_true", help="update pr_open tasks from GitHub (merged/closed)")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_status)

    s = sub.add_parser("show", help="a task's runs and reports")
    s.add_argument("task_id")
    s.add_argument("--role", choices=("plan", "build", "review", "verify", "pr"))
    s.set_defaults(fn=cmd_show)

    s = sub.add_parser("gates", help="run the deterministic gates for a ref (no agents)")
    s.add_argument("task_id")
    s.add_argument("--ref", default="HEAD")
    s.add_argument("--base", default="main")
    s.add_argument("--skip", default="")
    s.add_argument("--full-e2e", action="store_true")
    s.add_argument("--no-sandbox", action="store_true")
    s.set_defaults(fn=cmd_gates)

    s = sub.add_parser("clean", help="remove a task's worktree")
    s.add_argument("task_id")
    s.set_defaults(fn=cmd_clean)

    s = sub.add_parser("retry", help="requeue failed tasks (all, or the ones named) so a scheduler runs them again")
    s.add_argument("task_ids", nargs="*")
    s.set_defaults(fn=cmd_retry)

    s = sub.add_parser("abandon", help="mark a task abandoned")
    s.add_argument("task_id")
    s.add_argument("--note", default="")
    s.set_defaults(fn=cmd_abandon)

    s = sub.add_parser("check-output", help="classify a test log; zero tests is not a pass")
    s.add_argument("--cmd", required=True)
    s.add_argument("--exit", type=int, required=True)
    s.add_argument("log")
    s.set_defaults(fn=cmd_check_output)

    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
