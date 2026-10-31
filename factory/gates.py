"""Deterministic gates for a candidate commit. These — not an agent — decide pass/fail.

Always: clean, diff, conflict_markers, plan_untouched, verification. When the project configures
them (`.factory/config.yaml`): session_log, e2e_written, unit_tests, e2e_tests. Order: clean, diff,
conflict_markers, plan_untouched, session_log, e2e_written, verification, unit_tests, e2e_tests.
"""

from __future__ import annotations

import datetime as dt
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .config import E2E, Config
from .contracts import Task
from .tools import DENIED_COMMANDS
from .verification import PASS, classify, tests_run

CHEAP = ("clean", "diff", "conflict_markers", "plan_untouched", "session_log", "e2e_written")
CONFLICT_MARKER = re.compile(r"^\+(<{7}|\|{7}|>{7})( |$)")
ALL = CHEAP + ("verification", "unit_tests", "e2e_tests")


@dataclass
class Gate:
    name: str
    ok: bool | None          # None = skipped
    detail: str = ""

    @property
    def mark(self) -> str:
        return {True: "PASS", False: "FAIL", None: "skip"}[self.ok]


def manual_reason(task: Task, cfg: Config) -> str:
    """Why the factory cannot run this task ("" if it can): a verification command it refuses
    (terraform apply, sudo, gh, the project's denied_commands …) can only be run by hand."""
    denied = DENIED_COMMANDS + cfg.denied_commands
    refused = [c for c in task.verification if any(re.search(p, c) for p in denied)]
    return f"verification runs {refused[0]!r}, which the factory refuses; run it by hand" if refused else ""


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout


def changed_files(worktree: Path, base: str, sha: str) -> list[str]:
    return [f for f in git(worktree, "diff", "--name-only", f"{base}..{sha}").splitlines() if f]


@dataclass(frozen=True)
class NewTest:
    path: str      # repo-relative file
    target: str    # file stem (a cargo test target, a pytest module)
    name: str      # test function

    def __str__(self) -> str:
        return f"{self.target}::{self.name}"


def new_e2e_tests(patch: str, e2e: E2E) -> list[NewTest]:
    """Every test function added under the e2e dir: `#[test]`/`#[tokio::test]` fns (rust) or
    `def test_*` (python) in added lines of `patch`."""
    found, current, pending = [], None, False
    file_re = re.compile(r"\+\+\+ b/(" + re.escape(e2e.dir) + r"[^/]+" + re.escape(e2e.suffix) + r")$")
    for line in patch.splitlines():
        if line.startswith("+++ "):
            m = file_re.match(line)
            current, pending = (m.group(1) if m else None), False
        elif current and line.startswith("+"):
            body = line[1:].strip()
            stem = Path(current).stem
            if e2e.language == "python":
                m = re.match(r"(?:async\s+)?def\s+(test\w*)\s*\(", body)
                if m:
                    found.append(NewTest(current, stem, m.group(1)))
            elif re.match(r"#\[(tokio::)?test", body):
                pending = True
            elif pending:
                m = re.match(r"(?:pub\s+)?(?:async\s+)?fn\s+(\w+)", body)
                if m:
                    found.append(NewTest(current, stem, m.group(1)))
                    pending = False
    return found


def conflict_markers(patch: str) -> list[str]:
    """`path:line` of every added line that opens, splits or closes a merge-conflict hunk."""
    found, path, line = [], None, 0
    for text in patch.splitlines():
        if text.startswith("+++ "):
            path = text[6:] if text.startswith("+++ b/") else None
        elif text.startswith("@@"):
            m = re.search(r"\+(\d+)", text)
            line = int(m.group(1)) if m else 0
        elif path and text.startswith("+"):
            if CONFLICT_MARKER.match(text):
                found.append(f"{path}:{line}")
            line += 1
        elif path and not text.startswith("-"):
            line += 1
    return found


def _summary(output: str) -> str:
    lines = [l for l in output.splitlines() if l.startswith("test result") or "FAILED" in l or "panicked" in l]
    return "\n".join(lines[-12:]) or "\n".join(output.splitlines()[-12:])


def run_gates(task: Task, worktree: Path, base: str, sha: str, sandbox, cfg: Config, *,
              skip: tuple[str, ...] = (), full_e2e: bool = False, today: str | None = None) -> list[Gate]:
    gates: list[Gate] = []
    add = gates.append
    head = git(worktree, "rev-parse", "HEAD").strip()
    clean = git(worktree, "status", "--porcelain=v1").strip() == ""
    add(Gate("clean", head == sha and clean,
             f"HEAD {head[:12]} vs candidate {sha[:12]}; {'clean' if clean else 'dirty worktree'}"))

    files = changed_files(worktree, base, sha)
    lock = [f for f in files if f in cfg.lockfiles]
    changed = f"{len(files)} files changed" + (f" (lockfile changes: {', '.join(lock)})" if lock else "")
    add(Gate("diff", bool(files), changed if files else "no changes"))

    markers = conflict_markers(git(worktree, "diff", f"{base}..{sha}"))
    add(Gate("conflict_markers", not markers, ("conflict markers left at " + ", ".join(markers[:20])) if markers
             else "no conflict markers"))

    plan_touched = task.plan in files
    add(Gate("plan_untouched", not plan_touched, f"{task.plan} edited" if plan_touched else "plan unchanged"))

    if cfg.session_log:
        today = today or dt.date.today().isoformat()
        log_dir = cfg.session_log.rstrip("/") + "/"
        sessions = [f for f in files if f.startswith(log_dir)]
        add(Gate("session_log", bool(sessions), ", ".join(sessions) if sessions else
                 f"no {log_dir}*.md in diff (expected {log_dir}{today}.md)"))

    new = new_e2e_tests(git(worktree, "diff", f"{base}..{sha}", "--", cfg.e2e.dir), cfg.e2e) if cfg.e2e else []
    if cfg.e2e:
        kind = "#[test]" if cfg.e2e.language == "rust" else "def test_*"
        add(Gate("e2e_written", bool(new), ", ".join(map(str, new)) if new else
                 f"no {kind} added under {cfg.e2e.dir} (every task adds an e2e test)"))

    def run_named(name: str, cmds: list[str]) -> None:
        if name in skip:
            add(Gate(name, None))
            return
        lines, ok = [], True
        for c in cmds:
            r = sandbox.run(c)
            outcome = classify(c, r.code, r.output)
            ok &= outcome == PASS
            n = tests_run(r.output)
            lines.append(f"[{outcome}] exit={r.code}{f' tests={n}' if n is not None else ''} {c}"
                         + ("" if outcome == PASS else "\n" + _summary(r.output)))
        add(Gate(name, ok, "\n".join(lines) or "nothing to run"))

    run_named("verification", list(task.verification))
    if cfg.unit_tests:
        run_named("unit_tests", list(cfg.unit_tests))
    if cfg.e2e and (cfg.e2e.run_new or cfg.e2e.run_all):
        e2e = cfg.e2e
        run_all = e2e.run_all and (full_e2e or any(re.search(p, f) for p in e2e.run_all_when for f in files))
        if "e2e_tests" in skip:
            add(Gate("e2e_tests", None))
        elif run_all:
            run_named("e2e_tests", [e2e.run_all])
        elif new and e2e.run_new:
            run_named("e2e_tests", [e2e.run_new.format(target=t.target, name=t.name, path=t.path) for t in new])
        elif new:
            run_named("e2e_tests", [e2e.run_all])
        else:
            add(Gate("e2e_tests", False, "nothing to run: no new e2e test"))
    return gates


def passed(gates: list[Gate]) -> bool:
    return all(g.ok is not False for g in gates)


def table(gates: list[Gate]) -> str:
    rows = ["| Gate | Result | Detail |", "|---|---|---|"]
    for g in gates:
        detail = g.detail.replace("\n", "<br>").replace("|", "\\|")
        rows.append(f"| {g.name} | {g.mark} | {detail} |")
    return "\n".join(rows)
