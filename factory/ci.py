"""CI on open factory PRs.

The gates run before a PR opens; CI runs after, on every head the PR gets, including the rebased heads a
restack pushes, which the gates never saw. `factory status --refresh` reads each open PR's checks at its
head. When one fails on the factory's own candidate, the task becomes `ci_failed`, and its next run has
the builder fix the failures on the PR's branch, with the failing jobs' logs as feedback; review and gates
run again before the same PR is updated (pipeline.Rework).
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

# Cancelled, skipped, neutral and action-required checks say nothing about the change.
FAILED = {"FAILURE", "TIMED_OUT", "STARTUP_FAILURE", "ERROR"}
JOB_URL = re.compile(r"/actions/runs/\d+/job/(\d+)")
NOISE = re.compile(r"\x1b\[[0-9;]*m|^\d{4}-\d\d-\d\dT[\d:.]+Z ", re.M)    # ANSI colours, per-line timestamps
LOG_LIMIT = 8000        # per failing job: its tail, where the error is
BRIEF_LIMIT = 30000


@dataclass(frozen=True)
class Check:
    name: str
    conclusion: str
    url: str = ""

    @property
    def job_id(self) -> str | None:
        """The GitHub Actions job behind the check, whose log `gh` can fetch."""
        m = JOB_URL.search(self.url)
        return m.group(1) if m else None


def failing(rollup) -> list[Check]:
    """The failed checks in a PR's `statusCheckRollup`: check runs and commit statuses."""
    out = []
    for c in rollup or []:
        if c.get("__typename") == "StatusContext" or "context" in c:
            name, result, url = c.get("context") or "?", c.get("state") or "", c.get("targetUrl") or ""
        else:
            name = " / ".join(x for x in (c.get("workflowName"), c.get("name")) if x) or "?"
            result, url = c.get("conclusion") or "", c.get("detailsUrl") or ""
        if result.upper() in FAILED:
            out.append(Check(name, result.upper(), url))
    return out


def red(pr: dict, candidate: str | None) -> list[Check] | None:
    """The failed checks on a PR's head, when that head is the factory's candidate. None when CI can't be
    judged here: gh failed, or someone else pushed to the branch, so the checks aren't about our commit."""
    if not pr or not candidate or pr.get("headRefOid") != candidate:
        return None
    return failing(pr.get("statusCheckRollup"))


def names(checks) -> str:
    return ", ".join(c.name if isinstance(c, Check) else c for c in checks)


def job_log(root: Path, check: Check) -> str:
    """The tail of a GitHub Actions job's log, up to its last error; '' for other checks or when gh can't fetch
    it. The REST endpoint, because `gh run view --log-failed` prints nothing on some gh versions."""
    if not check.job_id:
        return ""
    p = subprocess.run(["gh", "api", f"repos/{{owner}}/{{repo}}/actions/jobs/{check.job_id}/logs"], cwd=root,
                       capture_output=True, text=True)
    if p.returncode != 0:
        return ""
    lines = NOISE.sub("", p.stdout.lstrip("\ufeff")).splitlines()
    last = max((i for i, line in enumerate(lines) if line.startswith("##[error]")), default=len(lines) - 1)
    text = "\n".join(lines[:last + 1]).strip()             # after the last error comes the job's cleanup
    return text if len(text) <= LOG_LIMIT else "… (earlier lines cut)\n" + text[-LOG_LIMIT:]


def brief(root: Path, pr_url: str, sha: str, checks: list[Check]) -> str:
    """The builder's feedback for a CI fix: what failed on the PR's head, with the jobs' logs."""
    parts = [
        f"# Fix failing CI\n\nThis task's PR ({pr_url}) passed the factory's gates, but CI fails on its head "
        f"commit {sha[:12]}. The worktree is the PR's branch at that commit: the task's change is already "
        f"committed. Fix what CI reports below without dropping any of the task's change. CI can run checks the "
        f"gates don't (formatting, lints, other targets). The sandbox has no network, so reproduce each failure "
        f"with `run` (the command the job ran) and check that it passes before you finish.",
        "## Failing checks\n\n" + "\n".join(f"- {c.name}: {c.conclusion}" + (f" ({c.url})" if c.url else "")
                                            for c in checks),
    ]
    for c in checks:
        log = job_log(root, c)
        parts.append(f"## Log: {c.name}\n\n" + (f"```text\n{log}\n```" if log else
                                                  "(no log available: not a GitHub Actions job, or gh couldn't fetch it)"))
    text = "\n\n".join(parts)
    return text if len(text) <= BRIEF_LIMIT else text[:BRIEF_LIMIT] + "\n… (truncated)"
