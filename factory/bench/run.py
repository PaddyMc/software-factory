"""Run benchmark cases in isolated factory homes and record their scores.

A cell is a normal pipeline run with PR creation disabled. Only the cell's own
repository and database are opened for writing; prompts and flow/model settings
are resolved from the repository that invoked the bench.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import hashlib
import importlib.metadata
import json
import os
import re
import shlex
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .. import agents, factory_home, observe, prices
from .. import config as C
from .. import sandbox as S
from ..db import open_db
from ..flows import Flow
from ..log import RunLog, log_path
from ..pipeline import Options, Pipeline, PipelineError, Stopped, create_worktree
from . import cases, report


POLL_SECONDS = 0.5


class BenchError(RuntimeError):
    """A bench request that must be refused before any cells start."""


@dataclass(frozen=True)
class Variant:
    id: str
    flow_name: str
    flow: Flow
    model: str | None


@dataclass(frozen=True)
class Cell:
    variant: Variant
    case: cases.Case
    number: int
    directory: Path
    cost_limit: float
    index: int


def cell_argv(cell: Cell, *, cases_dir: str | None, max_attempts: int,
              sandbox_on: bool) -> list[str]:
    """Describe the one-cell child invocation, with no cwd-dependent paths."""
    argv = ["--case", cell.case.id]
    if cases_dir:
        argv += ["--cases", str(Path(cases_dir).resolve())]
    argv += ["--flow", cell.variant.flow_name]
    if cell.variant.model is not None:
        argv += ["--model", cell.variant.model]
    argv += ["--dir", str(cell.directory.resolve()), "--max-attempts", str(max_attempts),
             "--cost-limit", f"{cell.cost_limit:.6f}"]
    if not sandbox_on:
        argv.append("--no-sandbox")
    return argv


def default_launch(root: Path, *, cases_dir: str | None, max_attempts: int,
                   sandbox_on: bool) -> Callable[[Cell], subprocess.Popen]:
    """Start quiet one-cell children in their own sessions, like plan task runs."""
    def launch(cell: Cell) -> subprocess.Popen:
        argv = cell_argv(cell, cases_dir=cases_dir, max_attempts=max_attempts, sandbox_on=sandbox_on)
        return subprocess.Popen([sys.executable, "-m", "factory.bench.run", *argv],
                                cwd=root, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.PIPE, start_new_session=True, text=True)
    return launch


def variants(cfg: C.Config, flow_names: list[str] | None = None,
             models: list[str] | None = None) -> list[Variant]:
    """Resolve flows × model overrides; repeated identical flags name one variant."""
    names = list(dict.fromkeys(flow_names or [cfg.flow]))
    overrides = list(dict.fromkeys(models)) if models else [None]
    out = []
    for name in names:
        flow = cfg.flows.get(name)
        if flow is None:
            raise BenchError(f"unknown flow {name} (flows: {', '.join(sorted(cfg.flows))})")
        for model in overrides:
            out.append(Variant(f"{name}@{model}" if model is not None else name, name, flow, model))
    return out


def fixture_sha(case: cases.Case) -> str:
    """Hash every fixture file, with its relative path, in deterministic order."""
    digest = hashlib.sha256()
    files = sorted((p for p in case.dir.rglob("*") if p.is_file()),
                   key=lambda p: p.relative_to(case.dir).as_posix())
    for path in files:
        digest.update(path.relative_to(case.dir).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def variant_steps(root: Path, flow: Flow, cfg: C.Config, model_override: str | None = None) -> list[dict]:
    """Describe the resolved agent steps.

    ``prompt_sha`` is SHA-256 of the whole resolved prompt file, including its
    frontmatter. Thus it changes exactly when the prompt text loaded by
    ``factory run`` changes, whether shipped or overridden by the invoking repo.
    """
    steps = []
    for step in flow.steps:
        if step.kind == "gates":
            continue
        meta, _ = agents.load_step(root, step)
        prompt = agents.step_prompt_source(root, step).read_text(encoding="utf-8")
        steps.append({
            "name": step.name,
            "kind": step.kind,
            "model": agents.step_model(root, step, cfg, model_override),
            "max_steps": agents.step_limit(step, cfg, meta),
            "prompt_sha": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            "loop": list(step.loop),
            "prove": step.prove,
        })
    return steps


def _model_entries(root: Path, cfg: C.Config, selected: list[Variant]) -> list[tuple[str, str]]:
    return [(f"{variant.id}.{step}", spec)
            for variant in selected
            for step, spec in agents.flow_models(root, variant.flow, cfg, variant.model).items()]


def _provider_keys(root: Path, cfg: C.Config, variant: Variant) -> list[str]:
    models = agents.flow_models(root, variant.flow, cfg, variant.model)
    return sorted({key for spec in models.values()
                   if (key := agents.PROVIDER_KEYS.get(spec.split(":", 1)[0]))})


def _inside(path: Path, directory: Path) -> bool:
    try:
        path.resolve().relative_to(directory.resolve())
        return True
    except ValueError:
        return False


def _check_requires(case: cases.Case, sandbox_on: bool) -> None:
    with tempfile.TemporaryDirectory(prefix=f"factory-bench-requires-{case.id}-") as scratch:
        worktree = Path(scratch)
        box = S.make(worktree, worktree / "cache", sandbox=sandbox_on, cfg=case.cfg.sandbox)
        for command in case.requires:
            result = box.run(f"command -v {shlex.quote(command)}")
            if result.code != 0:
                raise BenchError(f"{case.id}: required command {command!r} is missing from its sandbox")


def _check_dependency_sources(case: cases.Case) -> None:
    for source in case.cfg.dependency_dirs():
        if any(_inside(directory, source) for directory in (case.hidden_dir, case.solution_dir)):
            raise BenchError(f"{case.id}: hidden/solution files readable under its dependency_sources: {source}")


def _check_hidden_files(case: cases.Case) -> None:
    files = sorted((p for directory in (case.hidden_dir, case.solution_dir)
                    for p in directory.rglob("*") if p.is_file()), key=lambda p: str(p))
    quoted = " ".join(shlex.quote(str(path)) for path in files)
    command = (f"for f in {quoted}; do "
               "cat -- \"$f\" >/dev/null 2>&1 && printf '%s\\n' \"$f\"; done; true")
    with tempfile.TemporaryDirectory(prefix=f"factory-bench-hidden-{case.id}-") as scratch:
        worktree = Path(scratch)
        box = S.make(worktree, worktree / "cache", sandbox=True, cfg=case.cfg.sandbox)
        result = box.run(command)
    if result.code != 0:
        raise BenchError(f"{case.id}: cannot inspect hidden/solution files inside its sandbox: "
                         f"{result.output.strip()}")
    readable = result.output.strip().splitlines()
    if readable:
        raise BenchError(f"{case.id}: hidden/solution files readable inside its sandbox: "
                         f"{', '.join(readable)}")


def _check_test_paths(selected_cases: list[cases.Case], selected_variants: list[Variant]) -> None:
    """A test step needs each case's writable test paths, before any cell is started."""
    tested_flows = list(dict.fromkeys(
        variant.flow_name for variant in selected_variants
        if any(step.kind == "test" for step in variant.flow.steps)
    ))
    for case in selected_cases:
        if case.cfg.test_paths:
            continue
        for flow in tested_flows:
            raise BenchError(f"{case.id}: flow {flow} has a test step: set test_paths in the case's config")


def preflight(root: Path, cfg: C.Config, selected_cases: list[cases.Case],
              selected_variants: list[Variant], sandbox_on: bool) -> None:
    """Refuse unsafe or un-runnable benches before creating their run directory."""
    _check_test_paths(selected_cases, selected_variants)
    entries = _model_entries(root, cfg, selected_variants)
    missing = agents.missing_keys(dict(entries), os.environ)
    if missing:
        models = ", ".join(f"{step}={spec}" for step, spec in entries)
        raise BenchError(f"set {', '.join(missing)} first (models: {models})")
    if sandbox_on and not S.available():
        raise BenchError("bubblewrap (bwrap) is required; install it or pass --no-sandbox")
    for case in selected_cases:
        _check_requires(case, sandbox_on)
        _check_dependency_sources(case)
    if sandbox_on:
        for case in selected_cases:
            _check_hidden_files(case)


def _warn_unpriced(root: Path, cfg: C.Config, selected: list[Variant]) -> None:
    specs = dict.fromkeys(spec for _, spec in _model_entries(root, cfg, selected))
    for spec in specs:
        if prices.per_token(spec) is None:
            print(f"warning: no price for {spec}; --max-cost cannot limit it", file=sys.stderr)


def _version() -> str:
    try:
        return importlib.metadata.version("software-factory")
    except importlib.metadata.PackageNotFoundError:
        return "0.1.0"


def write_results(run_dir: Path, results: dict) -> None:
    """Atomically replace results.json, preserving every completed cell."""
    run_dir = Path(run_dir)
    tmp = run_dir / ".results.json.tmp"
    tmp.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, run_dir / "results.json")


def _relative_cell_dir(directory: Path) -> str:
    for parent in directory.parents:
        if parent.name == "cells":
            return directory.relative_to(parent.parent).as_posix()
    return directory.as_posix()


def _directory_repeat(directory: Path) -> int:
    suffix = directory.name.removeprefix("r")
    return int(suffix) if suffix.isdigit() else 1


def _empty_record(variant: Variant, case: cases.Case, repeat: int, outcome: str,
                  directory: Path | None, seconds: float = 0.0) -> dict:
    return {
        "variant": variant.id,
        "case": case.id,
        "repeat": repeat,
        "outcome": outcome,
        "attempts": 0,
        "cost_usd": 0.0,
        "seconds": round(seconds, 3),
        "model_calls": 0,
        "tokens_in": 0,
        "tokens_out": 0,
        "review_changes": 0,
        "step_limit_stops": 0,
        "failed_gates": [],
        "dir": _relative_cell_dir(directory) if directory is not None else None,
    }


def _record_from_db(db, variant: Variant, case: cases.Case, repeat: int, outcome: str,
                    directory: Path, started: float) -> dict:
    record = _empty_record(variant, case, repeat, outcome, directory, time.monotonic() - started)
    if db is None:
        return record
    row = db.task(case.contract.id)
    if row is None:
        return record
    runs = db.runs(case.contract.id)
    record.update({
        "attempts": row["attempts"] or 0,
        "cost_usd": float(row["cost_usd"] or 0.0),
        "model_calls": sum(run["steps"] or 0 for run in runs),
        "tokens_in": sum(run["tokens_in"] or 0 for run in runs),
        "tokens_out": sum(run["tokens_out"] or 0 for run in runs),
        "review_changes": sum(run["role"] == "review" and run["outcome"] == "CHANGES" for run in runs),
        "step_limit_stops": sum("step limit" in (run["outcome"] or "") for run in runs),
    })
    gate_runs = [run for run in runs if run["step"] == "gates"]
    if gate_runs:
        record["failed_gates"] = re.findall(r"^\| (\S+) \| FAIL \|", gate_runs[-1]["report"] or "", re.M)
    return record


def _recover_record(directory: Path, variant: Variant, case: cases.Case, repeat: int,
                    started: float) -> dict:
    db = None
    try:
        if (directory / "factory.db").is_file():
            db = open_db(directory)
        return _record_from_db(db, variant, case, repeat, "error", directory, started)
    except Exception:
        return _empty_record(variant, case, repeat, "error", directory, time.monotonic() - started)
    finally:
        if db is not None:
            db.close()


def _hidden_log(score: cases.HiddenScore) -> str:
    chunks = []
    for command in score.commands:
        output = command.output.rstrip()
        chunks.append(f"$ {command.cmd}\n{command.outcome}\n{output}\n")
    chunks.append(f"hidden: {'PASS' if score.passed else 'FAIL'}\n")
    return "\n".join(chunks)


def run_cell(root: Path, case: cases.Case, variant: Variant, directory: Path, *,
             max_attempts: int, max_cost: float, sandbox_on: bool) -> dict:
    """Materialize and score one cell, returning its JSON-serializable record."""
    root, directory = Path(root), Path(directory)
    started = time.monotonic()
    task = case.contract
    db = log = None
    previous_sigterm = None
    interrupted = None
    outcome = "error"
    try:
        directory.mkdir(parents=True, exist_ok=False)
        base = cases.materialize(case, directory / "repo")
        invoking_cfg = C.load(root)
        cell_cfg = dataclasses.replace(
            case.cfg, flow=variant.flow.name, flows=invoking_cfg.flows,
            models=invoking_cfg.models, max_steps=invoking_cfg.max_steps,
        )
        db = open_db(directory)
        db.upsert_task(task)
        db.update(task.id, status="queued", branch=f"factory/{task.id}", base_ref="main", base_sha=base,
                  trunk="main", stacked_on=None, candidate_sha=None, pr_url=None,
                  attempts=0, note=None, progress=None)
        db.claim(task.id, os.getpid())
        wt, base = create_worktree(directory / "repo", directory, task.id, "main")
        box = S.make(wt, directory / "cache", sandbox=sandbox_on, cfg=case.cfg.sandbox)
        opts = Options(base_ref="main", max_attempts=max_attempts, open_pr=False,
                       max_cost=max_cost, config=cell_cfg, flow=variant.flow)
        log = RunLog(log_path(directory, task.id), echo=False)

        def _stopped(signum, frame):
            raise Stopped("stopped by factory stop")

        previous_sigterm = signal.signal(signal.SIGTERM, _stopped)
        result = Pipeline(db, agents.LangChainRoles(root, variant.model, cfg=cell_cfg), task, wt, base, box,
                          opts, log=log, transcript_dir=directory / "transcripts" / task.id).run()
        if result.get("outcome") == "verified":
            candidate = db.task(task.id)["candidate_sha"]
            score = cases.score_hidden(
                case, directory / "repo", candidate,
                lambda hidden_wt: S.make(hidden_wt, directory / "cache", sandbox=sandbox_on,
                                         cfg=case.cfg.sandbox),
            )
            (directory / "hidden.log").write_text(_hidden_log(score), encoding="utf-8")
            outcome = "solved" if score.passed else "false_pass"
        elif result.get("outcome") == "failed":
            outcome = "failed"
    except PipelineError as e:
        outcome = "stopped" if "cost limit exceeded" in str(e) else "error"
    except (KeyboardInterrupt, Stopped) as e:
        interrupted = e
    except Exception:
        outcome = "error"
    finally:
        if previous_sigterm is not None:
            signal.signal(signal.SIGTERM, previous_sigterm)
        if log is not None:
            log.close()
        try:
            record = _record_from_db(db, variant, case, repeat=_directory_repeat(directory), outcome=outcome,
                                     directory=directory, started=started)
        finally:
            if db is not None:
                db.close()
    if interrupted is not None:
        interrupted.bench_record = record
        raise interrupted
    return record


def _write_cell_record(directory: Path, record: dict) -> None:
    """Publish a child's result only after its complete JSON is on disk."""
    directory.mkdir(parents=True, exist_ok=True)
    tmp = directory / ".cell.json.tmp"
    tmp.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, directory / "cell.json")


def cell_main(argv: list[str]) -> int:
    """Run exactly one cell in a child process and leave its record in cell.json."""
    parser = argparse.ArgumentParser(prog="factory.bench.run")
    parser.add_argument("--case", required=True, metavar="ID")
    parser.add_argument("--cases", metavar="DIR")
    parser.add_argument("--flow", required=True, metavar="NAME")
    parser.add_argument("--model", metavar="SPEC")
    parser.add_argument("--dir", required=True, metavar="DIR")
    parser.add_argument("--max-attempts", type=int, default=3, metavar="N")
    parser.add_argument("--cost-limit", type=float, required=True, metavar="USD")
    parser.add_argument("--no-sandbox", action="store_true")
    try:
        args = parser.parse_args(argv)
    except SystemExit as e:
        return 0 if e.code == 0 else 1

    try:
        root = Path.cwd()
        cfg = C.load(root)
        variant = variants(cfg, [args.flow], [args.model] if args.model is not None else None)[0]
        loaded = cases.load_cases([args.cases] if args.cases else None)
        case = next((case for case in loaded if case.id == args.case), None)
        if case is None:
            raise BenchError(f"unknown case {args.case} (cases: {', '.join(sorted(c.id for c in loaded))})")
        directory = Path(args.dir)
        record = run_cell(root, case, variant, directory, max_attempts=args.max_attempts,
                          max_cost=args.cost_limit, sandbox_on=not args.no_sandbox)
    except (KeyboardInterrupt, Stopped) as e:
        record = getattr(e, "bench_record", None)
        if record is None:
            print(f"bench cell interrupted: {e}", file=sys.stderr)
            return 1
    except Exception as e:
        print(f"bench cell: {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    try:
        _write_cell_record(directory, record)
    except Exception as e:
        print(f"bench cell: cannot write cell.json: {e}", file=sys.stderr)
        return 1
    return 0


def _materialized_base(directory: Path) -> str | None:
    repo = directory / "repo"
    if not repo.is_dir():
        return None
    proc = subprocess.run(["git", "rev-parse", "main"], cwd=repo, capture_output=True, text=True)
    return proc.stdout.strip() if proc.returncode == 0 else None


def _slug(variant_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9._@-]", "_", variant_id)


def _dry_run(root: Path, cfg: C.Config, selected_cases: list[cases.Case],
             selected_variants: list[Variant], repeat: int) -> int:
    count = len(selected_cases) * len(selected_variants) * repeat
    print(f"bench dry-run: {len(selected_cases)} cases × {len(selected_variants)} variants × "
          f"{repeat} = {count} cells")
    for variant in selected_variants:
        print(f"variant {variant.id}")
        for step in variant_steps(root, variant.flow, cfg, variant.model):
            print(f"  {step['name']} ({step['kind']}): {step['model']}, max {step['max_steps']} steps")
        keys = _provider_keys(root, cfg, variant)
        print(f"  keys: {', '.join(keys) if keys else '(none)'}")
    print("cells:")
    for variant in selected_variants:
        for case in selected_cases:
            for number in range(1, repeat + 1):
                print(f"{variant.id} · {case.id} #{number}")
    return 0


def _cell_line(index: int, total: int, record: dict, suffix: str = "") -> None:
    attempts = f"{record['attempts']} attempt" + ("" if record["attempts"] == 1 else "s")
    print(f"[{index}/{total}] {record['variant']} · {record['case']} #{record['repeat']}: "
          f"{record['outcome']} in {attempts}, ${record['cost_usd'] or 0.0:.2f}, "
          f"{observe.human_secs(record['seconds'])}{suffix}", flush=True)


def _run_sequential(root: Path, run_dir: Path, results: dict, selected_cases: list[cases.Case],
                    selected_variants: list[Variant], repeat: int, total: int, max_cost: float,
                    max_attempts: int, sandbox_on: bool) -> None:
    spent = 0.0
    index = 0
    interrupted = False
    for variant in selected_variants:
        if interrupted:
            break
        for case in selected_cases:
            if interrupted:
                break
            for number in range(1, repeat + 1):
                index += 1
                if spent >= max_cost:
                    record = _empty_record(variant, case, number, "skipped", None)
                else:
                    relative = Path("cells") / _slug(variant.id) / case.id / f"r{number}"
                    directory = run_dir / relative
                    cell_started = time.monotonic()
                    try:
                        record = run_cell(root, case, variant, directory, max_attempts=max_attempts,
                                          max_cost=max_cost - spent, sandbox_on=sandbox_on)
                    except (KeyboardInterrupt, Stopped) as e:
                        record = getattr(e, "bench_record", None) or _recover_record(
                            directory, variant, case, number, cell_started)
                        record["repeat"] = number
                        interrupted = True
                    except Exception:
                        record = _recover_record(directory, variant, case, number, cell_started)
                    if results["cases"][case.id]["base"] is None:
                        results["cases"][case.id]["base"] = _materialized_base(directory)
                    spent += float(record["cost_usd"] or 0.0)
                results["cells"].append(record)
                write_results(run_dir, results)
                _cell_line(index, total, record)
                if interrupted:
                    break


def _running_cost(directory: Path, task_id: str) -> float:
    """Best-effort live cost; an unreadable/incomplete cell db simply counts as zero."""
    db = None
    try:
        if not (directory / "factory.db").is_file():
            return 0.0
        db = open_db(directory, readonly=True)
        row = db.task(task_id)
        return float(row["cost_usd"] or 0.0) if row is not None else 0.0
    except (OSError, sqlite3.Error):
        return 0.0
    finally:
        if db is not None:
            db.close()


def _child_record(cell: Cell) -> dict:
    record = json.loads((cell.directory / "cell.json").read_text(encoding="utf-8"))
    if not isinstance(record, dict):
        raise ValueError("cell.json is not a mapping")
    record.update(variant=cell.variant.id, case=cell.case.id, repeat=cell.number)
    return record


def _crash_record(proc: subprocess.Popen, cell: Cell, started: float) -> dict:
    record = _recover_record(cell.directory, cell.variant, cell.case, cell.number, started)
    cell.directory.mkdir(parents=True, exist_ok=True)
    stderr = proc.stderr.read() if proc.stderr is not None else ""
    tail = "\n".join(stderr.splitlines()[-10:])
    text = f"child exited with status {proc.returncode}\n"
    if tail:
        text += f"stderr (last 10 lines):\n{tail}\n"
    (cell.directory / "crash.log").write_text(text, encoding="utf-8")
    return record


def _run_parallel(root: Path, run_dir: Path, results: dict, selected_cases: list[cases.Case],
                  selected_variants: list[Variant], repeat: int, total: int, max_cost: float,
                  max_attempts: int, sandbox_on: bool, parallel: int,
                  launch: Callable[[Cell], subprocess.Popen]) -> None:
    pending = []
    index = 0
    for variant in selected_variants:
        for case in selected_cases:
            for number in range(1, repeat + 1):
                index += 1
                relative = Path("cells") / _slug(variant.id) / case.id / f"r{number}"
                pending.append(Cell(variant, case, number, (run_dir / relative).resolve(), 0.0, index))

    running: dict[subprocess.Popen, tuple[Cell, float]] = {}
    spent = 0.0

    def finished(cell: Cell, record: dict, suffix: str = "") -> None:
        nonlocal spent
        record.update(variant=cell.variant.id, case=cell.case.id, repeat=cell.number)
        if record.get("dir") is not None and results["cases"][cell.case.id]["base"] is None:
            results["cases"][cell.case.id]["base"] = _materialized_base(cell.directory)
        spent += float(record["cost_usd"] or 0.0)
        results["cells"].append(record)
        write_results(run_dir, results)
        _cell_line(cell.index, total, record, suffix)

    try:
        while pending or running:
            for proc, (cell, started) in list(running.items()):
                if proc.poll() is None:
                    continue
                del running[proc]
                try:
                    record = _child_record(cell)
                    suffix = ""
                except (OSError, ValueError, TypeError):
                    record = _crash_record(proc, cell, started)
                    suffix = f" (child exit {proc.returncode}; crash.log)"
                finished(cell, record, suffix)

            recorded = spent + sum(_running_cost(cell.directory, cell.case.contract.id)
                                   for cell, _ in running.values())
            if pending and recorded >= max_cost:
                for cell in pending:
                    finished(cell, _empty_record(cell.variant, cell.case, cell.number, "skipped", None))
                pending.clear()

            # Cells started together share the remaining budget; their live cost is
            # included on the next poll, once each pipeline has updated its db.
            while pending and len(running) < parallel and recorded < max_cost:
                next_cell = pending.pop(0)
                cell = dataclasses.replace(next_cell, cost_limit=max_cost - recorded)
                started = time.monotonic()
                try:
                    proc = launch(cell)
                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    cell.directory.mkdir(parents=True, exist_ok=True)
                    (cell.directory / "crash.log").write_text(f"could not start child: {e}\n",
                                                               encoding="utf-8")
                    finished(cell, _recover_record(cell.directory, cell.variant, cell.case,
                                                   cell.number, started), " (launch failed; crash.log)")
                    recorded = spent + sum(_running_cost(running_cell.directory,
                                                         running_cell.case.contract.id)
                                           for running_cell, _ in running.values())
                    continue
                running[proc] = (cell, started)

            if not pending and not running:
                break
            time.sleep(POLL_SECONDS)
    except KeyboardInterrupt:
        for proc in running:
            if proc.poll() is None:
                try:
                    proc.terminate()
                except ProcessLookupError:
                    pass
        for proc in running:
            try:
                proc.wait()
            except ProcessLookupError:
                pass
        for proc, (cell, started) in running.items():
            try:
                record = _child_record(cell)
            except (OSError, ValueError, TypeError):
                record = _recover_record(cell.directory, cell.variant, cell.case, cell.number, started)
            finished(cell, record, " (interrupted)")
        running.clear()


def run_bench(root: Path, *, cases_dir: str | None = None, case_ids: list[str] | None = None,
              flow_names: list[str] | None = None, models: list[str] | None = None,
              repeat: int = 1, max_cost: float | None = None, max_attempts: int = 3,
              dry_run: bool = False, no_sandbox: bool = False, parallel: int = 1) -> int:
    """Run the selected case × variant × repeat cells within one total budget."""
    if max_cost is None and not dry_run:
        raise BenchError("--max-cost is required (bench runs spend real money); pass --dry-run to preview")
    if repeat < 1:
        raise BenchError("--repeat must be at least 1")
    if max_attempts < 1:
        raise BenchError("--max-attempts must be at least 1")
    if parallel < 1:
        raise BenchError("--parallel must be at least 1")
    if max_cost is not None and max_cost < 0:
        raise BenchError("--max-cost must not be negative")
    root = Path(root)
    try:
        cfg = C.load(root)
        selected_variants = variants(cfg, flow_names, models)
        loaded = cases.load_cases([cases_dir] if cases_dir else None)
    except (C.ConfigError, cases.CaseError) as e:
        raise BenchError(str(e)) from None

    by_id = {case.id: case for case in loaded}
    for case_id in case_ids or []:
        if case_id not in by_id:
            raise BenchError(f"unknown case {case_id} (cases: {', '.join(sorted(by_id))})")
    wanted = set(case_ids or [])
    selected_cases = [case for case in loaded if not wanted or case.id in wanted]
    if dry_run:
        _check_test_paths(selected_cases, selected_variants)
        return _dry_run(root, cfg, selected_cases, selected_variants, repeat)

    sandbox_on = not no_sandbox
    preflight(root, cfg, selected_cases, selected_variants, sandbox_on)
    _warn_unpriced(root, cfg, selected_variants)

    started = dt.datetime.now(dt.timezone.utc)
    run_id = started.strftime("%Y%m%d-%H%M%S")
    run_dir = factory_home() / "bench" / run_id
    if run_dir.exists():
        raise BenchError(f"bench run directory already exists: {run_dir}")
    results = {
        "run": {
            "id": run_id,
            "started_at": started.isoformat(timespec="seconds"),
            "ended_at": None,
            "factory": _version(),
            "sandbox": sandbox_on,
            "max_cost": max_cost,
            "max_attempts": max_attempts,
            "repeat": repeat,
        },
        "cases": {case.id: {"kind": case.kind, "base": None, "fixture_sha": fixture_sha(case)}
                  for case in selected_cases},
        "variants": {variant.id: {
            "flow": variant.flow_name,
            "model": variant.model,
            "steps": variant_steps(root, variant.flow, cfg, variant.model),
        } for variant in selected_variants},
        "cells": [],
    }
    run_dir.mkdir(parents=True, exist_ok=False)
    total = len(selected_cases) * len(selected_variants) * repeat
    print(f"bench {run_id}: {len(selected_cases)} cases × {len(selected_variants)} variants × "
          f"{repeat} = {total} cells, budget ${max_cost:.2f}", flush=True)
    write_results(run_dir, results)

    if parallel <= 1:
        _run_sequential(root, run_dir, results, selected_cases, selected_variants, repeat, total,
                        max_cost, max_attempts, sandbox_on)
    else:
        launch = default_launch(root, cases_dir=cases_dir, max_attempts=max_attempts, sandbox_on=sandbox_on)
        _run_parallel(root, run_dir, results, selected_cases, selected_variants, repeat, total,
                      max_cost, max_attempts, sandbox_on, parallel, launch)

    results["run"]["ended_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    write_results(run_dir, results)
    print()
    print(report.summary(results))
    return report.exit_code(results)


if __name__ == "__main__":
    sys.exit(cell_main(sys.argv[1:]))
