"""One task through plan -> build -> review -> verify -> PR (LangGraph).

Review "changes" and gate failures loop back to build with feedback, up to
`max_attempts` builds. A PR is opened only when every gate passes, so the end
state is either a working PR or a failed task with reasons — never a broken PR.

A PR that conflicts with its base runs resolve -> review -> verify -> PR instead:
its change is replayed onto the new base, the builder resolves the conflicted
files, and review and gates run again on the result before the PR is updated.

A PR whose CI fails runs ci -> build -> review -> verify -> PR: the builder works
on the PR's branch with the failing jobs' logs as feedback (see ci.py).
"""

from __future__ import annotations

import datetime as dt
import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypedDict

from langgraph.graph import END, StateGraph

from . import gates as G
from .agents import Ctx, Roles
from .config import Config
from .contracts import Task
from .db import DB
from .log import NullLog, clip


class PipelineError(RuntimeError):
    pass


@dataclass
class Resolution:
    """An open PR's change replayed onto a base it conflicts with (see `replay_worktree`)."""
    onto: str                              # what it is replayed onto: the trunk, or factory/<dependency>
    old_candidate: str                     # the PR's head before: the push lease, and what the comment names
    conflicts: tuple[str, ...] = ()        # files left with conflict markers; empty = it replayed cleanly
    brief: str = ""                        # the builder's task message: conflicted files and both sides' diffs


@dataclass
class CiFix:
    """An open PR whose CI fails on its head (ci.py): fixed on its branch, then reviewed and gated again."""
    old_candidate: str                     # the head CI failed on: the build starts there; the push lease
    checks: tuple[str, ...]                # the failing checks' names
    brief: str = ""                        # the builder's feedback: the failing checks and their logs


class Replayed:
    """The run record's output when a change replays cleanly: no agent ran."""
    text = "Replayed cleanly onto the new base; no conflicts to resolve."


@dataclass
class Options:
    base_ref: str
    max_attempts: int = 3
    open_pr: bool = True
    skip_gates: tuple[str, ...] = ()
    full_e2e: bool = False
    remote: str = "origin"
    max_cost: float | None = None          # abort the task once its recorded cost exceeds this (USD)
    config: Config = field(default_factory=Config)   # loaded from the main checkout, never the worktree
    stacked_on: tuple[str, ...] = ()       # open dependency PRs this task is built on ("task-t01 (url)")
    resolution: Resolution | None = None   # resolve this PR's conflicts instead of building from the plan
    ci_fix: CiFix | None = None            # fix this PR's failing CI instead of building from the plan


class State(TypedDict, total=False):
    attempt: int
    plan: str
    feedback: str
    sha: str
    verdict: str
    gates_ok: bool
    gates: str
    review: str
    verify: str
    outcome: str
    failure_sig: str        # identical gate failures on consecutive attempts => stop (no progress)
    stuck: bool


def git(cwd: Path, *args: str, check: bool = True) -> str:
    p = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if check and p.returncode != 0:
        raise PipelineError(f"git {' '.join(args)}: {p.stderr.strip()}")
    return p.stdout.strip()


def branch_name(task_id: str) -> str:
    return f"factory/{task_id}"


def create_worktree(root: Path, home: Path, task_id: str, base_ref: str,
                    merge: tuple[tuple[str, str], ...] = ()) -> tuple[Path, str]:
    """A fresh worktree on factory/<task> at `base_ref`. `merge` is more (label, sha) work to build on:
    the other open dependency PRs of a task stacked on several. Returns (worktree, base sha): the task's
    own changes are everything after the base sha."""
    wt = home / "worktrees" / task_id
    if wt.exists():
        raise PipelineError(f"worktree {wt} exists from a previous run; `factory clean {task_id}` first")
    wt.parent.mkdir(parents=True, exist_ok=True)
    base_sha = git(root, "rev-parse", "--verify", f"{base_ref}^{{commit}}")
    git(root, "worktree", "add", "-q", "-B", branch_name(task_id), str(wt), base_sha)
    if merge:
        labels = ", ".join(label for label, _ in merge)
        p = subprocess.run(["git", "merge", "-q", "--no-ff", "--no-edit", "-m", f"factory: stack {task_id} on {labels}",
                            *(sha for _, sha in merge)], cwd=wt, capture_output=True, text=True)
        if p.returncode != 0:
            git(wt, "merge", "--abort", check=False)
            git(root, "worktree", "remove", "--force", str(wt), check=False)
            raise PipelineError(f"cannot stack {task_id}: its open dependencies conflict ({labels}); "
                                f"merge one of their PRs first. {p.stdout.strip()} {p.stderr.strip()}".strip())
        base_sha = git(wt, "rev-parse", "HEAD")
    return wt, base_sha


def trunk_tip(root: Path, trunk: str, remote: str = "origin") -> str:
    """The trunk as `remote` has it now. A local branch can be behind what was merged on GitHub, and a task
    built on it starts without its merged dependencies."""
    git(root, "fetch", "-q", remote, trunk)
    return git(root, "rev-parse", f"{remote}/{trunk}")


DIFF_LIMIT = 20000


def _diff(root: Path, a: str, b: str, paths: tuple[str, ...]) -> str:
    out = git(root, "diff", f"{a}..{b}", "--", *paths)
    return out[:DIFF_LIMIT] + ("\n… (truncated: read the files)" if len(out) > DIFF_LIMIT else "") if out else "(none)"


def replay_worktree(root: Path, home: Path, task_id: str, old_base: str, candidate: str, onto: str,
                    label: str) -> tuple[Path, Resolution]:
    """A fresh worktree on factory/<task> at `onto` with the task's change (old_base..candidate, squashed)
    applied but not committed. Conflicted files keep diff3 markers for the builder to resolve."""
    wt = home / "worktrees" / task_id
    if wt.exists():
        raise PipelineError(f"worktree {wt} exists from a previous run; `factory clean {task_id}` first")
    wt.parent.mkdir(parents=True, exist_ok=True)
    squash = git(root, "commit-tree", f"{candidate}^{{tree}}", "-p", old_base, "-m", "task change")
    git(root, "worktree", "add", "-q", "-B", branch_name(task_id), str(wt), onto)
    p = subprocess.run(["git", "-c", "merge.conflictStyle=diff3", "cherry-pick", "--no-commit", squash],
                       cwd=wt, capture_output=True, text=True)
    conflicts = tuple(f for f in git(wt, "diff", "--name-only", "--diff-filter=U").splitlines() if f)
    if p.returncode != 0 and not conflicts:
        git(root, "worktree", "remove", "--force", str(wt), check=False)
        raise PipelineError(f"cannot replay {task_id} onto {label}: {p.stderr.strip()}")
    git(wt, "reset", "-q")                 # unstage: the build step commits whatever the worktree holds
    if not conflicts and not git(wt, "status", "--porcelain"):
        git(root, "worktree", "remove", "--force", str(wt), check=False)
        raise PipelineError(f"{task_id}'s change is already on {label}: nothing to replay")
    brief = "\n\n".join([
        f"# Resolve merge conflicts\n\nThis task's change was built, reviewed and gated on an older base. `{label}` "
        f"has moved since ({onto[:12]}), and the change no longer applies cleanly. The worktree is `{label}` with the "
        f"change replayed on top, uncommitted. Files that merged cleanly are already right. These files hold "
        f"diff3 conflict markers: `<<<<<<< HEAD` opens the new base's version, `|||||||` the old base's, "
        f"`=======` the task's, and `>>>>>>> … (task change)` ends the hunk.",
        "\n".join(f"- {f}" for f in conflicts),
        f"## What the task changed in them (old base → its PR)\n\n```diff\n{_diff(root, old_base, candidate, conflicts)}\n```",
        f"## What changed upstream in them (old base → {label})\n\n```diff\n{_diff(root, old_base, onto, conflicts)}\n```",
    ]) if conflicts else ""
    return wt, Resolution(onto=label, old_candidate=candidate, conflicts=conflicts, brief=brief)


class Pipeline:
    def __init__(self, db: DB, roles: Roles, task: Task, worktree: Path, base_sha: str, sandbox, opts: Options,
                 log=None, transcript_dir: Path | None = None):
        self.db, self.roles, self.task, self.wt, self.base_sha, self.sandbox, self.opts = (
            db, roles, task, worktree, base_sha, sandbox, opts)
        self.log = log or NullLog()
        self.transcript_dir = transcript_dir
        self.transcript: Path | None = None
        self.pr_url: str | None = None
        self.run_id: int | None = None
        # A build that leaves HEAD here changed nothing: the base, or the PR head whose CI it is fixing.
        self.start_sha = opts.ci_fix.old_candidate if opts.ci_fix else base_sha

    # ------------------------------------------------------------ helpers

    def ctx(self, s: State, **extra) -> Ctx:
        return Ctx(task=self.task, worktree=self.wt, base_sha=self.base_sha, attempt=s.get("attempt", 0),
                   sandbox=self.sandbox, plan=s.get("plan", ""), feedback=s.get("feedback", ""),
                   log=self._event, progress=self._progress, record=self._record, **extra)

    def _event(self, tag: str, message: str) -> None:
        """Log line + heartbeat/activity in the db, so `factory top` shows what is happening now."""
        self.log(tag, message)
        self.db.heartbeat(self.task.id, f"[{tag}] {message}")

    def _record(self, event: dict) -> None:
        if self.transcript is None:
            return
        event = {"at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds"), **event}
        with self.transcript.open("a") as f:
            f.write(json.dumps(event, default=str) + "\n")

    def _progress(self, steps: int, max_steps: int, tin: int, tout: int, cost: float | None = None,
                  refused: int = 0) -> None:
        role = self.db.conn.execute("SELECT role, attempt FROM runs WHERE id=?", (self.run_id,)).fetchone()
        label = f"{role['role']}#{role['attempt']}" if role else "?"
        text = f"{label} step {steps}/{max_steps} · {tin // 1000}k in / {tout // 1000}k out"
        text += f" · ${cost:.3f}" if cost is not None else ""
        text += f" · {refused} refused" if refused else ""
        self.db.progress(self.task.id, self.run_id, text, steps, tin, tout, cost, refused)
        if self.opts.max_cost is not None:
            spent = self.db.task(self.task.id)["cost_usd"] or 0.0
            if spent > self.opts.max_cost:
                raise PipelineError(f"cost limit exceeded: ${spent:.2f} > ${self.opts.max_cost:.2f}")

    def role(self, role: str, status: str, attempt: int, fn):
        self.db.update(self.task.id, status=status, progress=f"{role}#{attempt} starting")
        run_id = self.db.start_run(self.task.id, role, attempt)
        self.run_id = run_id
        if self.transcript_dir is not None:
            self.transcript_dir.mkdir(parents=True, exist_ok=True)
            self.transcript = self.transcript_dir / f"{run_id:05d}-{role}-{attempt}.jsonl"
            self.db.conn.execute("UPDATE runs SET transcript=? WHERE id=?", (str(self.transcript), run_id))
        self._event("stage", f"{status} ({role} #{attempt})")
        try:
            out, outcome, report, sha = fn()
        except Exception as e:  # record, then stop the pipeline
            self.db.finish_run(run_id, "error", f"{type(e).__name__}: {e}")
            self._event("stage", f"{role} #{attempt} error: {clip(f'{type(e).__name__}: {e}', 300)}")
            raise
        if getattr(out, "stopped", None):
            outcome = f"{outcome} ({out.stopped})"
        self.db.conn.execute("UPDATE runs SET model=? WHERE id=?", (getattr(out, "model", None), run_id))
        if hasattr(out, "steps"):
            self.db.progress(self.task.id, run_id, f"{role}#{attempt} {outcome}", out.steps, out.tokens_in,
                             out.tokens_out, out.cost_usd, out.refused)
        self.db.finish_run(run_id, outcome, report, sha)
        self._event("stage", f"{role} #{attempt} → {outcome}" + (f" @ {sha[:12]}" if sha else ""))
        return out

    # ------------------------------------------------------------ nodes

    def plan(self, s: State) -> State:
        out = self.role("plan", "planning", 0, lambda: (o := self.roles.plan(self.ctx(s)), "done", o.text, None))
        return {"plan": out.text, "attempt": 0, "feedback": ""}

    def _commit(self, out, message: str):
        """Commit whatever the agent left in the worktree; returns (out, outcome, report, sha) for `role`."""
        git(self.wt, "add", "-A")
        if not git(self.wt, "diff", "--cached", "--name-only"):
            return out, "no-changes", out.text, None
        git(self.wt, "commit", "-q", "-m", message)
        return out, "committed", out.text, git(self.wt, "rev-parse", "HEAD")

    def resolve(self, s: State) -> State:
        """Entry point when resolving: commit the replayed change, having the builder fix any conflicts first.
        A clean replay goes straight to the gates; a resolution is reviewed like any build."""
        r = self.opts.resolution
        plan = self.db.last_report(self.task.id, "plan", "done")
        message = f"factory({self.task.id}): {self.task.goal[:60]} (on {r.onto})"
        if not r.conflicts:
            self.role("resolve", "building", 0, lambda: self._commit(Replayed(), message))
            sha = git(self.wt, "rev-parse", "HEAD")
            self.db.update(self.task.id, candidate_sha=sha)
            return {"plan": plan, "attempt": 0, "sha": sha, "verdict": "APPROVE"}
        self.db.update(self.task.id, attempts=1)
        ctx = self.ctx({**s, "plan": plan, "attempt": 1}, resolution=r.brief)
        self.role("resolve", "building", 1, lambda: self._commit(self.roles.resolve(ctx), message))
        sha = git(self.wt, "rev-parse", "HEAD")
        if sha == self.base_sha:
            return {"plan": plan, "attempt": 1, "sha": sha, "verdict": "CHANGES",
                    "feedback": "The conflict resolution left no changes. Re-apply the task's change on the new base."}
        self.db.update(self.task.id, candidate_sha=sha)
        return {"plan": plan, "attempt": 1, "sha": sha, "verdict": ""}

    def ci(self, s: State) -> State:
        """Entry point when fixing CI: record what failed, then build on the PR's head with it as feedback."""
        f = self.opts.ci_fix
        self.role("ci", "building", 0, lambda: (None, "failing", f.brief, f.old_candidate))
        return {"plan": self.db.last_report(self.task.id, "plan", "done"), "attempt": 0, "feedback": f.brief}

    def build(self, s: State) -> State:
        attempt = s.get("attempt", 0) + 1
        self.db.update(self.task.id, attempts=attempt)
        feedback, f = s.get("feedback", ""), self.opts.ci_fix
        if f and f.brief not in feedback:          # the CI failures stay in view on every attempt
            feedback = f"{feedback}\n\n{f.brief}".strip()

        def run():
            out = self.roles.build(self.ctx({**s, "attempt": attempt, "feedback": feedback}))
            return self._commit(out, f"factory({self.task.id}): {self.task.goal[:60]} "
                                     + (f"(fix CI, attempt {attempt})" if f else f"(attempt {attempt})"))

        out = self.role("build", "building", attempt, run)
        sha = git(self.wt, "rev-parse", "HEAD")
        if sha == self.start_sha:
            return {"attempt": attempt, "sha": sha, "verdict": "CHANGES",
                    "feedback": "The previous attempt produced no changes, so CI still fails. Fix the failures."
                    if f else "The previous attempt produced no changes. Implement the task."}
        self.db.update(self.task.id, candidate_sha=sha)
        return {"attempt": attempt, "sha": sha}

    def review(self, s: State) -> State:
        if s["sha"] == self.start_sha:
            return {"verdict": "CHANGES"}
        out = self.role("review", "reviewing", s["attempt"],
                        lambda: (o := self.roles.review(self.ctx(s)), o.verdict, o.text, s["sha"]))
        fb = "" if out.verdict == "APPROVE" else f"Reviewer requested changes:\n\n{out.text}"
        return {"verdict": out.verdict, "review": out.text, "feedback": fb}

    def verify(self, s: State) -> State:
        def run():
            gs = G.run_gates(self.task, self.wt, self.base_sha, s["sha"], self.sandbox, self.opts.config,
                             skip=self.opts.skip_gates, full_e2e=self.opts.full_e2e)
            return gs, "pass" if G.passed(gs) else "fail", G.table(gs), s["sha"]

        gs = self.role("verify", "verifying", s["attempt"], run)
        table = G.table(gs)
        for g in gs:
            self._event("gate", f"{g.mark:<4} {g.name}: {clip(g.detail, 200)}")
        if not G.passed(gs):
            bad = [g for g in gs if g.ok is False]
            failed = "\n\n".join(f"### {g.name}\n{g.detail}" for g in bad)
            sig = json.dumps([(g.name, g.detail) for g in bad])
            stuck = sig == s.get("failure_sig")
            if stuck:
                self._event("stage", "no progress: the same gates failed with the same output twice in a row")
            return {"gates_ok": False, "gates": table, "failure_sig": sig, "stuck": stuck,
                    "feedback": f"Verification gates failed: {', '.join(g.name for g in bad)}\n\n{failed}"}
        out = self.role("verify", "verifying", s["attempt"],
                        lambda: (o := self.roles.verify(self.ctx(s, gates=table)), "report", o.text, s["sha"]))
        return {"gates_ok": True, "gates": table, "verify": out.text}

    def pr(self, s: State) -> State:
        if not self.opts.open_pr:
            self.db.update(self.task.id, status="verifying", progress=None, note="gates passed; --no-pr")
            self._event("stage", "gates passed; --no-pr, stopping before push")
            return {"outcome": "verified"}
        body = self.pr_body(s)

        def run():
            branch = branch_name(self.task.id)
            redo = self.opts.resolution or self.opts.ci_fix  # replace exactly the PR head it resolved or fixed,
            lease = (f"--force-with-lease=refs/heads/{branch}:{redo.old_candidate}"   # never a commit pushed since
                     if redo else "--force-with-lease")
            git(self.wt, "push", "-q", lease, "-u", self.opts.remote, f"HEAD:refs/heads/{branch}")
            # Only an OPEN PR is reused: `gh pr view <branch>` also matches closed/merged ones from earlier runs.
            existing = subprocess.run(["gh", "pr", "list", "--head", branch, "--state", "open", "--json", "url",
                                       "-q", ".[0].url // empty"], cwd=self.wt, capture_output=True, text=True)
            if existing.returncode == 0 and existing.stdout.strip():
                from .stack import edit_pr
                url = existing.stdout.strip()
                edit_pr(self.wt, url, body=body)
            else:
                p = subprocess.run(["gh", "pr", "create", "--base", self.opts.base_ref, "--head", branch,
                                    "--title", f"{self.task.id}: {self.task.goal[:70]}", "--body", body],
                                   cwd=self.wt, capture_output=True, text=True)
                if p.returncode != 0:
                    raise PipelineError(f"gh pr create failed: {p.stderr.strip()}")
                url = p.stdout.strip().splitlines()[-1]
            return url, "opened", url, s["sha"]

        self.pr_url = self.role("pr", "verifying", s["attempt"], run)
        if self.opts.resolution:
            from .stack import comment
            r = self.opts.resolution
            what = (f"resolved conflicts in {', '.join(f'`{f}`' for f in r.conflicts)}" if r.conflicts
                    else "it now replays cleanly")
            comment(self.wt, self.pr_url, f"Rebuilt on `{r.onto}` ({self.base_sha[:12]}): {what}. Candidate "
                                          f"{r.old_candidate[:12]} → {s['sha'][:12]}; review and gates ran on {s['sha'][:12]}.")
        if f := self.opts.ci_fix:
            from .stack import comment
            comment(self.wt, self.pr_url, f"CI failed on {f.old_candidate[:12]} ({', '.join(f'`{c}`' for c in f.checks)}): "
                                          f"fixed. Candidate {f.old_candidate[:12]} → {s['sha'][:12]}; review and gates "
                                          f"ran on {s['sha'][:12]}, and CI runs on it now.")
        self.db.update(self.task.id, status="pr_open", pr_url=self.pr_url, progress=None)
        self._event("stage", f"pr_open: {self.pr_url}")
        return {"outcome": "pr_open"}

    def fail(self, s: State) -> State:
        reason = s.get("feedback") or "unknown"
        why = "no progress (same failure twice)" if s.get("stuck") else f"gave up after {s.get('attempt', 0)} builds"
        headline = reason.splitlines()[0] if reason.strip() else "unknown"
        self.db.update(self.task.id, status="failed", progress=None, note=f"{why}: {headline}\n\n{reason[:4000]}")
        self._event("stage", f"failed — {why}: {clip(headline, 300)}")
        return {"outcome": "failed"}

    def pr_body(self, s: State) -> str:
        t = self.task
        return "\n\n".join([
            f"Factory task **`{t.id}`** from `{t.plan}` — {t.goal}",
            f"Candidate `{s['sha']}` on base `{self.opts.base_ref}` (`{self.base_sha[:12]}`), "
            f"{s['attempt']} build attempt(s). Gates passed; merging is the human gate.",
            *([f"**Stacked** on {', '.join(self.opts.stacked_on)}: merge those first. This PR shows only "
               f"`{t.id}`'s changes; after they merge, `factory status --refresh` moves it onto the trunk."]
              if self.opts.stacked_on else []),
            *([f"**Conflicts resolved** on `{r.onto}`: " + (", ".join(f"`{f}`" for f in r.conflicts) if r.conflicts
               else "none left") + f". Previous candidate `{r.old_candidate[:12]}`."]
              if (r := self.opts.resolution) else []),
            *([f"**CI fixed**: " + ", ".join(f"`{c}`" for c in f.checks) + f" failed on the previous candidate "
               f"`{f.old_candidate[:12]}`."] if (f := self.opts.ci_fix) else []),
            "## Verifier report\n\n" + s.get("verify", ""),
            "## Gates\n\n" + s.get("gates", ""),
            "<details><summary>Reviewer report</summary>\n\n" + s.get("review", "") + "\n\n</details>",
            "<details><summary>Plan</summary>\n\n" + s.get("plan", "") + "\n\n</details>",
        ])

    # ------------------------------------------------------------ graph

    def graph(self):
        g = StateGraph(State)
        for name in ("plan", "resolve", "ci", "build", "review", "verify", "pr", "fail"):
            g.add_node(name, getattr(self, name))
        g.set_entry_point("resolve" if self.opts.resolution else "ci" if self.opts.ci_fix else "plan")
        g.add_edge("plan", "build")
        g.add_edge("ci", "build")
        g.add_edge("build", "review")
        more = lambda s: s["attempt"] < self.opts.max_attempts and not s.get("stuck")
        g.add_conditional_edges("resolve", lambda s: "verify" if s["verdict"] == "APPROVE" else "review" if not s["verdict"]
                                else ("build" if more(s) else "fail"))
        g.add_conditional_edges("review", lambda s: "verify" if s["verdict"] == "APPROVE" else ("build" if more(s) else "fail"))
        g.add_conditional_edges("verify", lambda s: "pr" if s["gates_ok"] else ("build" if more(s) else "fail"))
        g.add_edge("pr", END)
        g.add_edge("fail", END)
        return g.compile()

    def run(self) -> State:
        try:
            return self.graph().invoke({}, config={"recursion_limit": 8 * self.opts.max_attempts + 10})
        except Exception as e:
            self.db.update(self.task.id, status="failed", progress=None, note=f"error: {type(e).__name__}: {e}"[:2000])
            self._event("stage", f"failed: {clip(f'{type(e).__name__}: {e}', 300)}")
            raise
