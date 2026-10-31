"""LangChain tools, scoped per role.

planner/reviewer: read-only. builder: + write/edit anywhere in the worktree + sandboxed run.
verifier: read-only + sandboxed run. Nobody gets commit, push, or database access.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from langchain_core.tools import tool

DENIED_COMMANDS = (
    r"\bgit\s+(push|commit|reset|checkout|switch|rebase|merge|tag|worktree|remote)\b",
    r"\bsudo\b", r"\bterraform\b.*\b(apply|destroy)\b", r"\bgh\b", r"\bfactory\s+",
)
HIDDEN_DIRS = ("target", ".git", "node_modules", ".venv", "__pycache__")


class PathGuard:
    """File tools work in the worktree. Reads may also open dependency sources (crates, toolchain);
    writes stay out of git internals."""

    def __init__(self, root: Path, sources: tuple[Path, ...] = ()):
        self.root = root.resolve()
        self.sources = tuple(s.resolve() for s in sources)    # read-only: `Config.dependency_dirs()`

    def _abs(self, path: str) -> Path:
        return (self.root / Path(path).expanduser()).resolve()

    def rel(self, path: str) -> str:
        p = self._abs(path)
        if p != self.root and self.root not in p.parents:
            raise PermissionError(f"{path} is outside the worktree")
        return p.relative_to(self.root).as_posix()

    def readable(self, path: str) -> Path:
        p = self._abs(path)
        if any(p == r or r in p.parents for r in (self.root, *self.sources)):
            return p
        raise PermissionError(f"{path} is outside the worktree and the dependency sources "
                              f"({', '.join(map(str, self.sources))})")

    def check_write(self, path: str) -> str:
        rel = self.rel(path)
        if rel.split("/")[0] == ".git":
            raise PermissionError(f"write to {rel}: git internals are off limits")
        return rel


@dataclass
class ToolLog:
    written: list[str] = field(default_factory=list)
    commands: list[tuple[str, int]] = field(default_factory=list)


def read_tools(root: Path, guard: PathGuard) -> list:
    @tool
    def read_file(path: str, start: int = 1, end: int | None = None) -> str:
        """Read a worktree-relative file, or a dependency's source by absolute path (e.g. ~/.cargo/registry/src/…).
        Lines are 1-indexed; `end` is inclusive. Output is numbered."""
        p = guard.readable(path)
        lines = p.read_text(errors="replace").splitlines()
        end = end or len(lines)
        return "\n".join(f"{i}\t{line}" for i, line in enumerate(lines[start - 1:end], start)) or "(empty)"

    @tool
    def list_dir(path: str = ".") -> str:
        """List a worktree-relative directory, or a dependency source directory (non-recursive). Directories end with '/'."""
        p = guard.readable(path)
        return "\n".join(sorted(c.name + ("/" if c.is_dir() else "") for c in p.iterdir()
                                if c.name not in HIDDEN_DIRS)) or "(empty)"

    @tool
    def grep(pattern: str, path: str = ".", glob: str | None = None, max_lines: int = 200) -> str:
        """Regex search under a worktree-relative path or a dependency source. `glob` filters file names, e.g. '*.rs'."""
        p = guard.readable(path)
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
        """Create or overwrite a worktree-relative file."""
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
        """Replace exactly one occurrence of `old` with `new` in a worktree-relative file."""
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
