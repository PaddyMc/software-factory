"""Stacked PRs.

A task whose dependency has an open (unmerged) PR is built on top of that PR: its worktree starts
from the dependency's candidate, and its PR targets `factory/<dependency>`, so the PR shows only the
task's own changes. `restack` keeps such a PR correct as you merge its dependencies:

- every dependency merged: rebase the task's own commits onto the trunk and point the PR at it;
- its one dependency was itself restacked: rebase onto the dependency's new candidate;
- one of several dependencies merged: point the PR at a dependency that is still open, so merging
  it can never land in an already-merged branch.

Gates ran on the original candidate; the PR gets a comment saying so whenever its commits move, and CI
runs on the new head (ci.py). When the commits do not rebase cleanly the task becomes `conflict`, and its
next run has the builder resolve the conflicts (pipeline.replay_worktree), with review and gates run again
before the PR is updated. A PR whose CI failed (`ci_failed`) is restacked the same way: its new head goes
back to `pr_open` for CI to judge, since the failure may have come from the dependency.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from .db import DB
from .pipeline import branch_name, git

PR_NUMBER = re.compile(r"/(\d+)/?$")


def _gh_api(root: Path, *args: str) -> bool:
    return subprocess.run(["gh", "api", *args], cwd=root, capture_output=True, text=True).returncode == 0


def edit_pr(root: Path, pr_url: str, **fields: str) -> bool:
    """Change a PR's base or body (`gh pr edit` breaks on some GitHub setups; the REST API does not)."""
    m = PR_NUMBER.search(pr_url or "")
    pairs = [arg for k, v in fields.items() for arg in ("-f", f"{k}={v}")]
    return bool(m) and _gh_api(root, "-X", "PATCH", f"repos/{{owner}}/{{repo}}/pulls/{m.group(1)}", *pairs)


def retarget(root: Path, pr_url: str, base: str) -> bool:
    """Point a PR at another base branch."""
    return edit_pr(root, pr_url, base=base)


def comment(root: Path, pr_url: str, body: str) -> bool:
    m = PR_NUMBER.search(pr_url or "")
    return bool(m) and _gh_api(root, f"repos/{{owner}}/{{repo}}/issues/{m.group(1)}/comments", "-f", f"body={body}")


def rebase(root: Path, home: Path, task_id: str, candidate: str, old_base: str, onto: str,
           remote: str = "origin") -> str | None:
    """Replay the task's own commits (old_base..candidate) onto `onto` and force-push them to its branch.
    Returns the new candidate sha, or None when the commits do not apply cleanly (nothing is pushed)."""
    wt = home / "restack" / task_id
    if wt.exists():
        git(root, "worktree", "remove", "--force", str(wt), check=False)
    wt.parent.mkdir(parents=True, exist_ok=True)
    git(root, "worktree", "add", "-q", "--detach", str(wt), candidate)
    try:
        p = subprocess.run(["git", "rebase", "-q", "--onto", onto, old_base], cwd=wt, capture_output=True, text=True)
        if p.returncode != 0:
            git(wt, "rebase", "--abort", check=False)
            return None
        new = git(wt, "rev-parse", "HEAD")
        branch = branch_name(task_id)
        git(wt, "push", "-q", f"--force-with-lease=refs/heads/{branch}:{candidate}", remote, f"HEAD:refs/heads/{branch}")
        return new
    finally:
        git(root, "worktree", "remove", "--force", str(wt), check=False)


def restack(db: DB, root: Path, home: Path, task_id: str, remote: str = "origin") -> str | None:
    """Bring one open stacked PR up to date with its dependencies. Returns what changed, or None."""
    row = db.task(task_id)
    deps = [d for d in (row["stacked_on"] or "").split(",") if d] if row else []
    if not deps or row["status"] not in ("pr_open", "ci_failed"):
        return None
    status = {d: (db.task(d)["status"] if db.task(d) else None) for d in deps}
    still_open = [d for d in deps if status[d] != "merged"]
    old = row["candidate_sha"]
    rerun = {"status": "pr_open", "note": None} if row["status"] == "ci_failed" else {}   # a new head: CI runs again

    if not still_open:
        trunk = row["trunk"] or "main"
        git(root, "fetch", "-q", remote, trunk)
        onto = git(root, "rev-parse", f"{remote}/{trunk}")
        new = rebase(root, home, task_id, old, row["base_sha"], onto, remote)
        retarget(root, row["pr_url"], trunk)
        if new is None:
            db.update(task_id, status="conflict", base_ref=trunk, stacked_on=None,
                      note=f"its dependencies merged but its commits conflict with {trunk}: the PR now targets "
                           f"{trunk} and also shows their changes until `factory run {task_id}` resolves it")
            comment(root, row["pr_url"], f"{', '.join(deps)} merged. This PR now targets `{trunk}`, but its "
                                         f"commits conflict with it, so the diff also shows their changes until "
                                         f"the factory resolves the conflicts.")
            return f"{task_id}: retargeted to {trunk}; conflicts (`factory run {task_id}` resolves them)"
        db.update(task_id, base_ref=trunk, base_sha=onto, candidate_sha=new, stacked_on=None, **rerun)
        comment(root, row["pr_url"], f"{', '.join(deps)} merged: rebased onto `{trunk}` ({onto[:12]}) and "
                                     f"retargeted. Candidate {old[:12]} → {new[:12]}; the gates ran on {old[:12]}.")
        return f"{task_id}: rebased onto {trunk}, PR retargeted"

    if len(deps) == 1:
        dep = db.task(deps[0])
        if dep["candidate_sha"] == row["base_sha"]:
            return None
        new = rebase(root, home, task_id, old, row["base_sha"], dep["candidate_sha"], remote)
        if new is None:
            db.update(task_id, status="conflict",
                      note=f"{deps[0]} moved and this PR's commits conflict with it: `factory run {task_id}` resolves it")
            return f"{task_id}: conflicts with {deps[0]} (`factory run {task_id}` resolves them)"
        db.update(task_id, base_sha=dep["candidate_sha"], candidate_sha=new, **rerun)
        comment(root, row["pr_url"], f"{deps[0]} moved: rebased onto it. Candidate {old[:12]} → {new[:12]}; "
                                     f"the gates ran on {old[:12]}.")
        return f"{task_id}: rebased onto {deps[0]}"

    if row["base_ref"] != branch_name(still_open[0]) and status.get(row["base_ref"].removeprefix("factory/")) == "merged":
        if retarget(root, row["pr_url"], branch_name(still_open[0])):
            db.update(task_id, base_ref=branch_name(still_open[0]))
            return f"{task_id}: PR now targets {branch_name(still_open[0])}"
    return None
