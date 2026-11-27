"""Whether an open factory PR can land on the configured trunk."""

from __future__ import annotations

from . import ci


def readiness(row, task, pr: dict, cfg) -> tuple[str, str | None]:
    """Judge one board task from its contract and GitHub's view of its PR.

    The verdict is ``ready``, ``waits`` (the factory can make progress later), or ``human`` (a person must
    decide). Reasons are deliberately ordered so a dry run reports the first thing blocking the landing.
    """
    if row["status"] != "pr_open":
        return "waits", f"{row['status']}: {row['note'] or ''}"
    if pr.get("state") != "OPEN":
        return "waits", "PR is not open"

    trunk = cfg.trunk
    base = pr.get("baseRefName")
    if base != trunk and base and base.startswith("factory/"):
        return "waits", f"stacked on {base.removeprefix('factory/')}"
    if base != trunk:
        return "human", f"targets {base}, not the trunk {trunk}"

    candidate = row["candidate_sha"]
    if not candidate or pr.get("headRefOid") != candidate:
        return "human", "someone else pushed to it"

    mergeable = pr.get("mergeable")
    if mergeable == "UNKNOWN":
        return "waits", "GitHub hasn't computed mergeability yet"
    if mergeable == "CONFLICTING":
        return "waits", f"conflicts with {trunk}"
    if mergeable != "MERGEABLE":
        return "waits", "GitHub hasn't computed mergeability yet"

    rollup = pr.get("statusCheckRollup") or []
    if running := ci.pending(rollup):
        return "waits", f"CI running ({len(running)} of {len(rollup)} checks pending)"
    if failed := ci.failing(rollup):
        return "waits", f"CI failed ({ci.names(failed)})"
    if not rollup and (cfg.land is None or cfg.land.require_checks):
        return "waits", "no CI checks on its head yet"

    if task.risk == "high":
        return "human", "risk: high"
    guidance = set(cfg.guidance)
    for changed in pr.get("files") or []:
        path = changed.get("path") or ""
        if path.startswith((".factory/", ".github/")) or path in guidance:
            return "human", f"changes {path}"
    return "ready", None
