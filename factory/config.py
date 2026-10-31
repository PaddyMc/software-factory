"""Per-project settings: `.factory/config.yaml` in the target repository.

Everything project-specific lives here: where plans are, which test every task must add, what
runs as the unit and e2e gates, and what the sandbox mounts. The factory itself stays generic.
Every key is optional. A repository without the file gets plans from `docs/plans/**/*.md` and
only the universal gates (clean, diff, conflict_markers, plan_untouched, verification).

The config is always read from the main checkout, never from a task worktree, so an agent
cannot weaken its own gates.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

CONFIG_PATH = ".factory/config.yaml"
E2E_LANGUAGES = ("rust", "python")
ROLES = ("plan", "build", "review", "verify")


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class E2E:
    """The test every task must add, and how the e2e gate runs it."""
    dir: str                                     # e.g. "crates/e2e/tests/"
    language: str = "rust"                       # how new tests are found: rust (#[test]) | python (def test_)
    run_new: str | None = None                   # per new test; {target} {name} {path} are filled in
    run_all: str | None = None                   # the whole suite
    run_all_when: tuple[str, ...] = ()           # regexes over changed paths that trigger run_all

    @property
    def suffix(self) -> str:
        return ".rs" if self.language == "rust" else ".py"


@dataclass(frozen=True)
class SandboxConfig:
    """What the bubblewrap sandbox exposes. `~` is the user's home, `{cache}` is $FACTORY_HOME/cache."""
    ro_binds: tuple[str, ...] = ("~/.rustup", "~/.local/bin", "~/.local/share/uv")
    rw_binds: tuple[str, ...] = ("~/.cargo",)
    hide: tuple[str, ...] = ("~/.cargo/credentials", "~/.cargo/credentials.toml")
    path: tuple[str, ...] = ("~/.cargo/bin", "~/.local/bin")
    env: dict[str, str] = field(default_factory=lambda: {
        "CARGO_HOME": "~/.cargo", "RUSTUP_HOME": "~/.rustup",
        "CARGO_TARGET_DIR": "{cache}/target", "UV_CACHE_DIR": "{cache}/uv"})
    offline_env: dict[str, str] = field(default_factory=lambda: {"CARGO_NET_OFFLINE": "true", "UV_OFFLINE": "1"})
    cache_dirs: tuple[str, ...] = ("target", "uv")


@dataclass(frozen=True)
class Config:
    name: str = "default"
    home: str | None = None                      # $FACTORY_HOME default; else ~/.local/share/factory/<name>
    plans: tuple[str, ...] = ("docs/plans/**/*.md",)
    exclude: tuple[str, ...] = ()                # globs never read as backlog (e.g. "docs/user/**")
    guidance: tuple[str, ...] = ("AGENTS.md", "CLAUDE.md")   # the first that exists joins every agent's prompt
    session_log: str | None = None               # e.g. "docs/sessions": every task adds <dir>/<today>.md
    e2e: E2E | None = None
    unit_tests: tuple[str, ...] = ()             # commands for the unit_tests gate
    lockfiles: tuple[str, ...] = ("Cargo.lock", "uv.lock", "package-lock.json", "poetry.lock", "go.sum")
    denied_commands: tuple[str, ...] = ()        # extra regexes the agents' `run` tool refuses
    # Directories the agents' file tools may also read by absolute path (dependency sources), never write.
    dependency_sources: tuple[str, ...] = ("~/.cargo/registry/src", "~/.cargo/git/checkouts", "~/.rustup/toolchains")
    models: dict[str, str] = field(default_factory=dict)      # role -> `provider:model`, over the prompt's own
    max_steps: dict[str, int] = field(default_factory=dict)   # role -> model calls allowed per agent run
    sandbox: SandboxConfig = field(default_factory=SandboxConfig)

    def dependency_dirs(self, home: Path | None = None) -> tuple[Path, ...]:
        home = home or Path.home()
        return tuple(home / p[2:] if p.startswith("~/") else Path(p) for p in self.dependency_sources)

    def home_dir(self) -> Path:
        if os.environ.get("FACTORY_HOME"):
            return Path(os.environ["FACTORY_HOME"])
        if self.home:
            return Path(self.home).expanduser()
        return Path.home() / ".local/share/factory" / self.name


def _strs(d: dict, key: str, where: str) -> tuple[str, ...] | None:
    if key not in d:
        return None
    v = d[key]
    if isinstance(v, str):
        v = [v]
    if not isinstance(v, list) or not all(isinstance(i, str) and i for i in v):
        raise ConfigError(f"{where}.{key} must be a string or a list of strings")
    return tuple(v)


def _dict(d: dict, key: str, where: str) -> dict[str, str] | None:
    if key not in d:
        return None
    v = d[key] or {}
    if not isinstance(v, dict):
        raise ConfigError(f"{where}.{key} must be a mapping")
    return {str(k): str(x) for k, x in v.items()}


def _known(d: dict, keys: set[str], where: str) -> None:
    extra = sorted(set(d) - keys)
    if extra:
        raise ConfigError(f"{where}: unknown key(s) {', '.join(extra)}")


def parse(data: dict | None, default_name: str = "default") -> Config:
    d = data or {}
    if not isinstance(d, dict):
        raise ConfigError(f"{CONFIG_PATH} must be a mapping")
    _known(d, {f for f in Config.__dataclass_fields__}, CONFIG_PATH)
    kw: dict = {"name": str(d.get("name") or default_name)}
    for key in ("home", "session_log"):
        if d.get(key) is not None:
            kw[key] = str(d[key])
    for key in ("plans", "exclude", "guidance", "unit_tests", "lockfiles", "denied_commands", "dependency_sources"):
        v = _strs(d, key, CONFIG_PATH)
        if v is not None:
            kw[key] = v
    for pat in kw.get("denied_commands", ()):
        _regex(pat, "denied_commands")
    for key in ("models", "max_steps"):
        v = _dict(d, key, CONFIG_PATH)
        if v is None:
            continue
        unknown = sorted(set(v) - set(ROLES))
        if unknown:
            raise ConfigError(f"{key}: unknown role(s) {', '.join(unknown)} (roles: {', '.join(ROLES)})")
        if key == "max_steps":
            if not all(x.isdigit() and int(x) > 0 for x in v.values()):
                raise ConfigError("max_steps values must be positive integers")
            v = {k: int(x) for k, x in v.items()}
        kw[key] = v
    if d.get("e2e") is not None:
        e = d["e2e"]
        if not isinstance(e, dict) or not e.get("dir"):
            raise ConfigError("e2e must be a mapping with at least `dir`")
        _known(e, {"dir", "language", "run_new", "run_all", "run_all_when"}, "e2e")
        lang = e.get("language", "rust")
        if lang not in E2E_LANGUAGES:
            raise ConfigError(f"e2e.language must be one of {E2E_LANGUAGES}")
        when = _strs(e, "run_all_when", "e2e") or ()
        for pat in when:
            _regex(pat, "e2e.run_all_when")
        kw["e2e"] = E2E(dir=str(e["dir"]).rstrip("/") + "/", language=lang, run_new=e.get("run_new"),
                        run_all=e.get("run_all"), run_all_when=when)
    if d.get("sandbox") is not None:
        s = d["sandbox"]
        if not isinstance(s, dict):
            raise ConfigError("sandbox must be a mapping")
        fields = SandboxConfig.__dataclass_fields__
        _known(s, set(fields), "sandbox")
        skw = {}
        for key in ("ro_binds", "rw_binds", "hide", "path", "cache_dirs"):
            v = _strs(s, key, "sandbox")
            if v is not None:
                skw[key] = v
        for key in ("env", "offline_env"):
            v = _dict(s, key, "sandbox")
            if v is not None:
                skw[key] = v
        kw["sandbox"] = SandboxConfig(**skw)
    return Config(**kw)


def _regex(pat: str, where: str) -> None:
    try:
        re.compile(pat)
    except re.error as e:
        raise ConfigError(f"{where}: invalid regex {pat!r}: {e}") from None


def load(root: Path) -> Config:
    """The project's config (defaults when the file is absent). `name` defaults to the repo directory."""
    path = root / CONFIG_PATH
    data = yaml.safe_load(path.read_text()) if path.is_file() else None
    return parse(data, default_name=root.name)
