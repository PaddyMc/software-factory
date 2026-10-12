"""One task through plan -> build -> review -> verify -> PR (LangGraph).

Review "changes" and gate failures loop back to build with feedback, up to
`max_attempts` builds. A PR is opened only when every gate passes, so the end
state is either a working PR or a failed task with reasons — never a broken PR.
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
class Options:
    base_ref: str
    max_attempts: int = 3
    open_pr: bool = True
    skip_gates: tuple[str, ...] = ()
    full_e2e: bool = False
    remote: str = "origin"
    max_cost: float | None = None          # abort the task once its recorded cost exceeds this (USD)
    config: Config = field(default_factory=Config)   # loaded from the main checkout, never the worktree


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


def create_worktree(root: Path, home: Path, task_id: str, base_ref: str) -> tuple[Path, str]:
    wt = home / "worktrees" / task_id
    if wt.exists():
        raise PipelineError(f"worktree {wt} exists from a previous run; `factory clean {task_id}` first")
    wt.parent.mkdir(parents=True, exist_ok=True)
    base_sha = git(root, "rev-parse", "--verify", f"{base_ref}^{{commit}}")
    git(root, "worktree", "add", "-q", "-B", branch_name(task_id), str(wt), base_sha)
    return wt, base_sha


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

    def build(self, s: State) -> State:
        attempt = s.get("attempt", 0) + 1
        self.db.update(self.task.id, attempts=attempt)

        def run():
            out = self.roles.build(self.ctx({**s, "attempt": attempt}))
            git(self.wt, "add", "-A")
            if not git(self.wt, "diff", "--cached", "--name-only"):
                return out, "no-changes", out.text, None
            git(self.wt, "commit", "-q", "-m", f"factory({self.task.id}): {self.task.goal[:60]} (attempt {attempt})")
            return out, "committed", out.text, git(self.wt, "rev-parse", "HEAD")

        out = self.role("build", "building", attempt, run)
        sha = git(self.wt, "rev-parse", "HEAD")
        if sha == self.base_sha:
            return {"attempt": attempt, "sha": sha, "verdict": "CHANGES",
                    "feedback": "The previous attempt produced no changes. Implement the task."}
        self.db.update(self.task.id, candidate_sha=sha)
        return {"attempt": attempt, "sha": sha}

    def review(self, s: State) -> State:
        if s["sha"] == self.base_sha:
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
            git(self.wt, "push", "-q", "--force-with-lease", "-u", self.opts.remote, f"HEAD:refs/heads/{branch}")
            # Only an OPEN PR is reused: `gh pr view <branch>` also matches closed/merged ones from earlier runs.
            existing = subprocess.run(["gh", "pr", "list", "--head", branch, "--state", "open", "--json", "url",
                                       "-q", ".[0].url // empty"], cwd=self.wt, capture_output=True, text=True)
            if existing.returncode == 0 and existing.stdout.strip():
                url = existing.stdout.strip()
                subprocess.run(["gh", "pr", "edit", url, "--body", body], cwd=self.wt, capture_output=True, text=True)
            else:
                p = subprocess.run(["gh", "pr", "create", "--base", self.opts.base_ref, "--head", branch,
                                    "--title", f"{self.task.id}: {self.task.goal[:70]}", "--body", body],
                                   cwd=self.wt, capture_output=True, text=True)
                if p.returncode != 0:
                    raise PipelineError(f"gh pr create failed: {p.stderr.strip()}")
                url = p.stdout.strip().splitlines()[-1]
            return url, "opened", url, s["sha"]

        self.pr_url = self.role("pr", "verifying", s["attempt"], run)
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
            "## Verifier report\n\n" + s.get("verify", ""),
            "## Gates\n\n" + s.get("gates", ""),
            "<details><summary>Reviewer report</summary>\n\n" + s.get("review", "") + "\n\n</details>",
            "<details><summary>Plan</summary>\n\n" + s.get("plan", "") + "\n\n</details>",
        ])

    # ------------------------------------------------------------ graph

    def graph(self):
        g = StateGraph(State)
        for name in ("plan", "build", "review", "verify", "pr", "fail"):
            g.add_node(name, getattr(self, name))
        g.set_entry_point("plan")
        g.add_edge("plan", "build")
        g.add_edge("build", "review")
        more = lambda s: s["attempt"] < self.opts.max_attempts and not s.get("stuck")
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
