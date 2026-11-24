"""Pure text summaries and comparisons of bench results."""

from __future__ import annotations

import json
from pathlib import Path

from . import stats as S


ELIGIBLE = S.ELIGIBLE


class ReportError(RuntimeError):
    """An unreadable or unknown bench result."""


def runs(home: Path) -> list[Path]:
    """Return bench run directories in chronological (run-id) order."""
    bench = Path(home) / "bench"
    if not bench.is_dir():
        return []
    return sorted((path for path in bench.iterdir() if path.is_dir()), key=lambda path: path.name)


def load(run_dir: Path) -> dict:
    path = Path(run_dir) / "results.json"
    try:
        results = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise ReportError(f"{path}: cannot read results.json: {e}") from None
    if not isinstance(results, dict):
        raise ReportError(f"{path}: cannot read results.json: top-level JSON value is not a mapping")
    for key in ("run", "cases", "variants", "cells"):
        if key not in results:
            raise ReportError(f"{path}: cannot read results.json: missing key {key!r}")
    return results


def resolve(home: Path, run_id: str | None = None) -> Path:
    known = runs(home)
    if run_id is None:
        if not known:
            raise ReportError("no bench runs yet")
        return known[-1]
    for run_dir in known:
        if run_dir.name == run_id:
            return run_dir
    names = ", ".join(sorted(path.name for path in known)) or "none"
    raise ReportError(f"unknown bench run {run_id} (runs: {names})")


def _repeat(results: dict) -> int:
    return int(results.get("run", {}).get("repeat", 1) or 1)


def _expanded(results: dict) -> tuple[dict, int]:
    """Add the unrecorded cells of an interrupted run as ``not run`` cells."""
    expanded = {**results, "cells": [dict(cell) for cell in results.get("cells", [])]}
    recorded = {(cell.get("variant"), cell.get("case"), cell.get("repeat")) for cell in expanded["cells"]}
    missing = []
    for variant in sorted(results.get("variants", {})):
        for case in sorted(results.get("cases", {})):
            for repeat in range(1, _repeat(results) + 1):
                if (variant, case, repeat) not in recorded:
                    missing.append({
                        "variant": variant,
                        "case": case,
                        "repeat": repeat,
                        "outcome": "not run",
                        "attempts": 0,
                        "cost_usd": 0.0,
                        "seconds": 0.0,
                        "dir": None,
                    })
    expanded["cells"].extend(missing)
    return expanded, len(missing)


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _variant_stats(cells: list[dict]) -> dict:
    eligible = [cell for cell in cells if cell["outcome"] in ELIGIBLE]
    ran = [cell for cell in cells if cell["outcome"] not in ("skipped", "not run")]
    solved = sum(cell["outcome"] == "solved" for cell in cells)
    return {
        "cells": len(cells),
        "solved": solved,
        "eligible": len(eligible),
        "false": sum(cell["outcome"] == "false_pass" for cell in cells),
        "regressed": sum(cell["outcome"] == "regressed" for cell in cells),
        "tampered": sum(cell["outcome"] == "tampered" for cell in cells),
        "failed": sum(cell["outcome"] == "failed" for cell in cells),
        "error": sum(cell["outcome"] == "error" for cell in cells),
        "stopped": sum(cell["outcome"] == "stopped" for cell in cells),
        "skipped": sum(cell["outcome"] == "skipped" for cell in cells),
        "not_run": sum(cell["outcome"] == "not run" for cell in cells),
        # Cells that never ran do not count in attempts, cost and wall-time means.
        "attempts": _mean([float(cell.get("attempts") or 0) for cell in ran]),
        "cost": _mean([float(cell.get("cost_usd") or 0.0) for cell in ran]),
        "total": sum(float(cell.get("cost_usd") or 0.0) for cell in cells),
        "minutes": _mean([float(cell.get("seconds") or 0.0) / 60 for cell in ran]),
    }


def _number(value: float | None, format_spec: str = ".1f", prefix: str = "") -> str:
    return f"{prefix}{value:{format_spec}}" if value is not None else "-"


def _signed_points(value: float | None) -> str:
    if value is None:
        return "-"
    formatted = f"{100 * value:+.0f}"
    if formatted in ("-0", "+0"):
        formatted = "+0"
    return formatted.replace("-", "−")


def _signed_money(value: float | None) -> str:
    if value is None:
        return "-"
    formatted = f"{value:+.2f}"
    sign = "−" if formatted.startswith("-") else "+"
    if float(formatted) == 0:
        sign = "+"
    return f"{sign}${abs(float(formatted)):.2f}"


def _comparison_line(a_variant: str, b_variant: str, comparison: dict) -> str:
    solved = comparison["solved_diff"]
    cost = comparison["cost_diff"]
    solved_low, solved_high = solved["ci"]
    cost_low, cost_high = cost["ci"]
    return (
        f"{b_variant} vs {a_variant}: solved {_signed_points(solved['mean'])} pts "
        f"[{_signed_points(solved_low)}, {_signed_points(solved_high)}] {solved['verdict']} · "
        f"cost {_signed_money(cost['mean'])}/cell "
        f"[{_signed_money(cost_low)}, {_signed_money(cost_high)}] {cost['verdict']}"
    )


def _cells_for(results: dict, variant: str) -> list[dict]:
    return [cell for cell in results.get("cells", []) if cell["variant"] == variant]


def summary(results: dict) -> str:
    """Render the per-variant table followed by solved counts per case and variant."""
    results, _ = _expanded(results)
    cells = results.get("cells", [])
    variant_ids = list(results.get("variants", {}))
    raw_stats = {variant: _variant_stats(_cells_for(results, variant)) for variant in variant_ids}
    analyses = {variant: S.variant_stats(_cells_for(results, variant)) for variant in variant_ids}
    pareto = S.pareto(analyses)
    solved_columns = {}
    pass_columns = {}
    for variant in variant_ids:
        raw, analysis = raw_stats[variant], analyses[variant]
        if analysis["solved"]["rate"] is None:
            solved_columns[variant] = "-"
        else:
            low, high = analysis["solved"]["ci"]
            solved_columns[variant] = (
                f"{raw['solved']}/{raw['eligible']} {100 * analysis['solved']['rate']:.0f}% "
                f"[{100 * low:.0f}–{100 * high:.0f}]"
            )
        if analysis["pass_k"] is None:
            pass_columns[variant] = "-"
        else:
            pass_columns[variant] = f"pass^{analysis['pass_k']['k']} {100 * analysis['pass_k']['rate']:.0f}%"

    variant_width = max([len("variant"), *(len(variant) for variant in variant_ids)])
    solved_width = max([len("solved"), *(len(value) for value in solved_columns.values())])
    pass_width = max([len("pass^k"), *(len(value) for value in pass_columns.values())])
    lines = [
        f"{'variant':<{variant_width}}  {'cells':>5}  {'solved':<{solved_width}}  "
        f"{'pass^k':<{pass_width}}  {'false':>5}  {'regressed':>9}  {'tampered':>8}  {'failed':>6}  "
        f"{'err/stop/skip/not run':>21}  {'attempts':>8}  {'cost/cell':>9}  "
        f"{'cost/solved':>11}  {'total':>9}  {'min/cell':>8}  *"
    ]
    for variant in variant_ids:
        raw, analysis = raw_stats[variant], analyses[variant]
        interruptions = f"{raw['error']}/{raw['stopped']}/{raw['skipped']}/{raw['not_run']}"
        marker = "  *" if variant in pareto else ""
        lines.append(
            f"{variant:<{variant_width}}  {raw['cells']:>5}  {solved_columns[variant]:<{solved_width}}  "
            f"{pass_columns[variant]:<{pass_width}}  {raw['false']:>5}  "
            f"{raw['regressed']:>9}  {raw['tampered']:>8}  {raw['failed']:>6}  "
            f"{interruptions:>21}  {_number(raw['attempts']):>8}  "
            f"{_number(analysis['cost_per_cell']['mean'], '.2f', '$'):>9}  "
            f"{_number(analysis['cost_per_solved'], '.2f', '$'):>11}  "
            f"{_number(raw['total'], '.2f', '$'):>9}  {_number(raw['minutes']):>8}{marker}"
        )

    case_ids = list(results.get("cases", {}))
    case_width = max([len("case"), *(len(case) for case in case_ids)])
    counts = {}
    for case in case_ids:
        for variant in variant_ids:
            stat = _variant_stats([cell for cell in cells
                                   if cell["case"] == case and cell["variant"] == variant])
            counts[case, variant] = f"{stat['solved']}/{stat['eligible']}"
    widths = {variant: max([len(variant), *(len(counts[case, variant]) for case in case_ids)])
              for variant in variant_ids}
    header = f"{'case':<{case_width}}" + "".join(f"  {variant:<{widths[variant]}}" for variant in variant_ids)
    lines += ["", header]
    for case in case_ids:
        lines.append(f"{case:<{case_width}}" + "".join(
            f"  {counts[case, variant]:<{widths[variant]}}" for variant in variant_ids))

    if len(variant_ids) > 1:
        first = variant_ids[0]
        comparisons = [
            _comparison_line(first, variant, S.compare(_cells_for(results, first), _cells_for(results, variant)))
            for variant in variant_ids[1:]
        ]
        lines += ["", *comparisons]
    return "\n".join(lines).rstrip()


def header(results: dict) -> str:
    run = results.get("run", {})
    cases = results.get("cases", {})
    variants = results.get("variants", {})
    repeat = _repeat(results)
    total = sum(float(cell.get("cost_usd") or 0.0) for cell in results.get("cells", []))
    budget = "" if run.get("max_cost") is None else f" of ${float(run['max_cost']):.2f}"
    lines = [f"bench {run.get('id') or '-'} · {len(cases)} cases · {len(variants)} variants × {repeat} · "
             f"${total:.2f}{budget} · factory {run.get('factory') or '-'}"]
    if not run.get("sandbox", True):
        lines.append("unsandboxed: agents could read the hidden tests")
    _, missing = _expanded(results)
    if missing:
        lines.append(f"not run: {missing} of {len(cases) * len(variants) * repeat} cells")
    return "\n".join(lines)


def cell_lines(results: dict, run_dir: Path) -> list[str]:
    expanded, _ = _expanded(results)
    recorded_count = len(results.get("cells", []))
    run_dir = Path(run_dir).resolve()
    lines = []
    for index, cell in enumerate(expanded["cells"]):
        prefix = f"{cell['variant']} · {cell['case']} #{cell['repeat']}: "
        if index >= recorded_count:
            lines.append(prefix + "not run, -, -, -, -")
            continue
        attempts = cell.get("attempts") or 0
        directory = cell.get("dir")
        if directory:
            path = Path(directory)
            directory = str(path if path.is_absolute() else run_dir / path)
        else:
            directory = "-"
        built = cell.get("candidates_built", 0)
        candidates = f", {built} candidates ({cell.get('candidates_passed', 0)} passed)" if built else ""
        lines.append(
            prefix + f"{cell['outcome']}, {attempts} attempt{'' if attempts == 1 else 's'}, "
            f"${float(cell.get('cost_usd') or 0.0):.2f}, "
            f"{float(cell.get('seconds') or 0.0) / 60:.1f} min{candidates}, {directory}"
        )
    return lines


def _table(headers: list[str], rows: list[list[str]]) -> str:
    widths = [max([len(header), *(len(row[index]) for row in rows)])
              for index, header in enumerate(headers)]
    lines = ["  ".join(f"{value:<{widths[index]}}" for index, value in enumerate(headers)).rstrip()]
    lines.extend("  ".join(f"{value:<{widths[index]}}" for index, value in enumerate(row)).rstrip()
                 for row in rows)
    return "\n".join(lines)


def _step_changes(a_id: str, a_variant: dict, b_id: str, b_variant: dict) -> list[str]:
    a_steps = {step.get("name"): step for step in a_variant.get("steps", [])}
    b_steps = {step.get("name"): step for step in b_variant.get("steps", [])}
    names = list(a_steps) + [name for name in b_steps if name not in a_steps]
    changes = []
    for name in names:
        if name not in b_steps:
            changes.append(f"{name}: only in {a_id}")
            continue
        if name not in a_steps:
            changes.append(f"{name}: only in {b_id}")
            continue
        a_step, b_step = a_steps[name], b_steps[name]
        differences = []
        if a_step.get("model") != b_step.get("model"):
            differences.append(f"model {a_step.get('model') or '-'} → {b_step.get('model') or '-'}")
        if a_step.get("prompt_sha") != b_step.get("prompt_sha"):
            a_sha = str(a_step.get("prompt_sha") or "-")[:12]
            b_sha = str(b_step.get("prompt_sha") or "-")[:12]
            differences.append(f"prompt_sha {a_sha} → {b_sha}")
        a_loop, b_loop = list(a_step.get("loop") or []), list(b_step.get("loop") or [])
        if a_loop != b_loop:
            differences.append(f"loop {a_loop} → {b_loop}")
        a_prove, b_prove = a_step.get("prove", False), b_step.get("prove", False)
        if a_prove != b_prove:
            differences.append(f"prove {a_prove} → {b_prove}")
        a_candidates, b_candidates = a_step.get("candidates", 1), b_step.get("candidates", 1)
        if a_candidates != b_candidates:
            differences.append(f"candidates {a_candidates} → {b_candidates}")
        if differences:
            changes.append(f"{name}: {', '.join(differences)}")
    return changes


def _solved_count(cells: list[dict]) -> str:
    if not cells:
        return "-"
    stat = _variant_stats(cells)
    return f"{stat['solved']}/{stat['eligible']}"


def _variant_pairs(a_id: str, a_results: dict, b_id: str, b_results: dict,
                   a_variant: str | None, b_variant: str | None) -> list[tuple[str, str]]:
    a_variants, b_variants = a_results.get("variants", {}), b_results.get("variants", {})
    if a_variant is None and b_variant is None:
        return [(variant, variant) for variant in a_variants if variant in b_variants]
    if a_variant is None:
        a_variant = b_variant
    if b_variant is None:
        b_variant = a_variant
    for run_id, variants, variant in ((a_id, a_variants, a_variant), (b_id, b_variants, b_variant)):
        if variant not in variants:
            raise ReportError(f"unknown bench variant {variant} in run {run_id}")
    return [(a_variant, b_variant)]


def compare(a_id: str, a_results: dict, b_id: str, b_results: dict, *,
            a_variant: str | None = None, b_variant: str | None = None) -> str:
    a_cases, b_cases = a_results.get("cases", {}), b_results.get("cases", {})
    a_variants, b_variants = a_results.get("variants", {}), b_results.get("variants", {})
    shared_cases = [case for case in a_cases if case in b_cases]
    pairs = _variant_pairs(a_id, a_results, b_id, b_results, a_variant, b_variant)
    explicit = a_variant is not None or b_variant is not None
    lines = [f"compare {a_id} → {b_id}"]
    for run_id, results in ((a_id, a_results), (b_id, b_results)):
        if not results.get("run", {}).get("sandbox", True):
            lines.append(f"{run_id} unsandboxed: agents could read the hidden tests")

    changed = [case for case in shared_cases
               if a_cases[case].get("fixture_sha") != b_cases[case].get("fixture_sha")]
    if changed:
        descriptions = []
        for case in changed:
            a_sha = str(a_cases[case].get("fixture_sha") or "-")[:12]
            b_sha = str(b_cases[case].get("fixture_sha") or "-")[:12]
            descriptions.append(f"{case} ({a_sha} → {b_sha})")
        case_line = f"cases: {len(shared_cases)} in both, changed: {', '.join(descriptions)}"
    else:
        case_line = f"cases: {len(shared_cases)} in both, unchanged"
    for run_id, own, other in ((a_id, a_cases, b_cases), (b_id, b_cases, a_cases)):
        only = [case for case in own if case not in other]
        if only:
            case_line += f" · only in {run_id}: {', '.join(only)}"
    lines.append(case_line)

    variant_line = f"variants: {len(pairs)} in both"
    if not explicit:
        for run_id, own, other in ((a_id, a_variants, b_variants), (b_id, b_variants, a_variants)):
            only = [variant for variant in own if variant not in other]
            if only:
                variant_line += f" · only in {run_id}: {', '.join(only)}"
    lines.append(variant_line)
    for own_variant, other_variant in pairs:
        changes = _step_changes(a_id, a_variants[own_variant], b_id, b_variants[other_variant])
        if changes:
            label = own_variant if own_variant == other_variant else f"{own_variant} → {other_variant}"
            lines.append(f"{label} · {' · '.join(changes)}")
            # Candidate changes also have a step-prefixed line for direct step comparisons.
            lines.extend(change for change in changes if "candidates " in change)

    variant_rows = []
    comparison_lines = []
    for own_variant, other_variant in pairs:
        own = [cell for cell in a_results.get("cells", []) if cell["variant"] == own_variant]
        other = [cell for cell in b_results.get("cells", []) if cell["variant"] == other_variant]
        a_stat = _variant_stats(own) if own else None
        b_stat = _variant_stats(other) if other else None

        def paired(key: str, format_spec: str = ".1f", prefix: str = "") -> str:
            left = _number(a_stat[key], format_spec, prefix) if a_stat is not None else "-"
            right = _number(b_stat[key], format_spec, prefix) if b_stat is not None else "-"
            return f"{left} → {right}"

        label = own_variant if own_variant == other_variant else f"{own_variant} → {other_variant}"
        variant_rows.append([
            label,
            f"{_solved_count(own)} → {_solved_count(other)}",
            f"{a_stat['false'] if a_stat is not None else '-'} → "
            f"{b_stat['false'] if b_stat is not None else '-'}",
            paired("cost", ".2f", "$"),
            paired("attempts"),
            paired("minutes"),
        ])
        comparison_lines.append(_comparison_line(own_variant, other_variant, S.compare(own, other)))

    pair_labels = [own if own == other else f"{own} → {other}" for own, other in pairs]
    case_rows = []
    for case in shared_cases:
        row = [case]
        for own_variant, other_variant in pairs:
            own = [cell for cell in a_results.get("cells", [])
                   if cell["case"] == case and cell["variant"] == own_variant]
            other = [cell for cell in b_results.get("cells", [])
                     if cell["case"] == case and cell["variant"] == other_variant]
            row.append(f"{_solved_count(own)} → {_solved_count(other)}")
        case_rows.append(row)
    parts = [
        "\n".join(lines),
        "",
        _table(["variant", "solved", "false", "cost/cell", "attempts", "min/cell"], variant_rows),
        "",
        _table(["case", *pair_labels], case_rows),
    ]
    if comparison_lines:
        parts += ["", *comparison_lines]
    return "\n".join(parts).rstrip()


def _json_variant(results: dict, variant: str, analysis: dict, on_front: bool) -> dict:
    cells = _cells_for(results, variant)
    raw = _variant_stats(cells)
    entry = dict(analysis)
    entry.update({
        "false_pass": sum(cell["outcome"] == "false_pass" for cell in cells),
        "regressed": sum(cell["outcome"] == "regressed" for cell in cells),
        "tampered": sum(cell["outcome"] == "tampered" for cell in cells),
        "integrity": {
            "gamed": sum(cell["outcome"] == "gamed" for cell in cells),
            "cells": sum(cell["outcome"] in ("held", "gamed") for cell in cells),
        },
        "minutes_per_cell": raw["minutes"],
        "pareto": on_front,
        "fingerprint": results.get("variants", {}).get(variant, {}).get("fingerprint"),
    })
    return entry


def _comparison_record(a_id: str, a_variant: str, a_results: dict,
                       b_id: str, b_variant: str, b_results: dict) -> dict:
    comparison = S.compare(_cells_for(a_results, a_variant), _cells_for(b_results, b_variant))
    return {"a": f"{a_id}:{a_variant}", "b": f"{b_id}:{b_variant}", **comparison}


def report_data(run_id: str, results: dict) -> dict:
    """Return one run's statistics and comparisons as a JSON-ready mapping."""
    variant_ids = list(results.get("variants", {}))
    analyses = {variant: S.variant_stats(_cells_for(results, variant)) for variant in variant_ids}
    front = S.pareto(analyses)
    variants = {
        variant: _json_variant(results, variant, analyses[variant], variant in front)
        for variant in variant_ids
    }
    comparisons = []
    if variant_ids:
        first = variant_ids[0]
        comparisons = [
            _comparison_record(run_id, first, results, run_id, variant, results)
            for variant in variant_ids[1:]
        ]
    return {"runs": [run_id], "variants": variants, "comparisons": comparisons}


def compare_data(a_id: str, a_results: dict, b_id: str, b_results: dict, *,
                 a_variant: str | None = None, b_variant: str | None = None) -> dict:
    """Return selected cross-run comparisons and their variant statistics."""
    pairs = _variant_pairs(a_id, a_results, b_id, b_results, a_variant, b_variant)
    run_ids = [a_id] if a_id == b_id else [a_id, b_id]
    analyses_by_run = {}
    fronts = {}
    for run_id, results in ((a_id, a_results), (b_id, b_results)):
        if run_id in analyses_by_run:
            continue
        analyses = {variant: S.variant_stats(_cells_for(results, variant))
                    for variant in results.get("variants", {})}
        analyses_by_run[run_id] = analyses
        fronts[run_id] = S.pareto(analyses)

    variants = {}
    for own_variant, other_variant in pairs:
        for run_id, results, variant in ((a_id, a_results, own_variant), (b_id, b_results, other_variant)):
            key = f"{run_id}:{variant}"
            if key not in variants:
                variants[key] = _json_variant(
                    results, variant, analyses_by_run[run_id][variant], variant in fronts[run_id])
    comparisons = [
        _comparison_record(a_id, own_variant, a_results, b_id, other_variant, b_results)
        for own_variant, other_variant in pairs
    ]
    return {"runs": run_ids, "variants": variants, "comparisons": comparisons}


def list_row(run_id: str, results: dict) -> str:
    run = results.get("run", {})
    cases = results.get("cases", {})
    variants = results.get("variants", {})
    cells = results.get("cells", [])
    total = len(cases) * len(variants) * _repeat(results)
    cost = sum(float(cell.get("cost_usd") or 0.0) for cell in cells)
    return (f"{run_id}  {run.get('started_at') or '-'}  {len(cases)} cases  {len(variants)} variants  "
            f"{len(cells)}/{total} cells  ${cost:.2f}")


def exit_code(results: dict) -> int:
    """Errors, budget stops and skipped cells make the bench command fail."""
    return int(any(cell["outcome"] in ("error", "stopped", "skipped") for cell in results.get("cells", [])))
