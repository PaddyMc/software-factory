"""Parse and validate task contracts in plan docs.

A plan carries a fenced ```yaml list whose mappings have exactly the 8 contract
keys. The plan is a spec only: task status lives in the factory database.
"""

from __future__ import annotations

import hashlib
import json
import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import config as C
from .globs import matches_any

KEYS = (
    "id", "goal", "spec_refs", "depends_on",
    "non_goals", "acceptance", "verification", "risk",
)
LIST_KEYS = ("spec_refs", "depends_on", "non_goals", "acceptance", "verification")
RISKS = ("low", "medium", "high")
ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*-t\d{2}[a-z]?$")
PLACEHOLDER_RE = re.compile(r"\b(TODO|TBD|FIXME|XXX)\b|<[A-Z_ ]+>")
_FENCE = re.compile(r"^```yaml\n(.*?)^```", re.S | re.M)


class ContractError(ValueError):
    pass


@dataclass(frozen=True)
class Task:
    id: str
    goal: str
    spec_refs: tuple[str, ...]
    depends_on: tuple[str, ...]
    non_goals: tuple[str, ...]
    acceptance: tuple[str, ...]
    verification: tuple[str, ...]
    risk: str
    plan: str = field(default="", compare=False)

    def mapping(self) -> dict:
        return {k: (list(v) if isinstance(v, tuple) else v) for k, v in
                ((k, getattr(self, k)) for k in KEYS)}

    def to_json(self) -> str:
        return json.dumps({**self.mapping(), "plan": self.plan}, sort_keys=True)

    @classmethod
    def from_json(cls, blob: str) -> "Task":
        d = json.loads(blob)
        return cls(plan=d.pop("plan", ""), **{k: tuple(d[k]) if k in LIST_KEYS else d[k] for k in KEYS})

    def contract_hash(self) -> str:
        blob = json.dumps(self.mapping(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode()).hexdigest()


def task_from_mapping(m: object, plan: str = "") -> Task:
    if not isinstance(m, dict):
        raise ContractError(f"{plan}: contract item is not a mapping: {m!r}")
    tid = m.get("id")
    missing = [k for k in KEYS if k not in m]
    extra = sorted(set(m) - set(KEYS))
    if missing or extra:
        raise ContractError(f"{plan}: task {tid!r} missing={missing} extra={extra}")
    for k in ("id", "goal", "risk"):
        if not isinstance(m[k], str) or not m[k].strip():
            raise ContractError(f"{plan}: task {tid!r} field {k!r} must be a non-empty string")
    for k in LIST_KEYS:
        v = m[k]
        if not isinstance(v, list) or not all(isinstance(i, str) and i.strip() for i in v):
            raise ContractError(f"{plan}: task {tid!r} field {k!r} must be a list of non-empty strings")
    if not ID_RE.match(m["id"]):
        raise ContractError(f"{plan}: task id {tid!r} must be workstream-prefixed like 'name-t01'")
    if m["risk"] not in RISKS:
        raise ContractError(f"{plan}: task {tid!r} risk {m['risk']!r} not in {RISKS}")
    if not m["acceptance"]:
        raise ContractError(f"{plan}: task {tid!r} has empty acceptance")
    return Task(plan=plan, **{k: tuple(m[k]) if k in LIST_KEYS else m[k] for k in KEYS})


def parse_text(text: str, plan: str = "") -> list[Task]:
    """Tasks from every fenced yaml block that is a list of mappings with an `id`."""
    tasks: list[Task] = []
    for block in _FENCE.findall(text):
        items = yaml.safe_load(block)
        if not isinstance(items, list) or not items:
            continue
        if not all(isinstance(i, dict) and "id" in i for i in items):
            continue  # some other yaml example
        tasks.extend(task_from_mapping(i, plan) for i in items)
    return tasks


def parse_plan(path: Path, root: Path | None = None) -> list[Task]:
    rel = str(path.relative_to(root)) if root else str(path)
    return parse_text(path.read_text(), rel)


def discover_plans(root: Path, cfg: C.Config | None = None) -> list[Path]:
    """Plan docs matching the project's `plans` globs, minus its `exclude` globs."""
    cfg = cfg or C.load(root)
    found = {p for pattern in cfg.plans for p in root.glob(pattern) if p.is_file()}
    return sorted(p for p in found if not matches_any(p.relative_to(root).as_posix(), cfg.exclude))


def load_all(root: Path, plans: list[Path] | None = None) -> dict[str, Task]:
    tasks: dict[str, Task] = {}
    for p in plans if plans is not None else discover_plans(root):
        for t in parse_plan(p, root):
            if t.id in tasks:
                raise ContractError(f"duplicate task id {t.id} in {t.plan} and {tasks[t.id].plan}")
            tasks[t.id] = t
    return tasks


def check_dependencies(tasks: dict[str, Task]) -> list[str]:
    """Unknown dependency ids and cycles."""
    errs = [f"{t.id}: unknown dependency {d}" for t in tasks.values() for d in t.depends_on if d not in tasks]
    WHITE, GREY, BLACK = 0, 1, 2
    color = {i: WHITE for i in tasks}

    def visit(i: str, stack: list[str]) -> None:
        color[i] = GREY
        for d in tasks[i].depends_on:
            if d not in tasks:
                continue
            if color[d] == GREY:
                errs.append("dependency cycle: " + " -> ".join(stack[stack.index(d):] + [d]))
            elif color[d] == WHITE:
                visit(d, stack + [d])
        color[i] = BLACK

    for i in tasks:
        if color[i] == WHITE:
            visit(i, [i])
    return errs


def check_command(cmd: str) -> list[str]:
    """Command-selection problems in a verification command."""
    errs = []
    if re.match(r"^(Run|Check|Verify|Ensure|Confirm)\b", cmd):
        errs.append(f"prose prefix, not a command: {cmd!r}")
    try:
        argv = shlex.split(cmd)
    except ValueError as e:
        return [f"unparseable command {cmd!r}: {e}"]
    if "pytest" in argv and "-k" in argv:
        i = argv.index("-k")
        if i + 1 >= len(argv) or argv[i + 1].startswith("-"):
            errs.append(f"pytest -k without an expression: {cmd!r}")
    if argv[:2] == ["cargo", "test"] and "--exact" in argv:
        if not [a for a in argv[2:] if not a.startswith("-")]:
            errs.append(f"cargo test --exact without a test name: {cmd!r}")
    return errs


def check_placeholders(t: Task) -> list[str]:
    errs = []
    for k in ("goal", "acceptance", "verification"):
        vals = [getattr(t, k)] if isinstance(getattr(t, k), str) else list(getattr(t, k))
        errs += [f"{t.id}: placeholder in {k}: {v!r}" for v in vals if PLACEHOLDER_RE.search(v)]
    return errs


def validate_tasks(tasks: list[Task], known: dict[str, Task] | None = None) -> list[str]:
    """Schema-level checks across `tasks`; `known` adds tasks from other plans for dependency resolution."""
    errs, seen = [], set()
    for t in tasks:
        if t.id in seen:
            errs.append(f"duplicate task id {t.id}")
        seen.add(t.id)
    by_id = {**(known or {}), **{t.id: t for t in tasks}}
    errs += [e for e in check_dependencies(by_id) if any(e.startswith(t.id) or t.id in e for t in tasks)]
    for t in tasks:
        errs += [f"{t.id}: {e}" for c in t.verification for e in check_command(c)]
        errs += check_placeholders(t)
    return errs


def validate_plan(path: Path, root: Path | None = None) -> tuple[list[Task], list[str]]:
    """Parse + validate one plan. Never edits the plan."""
    try:
        tasks = parse_plan(path, root)
    except (ContractError, yaml.YAMLError) as e:
        return [], [str(e)]
    if not tasks:
        return [], [f"{path}: no task contracts found"]
    return tasks, validate_tasks(tasks)


def find_task(root: Path, task_id: str) -> Task:
    tasks = load_all(root)
    if task_id not in tasks:
        raise ContractError(f"unknown task {task_id} (no contract in the plans; see `plans` in {C.CONFIG_PATH})")
    return tasks[task_id]


def plan_name(plan: str) -> str:
    """Short name of a plan: its file stem (`docs/plans/infra/deploy.md` -> `deploy`)."""
    return Path(plan).stem


def find_plan(root: Path, ref: str) -> Path | None:
    """A plan doc by path (repo-relative or absolute) or by name (file stem); None if there is none.
    Raises ContractError when a name matches more than one plan."""
    p = Path(ref) if Path(ref).is_absolute() else root / ref
    if p.is_file():
        return p
    hits = [q for q in discover_plans(root) if q.stem == ref]
    if len(hits) > 1:
        raise ContractError(f"{ref} matches several plans: " + ", ".join(str(q.relative_to(root)) for q in hits))
    return hits[0] if hits else None


def plan_order(tasks: list[Task]) -> list[Task]:
    """`tasks` (one plan) in dependency order; ties keep plan order."""
    ids = {t.id for t in tasks}
    done: set[str] = set()
    out: list[Task] = []
    while len(out) < len(tasks):
        for t in tasks:
            if t.id not in done and all(d in done or d not in ids for d in t.depends_on):
                out.append(t)
                done.add(t.id)
                break
        else:
            raise ContractError("dependency cycle in " + ", ".join(t.id for t in tasks if t.id not in done))
    return out
