"""`factory` CLI."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from . import config as C
from . import contracts, factory_home, github, repo_root
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
                if why := G.manual_reason(t, cfg):
                    print(f"     warn: {t.id} is not factory-runnable: {why}")
            bad += bool(errs)
    return 1 if bad else 0


def cmd_run(a) -> int:
    root = repo_root()
    try:
        tasks = contracts.load_all(root)
        plan = None if a.target in tasks else contracts.find_plan(root, a.target)
    except contracts.ContractError as e:
        print(f"FAIL {e}", file=sys.stderr)
        return 1
    if a.target in tasks:
        a.task_id = a.target
        return cmd_run_one(a)
    if plan is None:
        print(f"{a.target} is neither a task id nor a plan (a path, or a plan's file name without .md)",
              file=sys.stderr)
        return 2
    return cmd_run_plan(a, plan, tasks)


def _child_args(a) -> list[str]:
    """Flags each task's child `factory run` inherits from the plan run's command line."""
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


def cmd_run_plan(a, plan: Path, tasks: dict) -> int:
    """Every task of one plan: one PR each, dependents stacked on their dependencies' open PRs."""
    import os

    from . import scheduler
    from .agents import missing_keys, role_models

    root = repo_root()
    rel = str(plan.relative_to(root))
    try:
        mine = contracts.plan_order([t for t in tasks.values() if t.plan == rel])
    except contracts.ContractError as e:
        print(f"FAIL {e}", file=sys.stderr)
        return 1
    if not mine:
        print(f"{rel} has no task contracts", file=sys.stderr)
        return 1
    errs = contracts.validate_tasks(mine, tasks)
    if errs:
        print("contracts invalid:\n  " + "\n  ".join(errs), file=sys.stderr)
        return 1
    cfg = C.load(root)
    models = role_models(root, a.model, cfg)
    missing = missing_keys(models, os.environ)
    if missing:
        print(f"set {', '.join(missing)} first", file=sys.stderr)
        return 1
    db = _db()
    db.sync(tasks)       # the run works from the db; make sure it has the current contracts
    _refresh(db)         # merged dependencies, dead runs, stacked PRs to move
    skip = tuple(x for x in a.skip_gates.split(",") if x)
    manual = {t.id: why for t in mine if (why := G.manual_reason(t, cfg)) and "verification" not in skip}
    p = scheduler.Plan(name=contracts.plan_name(rel), tasks=[t.id for t in mine], parallel=a.parallel,
                       network_for=tuple(x for x in (a.network_for or "").split(",") if x),
                       child_args=_child_args(a), manual=manual)
    results = scheduler.run(db, p, scheduler.default_launch(root))
    print(scheduler.summary(db, p))
    return 0 if all(s in ("pr_open", "merged") for s in results.values()) else 1


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
    if (why := G.manual_reason(task, cfg)) and "verification" not in a.skip_gates:
        print(f"{task.id}: {why}", file=sys.stderr)
        return 1
    models = role_models(root, a.model, cfg)
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
    stacked, unmet = db.deps(task)
    if unmet and not a.force:
        print(f"{task.id} waits for {', '.join(unmet)}: each dependency needs a merged or an open PR "
              f"(use --force to override)", file=sys.stderr)
        return 1
    old_wt = home / "worktrees" / task.id
    if old_wt.exists() and not (row["status"] in ACTIVE and pid_alive(row["pid"])):
        git(root, "worktree", "remove", "--force", str(old_wt))      # a finished run's leftovers
    resolution = ci_fix = None
    try:
        if row["status"] == "conflict" and not a.force:    # resolve the open PR's conflicts; --force rebuilds it
            wt, base_sha, pr_base, trunk, stacked, resolution = _replay(db, root, home, row)
        elif row["status"] == "ci_failed" and not a.force:  # fix the open PR's failing CI; --force rebuilds it
            from .stack import restack
            if (moved := restack(db, root, home, task.id)) and (now := db.task(task.id)["status"]) != "ci_failed":
                # The failure may have been its dependency's: CI judges the new head first.
                print(moved + ("; nothing to fix until CI runs on the new head" if now == "pr_open" else ""))
                return 0
            row = db.task(task.id)                          # a restack may have retargeted the PR
            fix = _ci_fix(root, home, row)
            if fix is None:
                db.update(task.id, status="pr_open", note=None)
                print(f"{task.id}: CI no longer fails on {row['pr_url']}; nothing to fix")
                return 0
            wt, ci_fix = fix
            base_sha, pr_base = row["base_sha"], row["base_ref"]
            stacked = [d for d in (row["stacked_on"] or "").split(",") if d and db.task(d)["status"] != "merged"]
        else:
            deps = [db.task(d) for d in stacked]
            if deps:   # build on the open PRs: start from the first, merge the others in; the PR targets the first
                trunk = deps[0]["trunk"] or deps[0]["base_ref"]
                pr_base, start = f"factory/{stacked[0]}", deps[0]["candidate_sha"]
                merge = tuple((d["id"], d["candidate_sha"]) for d in deps[1:])
            else:
                trunk = a.base or git(root, "rev-parse", "--abbrev-ref", "HEAD")
                pr_base, start, merge = trunk, _tip_or_local(root, trunk), ()
            wt, base_sha = create_worktree(root, home, task.id, start, merge)
    except PipelineError as e:
        print(e, file=sys.stderr)
        return 1
    if resolution:      # the open PR and its candidate stay until the resolution replaces them
        deps = [db.task(d) for d in stacked]
        db.update(task.id, status="queued", base_ref=pr_base, base_sha=base_sha, trunk=trunk,
                  stacked_on=",".join(stacked) or None, attempts=0, note=None, progress=None)
    elif ci_fix:        # likewise; the PR keeps its base and stack, only its head moves
        deps = [db.task(d) for d in stacked]
        db.update(task.id, status="queued", attempts=0, note=None, progress=None)
    else:
        db.update(task.id, status="queued", branch=f"factory/{task.id}", base_ref=pr_base, base_sha=base_sha,
                  trunk=trunk, stacked_on=",".join(stacked) or None,
                  candidate_sha=None, pr_url=None, attempts=0, note=None, progress=None)
    db.claim(task.id, os.getpid())
    sbx = S.make(wt, home / "cache", sandbox=not a.no_sandbox, network=a.network, cfg=cfg.sandbox)
    opts = Options(base_ref=pr_base, max_attempts=a.max_attempts, open_pr=not a.no_pr,
                   skip_gates=tuple(x for x in a.skip_gates.split(",") if x), full_e2e=a.full_e2e,
                   max_cost=a.max_cost, config=cfg, stacked_on=tuple(f"{d['id']} ({d['pr_url']})" for d in deps),
                   resolution=resolution, ci_fix=ci_fix)
    log = RunLog(log_path(home, task.id), echo=not a.quiet)
    log("run", f"=== {task.id}: worktree {wt} on factory/{task.id} from {pr_base} ({base_sha[:12]})"
               + (f", stacked on {', '.join(stacked)}" if stacked else "")
               + (f", resolving conflicts in {', '.join(resolution.conflicts) or 'nothing (replays cleanly)'}"
                  if resolution else "")
               + (f", fixing CI ({', '.join(ci_fix.checks)}) on {ci_fix.old_candidate[:12]}" if ci_fix else "")
               + f"; models {', '.join(f'{r}={m}' for r, m in models.items())}")
    print(f"log: {log.path}  (follow elsewhere: factory logs {task.id} -f)", flush=True)
    try:
        result = Pipeline(db, LangChainRoles(root, a.model, cfg=cfg), task, wt, base_sha, sbx, opts, log=log,
                          transcript_dir=home / "transcripts" / task.id).run()
    finally:
        log.close()
    row = db.task(task.id)
    if resolution and row["status"] == "failed":
        db.update(task.id, note=f"{row['note']}\n\nThe PR still holds {resolution.old_candidate[:12]}, which conflicts "
                                f"with {resolution.onto}. Running the task again rebuilds it from scratch.")
        row = db.task(task.id)
    if ci_fix and row["status"] == "failed":
        db.update(task.id, note=f"{row['note']}\n\nThe PR still holds {ci_fix.old_candidate[:12]}, whose CI fails "
                                f"({', '.join(ci_fix.checks)}). Running the task again rebuilds it from scratch.")
        row = db.task(task.id)
    summary = (f"{task.id}: {row['status']} after {row['attempts']} build(s)"
               + (f" — {row['pr_url']}" if row["pr_url"] else "")
               + (f" — ${row['cost_usd']:.2f}" if row["cost_usd"] is not None else ""))
    print(summary + (f"\n{row['note']}" if row["note"] else ""))
    if a.notify:
        _notify(f"factory: {task.id} {row['status']}", row["pr_url"] or observe.failing_summary(row["note"]))
    return 0 if result.get("outcome") in ("pr_open", "verified") else 1


def _tip_or_local(root: Path, trunk: str) -> str:
    """Start from the trunk as origin has it; the local branch only when origin cannot be reached."""
    from .pipeline import PipelineError, trunk_tip
    try:
        return trunk_tip(root, trunk)
    except PipelineError as e:
        print(f"warning: building on the local {trunk}, which may be behind origin: {e}", file=sys.stderr)
        return trunk


def _replay(db, root: Path, home: Path, row):
    """A conflicting PR's change replayed onto where it now belongs: its one open dependency's candidate, or
    the trunk as origin has it. Returns (worktree, base sha, PR base, trunk, still-open dependencies, Resolution)."""
    from .pipeline import PipelineError, branch_name, replay_worktree, trunk_tip
    from .stack import retarget
    deps = [d for d in (row["stacked_on"] or "").split(",") if d and db.task(d)["status"] != "merged"]
    trunk = row["trunk"] or row["base_ref"]
    if len(deps) > 1:
        raise PipelineError(f"{row['id']} is stacked on several open PRs ({', '.join(deps)}); merge them, "
                            f"`factory status --refresh`, then run it again")
    if deps:
        onto, label = db.task(deps[0])["candidate_sha"], branch_name(deps[0])
    else:
        onto, label = trunk_tip(root, trunk), trunk
    wt, resolution = replay_worktree(root, home, row["id"], row["base_sha"], row["candidate_sha"], onto, label)
    if row["base_ref"] != label:        # its dependency merged while it waited: the PR moves to the trunk
        retarget(root, row["pr_url"], label)
    return wt, onto, label, trunk, deps, resolution


def _ci_fix(root: Path, home: Path, row):
    """The open PR's branch at the candidate its CI failed on, and what failed: (worktree, CiFix). None when CI
    no longer fails there (a job was re-run, or is running again)."""
    from . import ci
    from .pipeline import CiFix, PipelineError, branch_name, create_worktree, git
    pr = _pr_state(row["pr_url"])
    if not pr:
        raise PipelineError(f"can't read the checks of {row['pr_url']} from GitHub")
    red = ci.red(pr, row["candidate_sha"])
    if red is None:
        raise PipelineError(f"{row['pr_url']} has head {(pr.get('headRefOid') or '?')[:12]}, not the factory's candidate "
                            f"{row['candidate_sha'][:12]}: someone pushed to it. Fix CI there, or --force to rebuild")
    if not red:
        return None
    git(root, "fetch", "-q", "origin", branch_name(row["id"]), check=False)   # a PR taken up from another board
    wt, _ = create_worktree(root, home, row["id"], row["candidate_sha"])
    return wt, CiFix(old_candidate=row["candidate_sha"], checks=tuple(c.name for c in red),
                     brief=ci.brief(root, row["pr_url"], row["candidate_sha"], red))


def _notify(title: str, body: str) -> None:
    import shutil
    if shutil.which("notify-send"):
        subprocess.run(["notify-send", title, body or ""], capture_output=True)


def _pr_state(url: str) -> dict:
    """GitHub's view of a PR: {"state": OPEN|MERGED|CLOSED, "mergeable": MERGEABLE|CONFLICTING|UNKNOWN,
    "headRefOid": its head sha, "statusCheckRollup": [the checks on that head]}, or {} when gh fails. GitHub
    computes `mergeable` lazily: UNKNOWN now is usually known by the next refresh."""
    # The head comes from `commits`: older gh (2.4, Ubuntu's) has no `headRefOid` field and rejects the call.
    p = subprocess.run(["gh", "pr", "view", url, "--json", "state,mergeable,commits,statusCheckRollup"],
                       capture_output=True, text=True)
    try:
        pr = json.loads(p.stdout) if p.returncode == 0 else {}
    except json.JSONDecodeError:
        return {}
    if commits := pr.pop("commits", None):
        pr["headRefOid"] = commits[-1].get("oid")
    return pr


def _factory_prs(root: Path) -> dict[str, dict]:
    """Every factory PR on GitHub by task id: {"url", "state", "baseRefName"}, an open one ahead of a merged one.
    Closed PRs are left out (a board reset leaves old ones behind). {} when gh fails."""
    p = subprocess.run(["gh", "pr", "list", "--state", "all", "--limit", "1000", "--json", "headRefName,url,state,baseRefName"],
                       cwd=root, capture_output=True, text=True)
    try:
        prs = json.loads(p.stdout) if p.returncode == 0 else []
    except json.JSONDecodeError:
        return {}
    found: dict[str, dict] = {}
    for pr in prs:
        task_id = pr["headRefName"].removeprefix("factory/")
        if task_id != pr["headRefName"] and pr["state"] in ("OPEN", "MERGED") and \
                found.get(task_id, {}).get("state") != "OPEN":
            found[task_id] = pr
    return found


def _adopt(db, root: Path, remote: str = "origin") -> None:
    """Take up factory PRs this board didn't open: another maintainer's runs, or this board's before a reset.
    A queued or failed task with an open or merged PR on factory/<task> becomes pr_open or merged, so everyone
    working from the same GitHub repo sees the same board. Holds (abandoned) and running tasks are left alone."""
    from .pipeline import PipelineError, branch_name, git
    waiting = [r for r in db.tasks() if r["status"] in ("queued", "failed") and not r["pr_url"]]
    prs = _factory_prs(root) if waiting else {}
    for row in waiting:
        pr = prs.get(row["id"])
        if pr is None:
            continue
        branch = branch_name(row["id"])
        if pr["state"] == "MERGED":
            db.update(row["id"], status="merged", branch=branch, pr_url=pr["url"], note=None, progress=None)
            print(f"{row['id']}: merged in {pr['url']} (taken up from GitHub)", file=sys.stderr)
            continue
        base = pr["baseRefName"]
        try:            # the task's own changes are those after where its branch left its base
            git(root, "fetch", "-q", remote, branch, base)
            candidate = git(root, "rev-parse", f"{remote}/{branch}")
            base_sha = git(root, "merge-base", candidate, f"{remote}/{base}")
        except PipelineError as e:
            print(f"{row['id']}: can't take up {pr['url']}: {e}", file=sys.stderr)
            continue
        dep = base.removeprefix("factory/") if base.startswith("factory/") else None
        trunk, hops = base, 0
        while trunk.startswith("factory/") and (up := prs.get(trunk.removeprefix("factory/"))) and hops < 20:
            trunk, hops = up["baseRefName"], hops + 1       # a stack ends on the trunk
        db.update(row["id"], status="pr_open", branch=branch, pr_url=pr["url"], base_ref=base, base_sha=base_sha,
                  candidate_sha=candidate, trunk=None if trunk.startswith("factory/") else trunk, stacked_on=dep,
                  note="PR opened outside this board; taken up from GitHub", progress=None)
        print(f"{row['id']}: PR open at {pr['url']}" + (f", stacked on {dep}" if dep else "")
              + " (taken up from GitHub)", file=sys.stderr)


def _refresh(db) -> None:
    from . import ci
    _adopt(db, repo_root())
    for row in db.tasks():
        if row["status"] in ACTIVE and row["pid"] and not pid_alive(row["pid"]):
            db.update(row["id"], status="failed", progress=None,
                      note=f"process {row['pid']} exited mid-run (killed or crashed); `factory clean` then rerun")
        if row["status"] in ("pr_open", "conflict", "ci_failed") and row["pr_url"]:
            pr = _pr_state(row["pr_url"])
            is_open = row["status"] in ("pr_open", "ci_failed")
            if pr.get("state") == "MERGED":
                db.update(row["id"], status="merged")
            elif pr.get("state") == "CLOSED":
                db.update(row["id"], status="abandoned", note="PR closed without merge")
            # A stacked PR is checked against its dependency by restack below, not by GitHub.
            elif pr.get("mergeable") == "CONFLICTING" and is_open and not row["stacked_on"]:
                db.update(row["id"], status="conflict",
                          note=f"its PR conflicts with {row['base_ref']}: `factory run {row['id']}` resolves it")
                print(f"{row['id']}: conflicts with {row['base_ref']} (`factory run {row['id']}` resolves them)",
                      file=sys.stderr)
            elif is_open and pr.get("headRefOid"):
                red = ci.red(pr, row["candidate_sha"])
                if red and row["status"] == "pr_open":
                    db.update(row["id"], status="ci_failed",
                              note=f"CI fails on its head: {ci.names(red)}: `factory run {row['id']}` fixes it")
                    print(f"{row['id']}: CI fails ({ci.names(red)}) (`factory run {row['id']}` fixes it)",
                          file=sys.stderr)
                elif red == [] and row["status"] == "ci_failed":     # re-run and passing, or running again
                    db.update(row["id"], status="pr_open", note=None)
                    print(f"{row['id']}: CI no longer fails", file=sys.stderr)
                elif red is None and row["status"] == "ci_failed":   # someone else pushed to it: not ours to fix
                    db.update(row["id"], status="pr_open",
                              note=f"its head {pr['headRefOid'][:12]} isn't the factory's candidate; its CI is left "
                                   f"to whoever pushed it")
                    print(f"{row['id']}: someone pushed to its PR; its CI is theirs now", file=sys.stderr)
    from .stack import restack
    for row in db.tasks():          # by id, so a plan's stack moves bottom-up
        if row["status"] in ("pr_open", "ci_failed") and row["stacked_on"]:
            msg = restack(db, repo_root(), factory_home(), row["id"])
            if msg:
                print(msg, file=sys.stderr)


def _detail(db, r) -> str:
    return observe.detail(db, r)


def cmd_status(a) -> int:
    db = _db()
    if a.refresh:
        _refresh(db)
    rows = observe.in_plan(db.tasks(), a.plan)
    if a.json:
        print(json.dumps([dict(r) | {"detail": _detail(db, r)} for r in rows], indent=2))
        return 0
    if not rows:
        print(f"no tasks in {a.plan}" if a.plan else "no tasks yet — `factory sync` loads every contract from the plans")
    for name, rs in observe.plan_groups(db, rows):
        print(f"{name}  {observe.strip(db, rs)}  {observe.counts(db, rs)}")
        for r in rs:
            cost = f"${r['cost_usd']:.2f}" if r["cost_usd"] is not None else ""
            status = "DEAD" if observe.liveness(r) else r["status"]
            print(f"  {r['id']:<32} {status:<10} builds={r['attempts']:<2} {cost:>6} {_detail(db, r)}")
    return 0


def cmd_top(a) -> int:
    import time
    home = factory_home()
    db = _db()
    try:
        while True:
            screen = observe.render_top(db, home, events=a.events, plan=a.plan)
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
    ready = [r["id"] for r in db.tasks() if r["status"] == "queued" and db.ready(r["id"])]
    print("ready to run: " + (", ".join(ready) if ready else "none"))
    print("run a whole plan: factory run <plan>   (e.g. factory run "
          + contracts.plan_name(next(iter(tasks.values())).plan) + ")" if tasks else "")
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
    row = _db().task(task.id)
    stacked = a.base is None and row is not None and row["stacked_on"] and row["base_sha"]
    a.base = row["base_sha"] if stacked else (a.base or "main")   # a stacked PR is reviewed against its dependency
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


def cmd_abandon(a) -> int:
    _db().update(a.task_id, status="abandoned", note=a.note)
    return 0


def cmd_requeue(a) -> int:
    """Put failed or abandoned tasks back to `queued`, so the next plan run picks them up. Running tasks,
    open PRs and merged tasks are left alone; the next run replaces any leftover worktree itself."""
    db = _db()
    rc = 0
    for tid in a.task_ids:
        row = db.task(tid)
        if row is None:
            print(f"{tid}: not on the board (run `factory sync` first)")
            rc = 1
        elif row["status"] in ACTIVE and pid_alive(row["pid"]):
            print(f"{tid}: running ({row['status']}, pid {row['pid']}); leaving it")
            rc = 1
        elif row["status"] in ("pr_open", "conflict", "ci_failed", "merged"):
            print(f"{tid}: {row['status']}; nothing to requeue")
            rc = 1
        elif row["status"] == "queued":
            print(f"{tid}: already queued")
        else:
            db.update(tid, status="queued", note=None, progress=None)
            print(f"{tid}: {row['status']} -> queued")
    return rc


def cmd_init(a) -> int:
    """Set this repository up for the factory: .factory/config.yaml, the workflow skills, a starter plan,
    the session-log directory and a section in the agent guidance. Existing files are kept unless --force."""
    from . import scaffold

    root = repo_root()
    try:
        done = scaffold.init(root, force=a.force, skills=not a.no_skills,
                             session_log=None if a.no_session_log else a.session_log)
    except C.ConfigError as e:
        print(f"{C.CONFIG_PATH}: {e}", file=sys.stderr)
        return 1
    for action, rel, note in done:
        print(f"{action:<6} {rel}" + (f" ({note})" if note else ""))
    print("\nnext:\n"
          "  1. review .factory/config.yaml (`factory config` prints the effective settings)\n"
          "  2. plan work with /plan-workstream (Codex: $plan-workstream), or replace the example plan\n"
          "  3. factory validate-plan && factory sync\n"
          "  4. export OPENROUTER_API_KEY=… and `factory run <plan>`")
    return 0


def cmd_prompt(a) -> int:
    """A role's prompt as the agents get it: the repository's override, else the one shipped with the factory."""
    from .agents import ROLE_FILES, prompt_source, role_model

    root = repo_root()
    role = next((r for r, f in ROLE_FILES.items() if a.role in (r, f)), None)
    if role is None:
        print(f"unknown role {a.role}; one of {', '.join(ROLE_FILES)}", file=sys.stderr)
        return 2
    src = prompt_source(root, role)
    print(f"# {src} · model {role_model(root, role, C.load(root))}\n")
    print(src.read_text().rstrip())
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
    print(f"# {source}; state in {factory_home()}; GitHub: {github.describe(os.environ)}")
    print(yaml.safe_dump(plain(cfg), sort_keys=False).rstrip())
    return 0


def cmd_check_output(a) -> int:
    out = Path(a.log).read_text(errors="replace")
    outcome = classify(a.cmd, a.exit, out)
    print(f"{outcome}: {a.cmd} (tests run: {tests_run(out)})")
    return 0 if outcome == PASS else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="factory", description="plan -> build -> review -> verify -> PR, per task; "
                                                         "`factory run <plan>` runs a whole plan")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="set this repository up: config, skills, starter plan, session log, guidance")
    s.add_argument("--force", action="store_true", help="overwrite existing files")
    s.add_argument("--no-skills", action="store_true", help="skip workflow skills in .claude/skills and Codex links in .agents/skills")
    s.add_argument("--session-log", default="docs/sessions", metavar="DIR",
                   help="require a session log entry per task in DIR (default docs/sessions)")
    s.add_argument("--no-session-log", action="store_true", help="don't require session logs")
    s.set_defaults(fn=cmd_init)

    s = sub.add_parser("prompt", help="print a role's prompt (the repository's override, else the shipped one)")
    s.add_argument("role", help="plan | build | review | verify (or planner, builder, …)")
    s.set_defaults(fn=cmd_prompt)

    s = sub.add_parser("config", help="print the effective project settings")
    s.set_defaults(fn=cmd_config)

    s = sub.add_parser("validate-plan", help="validate task contracts (never edits the plan)")
    s.add_argument("plans", nargs="*")
    s.set_defaults(fn=cmd_validate_plan)

    s = sub.add_parser("run", help="run every task of a plan (one PR each) or a single task")
    s.add_argument("target", help="a plan (path, or file name without .md) or a task id")
    s.add_argument("--parallel", type=int, default=3, help="plan run: max tasks running at once")
    s.add_argument("--network-for", help="plan run: comma list of task ids that get --network")
    s.add_argument("--max-cost", type=float, help="abort a task once it has cost this many USD")
    s.add_argument("--base", help="base branch for the worktree and PR (default: current branch)")
    s.add_argument("--model", help="override every role's model, e.g. openrouter:z-ai/glm-5.3")
    s.add_argument("--max-attempts", type=int, default=3, help="max build attempts (review/gate loops)")
    s.add_argument("--network", action="store_true", help="allow network inside the sandbox")
    s.add_argument("--no-sandbox", action="store_true", help="run commands without bubblewrap (unsafe)")
    s.add_argument("--no-pr", action="store_true", help="stop after gates pass; do not push or open a PR")
    s.add_argument("--skip-gates", default="", help="comma list, e.g. e2e_tests (recorded in the PR body)")
    s.add_argument("--full-e2e", action="store_true", help="run the whole e2e suite (e2e.run_all)")
    s.add_argument("--force", action="store_true", help="run despite its status or dependencies without PRs")
    s.add_argument("--quiet", action="store_true", help="log to file only (no terminal echo)")
    s.add_argument("--notify", action="store_true", help="desktop notification (notify-send) when the run ends")
    s.set_defaults(fn=cmd_run)

    s = sub.add_parser("top", help="live dashboard: plans with their task counters, running tasks, recent events")
    s.add_argument("plan", nargs="?", help="only this plan (name or path)")
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

    s = sub.add_parser("status", help="task board, grouped by plan")
    s.add_argument("plan", nargs="?", help="only this plan (name or path)")
    s.add_argument("--refresh", action="store_true",
                   help="pick up merged/closed PRs and PRs opened elsewhere from GitHub, move stacked PRs "
                        "whose dependencies merged, and mark PRs that conflict or fail CI")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_status)

    s = sub.add_parser("show", help="a task's runs and reports")
    s.add_argument("task_id")
    s.add_argument("--role", choices=("plan", "build", "resolve", "ci", "review", "verify", "pr"))
    s.set_defaults(fn=cmd_show)

    s = sub.add_parser("gates", help="run the deterministic gates for a ref (no agents)")
    s.add_argument("task_id")
    s.add_argument("--ref", default="HEAD")
    s.add_argument("--base", help="default: the PR a stacked task is built on, else main")
    s.add_argument("--skip", default="")
    s.add_argument("--full-e2e", action="store_true")
    s.add_argument("--no-sandbox", action="store_true")
    s.set_defaults(fn=cmd_gates)

    s = sub.add_parser("clean", help="remove a task's worktree")
    s.add_argument("task_id")
    s.set_defaults(fn=cmd_clean)

    s = sub.add_parser("abandon", help="mark a task abandoned")
    s.add_argument("task_id")
    s.add_argument("--note", default="")
    s.set_defaults(fn=cmd_abandon)

    s = sub.add_parser("requeue", help="put failed or abandoned tasks back to queued for the next plan run")
    s.add_argument("task_ids", nargs="+", metavar="TASK")
    s.set_defaults(fn=cmd_requeue)

    s = sub.add_parser("check-output", help="classify a test log; zero tests is not a pass")
    s.add_argument("--cmd", required=True)
    s.add_argument("--exit", type=int, required=True)
    s.add_argument("log")
    s.set_defaults(fn=cmd_check_output)

    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
