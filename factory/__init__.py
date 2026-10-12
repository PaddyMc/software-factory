"""Software factory.

`factory run <task>` drives four role agents (plan, build, review, verify) over one task
contract in an isolated worktree and ends in a pull request. Task state lives in a local
SQLite database under $FACTORY_HOME. Project-specific settings live in `.factory/config.yaml`
(see `factory.config`); `factory init` scaffolds them.
"""

from pathlib import Path
import os
import subprocess


def repo_root(start: Path | None = None) -> Path:
    """Main checkout containing `start` (default: cwd), even when called from a worktree."""
    out = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        cwd=start or Path.cwd(), capture_output=True, text=True, check=True,
    )
    return Path(out.stdout.strip()).parent


def factory_home() -> Path:
    """Local state root (database, worktrees, logs). Never inside a checkout.

    $FACTORY_HOME, else the project's `home` setting, else ~/.local/share/factory/<project name>."""
    if os.environ.get("FACTORY_HOME"):
        return Path(os.environ["FACTORY_HOME"])
    from . import config
    try:
        root = repo_root()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return Path.home() / ".local/share/factory/default"
    return config.load(root).home_dir()
