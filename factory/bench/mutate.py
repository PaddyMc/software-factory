"""Deterministic AST mutants of the functions a reference solution changes."""

from __future__ import annotations

import ast
import copy
import hashlib
import random
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . import cases

DEFAULT_MUTANTS = 20
_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
_COMPARISONS = {
    ast.Eq: ast.NotEq,
    ast.NotEq: ast.Eq,
    ast.Lt: ast.Gt,
    ast.LtE: ast.GtE,
    ast.Gt: ast.Lt,
    ast.GtE: ast.LtE,
    ast.Is: ast.IsNot,
    ast.IsNot: ast.Is,
    ast.In: ast.NotIn,
    ast.NotIn: ast.In,
}
_ARITHMETIC = {ast.Add: ast.Sub, ast.Sub: ast.Add}


@dataclass(frozen=True)
class Mutant:
    """One changed Python file, ready to lay over a reference solution."""

    path: str
    function: str
    kind: str
    line: int
    source: str

    def apply(self, root: Path) -> None:
        target = Path(root) / self.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.source, encoding="utf-8")


@dataclass
class _Site:
    parent: ast.AST
    field: str
    index: int | None
    function: str
    kind: str
    line: int
    replacement: ast.AST

    def replace(self) -> None:
        old = getattr(self.parent, self.field)
        if self.index is not None:
            old = old[self.index]
        ast.copy_location(self.replacement, old)
        if self.index is None:
            setattr(self.parent, self.field, self.replacement)
        else:
            getattr(self.parent, self.field)[self.index] = self.replacement


class _FunctionIndex(ast.NodeVisitor):
    """Index functions by qualified name, retaining duplicate definitions in order."""

    def __init__(self):
        self.stack: list[str] = []
        self.functions: dict[str, list[ast.AST]] = {}
        self.names: dict[int, str] = {}

    def _visit_function(self, node: ast.AST, name: str) -> None:
        qualified = ".".join([*self.stack, name])
        self.functions.setdefault(qualified, []).append(node)
        self.names[id(node)] = qualified
        self.stack.append(name)
        self.generic_visit(node)
        self.stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node, node.name)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node, node.name)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self._visit_function(node, "<lambda>")

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()


def _index(tree: ast.Module) -> _FunctionIndex:
    index = _FunctionIndex()
    index.visit(tree)
    return index


def _changed_functions(base: ast.Module | None, solution: ast.Module,
                       solution_index: _FunctionIndex) -> set[int]:
    base_index = _index(base) if base is not None else None
    changed = set()
    for name, functions in solution_index.functions.items():
        old = base_index.functions.get(name, []) if base_index is not None else []
        for position, function in enumerate(functions):
            if (position >= len(old)
                    or ast.dump(old[position], include_attributes=False)
                    != ast.dump(function, include_attributes=False)):
                changed.add(id(function))
    return changed


def _mutation_sites(tree: ast.Module, changed: set[int], names: dict[int, str]) -> list[_Site]:
    sites: list[_Site] = []

    def add(parent: ast.AST, field: str, position: int | None, node: ast.AST,
            function: str, kind: str, replacement: ast.AST) -> None:
        sites.append(_Site(parent, field, position, function, kind,
                           getattr(node, "lineno", getattr(parent, "lineno", 1)), replacement))

    def consider(parent: ast.AST, field: str, position: int | None, node: ast.AST,
                 function: str) -> None:
        if isinstance(node, ast.Return):
            if node.value is not None and not (
                    isinstance(node.value, ast.Constant) and node.value.value is None):
                add(node, "value", None, node, function, "return", ast.Constant(value=None))
            return
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool):
                add(parent, field, position, node, function, "boolean",
                    ast.Constant(value=not node.value))
            elif isinstance(node.value, int):
                add(parent, field, position, node, function, "integer",
                    ast.Constant(value=node.value + 1))
            return
        replacement = _COMPARISONS.get(type(node)) or _ARITHMETIC.get(type(node))
        if replacement is not None:
            kind = "comparison" if type(node) in _COMPARISONS else "arithmetic"
            add(parent, field, position, node, function, kind, replacement())

    def walk(node: ast.AST, function: str = "", active: bool = False) -> None:
        if isinstance(node, _FUNCTIONS):
            function = names.get(id(node), function)
            active = active or id(node) in changed
        for field, value in ast.iter_fields(node):
            children = value if isinstance(value, list) else [value]
            for position, child in enumerate(children):
                if not isinstance(child, ast.AST):
                    continue
                if active:
                    consider(node, field, position if isinstance(value, list) else None,
                             child, function)
                walk(child, function, active)

    walk(tree)
    return sites


def file_mutants(path: str, source: str, base_source: str | None = None) -> list[Mutant]:
    """Return every supported mutation of a changed function in one Python file."""
    try:
        solution = ast.parse(source, filename=path)
    except SyntaxError:
        return []
    try:
        base = ast.parse(base_source, filename=path) if base_source is not None else None
    except SyntaxError:
        base = None
    solution_index = _index(solution)
    changed = _changed_functions(base, solution, solution_index)
    sites = _mutation_sites(solution, changed, solution_index.names)
    mutants = []
    for site in sites:
        tree, selected = copy.deepcopy((solution, site))
        selected.replace()
        ast.fix_missing_locations(tree)
        mutants.append(Mutant(path, site.function, site.kind, site.line,
                              ast.unparse(tree) + "\n"))
    return mutants


def mutants(case: cases.Case, limit: int = DEFAULT_MUTANTS) -> list[Mutant]:
    """Choose up to ``limit`` mutants in a stable order seeded only by the case id."""
    if limit < 0:
        raise ValueError("mutant limit must not be negative")
    candidates = []
    for path in sorted(case.solution_dir.rglob("*.py"),
                       key=lambda p: p.relative_to(case.solution_dir).as_posix()):
        relative = path.relative_to(case.solution_dir).as_posix()
        base_path = case.repo_dir / relative
        base_source = base_path.read_text(encoding="utf-8") if base_path.is_file() else None
        source = path.read_text(encoding="utf-8")
        if base_source == source:
            continue
        candidates.extend(file_mutants(relative, source, base_source))
    seed = int.from_bytes(hashlib.sha256(case.id.encode("utf-8")).digest(), "big")
    random.Random(seed).shuffle(candidates)
    return candidates[:limit]
