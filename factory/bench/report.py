"""The tables printed at the end of a bench run, rendered from results.json data."""

from __future__ import annotations


SCORED = ("solved", "false_pass", "failed")


def _table(headers: list[str], rows: list[list[str]]) -> str:
    widths = [len(header) for header in headers]
    for row in rows:
        for i, value in enumerate(row):
            widths[i] = max(widths[i], len(value))
    lines = ["  ".join(header.ljust(widths[i]) for i, header in enumerate(headers)).rstrip()]
    lines.extend("  ".join(value.ljust(widths[i]) for i, value in enumerate(row)).rstrip() for row in rows)
    return "\n".join(lines)


def _mean(cells: list[dict], key: str) -> float:
    return sum((cell[key] or 0.0) for cell in cells) / len(cells) if cells else 0.0


def variant_table(results: dict) -> str:
    rows = []
    for variant_id in results["variants"]:
        cells = [cell for cell in results["cells"] if cell["variant"] == variant_id]
        counts = {outcome: sum(cell["outcome"] == outcome for cell in cells)
                  for outcome in ("solved", "false_pass", "failed", "error", "stopped", "skipped")}
        scored = sum(counts[outcome] for outcome in SCORED)
        solved = (f"{counts['solved']}/{scored} {100 * counts['solved'] / scored:.0f}%" if scored
                  else "0/0 -")
        total_cost = sum(cell["cost_usd"] or 0.0 for cell in cells)
        rows.append([
            variant_id,
            str(len(cells)),
            solved,
            str(counts["false_pass"]),
            str(counts["failed"]),
            f"{counts['error']}/{counts['stopped']}/{counts['skipped']}",
            f"{_mean(cells, 'attempts'):.1f}",
            f"${_mean(cells, 'cost_usd'):.2f}",
            f"${total_cost:.2f}",
            f"{_mean(cells, 'seconds') / 60:.1f}",
        ])
    return _table(["variant", "cells", "solved", "false", "failed", "err/stop/skip", "attempts",
                   "cost/cell", "total", "min/cell"], rows)


def case_table(results: dict) -> str:
    variant_ids = list(results["variants"])
    rows = []
    for case_id in results["cases"]:
        row = [case_id]
        for variant_id in variant_ids:
            cells = [cell for cell in results["cells"]
                     if cell["case"] == case_id and cell["variant"] == variant_id]
            solved = sum(cell["outcome"] == "solved" for cell in cells)
            row.append(f"{solved}/{len(cells)}")
        rows.append(row)
    return _table(["case", *variant_ids], rows)


def tables(results: dict) -> str:
    return variant_table(results) + "\n\n" + case_table(results)
