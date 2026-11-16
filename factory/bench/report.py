"""Pure text summaries of bench results (also used by later report commands)."""

from __future__ import annotations


ELIGIBLE = ("solved", "false_pass", "failed")


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _variant_stats(cells: list[dict]) -> dict:
    eligible = [cell for cell in cells if cell["outcome"] in ELIGIBLE]
    ran = [cell for cell in cells if cell["outcome"] != "skipped"]
    solved = sum(cell["outcome"] == "solved" for cell in cells)
    return {
        "cells": len(cells),
        "solved": solved,
        "eligible": len(eligible),
        "false": sum(cell["outcome"] == "false_pass" for cell in cells),
        "failed": sum(cell["outcome"] == "failed" for cell in cells),
        "error": sum(cell["outcome"] == "error" for cell in cells),
        "stopped": sum(cell["outcome"] == "stopped" for cell in cells),
        "skipped": sum(cell["outcome"] == "skipped" for cell in cells),
        # Skipped cells never ran, so attempts, cost and wall-time means exclude them.
        "attempts": _mean([float(cell.get("attempts") or 0) for cell in ran]),
        "cost": _mean([float(cell.get("cost_usd") or 0.0) for cell in ran]),
        "total": sum(float(cell.get("cost_usd") or 0.0) for cell in cells),
        "minutes": _mean([float(cell.get("seconds") or 0.0) / 60 for cell in ran]),
    }


def _number(value: float | None, format_spec: str = ".1f", prefix: str = "") -> str:
    return f"{prefix}{value:{format_spec}}" if value is not None else "-"


def summary(results: dict) -> str:
    """Render the per-variant table followed by solved counts per case and variant."""
    cells = results.get("cells", [])
    variant_ids = list(results.get("variants", {}))
    stats = {variant: _variant_stats([cell for cell in cells if cell["variant"] == variant])
             for variant in variant_ids}
    variant_width = max([len("variant"), *(len(variant) for variant in variant_ids)])
    lines = [
        f"{'variant':<{variant_width}}  {'cells':>5}  {'solved':<11}  {'false':>5}  {'failed':>6}  "
        f"{'err/stop/skip':>13}  {'attempts':>8}  {'cost/cell':>9}  {'total':>9}  {'min/cell':>8}"
    ]
    for variant in variant_ids:
        stat = stats[variant]
        solved = (f"{stat['solved']}/{stat['eligible']} {100 * stat['solved'] / stat['eligible']:.0f}%"
                  if stat["eligible"] else "-")
        interruptions = f"{stat['error']}/{stat['stopped']}/{stat['skipped']}"
        lines.append(
            f"{variant:<{variant_width}}  {stat['cells']:>5}  {solved:<11}  {stat['false']:>5}  "
            f"{stat['failed']:>6}  {interruptions:>13}  {_number(stat['attempts']):>8}  "
            f"{_number(stat['cost'], '.2f', '$'):>9}  {_number(stat['total'], '.2f', '$'):>9}  "
            f"{_number(stat['minutes']):>8}"
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
    return "\n".join(lines).rstrip()


def exit_code(results: dict) -> int:
    """Errors, budget stops and skipped cells make the bench command fail."""
    return int(any(cell["outcome"] in ("error", "stopped", "skipped") for cell in results.get("cells", [])))
