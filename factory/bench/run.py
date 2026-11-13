"""Run bench cases in isolated cells and record their scores.

A variant is a flow, optionally with one model overriding every agent step. Every
(variant, case, repeat) cell is a factory home of its own: the case repository,
pipeline worktree, database, logs and transcripts all live below the run directory.
Preflight checks finish before a run directory is created, and each cell gets only
the budget left after the cells already recorded.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import importlib.metadata
import json
import os
import re
import shlex
import sys
import tempfile
import time
from dataclasses import dataclass, replace
from pathlib import Path

from .. import config as C
from .. import prices
from .. import sandbox as S
from ..agents import (LangChainRoles, PROVIDER_KEYS, flow_models, load_step, missing_keys,
                      step_limit, step_model, step_prompt_source)
from ..db import now, open_db
from ..flows import Flow
from ..log import RunLog, clip, log_path
from ..observe import human_secs
from ..pipeline import Options, Pipeline, PipelineError, create_worktree, git
from . import cases, report


class BenchError(RuntimeError):
    pass


@dataclass(frozen=True)
class Variant:
    id: str
    flow: Flow
    model: str | None


def _validate_args(a) -> None:
    if a.max_cost is None and not a.dry_run:
        raise BenchError("--max-cost is required (or pass --dry-run)")
    if a.repeat < 1:
        raise BenchError("--repeat must be at least 1")
    if a.max_attempts < 1:
        raise BenchError("--max-attempts must be at least 1")


def select_variants(cfg: C.Config, flow_names=None, model_specs=None) -> list[Variant]:
    """The flag-ordered product of flows and model overrides, with duplicate variants removed."""
    names = list(dict.fromkeys(flow_names or [cfg.flow]))
    flows = []
    for name in names:
        flow = cfg.flows.get(name)
        if flow is None:
            raise BenchError(f"unknown flow {name} (flows: {', '.join(sorted(cfg.flows))})")
        flows.append(flow)
    specs = list(dict.fromkeys(model_specs)) if model_specs else [None]
    return [Variant(f"{flow.name}@{spec}" if spec is not None else flow.name, flow, spec)
            for flow in flows for spec in specs]


def select_cases(dirs=None, ids=None) -> list[cases.Case]:
    """Load a suite and select its cases by id, keeping the suite's sorted order."""
    try:
        found = cases.load_cases(dirs)
    except cases.CaseError as e:
        raise BenchError(str(e)) from None
    where = ", ".join(map(str, dirs)) if dirs else "the shipped suite"
    if not found:
        raise BenchError(f"no cases found under {where}")
    if ids:
        known = {case.id for case in found}
        for case_id in dict.fromkeys(ids):
            if case_id not in known:
                raise BenchError(f"unknown case {case_id} (cases: {', '.join(sorted(known))})")
        wanted = set(ids)
        found = [case for case in found if case.id in wanted]
    return found


def overlay(case_cfg: C.Config, repo_cfg: C.Config) -> C.Config:
    """The case's gates and isolation, with the invoking repository's agent setup laid over it."""
    return replace(case_cfg, flow=repo_cfg.flow, flows=repo_cfg.flows,
                   models=repo_cfg.models, max_steps=repo_cfg.max_steps)


def _private_files(case: cases.Case) -> list[Path]:
    return sorted((path for source in (case.hidden_dir, case.solution_dir)
                   for path in source.rglob("*") if path.is_file()), key=lambda path: str(path))


def _check_dependency_sources(case: cases.Case) -> None:
    sources = [(raw, raw.resolve()) for raw in case.cfg.dependency_dirs()]
    for path in _private_files(case):
        resolved = path.resolve()
        for raw, source in sources:
            if source == resolved or source in resolved.parents:
                rel = path.relative_to(case.dir).as_posix()
                raise BenchError(f"{case.id}: {rel} is readable through dependency_sources ({raw})")


def _probe_case(case: cases.Case, sandbox_on: bool) -> None:
    """Check required executables and hidden-file visibility in a disposable sandbox."""
    with tempfile.TemporaryDirectory(prefix=f"factory-bench-probe-{case.id}-") as tmp:
        scratch = Path(tmp)
        box = S.make(scratch, scratch / "cache", sandbox=sandbox_on, cfg=case.cfg.sandbox)
        for command in case.requires:
            result = box.run(f"command -v {shlex.quote(command)} >/dev/null 2>&1")
            if result.code != 0:
                raise BenchError(f"{case.id}: requires {command!r}, which is missing from its sandbox")
        _check_dependency_sources(case)
        if not sandbox_on:
            return
        probes = []
        for path in _private_files(case):
            quoted = shlex.quote(str(path.resolve()))
            probes.append(f"[ ! -r {quoted} ] || printf '%s\\n' {quoted}")
        result = box.run("; ".join(probes))
        readable = [line.strip() for line in result.output.splitlines() if line.strip()]
        if readable:
            raise BenchError(f"{case.id}: its hidden files are readable inside the sandbox: "
                             + ", ".join(readable))


def preflight(root: Path, cfg: C.Config, variants: list[Variant], selected: list[cases.Case], a) -> dict:
    """Refuse an unsafe or unstartable run before creating anything below $FACTORY_HOME.

    Returns each variant's resolved step models for dry-run output and results metadata.
    """
    _validate_args(a)
    if not a.no_sandbox and not S.available():
        raise BenchError("bubblewrap (bwrap) is required; install it or pass --no-sandbox")

    # Model resolution depends only on the overlaid agent settings, which are the same for
    # every case. Keep the per-variant mapping so dry-run names each flow step, not just roles.
    setup_cfg = overlay(selected[0].cfg, cfg)
    models = {variant.id: flow_models(root, variant.flow, setup_cfg, variant.model) for variant in variants}
    all_models = {f"{variant_id}/{step}": spec
                  for variant_id, steps in models.items() for step, spec in steps.items()}
    missing = missing_keys(all_models, os.environ)
    if missing:
        detail = ", ".join(f"{step}={spec}" for step, spec in all_models.items())
        raise BenchError(f"set {', '.join(missing)} first (models: {detail})")

    for case in selected:
        _probe_case(case, not a.no_sandbox)

    if not a.dry_run and a.max_cost is not None:
        for spec in dict.fromkeys(all_models.values()):
            if prices.per_token(spec) is None:
                print(f"warning: no price known for {spec}; --max-cost cannot limit it", file=sys.stderr)
    return models


def fixture_sha(case: cases.Case) -> str:
    digest = hashlib.sha256()
    files = sorted((path for path in case.dir.rglob("*") if path.is_file()),
                   key=lambda path: path.relative_to(case.dir).as_posix())
    for path in files:
        rel = path.relative_to(case.dir).as_posix()
        digest.update(rel.encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


def variant_steps(root: Path, cfg: C.Config, variant: Variant) -> list[dict]:
    steps = []
    for step in variant.flow.steps:
        if step.kind == "gates":
            continue
        meta = load_step(root, step)[0]
        steps.append({
            "name": step.name,
            "kind": step.kind,
            "model": step_model(root, step, cfg, variant.model),
            "max_steps": step_limit(step, cfg, meta),
            "prompt_sha": hashlib.sha256(step_prompt_source(root, step).read_bytes()).hexdigest(),
        })
    return steps


def write_results(run_dir: Path, results: dict) -> None:
    """Atomically replace results.json; a separate seam also makes persistence observable in tests."""
    run_dir = Path(run_dir)
    tmp = run_dir / ".results.json.tmp"
    tmp.write_text(json.dumps(results, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    os.replace(tmp, run_dir / "results.json")


def _factory_version() -> str:
    try:
        return importlib.metadata.version("software-factory")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def _relative_cell_dir(variant: Variant, case: cases.Case, repeat: int) -> Path:
    return Path("cells") / variant.id.replace("/", "_") / case.id / str(repeat)


def _empty_cell(variant: Variant, case: cases.Case, repeat: int, directory: Path) -> dict:
    return {
        "variant": variant.id,
        "case": case.id,
        "repeat": repeat,
        "outcome": "error",
        "attempts": 0,
        "cost_usd": 0.0,
        "seconds": 0.0,
        "model_calls": 0,
        "tokens_in": 0,
        "tokens_out": 0,
        "review_changes": 0,
        "step_limit_stops": 0,
        "failed_gates": [],
        "dir": directory.as_posix(),
        "error": None,
    }


def _record_metrics(cell: dict, db, task_id: str) -> None:
    row = db.task(task_id)
    runs = db.runs(task_id)
    if row is not None:
        cell["attempts"] = row["attempts"]
        cell["cost_usd"] = row["cost_usd"]
    cell["model_calls"] = sum(run["steps"] or 0 for run in runs)
    cell["tokens_in"] = sum(run["tokens_in"] or 0 for run in runs)
    cell["tokens_out"] = sum(run["tokens_out"] or 0 for run in runs)
    cell["review_changes"] = sum(run["role"] == "review" and run["outcome"] == "CHANGES" for run in runs)
    cell["step_limit_stops"] = sum("(step limit)" in (run["outcome"] or "") for run in runs)
    gates = [run for run in runs if run["step"] == "gates"]
    cell["failed_gates"] = re.findall(r"\| (\S+) \| FAIL \|", gates[-1]["report"] or "") if gates else []


def _write_hidden_log(path: Path, score: cases.HiddenScore) -> None:
    blocks = []
    for result in score.commands:
        blocks.append(f"$ {result.cmd}\n[{result.outcome}]\n{result.output.rstrip()}\n")
    path.write_text("\n".join(blocks), encoding="utf-8")


def run_cell(root: Path, repo_cfg: C.Config, case: cases.Case, variant: Variant, repeat: int,
             cell_dir: Path, a, remaining: float) -> dict:
    """Run and score one cell, converting every pipeline ending to a bench outcome."""
    started = time.monotonic()
    cell = _empty_cell(variant, case, repeat, _relative_cell_dir(variant, case, repeat))
    db = log = None
    interrupted = False
    try:
        cell_dir.mkdir(parents=True, exist_ok=False)
        cfg = overlay(case.cfg, repo_cfg)
        base = cases.materialize(case, cell_dir / "repo")
        # A cell must be able to commit even on a host with no global git identity. These local
        # settings do not affect the already-created, deterministic base commit.
        git(cell_dir / "repo", "config", "user.name", "Factory Bench")
        git(cell_dir / "repo", "config", "user.email", "bench@factory.invalid")

        db = open_db(cell_dir)
        task = case.contract
        db.upsert_task(task)
        db.update(task.id, status="queued", branch=f"factory/{task.id}", base_ref="main", base_sha=base,
                  trunk="main", stacked_on=None, candidate_sha=None, pr_url=None, attempts=0,
                  note=None, progress=None)
        db.claim(task.id, os.getpid())
        wt, base_sha = create_worktree(cell_dir / "repo", cell_dir, task.id, "main")
        box = S.make(wt, cell_dir / "cache", sandbox=not a.no_sandbox, network=False, cfg=cfg.sandbox)
        opts = Options(base_ref="main", max_attempts=a.max_attempts, open_pr=False, skip_gates=(),
                       full_e2e=False, max_cost=remaining, config=cfg, flow=variant.flow)
        log = RunLog(log_path(cell_dir, task.id), echo=False)
        log("run", f"=== bench {variant.id} · {case.id} #{repeat}: worktree {wt} from {base_sha[:12]}")
        state = Pipeline(db, LangChainRoles(root, variant.model, cfg=cfg), task, wt, base_sha, box, opts,
                         log=log, transcript_dir=cell_dir / "transcripts" / task.id).run()
        outcome = state.get("outcome")
        if outcome == "verified":
            row = db.task(task.id)
            sha = row["candidate_sha"] if row is not None else None
            if not sha:
                raise RuntimeError("verified pipeline has no candidate commit")
            score = cases.score_hidden(
                case, cell_dir / "repo", sha,
                lambda worktree: S.make(worktree, cell_dir / "cache", sandbox=not a.no_sandbox, cfg=cfg.sandbox))
            _write_hidden_log(cell_dir / "hidden.log", score)
            cell["outcome"] = "solved" if score.passed else "false_pass"
        elif outcome == "failed":
            cell["outcome"] = "failed"
        else:
            cell["outcome"] = "error"
            cell["error"] = f"pipeline ended with unexpected outcome {outcome!r}"
    except KeyboardInterrupt:
        cell["outcome"] = "error"
        cell["error"] = "interrupted"
        interrupted = True
    except PipelineError as e:
        stopped = "cost limit exceeded" in str(e)
        cell["outcome"] = "stopped" if stopped else "error"
        cell["error"] = str(e)
    except Exception as e:
        cell["outcome"] = "error"
        cell["error"] = f"{type(e).__name__}: {e}"
    finally:
        if log is not None:
            log.close()
        if db is not None:
            try:
                _record_metrics(cell, db, case.contract.id)
            finally:
                db.close()
        cell["seconds"] = max(0.0, time.monotonic() - started)
    if interrupted:
        cell["_interrupted"] = True
    return cell


def _dry_run(variants: list[Variant], selected: list[cases.Case], repeat: int, models: dict) -> None:
    total = len(variants) * len(selected) * repeat
    index = 0
    for variant in variants:
        for case in selected:
            for iteration in range(1, repeat + 1):
                index += 1
                print(f"[{index}/{total}] {variant.id} · {case.id} #{iteration}")
    for variant in variants:
        steps = " · ".join(f"{step} {spec}" for step, spec in models[variant.id].items())
        print(f"{variant.id}: {steps}")
        keys = sorted({PROVIDER_KEYS.get(spec.split(":", 1)[0])
                       for spec in models[variant.id].values()} - {None})
        print(f"  keys: {', '.join(keys) if keys else '(none)'}")


def _new_run_dir(home: Path) -> tuple[dt.datetime, Path]:
    bench_dir = home / "bench"
    bench_dir.mkdir(parents=True, exist_ok=True)
    while True:
        started = dt.datetime.now(dt.timezone.utc)
        run_dir = bench_dir / started.strftime("%Y%m%d-%H%M%S")
        try:
            run_dir.mkdir()
            return started, run_dir
        except FileExistsError:
            time.sleep(0.05)


def _cell_line(index: int, total: int, cell: dict) -> str:
    prefix = f"[{index}/{total}] {cell['variant']} · {cell['case']} #{cell['repeat']}: {cell['outcome']}"
    if cell["outcome"] == "skipped":
        return prefix + " (budget spent)"
    cost = f"${cell['cost_usd']:.2f}" if cell["cost_usd"] is not None else "cost unknown"
    line = (prefix + f" in {cell['attempts']} attempt{'s' if cell['attempts'] != 1 else ''}, "
            f"{cost}, {human_secs(cell['seconds'])}")
    if cell["outcome"] in ("error", "stopped") and cell.get("error"):
        line += f" ({clip(cell['error'], 200)})"
    return line


def bench(a, root: Path, home: Path) -> int:
    """The `factory bench run` command body; cli translates BenchError to a refusal."""
    try:
        repo_cfg = C.load(root)
    except C.ConfigError as e:
        raise BenchError(f"{C.CONFIG_PATH}: {e}") from None
    _validate_args(a)                    # budget and numeric flags precede every other check
    variants = select_variants(repo_cfg, a.flow, a.model)
    selected = select_cases([a.cases] if a.cases else None, a.case)
    models = preflight(root, repo_cfg, variants, selected, a)
    if a.dry_run:
        _dry_run(variants, selected, a.repeat, models)
        return 0

    started, run_dir = _new_run_dir(Path(home))
    run_id = run_dir.name
    case_records = {}
    for case in selected:
        with tempfile.TemporaryDirectory(prefix=f"factory-bench-base-{case.id}-") as tmp:
            base = cases.materialize(case, Path(tmp) / "repo")
        case_records[case.id] = {"kind": case.kind, "base": base, "fixture_sha": fixture_sha(case)}
    setup_cfg = overlay(selected[0].cfg, repo_cfg)
    results = {
        "run": {
            "id": run_id,
            "started_at": started.isoformat(timespec="seconds"),
            "ended_at": None,
            "factory": _factory_version(),
            "sandbox": not a.no_sandbox,
            "max_cost": a.max_cost,
            "max_attempts": a.max_attempts,
            "repeat": a.repeat,
        },
        "cases": case_records,
        "variants": {
            variant.id: {"flow": variant.flow.name, "model": variant.model,
                         "steps": variant_steps(root, setup_cfg, variant)}
            for variant in variants
        },
        "cells": [],
    }
    write_results(run_dir, results)
    total = len(variants) * len(selected) * a.repeat
    print(f"bench {run_id}: {len(selected)} case(s) × {len(variants)} variant(s) × {a.repeat} = "
          f"{total} cells, budget ${a.max_cost:.2f}")

    index = 0
    for variant in variants:
        for case in selected:
            for iteration in range(1, a.repeat + 1):
                index += 1
                relative = _relative_cell_dir(variant, case, iteration)
                spent = sum(cell["cost_usd"] or 0.0 for cell in results["cells"])
                if spent >= a.max_cost:
                    cell = _empty_cell(variant, case, iteration, relative)
                    cell["outcome"] = "skipped"
                    cell["seconds"] = 0.0
                else:
                    cell = run_cell(root, repo_cfg, case, variant, iteration, run_dir / relative, a,
                                    max(0.0, a.max_cost - spent))
                interrupted = cell.pop("_interrupted", False)
                results["cells"].append(cell)
                write_results(run_dir, results)
                print(_cell_line(index, total, cell), flush=True)
                if interrupted:
                    results["run"]["ended_at"] = now()
                    write_results(run_dir, results)
                    print(report.tables(results))
                    return 1

    results["run"]["ended_at"] = now()
    write_results(run_dir, results)
    print(report.tables(results))
    return 1 if any(cell["outcome"] in ("error", "stopped", "skipped") for cell in results["cells"]) else 0
