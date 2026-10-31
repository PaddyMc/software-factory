"""`factory init`: the files a repository needs to use the factory.

The factory's code, role prompts and policy stay in the installed package. A repository gets only its
settings (.factory/config.yaml), the workflow skills under .claude/skills (Claude Code and OpenCode)
with links under .agents/skills (Codex), a starter plan, the session-log directory, and agent guidance.
Re-running is safe: existing files are kept unless `force`, and the guidance section is replaced in place.
"""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path

from . import config as C
from .contracts import discover_plans

SKILLS = ("plan-workstream", "review-task", "factory-ops")
BEGIN, END = "<!-- factory:begin -->", "<!-- factory:end -->"
DEFAULT_SESSION_LOG = "docs/sessions"


def templates():
    return resources.files("factory") / "templates"


def unit_test_preset(root: Path) -> list[str]:
    """Unit test commands guessed from the repository's build files (none when unsure)."""
    if (root / "Cargo.toml").is_file():
        return ["cargo test --workspace"]
    if (root / "pyproject.toml").is_file():
        return ["uv run pytest -q"]
    return []


def config_text(root: Path, session_log: str | None) -> str:
    text = (templates() / "config.yaml").read_text().replace("name: my-project", f"name: {json.dumps(root.name)}", 1)
    if session_log:
        text = text.replace("# session_log: docs/sessions", f"session_log: {session_log}", 1)
    if unit := unit_test_preset(root):
        text = text.replace('# unit_tests: ["pytest -q tests/unit"]', f"unit_tests: {json.dumps(unit)}", 1)
    return text


def _files(node, prefix: str = ""):
    """(relative path, file) for every file under a package resource directory."""
    for child in sorted(node.iterdir(), key=lambda c: c.name):
        if child.is_dir():
            yield from _files(child, f"{prefix}{child.name}/")
        elif child.name != "__pycache__":
            yield f"{prefix}{child.name}", child


def plans_dir(cfg: C.Config) -> str:
    """Where a starter plan goes: the fixed prefix of the first `plans` glob."""
    parts = []
    for part in (cfg.plans[0] if cfg.plans else "docs/plans/*.md").split("/")[:-1]:
        if any(ch in part for ch in "*?["):
            break
        parts.append(part)
    return "/".join(parts) or "docs/plans"


def guidance_section(root: Path, cfg: C.Config) -> tuple[str, str, str]:
    """Write the factory section into the first guidance file that exists (AGENTS.md by default),
    creating it if none does; replace the section in place when it is already there."""
    name = next((n for n in cfg.guidance if (root / n).is_file()), (cfg.guidance or ("AGENTS.md",))[0])
    path = root / name
    block = f"{BEGIN}\n{(templates() / 'agents-section.md').read_text().strip()}\n{END}"
    text = path.read_text() if path.is_file() else ""
    if BEGIN in text and END in text and text.index(BEGIN) < text.index(END):
        new = text[:text.index(BEGIN)] + block + text[text.index(END) + len(END):]
        action, note = ("keep", "factory section up to date") if new == text else ("update", "factory section replaced")
    else:
        new = (text.rstrip("\n") + "\n\n" if text.strip() else "") + block + "\n"
        action, note = ("update", "factory section appended") if text else ("wrote", "")
    if new != text:
        path.write_text(new)
    return action, name, note


def init(root: Path, *, force: bool = False, skills: bool = True,
         session_log: str | None = DEFAULT_SESSION_LOG) -> list[tuple[str, str, str]]:
    """Scaffold `root`; returns (action, path, note) for every file considered."""
    done: list[tuple[str, str, str]] = []

    def write(rel: str, text: str) -> None:
        dest = root / rel
        if dest.exists() and not force:
            done.append(("keep", rel, "exists; --force overwrites"))
            return
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text)
        done.append(("wrote", rel, ""))

    def link_skill(name: str) -> None:
        rel = f".agents/skills/{name}"
        dest = root / rel
        target = Path(f"../../.claude/skills/{name}")
        if dest.is_symlink() and dest.readlink() == target:
            done.append(("keep", rel, f"links to {target}"))
            return
        if dest.is_symlink() and force:
            dest.unlink()
        elif dest.exists() or dest.is_symlink():
            note = "exists; --force replaces symlink" if dest.is_symlink() else "exists; keeping existing Codex skill"
            done.append(("keep", rel, note))
            return
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.symlink_to(target, target_is_directory=True)
        done.append(("linked", rel, f"-> {target}"))

    write(C.CONFIG_PATH, config_text(root, session_log))
    cfg = C.load(root)          # what the repository now has, which may be an existing config
    if skills:
        for name in SKILLS:
            rel = f".claude/skills/{name}"
            if (root / rel).exists() and not force:
                done.append(("keep", rel, "exists; --force overwrites"))
            else:
                for sub, src in _files(templates() / "skills" / name):
                    write(f"{rel}/{sub}", src.read_text())
            link_skill(name)
    if cfg.session_log:
        log_dir = root / cfg.session_log
        if not (log_dir.is_dir() and any(log_dir.iterdir())):
            write(f"{cfg.session_log.rstrip('/')}/README.md", (templates() / "session-log.md").read_text())
    if not discover_plans(root, cfg):
        write(f"{plans_dir(cfg)}/example.md", (templates() / "example-plan.md").read_text())
    done.append(guidance_section(root, cfg))
    return done
