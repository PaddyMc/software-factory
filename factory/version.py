"""`factory version`: package metadata, plus `git describe` when running from the factory's own checkout."""

import importlib.metadata
import re
import subprocess
from pathlib import Path

_GIT_TIMEOUT = 5.0


def _project_name(pyproject: Path) -> str | None:
    section = ""
    with pyproject.open() as f:
        for line in f:
            stripped = line.strip()
            if stripped.startswith("["):
                section = stripped
            elif section == "[project]":
                m = re.match(r"^\s*name\s*=\s*[\"']([^\"']+)[\"']", line)
                if m:
                    return m.group(1)
    return None


def _git(cwd: Path, *args: str) -> str | None:
    try:
        p = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True,
                           timeout=_GIT_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return p.stdout.strip() if p.returncode == 0 else None


def _package_dir() -> Path:
    return Path(__file__).parent


def describe(package_dir: Path) -> str | None:
    root = Path(package_dir).parent
    pyproject = root / "pyproject.toml"
    if not pyproject.is_file() or _project_name(pyproject) != "software-factory":
        return None
    top = _git(root, "rev-parse", "--show-toplevel")
    if top is None or Path(top).resolve() != root.resolve():
        return None
    return _git(root, "describe", "--tags", "--match", "v[0-9]*", "--always", "--dirty")


def line() -> str:
    try:
        v = importlib.metadata.version("software-factory")
    except importlib.metadata.PackageNotFoundError:
        v = "unknown"
    d = describe(_package_dir())
    return f"factory {v}" + (f" ({d})" if d else "")
