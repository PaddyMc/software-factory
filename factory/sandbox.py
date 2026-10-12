"""Command sandbox for agent `run` tools and verification gates.

`Bwrap` runs a command under bubblewrap: the host filesystem is read-only, $HOME,
/tmp and /run are empty tmpfs (no ssh keys, gh tokens, cloud configs, docker
socket), the environment is cleared, there is no network unless asked for, and
only the task worktree plus build caches are writable. The factory database is
not visible inside, so agents cannot change task state.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .config import SandboxConfig

SECRET_ENV = re.compile(r"KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|AUTH", re.I)


@dataclass
class Result:
    code: int
    output: str


def _home() -> Path:
    return Path.home()


def _admin_dir(worktree: Path) -> Path | None:
    """The worktree's private git admin dir (.git/worktrees/<name>), if it is a linked worktree."""
    gitfile = worktree / ".git"
    if gitfile.is_file():
        m = re.match(r"gitdir: (.+)", gitfile.read_text().strip())
        if m:
            return (worktree / m.group(1)).resolve()
    return None


@dataclass
class Bwrap:
    worktree: Path
    cache_dir: Path                       # $FACTORY_HOME/cache: shared build caches
    network: bool = False
    extra_rw: list[Path] = field(default_factory=list)
    cfg: SandboxConfig = field(default_factory=SandboxConfig)

    def _expand(self, value: str) -> str:
        return value.replace("{cache}", str(self.cache_dir)).replace("~", str(_home()), 1 if value.startswith("~") else 0)

    def env(self) -> dict[str, str]:
        path = [self._expand(p) for p in self.cfg.path] + ["/usr/local/bin", "/usr/bin", "/bin"]
        env = {"HOME": str(_home()), "PATH": ":".join(path), "LANG": "C.UTF-8", "TERM": "dumb"}
        env |= {k: self._expand(v) for k, v in self.cfg.env.items()}
        if not self.network:
            env |= {k: self._expand(v) for k, v in self.cfg.offline_env.items()}
        return env

    def argv(self, cmd: str) -> list[str]:
        home = _home()
        wt = self.worktree.resolve()
        a = ["bwrap", "--die-with-parent", "--unshare-all"]
        if self.network:
            a.append("--share-net")
        a += ["--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc",
              "--tmpfs", "/tmp", "--tmpfs", "/run", "--tmpfs", str(home)]
        for paths, flag in ((self.cfg.rw_binds, "--bind"), (self.cfg.ro_binds, "--ro-bind")):
            for p in map(Path, map(self._expand, paths)):
                if p.exists():
                    a += [flag, str(p), str(p)]
        for f in map(Path, map(self._expand, self.cfg.hide)):
            if f.exists():
                a += ["--ro-bind", "/dev/null", str(f)]
        for d in self.cfg.cache_dirs:
            (self.cache_dir / d).mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        a += ["--bind", str(self.cache_dir), str(self.cache_dir)]
        admin = _admin_dir(wt)
        if admin is not None:
            common = admin.parent.parent  # <repo>/.git
            a += ["--ro-bind", str(common), str(common), "--bind", str(admin), str(admin)]
        for p in self.extra_rw:
            a += ["--bind", str(p), str(p)]
        a += ["--bind", str(wt), str(wt), "--chdir", str(wt), "--clearenv"]
        for k, v in self.env().items():
            a += ["--setenv", k, v]
        return a + ["bash", "-c", cmd]

    def run(self, cmd: str, timeout: int = 1800) -> Result:
        return _exec(self.argv(cmd), cwd=self.worktree, env=None, timeout=timeout)


@dataclass
class Unsandboxed:
    """No isolation beyond a scrubbed environment. Tests and --no-sandbox only."""
    worktree: Path
    network: bool = True

    def run(self, cmd: str, timeout: int = 1800) -> Result:
        env = {k: v for k, v in os.environ.items() if not SECRET_ENV.search(k)}
        return _exec(["bash", "-c", cmd], cwd=self.worktree, env=env, timeout=timeout)


def _exec(argv: list[str], cwd: Path, env: dict | None, timeout: int) -> Result:
    try:
        p = subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return Result(-1, f"timeout after {timeout}s")
    return Result(p.returncode, p.stdout + p.stderr)


def available() -> bool:
    return shutil.which("bwrap") is not None


def make(worktree: Path, cache_dir: Path, *, sandbox: bool = True, network: bool = False,
         cfg: SandboxConfig | None = None):
    if not sandbox:
        return Unsandboxed(worktree, network=True)
    if not available():
        raise RuntimeError("bubblewrap (bwrap) is required; install it or pass --no-sandbox")
    return Bwrap(worktree, cache_dir, network=network, cfg=cfg or SandboxConfig())
