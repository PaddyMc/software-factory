"""LangChain tools, scoped per role.

planner/reviewer: read-only. builder: + write/edit within allowed_paths + sandboxed run.
verifier: read-only + sandboxed run. Nobody gets commit, push, or database access.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from langchain_core.tools import tool

from .globs import glob_to_regex

DENIED_COMMANDS = (
    r"\bgit\s+(push|commit|reset|checkout|switch|rebase|merge|tag|worktree|remote)\b",
    r"\bsudo\b", r"\bterraform\b.*\b(apply|destroy)\b", r"\bgh\b", r"\bfactory\s+",
)
HIDDEN_DIRS = ("target", ".git", "node_modules", ".venv", "__pycache__")


class PathGuard:
    def __init__(self, root: Path, allowed: tuple[str, ...] | list[str]):
        self.root = root.resolve()
        self.allowed = list(allowed)
        self._res = [glob_to_regex(a) for a in allowed]

    def rel(self, path: str) -> str:
        p = (self.root / path).resolve()
        if p != self.root and self.root not in p.parents:
            raise PermissionError(f"{path} is outside the worktree")
        return p.relative_to(self.root).as_posix()

    def allows(self, rel: str) -> bool:
        return any(r.match(rel) for r in self._res)

    def check_write(self, path: str) -> str:
        rel = self.rel(path)
        if not self.allows(rel):
            raise PermissionError(f"write to {rel} is outside allowed_paths {self.allowed}")
        return rel


@dataclass
class ToolLog:
    written: list[str] = field(default_factory=list)
    commands: list[tuple[str, int]] = field(default_factory=list)


def read_tools(root: Path, guard: PathGuard) -> list:
    @tool
    def read_file(path: str, start: int = 1, end: int | None = None) -> str:
        """Read a worktree-relative file. Lines are 1-indexed; `end` is inclusive. Output is numbered."""
        p = root / guard.rel(path)
        lines = p.read_text(errors="replace").splitlines()
        end = end or len(lines)
        return "\n".join(f"{i}\t{line}" for i, line in enumerate(lines[start - 1:end], start)) or "(empty)"

    @tool
    def list_dir(path: str = ".") -> str:
        """List a worktree-relative directory (non-recursive). Directories end with '/'."""
        p = root / guard.rel(path)
        return "\n".join(sorted(c.name + ("/" if c.is_dir() else "") for c in p.iterdir()
                                if c.name not in HIDDEN_DIRS)) or "(empty)"

    @tool
    def grep(pattern: str, path: str = ".", glob: str | None = None, max_lines: int = 200) -> str:
        """Regex search under a worktree-relative path. `glob` filters file names, e.g. '*.rs'."""
        p = root / guard.rel(path)
        if shutil.which("rg"):
            cmd = ["rg", "-n", "--no-heading", "-e", pattern, str(p)] + (["-g", glob] if glob else [])
        else:
            cmd = ["grep", "-rn", "-E", pattern, str(p)] + ([f"--include={glob}"] if glob else [])
        out = subprocess.run(cmd, capture_output=True, text=True, cwd=root).stdout
        lines = out.replace(str(root) + "/", "").splitlines()
        more = f"\n… {len(lines) - max_lines} more" if len(lines) > max_lines else ""
        return "\n".join(lines[:max_lines]) + more or "(no matches)"

    return [read_file, list_dir, grep]


def diff_tool(root: Path, base_sha: str) -> list:
    @tool
    def git_diff(path: str = "", stat: bool = False) -> str:
        """The change under review: `git diff <base>..HEAD`, optionally limited to a path or as --stat."""
        cmd = ["git", "diff", "--stat" if stat else "--patch", f"{base_sha}..HEAD"] + (["--", path] if path else [])
        out = subprocess.run(cmd, capture_output=True, text=True, cwd=root).stdout
        return out[:60000] or "(no changes)"

    return [git_diff]


def write_tools(root: Path, guard: PathGuard, log: ToolLog) -> list:
    @tool
    def write_file(path: str, content: str) -> str:
        """Create or overwrite a file. Must be within the task's allowed_paths."""
        try:
            rel = guard.check_write(path)
        except PermissionError as e:
            return f"refused: {e}"
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        log.written.append(rel)
        return f"wrote {rel}"

    @tool
    def edit_file(path: str, old: str, new: str) -> str:
        """Replace exactly one occurrence of `old` with `new` in a file within allowed_paths."""
        try:
            rel = guard.check_write(path)
        except PermissionError as e:
            return f"refused: {e}"
        p = root / rel
        text = p.read_text()
        n = text.count(old)
        if n != 1:
            return f"error: `old` occurs {n} times in {rel}; it must occur exactly once"
        p.write_text(text.replace(old, new, 1))
        log.written.append(rel)
        return f"edited {rel}"

    return [write_file, edit_file]


def run_tool(sandbox, log: ToolLog, extra_denied: tuple[str, ...] = ()) -> list:
    denied = DENIED_COMMANDS + tuple(extra_denied)

    @tool
    def run(command: str, timeout: int = 900) -> str:
        """Run a shell command in the sandboxed worktree (builds, tests…). No network, no secrets;
        git commit/push and gh are refused (the factory commits for you). Returns exit code + last 200 lines."""
        for pat in denied:
            if re.search(pat, command):
                return f"refused: command matches denied pattern {pat!r}"
        r = sandbox.run(command, timeout=timeout)
        log.commands.append((command, r.code))
        return f"exit {r.code}\n" + "\n".join(r.output.splitlines()[-200:])

    return [run]
