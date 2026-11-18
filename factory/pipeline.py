"""One task through plan -> build -> review -> verify -> PR (LangGraph).

Review "changes" and gate failures loop back to build with feedback, up to
`max_attempts` builds. A PR is opened only when every gate passes, so the end
state is either a working PR or a failed task with reasons — never a broken PR.

A PR that conflicts with its base runs resolve -> review -> verify -> PR instead:
its change is replayed onto the new base, the builder resolves the conflicted
files, and review and gates run again on the result before the PR is updated.

An open PR whose CI fails is reworked: rework -> build -> review -> verify -> PR: the
builder works on the PR's branch with the failing jobs' logs as feedback (see ci.py). An open PR whose
reviewer requested changes is reworked with the review's brief, or answered on the PR when nothing changes.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import os
import random
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypedDict

from langgraph.graph import END, StateGraph

from . import agents, flows, globs
from . import gates as G
from . import github
from . import prbody
from . import verification
from .agents import Ctx, Roles
from .config import Config
from .contracts import Task
from .db import DB
from .log import NullLog, clip


class PipelineError(RuntimeError):
    pass


class Stopped(BaseException):
    """Raised in the main thread when SIGTERM arrives: the run was stopped by `factory stop`."""


def stopped_note() -> str:
    return f"stopped by factory stop at {dt.datetime.now(dt.timezone.utc):%H:%M} UTC; run it again to start over"


@dataclass
class Resolution:
    """An open PR's change replayed onto a base it conflicts with (see `replay_worktree`)."""
    onto: str                              # what it is replayed onto: the trunk, or factory/<dependency>
    old_candidate: str                     # the PR's head before: the push lease, and what the comment names
    conflicts: tuple[str, ...] = ()        # files left with conflict markers; empty = it replayed cleanly
    brief: str = ""                        # the builder's task message: conflicted files and both sides' diffs


@dataclass
class Rework:
    """An open PR's head, reworked on its branch, then reviewed and gated again."""
    kind: str                              # the run role, and the key into KINDS: "ci" for a failing CI
    old_candidate: str                     # the PR head: the build starts there; the push is leased on it
    what: tuple[str, ...]                  # the names of what triggered it: the failing checks' names
    brief: str = ""                        # the builder's feedback, kept in view on every attempt
    through: int | None = None             # the highest review id the brief covers (a review rework)


@dataclass(frozen=True)
class Kind:
    """The kind-specific wording of one rework (see `KINDS`): looked up from `Rework.kind`."""
    entry_outcome: str
    commit_body: object                 # why this rework was committed, with its attempt number
    no_change: str
    comment: object
    body_line: object
    failure_note: object
    log: object


KINDS = {
    "ci": Kind(
        entry_outcome="failing",
        commit_body=lambda attempt: f"Fix CI, attempt {attempt}.",
        no_change="The previous attempt produced no changes, so CI still fails. Fix the failures.",
        comment=lambda r, new_sha, msg: (
            f"CI failed on {r.old_candidate[:12]} ({', '.join(f'`{c}`' for c in r.what)}): fixed. Candidate "
            f"{r.old_candidate[:12]} → {new_sha[:12]}; review and gates ran on {new_sha[:12]}, and CI runs on it now."
        ),
        body_line=lambda r: (
            f"**CI fixed**: " + ", ".join(f"`{c}`" for c in r.what) +
            f" failed on the previous candidate `{r.old_candidate[:12]}`."
        ),
        failure_note=lambda r: (
            f"The PR still holds {r.old_candidate[:12]}, whose CI fails ({', '.join(r.what)}). "
            f"Running the task again rebuilds it from scratch."
        ),
        log=lambda r: f"fixing CI ({', '.join(r.what)}) on {r.old_candidate[:12]}",
    ),
    "human_review": Kind(
        entry_outcome="changes_requested",
        commit_body=lambda attempt: f"Address review, attempt {attempt}.",
        no_change="The previous attempt produced no changes, so the review's requests are still unanswered. "
                  "Address them, or answer them in your final message.",
        comment=lambda r, new_sha, msg: (
            f"Addressed review by {', '.join('@' + l for l in r.what)} on {r.old_candidate[:12]}: {msg}. Candidate "
            f"{r.old_candidate[:12]} → {new_sha[:12]}; review and gates ran on {new_sha[:12]}."
        ),
        body_line=lambda r: (
            f"**Review addressed** by {', '.join('@' + l for l in r.what)} on the previous candidate "
            f"`{r.old_candidate[:12]}`."
        ),
        failure_note=lambda r: (
            f"The PR still holds {r.old_candidate[:12]}, whose reviews are still unaddressed. "
            f"Running the task again rebuilds it from scratch."
        ),
        log=lambda r: f"addressing review by {', '.join('@' + l for l in r.what)} on {r.old_candidate[:12]}",
    ),
}


def answer_text(text: str) -> str:
    """The builder's final message for a PR comment: the `RESULT:` line is for the factory, not the human."""
    return "\n".join(line for line in text.strip().splitlines() if not line.strip().startswith("RESULT:")).strip()


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
    rework: Rework | None = None           # rework this open PR's head (its failing CI) instead of building from the plan
    flow: flows.Flow = flows.DEFAULT       # the agent flow a fresh build runs (rework entries are fixed)


class State(TypedDict, total=False):
    attempt: int
    plan: str
    feedback: str
    test_sha: str
    test_step: str
    test_report: str
    test_files: list[str]
    red_commands: list[str]
    test_failed: bool
    sha: str
    verdict: str
    gates_ok: bool
    gates_ran: bool          # a candidates attempt already ran the gates once per candidate
    gates: str
    gates_pr: str           # gate details cut for the PR; `gates` stays whole for the verifier
    checks: list[prbody.Check]  # gate results and command/test counts for the PR's Checks paragraph
    selection: tuple[int, int, str]  # first-attempt candidates: total, passing, "selector" | "smallest diff"
    reviews: dict[str, str]  # review step name -> its report (one PR-body block per review step)
    review_outcomes: dict[str, str]  # review step name -> its run's verdict, in this attempt
    verify: str
    summary: prbody.Summary
    outcome: str
    failure_sig: str        # identical gate failures on consecutive attempts => stop (no progress)
    stuck: bool
    answer: str             # a rework the builder changed nothing on: the builder's message, answered on the PR


def git(cwd: Path, *args: str, check: bool = True) -> str:
    """Every git call the factory makes outside the sandbox; with a GitHub token set, its fetches and
    pushes to github.com use it (see github.py)."""
    p = subprocess.run(["git", *github.git_options(os.environ), *args], cwd=cwd, capture_output=True, text=True)
    if check and p.returncode != 0:
        raise PipelineError(f"git {' '.join(args)}: {p.stderr.strip()}")
    return p.stdout.strip()


def branch_name(task_id: str) -> str:
    return f"factory/{task_id}"


SUBJECT_LIMIT = 72


def commit_message(task_id: str, goal: str, body: str) -> str:
    """A word-cut goal subject that fits GitHub's subject limit, with the reason in the body."""
    prefix = f"factory({task_id}): "
    return prefix + prbody.shorten(goal, SUBJECT_LIMIT - len(prefix)) + "\n\n" + body


def pr_title(task_id: str, goal: str, summary: prbody.Summary) -> str:
    return f"{task_id}: " + (summary.title or prbody.shorten(goal, SUBJECT_LIMIT))


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


def remove_worktree(wt: Path, cwd: Path) -> None:
    """Remove a worktree, including an unregistered directory left by an interrupted cleanup."""
    git(cwd, "worktree", "remove", "--force", str(wt), check=False)
    if wt.exists():
        shutil.rmtree(wt, ignore_errors=True)


def trunk_tip(root: Path, trunk: str, remote: str = "origin") -> str:
    """The trunk as `remote` has it now. A local branch can be behind what was merged on GitHub, and a task
    built on it starts without its merged dependencies."""
    git(root, "fetch", "-q", remote, trunk)
    return git(root, "rev-parse", f"{remote}/{trunk}")


DIFF_LIMIT = 20000
GATE_TABLE_WIDTH = 160
SHRUNK_LIMIT = 2000
TEST_TRIES = 2


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
        # A build that leaves HEAD at the base (or the PR head being reworked) changed nothing. A fresh
        # flow with a test step gets a second no-change baseline once its acceptance tests are committed.
        self.start_sha = opts.rework.old_candidate if opts.rework else base_sha
        self.test_sha: str | None = None
        # The flow's shape: [plan]? [test]? build+ (review | gates)* [verify]? (validated in flows.py).
        steps = opts.flow.steps
        self.plan_step = steps[0] if steps[0].kind == "plan" else None
        test_at = 1 if self.plan_step else 0
        self.test_step = steps[test_at] if len(steps) > test_at and steps[test_at].kind == "test" else None
        self.build_steps = tuple(s for s in steps if s.kind == "build")
        self.verify_step = steps[-1] if steps[-1].kind == "verify" else None
        first_post = test_at + (1 if self.test_step else 0) + len(self.build_steps)
        self.post_steps = steps[first_post: len(steps) - (1 if self.verify_step else 0)]

    # ------------------------------------------------------------ helpers

    def ctx(self, s: State, **extra) -> Ctx:
        kw = dict(task=self.task, worktree=self.wt, base_sha=self.base_sha, attempt=s.get("attempt", 0),
                  sandbox=self.sandbox, plan=s.get("plan", ""), feedback=s.get("feedback", ""),
                  log=self._event, progress=self._progress, record=self._record)
        kw.update(extra)
        return Ctx(**kw)

    def _event(self, tag: str, message: str) -> None:
        """Log line + heartbeat/activity in the db, so `factory top` shows what is happening now."""
        self.log(tag, message)
        if not self.db.heartbeat(self.task.id, f"[{tag}] {message}"):
            self.log("board", "board busy: skipped a heartbeat")

    def _record(self, event: dict) -> None:
        if self.transcript is None:
            return
        event = {"at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds"), **event}
        with self.transcript.open("a") as f:
            f.write(json.dumps(event, default=str) + "\n")

    def _progress(self, steps: int, max_steps: int, tin: int, tout: int, cost: float | None = None,
                  refused: int = 0) -> None:
        run = self.db.conn.execute("SELECT role, step, attempt, candidate FROM runs WHERE id=?",
                                   (self.run_id,)).fetchone()
        label = f"{run['step'] or run['role']}#{run['attempt']}" if run else "?"
        if run and run["candidate"] is not None:
            label += f".{run['candidate']}"
        text = f"{label} step {steps}/{max_steps} · {tin // 1000}k in / {tout // 1000}k out"
        text += f" · ${cost:.3f}" if cost is not None else ""
        text += f" · {refused} refused" if refused else ""
        if not self.db.progress(self.task.id, self.run_id, text, steps, tin, tout, cost, refused):
            self.log("board", "board busy: skipped a progress update")
        if self.opts.max_cost is not None:
            spent = self.db.task(self.task.id)["cost_usd"] or 0.0
            if spent > self.opts.max_cost:
                raise PipelineError(f"cost limit exceeded: ${spent:.2f} > ${self.opts.max_cost:.2f}")

    def role(self, role: str, status: str, attempt: int, fn, flow: str | None = None, step: str | None = None,
             candidate: int | None = None):
        label = f"{step or role}#{attempt}" + (f".{candidate}" if candidate is not None else "")
        progress_label = label if candidate is not None else f"{role}#{attempt}"
        stage_label = label if candidate is not None else f"{role} #{attempt}"
        self.db.update(self.task.id, status=status, progress=f"{progress_label} starting")
        run_id = self.db.start_run(self.task.id, role, attempt,
                                   flow=flow or self.opts.flow.name, step=step or role, candidate=candidate)
        self.run_id = run_id
        if self.transcript_dir is not None:
            self.transcript_dir.mkdir(parents=True, exist_ok=True)
            self.transcript = self.transcript_dir / f"{run_id:05d}-{role}-{attempt}.jsonl"
            self.db.conn.execute("UPDATE runs SET transcript=? WHERE id=?", (str(self.transcript), run_id))
        self._event("stage", f"{status} ({stage_label})")
        try:
            out, outcome, report, sha = fn()
        except Exception as e:  # record, then stop the pipeline
            self.db.finish_run(run_id, "error", f"{type(e).__name__}: {e}")
            self._event("stage", f"{stage_label} error: {clip(f'{type(e).__name__}: {e}', 300)}")
            raise
        if getattr(out, "stopped", None):
            outcome = f"{outcome} ({out.stopped})"
        self.db.conn.execute("UPDATE runs SET model=?, prompt_version=? WHERE id=?",
                             (getattr(out, "model", None), getattr(out, "prompt_version", None), run_id))
        if hasattr(out, "steps"):
            self.db.progress(self.task.id, run_id, f"{progress_label} {outcome}", out.steps, out.tokens_in,
                             out.tokens_out, out.cost_usd, out.refused)
        self.db.finish_run(run_id, outcome, report, sha)
        self._event("stage", f"{stage_label} → {outcome}" + (f" @ {sha[:12]}" if sha else ""))
        return out

    # ------------------------------------------------------------ nodes

    def plan(self, s: State) -> State:
        step = self.plan_step
        out = self.role("plan", "planning", 0,
                        lambda: (o := self.roles.step(step, self.ctx(s)), "done", o.text, None), step=step.name)
        return {"plan": out.text, "attempt": 0, "feedback": ""}

    def _acceptance_commands(self, sha: str) -> list[str]:
        """The contract's test commands plus one run_new command per e2e test added at this try's commit."""
        commands = [c for c in self.task.verification if verification.is_test_command(c)]
        e2e = self.opts.config.e2e
        if e2e and e2e.run_new:
            patch = git(self.wt, "diff", f"{self.base_sha}..{sha}", "--", e2e.dir)
            commands += [e2e.run_new.format(target=t.target, name=t.name, path=t.path)
                         for t in G.new_e2e_tests(patch, e2e)]
        return commands

    def _test_try(self, ctx: Ctx):
        """Run the tester once, then prove at least one acceptance command is red at its commit."""
        out = self.roles.step(self.test_step, ctx)
        git(self.wt, "add", "-A")
        paths = git(self.wt, "diff", "--cached", "--name-only", self.base_sha).splitlines()
        empty = ((), (), ())
        if not paths:
            return out, "no-changes", "The try wrote no tests.", None, *empty
        outside = [p for p in paths if not globs.matches_any(p, self.opts.config.test_paths)]
        if outside:
            allowed = ", ".join(self.opts.config.test_paths)
            reason = f"The try changed paths outside test_paths ({allowed}): {', '.join(outside)}"
            return out, "out-of-scope", reason, None, *empty
        git(self.wt, "commit", "-q", "-m", f"factory({self.task.id}): acceptance tests")
        sha = git(self.wt, "rev-parse", "HEAD")
        red, passing = [], []
        for command in self._acceptance_commands(sha):
            result = self.sandbox.run(command)
            n = verification.tests_run(result.output)
            if n == 0:
                return out, "not-red", f"{command} selects no tests: write the tests it names", None, *empty
            if verification.classify(command, result.code, result.output) == verification.FAIL:
                red.append(command)
            else:
                passing.append(command)
        if not red:
            return out, "not-red", "the tests pass before the change", None, *empty
        return out, "committed", "", sha, tuple(paths), tuple(red), tuple(passing)

    def test(self, s: State) -> State:
        """Write, commit and red-check the acceptance tests once, before the first build."""
        step = self.test_step
        if (not any(verification.is_test_command(c) for c in self.task.verification)
                and self.opts.config.e2e is None):
            reason = "no verification test command and no e2e tests configured: nothing for the tester to write"
            self.role("test", "building", 0, lambda: (None, "skipped", reason, None), step=step.name)
            return {"feedback": ""}
        feedback = s.get("feedback", "")
        for number in range(1, TEST_TRIES + 1):
            ctx = self.ctx({**s, "attempt": number, "feedback": feedback})
            result = {}

            def run():
                out, outcome, reason, sha, files, red, passing = self._test_try(ctx)
                report = out.text
                if outcome == "committed":
                    bullets = lambda commands: "\n".join(f"- `{c}`" for c in commands) or "- (none)"
                    report += ("\n\n# Red check\n\nRed commands:\n" + bullets(red)
                               + "\n\nAlready passing:\n" + bullets(passing))
                result.update(outcome=outcome, reason=reason, sha=sha, files=files, red=red, report=report)
                return out, outcome, report, sha

            self.role("test", "building", number, run, step=step.name)
            if result["outcome"] == "committed":
                self.test_sha = result["sha"]
                return {"test_sha": result["sha"], "test_step": step.name, "test_report": result["report"],
                        "test_files": list(result["files"]), "red_commands": list(result["red"]), "feedback": ""}
            feedback = result["reason"]
            git(self.wt, "reset", "-q", "--hard", self.base_sha)
            git(self.wt, "clean", "-q", "-fd")
        return {"feedback": feedback, "test_failed": True}

    def _commit(self, out, message: str, wt: Path | None = None):
        """Commit whatever the agent left in the worktree; returns (out, outcome, report, sha) for `role`."""
        wt = wt or self.wt
        git(wt, "add", "-A")
        if not git(wt, "diff", "--cached", "--name-only"):
            return out, "no-changes", out.text, None
        git(wt, "commit", "-q", "-m", message)
        return out, "committed", out.text, git(wt, "rev-parse", "HEAD")

    def resolve(self, s: State) -> State:
        """Entry point when resolving: commit the replayed change, having the builder fix any conflicts first.
        A clean replay goes straight to the gates; a resolution is reviewed like any build."""
        r = self.opts.resolution
        plan = self.db.last_report(self.task.id, "plan", "done")
        message = commit_message(self.task.id, self.task.goal, f"Rebuilt on {r.onto}.")
        if not r.conflicts:
            self.role("resolve", "building", 0, lambda: self._commit(Replayed(), message))
            sha = git(self.wt, "rev-parse", "HEAD")
            self.db.update(self.task.id, candidate_sha=sha)
            return {"plan": plan, "attempt": 0, "sha": sha, "verdict": "APPROVE"}
        self.db.update(self.task.id, attempts=1)
        ctx = self.ctx({**s, "plan": plan, "attempt": 1}, resolution=r.brief)
        self.role("resolve", "building", 1,
                  lambda: self._commit(self.roles.resolve(ctx, self.build_steps[0]), message))
        sha = git(self.wt, "rev-parse", "HEAD")
        if sha == self.base_sha:
            return {"plan": plan, "attempt": 1, "sha": sha, "verdict": "CHANGES",
                    "feedback": "The conflict resolution left no changes. Re-apply the task's change on the new base."}
        self.db.update(self.task.id, candidate_sha=sha)
        return {"plan": plan, "attempt": 1, "sha": sha, "verdict": ""}

    def rework(self, s: State) -> State:
        """Entry point when reworking: record what triggered it, then build on the PR's head with the brief."""
        r = self.opts.rework
        self.role(r.kind, "building", 0, lambda: (None, KINDS[r.kind].entry_outcome, r.brief, r.old_candidate))
        return {"plan": self.db.last_report(self.task.id, "plan", "done"), "attempt": 0, "feedback": r.brief}

    def _no_build_changes(self, sha: str) -> bool:
        return sha == self.start_sha or (self.test_sha is not None and sha == self.test_sha)

    def _candidates_run(self, attempt: int) -> bool:
        return (self.build_steps[0].candidates > 1 and attempt == 1
                and self.opts.resolution is None and self.opts.rework is None)

    def attempt(self, s: State) -> State:
        """One attempt: every build step of the flow in order, each committing what it leaves."""
        attempt = s.get("attempt", 0) + 1
        self.db.update(self.task.id, attempts=attempt)
        feedback, r = s.get("feedback", ""), self.opts.rework
        if r and r.brief not in feedback:          # the brief stays in view on every attempt
            feedback = f"{feedback}\n\n{r.brief}".strip()
        plan = s.get("plan", "")
        if not plan and self.plan_step is None:
            plan = "(This flow has no plan step: plan from the contract.)"
        message = commit_message(self.task.id, self.task.goal,
                                 KINDS[r.kind].commit_body(attempt) if r else f"Build attempt {attempt}.")
        if self._candidates_run(attempt):
            return self._candidates(s, attempt, plan, feedback, message)

        earlier, out = [], None
        for step in self.build_steps:
            ctx = self.ctx({**s, "plan": plan, "attempt": attempt, "feedback": feedback}, earlier=tuple(earlier),
                           test_files=tuple(s.get("test_files") or ()),
                           red_commands=tuple(s.get("red_commands") or ()))
            out = self.role("build", "building", attempt,
                            lambda step=step, ctx=ctx: self._commit(self.roles.step(step, ctx), message),
                            step=step.name)
            earlier.append(out.text)
        sha = git(self.wt, "rev-parse", "HEAD")
        if self._no_build_changes(sha):
            if r and r.kind == "human_review" and attempt == 1:
                # The builder answered a review that needs no code change: it goes to the PR, not to a retry.
                return {"attempt": attempt, "sha": sha, "answer": out.text, "gates_ran": False}
            return {"attempt": attempt, "sha": sha, "verdict": "CHANGES", "gates_ran": False,
                    "feedback": KINDS[r.kind].no_change
                    if r else "The previous attempt produced no changes. Implement the task."}
        self.db.update(self.task.id, candidate_sha=sha)
        return {"attempt": attempt, "sha": sha, "reviews": {}, "review_outcomes": {}, "gates_ran": False}

    def _candidate_worktree(self, number: int, start: str) -> tuple[Path, object]:
        wt = self.opts.config.home_dir() / "worktrees" / f"{self.task.id}.c{number}"
        if wt.exists():
            raise PipelineError(f"worktree {wt} exists from a previous run; `factory clean {self.task.id}` first")
        wt.parent.mkdir(parents=True, exist_ok=True)
        git(self.wt, "worktree", "add", "-q", "--detach", str(wt), start)
        self._event("stage", f"candidate {number}: worktree {wt} at {start[:12]}")
        return wt, dataclasses.replace(self.sandbox, worktree=wt)

    def _remove_candidate_worktrees(self) -> None:
        if not self.build_steps or self.build_steps[0].candidates <= 1:
            return
        for number in range(2, self.build_steps[0].candidates + 1):
            wt = self.opts.config.home_dir() / "worktrees" / f"{self.task.id}.c{number}"
            remove_worktree(wt, self.wt)

    def _changed_lines(self, start: str, sha: str) -> int:
        lines = git(self.wt, "diff", "--numstat", f"{start}..{sha}").splitlines()
        return sum(int(added) + int(deleted) for line in lines
                   for added, deleted, _ in [line.split("\t", 2)]
                   if added.isdigit() and deleted.isdigit())

    def _select(self, s: State, attempt: int, start: str, passing: list[dict]) -> tuple[dict, str]:
        """Ask the selector to choose among passing candidates, falling back to the smallest diff."""
        ordered = list(passing)
        random.Random(self.task.id).shuffle(ordered)
        sections = []
        for result in ordered:
            sha = result["sha"]
            stat = git(self.wt, "diff", "--stat", f"{start}..{sha}")[:DIFF_LIMIT]
            patch = git(self.wt, "diff", f"{start}..{sha}")[:DIFF_LIMIT]
            sections.append(f"## Candidate {result['number']}\n\n### Diffstat\n\n```text\n{stat}\n```\n\n"
                            f"### Diff against start commit {start}\n\n```diff\n{patch}\n```\n\n"
                            f"### Gates\n\n{result['table']}")
        message = ("# Contract\n\n" + agents.contract_block(self.task)
                   + "\n\n# Passing candidates\n\n" + "\n\n".join(sections))
        git(self.wt, "reset", "-q", "--hard", start)
        git(self.wt, "clean", "-q", "-fd")
        chosen = None

        def run():
            nonlocal chosen
            out = self.roles.step(flows.Step("select", "select"), self.ctx({**s, "attempt": attempt}),
                                  tag=f"select#{attempt}", message=message)
            number = agents.parse_choice(out.text)
            chosen = next((r for r in passing if r["number"] == number), None)
            return out, "ok" if chosen is not None else "fallback", out.text, None

        self.role("select", "building", attempt, run, step="select")
        if chosen is None:
            self._event("stage", "selector gave no valid choice: smallest diff")
            return min(passing, key=lambda r: (self._changed_lines(start, r["sha"]), r["number"])), "smallest diff"
        return chosen, "selector"

    def _candidates(self, s: State, attempt: int, plan: str, feedback: str, message: str) -> State:
        """Build and gate each first-attempt candidate in turn, then select one or keep the closest."""
        step = self.build_steps[0]
        n = step.candidates
        start = self.test_sha or self.base_sha
        results, snapshots = [], {}
        try:
            for number in range(1, n + 1):
                wt, sbx = (self.wt, self.sandbox) if number == 1 else self._candidate_worktree(number, start)
                ctx = self.ctx({**s, "plan": plan, "attempt": attempt, "feedback": feedback},
                               worktree=wt, sandbox=sbx, earlier=(),
                               test_files=tuple(s.get("test_files") or ()),
                               red_commands=tuple(s.get("red_commands") or ()))
                self.role("build", "building", attempt,
                          lambda wt=wt, ctx=ctx, number=number: self._commit(
                              self.roles.step(step, ctx, tag=f"{step.name}#{attempt}.{number}"), message, wt=wt),
                          step=step.name, candidate=number)
                if "resume" in step.loop:
                    snapshots[number] = self.roles.resumes[step.name]
                sha = git(wt, "rev-parse", "HEAD")
                gs, table, table_pr, checks = self._gates_once(s, attempt, wt, sbx, sha, candidate=number)
                results.append({"number": number, "sha": sha, "gs": gs, "table": table,
                                "table_pr": table_pr, "checks": checks})

            passing = [r for r in results if G.passed(r["gs"])]
            selection = None
            if passing:
                if len(passing) > 1:
                    chosen, how = self._select(s, attempt, start, passing)
                else:
                    chosen, how = passing[0], "smallest diff"
                selection = (n, len(passing), how)
                self._event("stage", f"chose candidate {chosen['number']} of {n} "
                                     f"({len(passing)} passed the gates; {how})")
            else:
                chosen = min(results, key=lambda r: (sum(g.ok is False for g in r["gs"]), r["number"]))
                self._event("stage", f"no candidate passed the gates; candidate {chosen['number']} of {n} "
                                     "carries on (fewest failing gates)")
            sha = chosen["sha"]
            git(self.wt, "reset", "-q", "--hard", sha)
            git(self.wt, "clean", "-q", "-fd")
            self.db.update(self.task.id, candidate_sha=sha)
            if "resume" in step.loop:
                self.roles.resumes[step.name] = snapshots[chosen["number"]]
            out = {"attempt": attempt, "sha": sha, "reviews": {}, "review_outcomes": {}, "gates_ran": True,
                   "gates_ok": bool(passing), "gates": chosen["table"], "gates_pr": chosen["table_pr"],
                   "checks": chosen["checks"]}
            if selection is not None:
                out["selection"] = selection
            if not passing:
                feedback, sig, stuck = self._gate_failure(chosen["gs"], s)
                out.update(feedback=feedback, failure_sig=sig, stuck=stuck)
            return out
        finally:
            self._remove_candidate_worktrees()

    def review_step(self, step: flows.Step):
        """The graph node of one review step: the first CHANGES ends the attempt."""
        def node(s: State) -> State:
            if self._no_build_changes(s["sha"]):
                return {"verdict": "CHANGES"}
            extra = {"review_brief": self.opts.rework.brief} \
                if (self.opts.rework and self.opts.rework.kind == "human_review") else {}
            result = {}

            def restore_candidate():
                removed = git(self.wt, "status", "--porcelain")
                git(self.wt, "reset", "-q", "--hard", s["sha"])
                git(self.wt, "clean", "-q", "-fd")
                if removed:
                    self._event(step.name, "review: reset the worktree to the candidate, removed:\n" + removed)

            def run():
                out = self.roles.step(step, self.ctx(s, **extra))
                report, verdict, outcome = out.text, out.verdict, out.verdict
                if step.prove:
                    # Prove against the committed candidate, never against files the reviewer wrote.
                    restore_candidate()
                    report, verdict, outcome = agents.apply_proof(
                        out.text, out.verdict, self.sandbox, self.opts.config.denied_commands)
                    # A REPRO can write too; leave the candidate clean for the remaining steps and gates.
                    restore_candidate()
                result.update(report=report, verdict=verdict, outcome=outcome)
                return out, outcome, report, s["sha"]

            self.role("review", "reviewing", s["attempt"], run, step=step.name)
            report, verdict, outcome = result["report"], result["verdict"], result["outcome"]
            who = "Reviewer" if step.name == step.kind else f"Reviewer `{step.name}`"
            fb = "" if verdict == "APPROVE" else f"{who} requested changes:\n\n{report}"
            return {"verdict": verdict, "reviews": {**s.get("reviews", {}), step.name: report},
                    "review_outcomes": {**s.get("review_outcomes", {}), step.name: outcome},
                    "feedback": fb}
        return node

    def _gates_once(self, s: State, attempt: int, wt: Path, sbx, sha: str, candidate: int | None = None):
        """Run and record the gates once, on either the task worktree or one candidate's worktree."""
        def run():
            gs = G.run_gates(self.task, wt, self.base_sha, sha, sbx, self.opts.config,
                             skip=self.opts.skip_gates, full_e2e=self.opts.full_e2e,
                             test_commit=s.get("test_sha"), test_files=tuple(s.get("test_files") or ()),
                             test_red=tuple(s.get("red_commands") or ()))
            return gs, "pass" if G.passed(gs) else "fail", G.table(gs), sha

        gs = self.role("verify", "verifying", attempt, run, step="gates", candidate=candidate)
        table = G.table(gs)
        table_pr = G.table(gs, width=GATE_TABLE_WIDTH)
        checks = []
        for g in gs:
            commands = tests = None
            if g.name in ("verification", "unit_tests", "e2e_tests") and g.ok is not None:
                lines = [line for line in g.detail.splitlines() if line.startswith("[")]
                counts = [int(match.group(1)) for line in lines
                          for match in re.finditer(r"tests=(\d+)", line)]
                commands, tests = len(lines), sum(counts) if counts else None
            checks.append(prbody.Check(g.name, g.ok, commands, tests))
            self._event("gate", f"{g.mark:<4} {g.name}: {clip(g.detail, 200)}")
        return gs, table, table_pr, checks

    def _gate_failure(self, gs, s: State) -> tuple[str, str, bool]:
        bad = [g for g in gs if g.ok is False]
        failed = "\n\n".join(f"### {g.name}\n{g.detail}" for g in bad)
        sig = json.dumps([(g.name, g.detail) for g in bad])
        stuck = sig == s.get("failure_sig")
        if stuck:
            self._event("stage", "no progress: the same gates failed with the same output twice in a row")
        feedback = f"Verification gates failed: {', '.join(g.name for g in bad)}\n\n{failed}"
        return feedback, sig, stuck

    def gates(self, s: State) -> State:
        """The gates step (role verify, step gates): any failure ends the attempt."""
        gs, table, table_pr, checks = self._gates_once(s, s["attempt"], self.wt, self.sandbox, s["sha"])
        if not G.passed(gs):
            feedback, sig, stuck = self._gate_failure(gs, s)
            return {"gates_ok": False, "gates": table, "gates_pr": table_pr, "checks": checks,
                    "failure_sig": sig, "stuck": stuck, "feedback": feedback}
        return {"gates_ok": True, "gates": table, "gates_pr": table_pr, "checks": checks}

    def _cleaned_reviews(self, s: State) -> dict[str, str]:
        """The flow's review reports in step order, using the same last-draft cleaning as the PR body."""
        reviews = s.get("reviews", {})
        return {step.name: prbody.clean_report(reviews.get(step.name, ""), "## Acceptance criteria")
                for step in self.opts.flow.steps if step.kind == "review"}

    def _capped_reviews(self, cleaned: dict[str, str]) -> dict[str, str]:
        """Non-empty review reports ready for the verifier, with pointers to their full run records."""
        return {name: prbody.cap(report, prbody.BLOCK_LIMIT, f"factory show {self.task.id} --step {name}")
                for name, report in cleaned.items() if report}

    def _changed_files(self, s: State) -> list[str]:
        return git(self.wt, "diff", "--name-only", f"{self.base_sha}..{s['sha']}").splitlines()

    def verify(self, s: State) -> State:
        step = self.verify_step
        reviews = self._capped_reviews(self._cleaned_reviews(s))
        summary = None

        def run():
            nonlocal summary
            out = self.roles.step(step, self.ctx(s, gates=s["gates"], reviews=reviews))
            parsed = prbody.parse_summary(out.text)
            if parsed is not None:
                summary = prbody.bound_summary(parsed, self.task.id, step.name)
                return out, "report", out.text, s["sha"]
            summary = prbody.fallback_summary(self.task, self._changed_files(s), reviews)
            self._event("stage", f"{step.name} #{s['attempt']}: summary unparseable; using the fallback")
            return out, "report (fallback)", out.text, s["sha"]

        out = self.role("verify", "verifying", s["attempt"], run, step=step.name)
        return {"verify": out.text, "summary": summary}

    def pr(self, s: State) -> State:
        added = {}
        if s.get("summary") is None:
            reviews = self._capped_reviews(self._cleaned_reviews(s))
            added["summary"] = prbody.fallback_summary(self.task, self._changed_files(s), reviews)
            s = {**s, **added}
            self._event("stage", "pr: no verify step; using the fallback summary")
        if not self.opts.open_pr:
            self.db.update(self.task.id, status="verifying", progress=None, note="gates passed; --no-pr")
            self._event("stage", "gates passed; --no-pr, stopping before push")
            return {"outcome": "verified", **added}
        body = self.pr_body(s)
        title = pr_title(self.task.id, self.task.goal, s["summary"])

        def run():
            branch = branch_name(self.task.id)
            redo = self.opts.resolution or self.opts.rework  # replace exactly the PR head it resolved or reworked,
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
                                    "--title", title, "--body", body],
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
        if r := self.opts.rework:
            from .stack import comment
            msg = answer_text(self.db.last_report(self.task.id, "build", "committed"))
            comment(self.wt, self.pr_url, KINDS[r.kind].comment(r, s["sha"], msg))
        update = {"status": "pr_open", "pr_url": self.pr_url, "progress": None}
        if (r := self.opts.rework) and r.kind == "human_review" and r.through is not None:
            update["reviews_addressed"] = r.through
        self.db.update(self.task.id, **update)
        self._event("stage", f"pr_open: {self.pr_url}")
        return {"outcome": "pr_open", **added}

    def answer(self, s: State) -> State:
        """The builder's first attempt left the PR's head unchanged: nothing to push or re-review. The
        builder's answer goes on the PR as a comment, the reviews count as addressed, and the task is open."""
        r = self.opts.rework
        from .stack import comment
        url = self.db.task(self.task.id)["pr_url"]
        comment(self.wt, url, answer_text(s["answer"]))
        self._event("stage", f"answered on {url}; no change to push")
        self.db.update(self.task.id, status="pr_open", note=None, progress=None,
                       reviews_addressed=r.through)
        self._event("stage", f"pr_open: {url}")
        return {"outcome": "pr_open"}

    def fail(self, s: State) -> State:
        reason = s.get("feedback") or "unknown"
        why = (f"the test step gave up after {TEST_TRIES} tries" if s.get("test_failed")
               else "no progress (same failure twice)" if s.get("stuck")
               else f"gave up after {s.get('attempt', 0)} builds")
        headline = reason.splitlines()[0] if reason.strip() else "unknown"
        self.db.update(self.task.id, status="failed", progress=None, note=f"{why}: {headline}\n\n{reason[:4000]}")
        self._event("stage", f"failed — {why}: {clip(headline, 300)}")
        return {"outcome": "failed"}

    def pr_body(self, s: State) -> str:
        t = self.task
        flow = self.opts.flow
        review_steps = [step for step in flow.steps if step.kind == "review"]
        cleaned = self._cleaned_reviews(s)
        pointers = {step.name: f"factory show {t.id} --step {step.name}" for step in review_steps}
        tail = f"The planner's plan and every agent's full report: `factory show {t.id}`"
        summary = s.get("summary")
        if summary is None:                  # also make direct pr_body callers safe on a verify-less flow
            summary = prbody.fallback_summary(t, self._changed_files(s), self._capped_reviews(cleaned))
        changed = "\n".join(f"- {bullet}" for bullet in summary.changed)
        check = "\n".join(f"- {bullet}" for bullet in summary.check) or "Nothing flagged."
        outcomes = s.get("review_outcomes", {})
        reviews = [(step.name, outcomes.get(step.name)) for step in review_steps]
        checks = prbody.checks_paragraph(s.get("checks", []), reviews, s["sha"], s.get("attempt", 1))
        if selection := s.get("selection"):
            total, passing, how = selection
            checks += f" Chosen from {total} candidates ({passing} passed the gates; {how})."
        row = self.db.task(t.id)
        footer = prbody.footer(t, flow, s["sha"], self.opts.base_ref, self.base_sha,
                               row["cost_usd"] if row else None)

        def review_block(step: flows.Step, limit: int) -> str:
            # Cap first so the note's character counts still describe the agent's original report.
            report = prbody.cap(cleaned[step.name], limit, pointers[step.name])
            return (f"<details><summary>Reviewer report ({step.name})</summary>\n\n"
                    + prbody.demote(report) + "\n\n</details>")

        blocks = {step.name: review_block(step, prbody.BLOCK_LIMIT) for step in review_steps}
        gate_block = ("<details><summary>Gate table</summary>\n\n"
                      + prbody.demote("## Gates\n\n" + s.get("gates_pr", "")) + "\n\n</details>")
        task_report = prbody.cap(prbody.demote(prbody.task_text(t)), prbody.BLOCK_LIMIT, f"factory show {t.id}")
        task_block = f"<details><summary>The task</summary>\n\n{task_report}\n\n</details>"
        test_report = s.get("test_report", "")
        test_name = s.get("test_step", self.test_step.name if self.test_step else "test")
        test_pointer = f"factory show {t.id} --step {test_name}"
        cleaned_test = prbody.clean_report(test_report, "## Acceptance criteria")

        def acceptance_tests_block(limit: int) -> str:
            report = prbody.cap(cleaned_test, limit, test_pointer)
            return (f"<details><summary>Acceptance tests ({test_name})</summary>\n\n"
                    + prbody.demote(report) + "\n\n</details>")

        test_block = acceptance_tests_block(prbody.BLOCK_LIMIT) if test_report else ""

        def assemble(with_tail: bool = True) -> str:
            # HTML closes a formatting element at the end of the document. Leaving `sub` open keeps
            # the pointer in the footer while preserving t01's pin that it is the body's final text.
            end = "<sub>" + footer + (" · " + tail if with_tail else "")
            return "\n\n".join([
                *([f"**Stacked** on {', '.join(self.opts.stacked_on)}: merge those first. This PR shows only "
                   f"`{t.id}`'s changes; after they merge, `factory status --refresh` moves it onto the trunk."]
                  if self.opts.stacked_on else []),
                *([f"**Conflicts resolved** on `{r.onto}`: " + (", ".join(f"`{f}`" for f in r.conflicts) if r.conflicts
                   else "none left") + f". Previous candidate `{r.old_candidate[:12]}`."]
                  if (r := self.opts.resolution) else []),
                *([KINDS[r.kind].body_line(r)] if (r := self.opts.rework) else []),
                "## What changed\n\n" + changed,
                "## What to check\n\n" + check,
                "## Checks\n\n" + checks,
                gate_block,
                task_block,
                *([test_block] if test_report else []),
                *blocks.values(),
                "---\n\n" + end,
            ])

        longest = sorted(review_steps, key=lambda step: len(cleaned[step.name]), reverse=True)

        def shrink(step: flows.Step) -> None:
            blocks[step.name] = review_block(step, SHRUNK_LIMIT)

        def replace(step: flows.Step) -> None:
            blocks[step.name] = f"Reviewer report ({step.name}): `{pointers[step.name]}`"

        def shrink_test() -> None:
            nonlocal test_block
            test_block = acceptance_tests_block(SHRUNK_LIMIT)

        def replace_test() -> None:
            nonlocal test_block
            test_block = f"Acceptance tests ({test_name}): `{test_pointer}`"

        def replace_task() -> None:
            nonlocal task_block
            task_block = f"The task: `factory show {t.id}`"

        def replace_gates() -> None:
            nonlocal gate_block
            gate_block = f"Gate table: `factory show {t.id} --step gates`"

        steps = [*(lambda step=step: shrink(step) for step in longest),
                 *(lambda step=step: replace(step) for step in longest),
                 *([shrink_test, replace_test] if test_report else []), replace_task, replace_gates]

        def last_resort() -> str:
            room = prbody.BODY_LIMIT - len(tail) - 2
            if room < 0:                 # only a monkeypatched, impossibly small body limit
                return (assemble(False) + "\n\n" + tail)[:max(0, prbody.BODY_LIMIT)]
            return prbody.cap(assemble(False), room, f"factory show {t.id}") + "\n\n" + tail

        return prbody.fit(assemble, steps, prbody.BODY_LIMIT, last_resort)

    # ------------------------------------------------------------ graph

    def graph(self):
        g = StateGraph(State)
        # The post-build steps (review steps and the gates step, in flow order) get one node each;
        # the review nodes are prefixed so a custom step name can never collide with a fixed one.
        post = [f"review-{s.name}" if s.kind == "review" else "gates" for s in self.post_steps]
        after = dict(zip([s.name for s in self.post_steps], post))
        for name in ("resolve", "rework", "attempt", "gates", "pr", "answer", "fail"):
            g.add_node(name, getattr(self, name))
        if self.test_step:
            g.add_node("test", self.test)
            g.add_conditional_edges("test", lambda s: "fail" if s.get("test_failed") else "attempt")
        if self.plan_step:
            g.add_node("plan", self.plan)
            g.add_edge("plan", "test" if self.test_step else "attempt")
        for step in self.post_steps:
            if step.kind == "review":
                g.add_node(after[step.name], self.review_step(step))
        if self.verify_step:
            g.add_node("verify", self.verify)
            g.add_edge("verify", "pr")
        g.set_entry_point("resolve" if self.opts.resolution else "rework" if self.opts.rework
                          else "plan" if self.plan_step else "test" if self.test_step else "attempt")
        g.add_edge("rework", "attempt")
        more = lambda s: s["attempt"] < self.opts.max_attempts and not s.get("stuck")
        # A flow may put the gates step before some review steps; on pass the gates node routes on
        # to the next post step (or verify/pr when it is last), never past the remaining reviewers.
        gates_at = next(i for i, s in enumerate(self.post_steps) if s.kind == "gates")
        next_after_gates = post[gates_at + 1] if gates_at + 1 < len(post) else (
            "verify" if self.verify_step else "pr")

        def attempt_next(s):
            if s.get("answer") is not None:
                return "answer"
            if s.get("gates_ran"):
                return next_after_gates if s["gates_ok"] else ("attempt" if more(s) else "fail")
            return (("attempt" if more(s) else "fail") if self._no_build_changes(s["sha"]) else post[0])

        g.add_conditional_edges("attempt", attempt_next)
        g.add_conditional_edges("resolve", lambda s: "gates" if s["verdict"] == "APPROVE"
                                else post[0] if not s["verdict"]
                                else ("attempt" if more(s) else "fail"))
        g.add_conditional_edges("gates", lambda s, nxt=next_after_gates: nxt if s["gates_ok"]
                                else ("attempt" if more(s) else "fail"))
        for i, step in enumerate(self.post_steps):
            if step.kind != "review":
                continue
            nxt = post[i + 1] if i + 1 < len(post) else ("verify" if self.verify_step else "pr")
            g.add_conditional_edges(after[step.name],
                                    lambda s, nxt=nxt: nxt if s["verdict"] == "APPROVE"
                                    else ("attempt" if more(s) else "fail"))
        g.add_edge("answer", END)
        g.add_edge("pr", END)
        g.add_edge("fail", END)
        return g.compile()

    def run(self) -> State:
        try:
            return self.graph().invoke(
                {}, config={"recursion_limit": (8 + len(self.opts.flow.steps)) * self.opts.max_attempts + 10})
        except Stopped:
            note = stopped_note()
            if self.run_id is not None and self.db.conn.execute(
                    "SELECT 1 FROM runs WHERE id=? AND ended_at IS NULL", (self.run_id,)).fetchone():
                self.db.finish_run(self.run_id, "stopped", note)
            self.db.update(self.task.id, status="failed", progress=None, note=note)
            self._event("stage", "stopped")
            raise
        except Exception as e:
            self.db.update(self.task.id, status="failed", progress=None, note=f"error: {type(e).__name__}: {e}"[:2000])
            self._event("stage", f"failed: {clip(f'{type(e).__name__}: {e}', 300)}")
            raise
        finally:
            self._remove_candidate_worktrees()
