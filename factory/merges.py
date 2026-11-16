"""What a human changed on a factory PR between its candidate and its merge."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from .db import DB
from .pipeline import DIFF_LIMIT, PipelineError, branch_name, git
from .stack import PR_NUMBER


def _fetch(root: Path, row) -> None:
    """Fetch the PR head's objects, using GitHub's pull ref after its branch is deleted."""
    branch = branch_name(row["id"])
    try:
        git(root, "fetch", "-q", "origin", branch)
        return
    except PipelineError:
        pass
    match = PR_NUMBER.search(row["pr_url"] or "")
    pull_ref = f"refs/pull/{match.group(1)}/head" if match else "refs/pull/<number>/head"
    if match:
        try:
            git(root, "fetch", "-q", "origin", pull_ref)
            return
        except PipelineError as e:
            raise PipelineError(f"couldn't fetch {branch} or {pull_ref}: {e}") from e
    raise PipelineError(f"couldn't fetch {branch} or {pull_ref}: the PR URL has no number")


def _is_ancestor(root: Path, candidate: str, head: str) -> bool:
    p = subprocess.run(["git", "merge-base", "--is-ancestor", candidate, head], cwd=root,
                       capture_output=True, text=True)
    if p.returncode not in (0, 1):
        raise PipelineError(f"git merge-base --is-ancestor {candidate} {head}: {p.stderr.strip()}")
    return p.returncode == 0


def _cap(report: str) -> str:
    return report[:DIFF_LIMIT] + ("\n… (truncated)" if len(report) > DIFF_LIMIT else "")


def _unreadable(task_id: str, why: str) -> None:
    print(f"{task_id}: merged; can't tell whether it was changed before merging ({why})", file=sys.stderr)


def record(db: DB, root: Path, row, head: str | None) -> None:
    """Record one merge run for a task just marked merged, or say why its final head can't be read."""
    tid, candidate = row["id"], row["candidate_sha"]
    if not head:
        _unreadable(tid, "gh gave no head for its PR")
        return
    if head == candidate:
        outcome = "as_built"
        report = f"Merged as built: its head is the factory's candidate `{candidate[:12]}`."
    else:
        try:
            _fetch(root, row)
            if not _is_ancestor(root, candidate, head):
                outcome = "edited"
                report = ("The PR head was rewritten before merging; the factory's candidate is not its ancestor.\n\n"
                          + git(root, "diff", "--stat", candidate, head))
            else:
                report = git(root, "log", "--first-parent", "--no-merges", "--stat", "-p",
                             f"{candidate}..{head}")
                if report:
                    outcome = "edited"
                else:
                    outcome = "as_built"
                    report = ("Merged as built: only merges of the base landed after the factory's candidate "
                              "(for example, GitHub's Update branch).")
        except PipelineError as e:
            _unreadable(tid, str(e))
            return
    run_id = db.start_run(tid, "merge", 0)
    db.finish_run(run_id, outcome, _cap(report), sha=head)
