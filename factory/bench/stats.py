"""Case-clustered bootstrap statistics for bench results."""

from __future__ import annotations

import math
import random


BOOTSTRAP = 2000
SEED = 0
ELIGIBLE = ("solved", "false_pass", "failed", "regressed", "tampered")


def _cost(cell: dict) -> float:
    return float(cell.get("cost_usd") or 0.0)


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _clusters(cells: list[dict]) -> list[tuple[str, list[dict]]]:
    grouped = {}
    for cell in cells:
        if cell.get("outcome") in ELIGIBLE:
            grouped.setdefault(cell["case"], []).append(cell)
    return [(case, grouped[case]) for case in sorted(grouped)]


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def _interval(samples: list[float]) -> list[float | None]:
    if not samples:
        return [None, None]
    return [_percentile(samples, 0.025), _percentile(samples, 0.975)]


def _draw(rng: random.Random, cells: list[dict]) -> list[dict]:
    return [cells[rng.randrange(len(cells))] for _ in cells]


def _case_values(cells: list[dict]) -> tuple[float, float]:
    return (
        sum(cell["outcome"] == "solved" for cell in cells) / len(cells),
        _mean([_cost(cell) for cell in cells]),
    )


def variant_stats(cells: list[dict]) -> dict:
    """Summarize one variant, giving every case equal weight."""
    clusters = _clusters(cells)
    eligible = [cell for _, case_cells in clusters for cell in case_cells]
    values = [_case_values(case_cells) for _, case_cells in clusters]
    solved_rate = _mean([solved for solved, _ in values])
    cost_per_cell = _mean([cost for _, cost in values])

    rng = random.Random(SEED)
    solved_samples = []
    cost_samples = []
    for _ in range(BOOTSTRAP if clusters else 0):
        drawn_values = []
        for _ in clusters:
            case_cells = clusters[rng.randrange(len(clusters))][1]
            drawn_values.append(_case_values(_draw(rng, case_cells)))
        solved_samples.append(_mean([solved for solved, _ in drawn_values]))
        cost_samples.append(_mean([cost for _, cost in drawn_values]))

    pass_k = None
    if clusters:
        k = min(len(case_cells) for _, case_cells in clusters)
        if k > 1:
            passed = 0
            for _, case_cells in clusters:
                repeats = sorted(case_cells, key=lambda cell: cell.get("repeat") or 0)
                passed += all(cell["outcome"] == "solved" for cell in repeats[:k])
            pass_k = {"k": k, "rate": passed / len(clusters)}

    solved_cells = [cell for cell in eligible if cell["outcome"] == "solved"]
    return {
        "cases": len(clusters),
        "cells": len(eligible),
        "solved": {"rate": solved_rate, "ci": _interval(solved_samples)},
        "pass_k": pass_k,
        "cost_per_cell": {"mean": cost_per_cell, "ci": _interval(cost_samples)},
        "cost_per_solved": _mean([_cost(cell) for cell in solved_cells]),
    }


def _verdict(interval: list[float | None], *, cost: bool = False) -> str:
    low, high = interval
    if low is not None and low > 0:
        return "dearer" if cost else "better"
    if high is not None and high < 0:
        return "cheaper" if cost else "worse"
    return "inconclusive"


def compare(a_cells: list[dict], b_cells: list[dict]) -> dict:
    """Compare B with A on their shared cases using a paired case bootstrap."""
    a_clusters = dict(_clusters(a_cells))
    b_clusters = dict(_clusters(b_cells))
    cases = sorted(set(a_clusters) & set(b_clusters))
    per_case = []
    solved_differences = []
    cost_differences = []
    for case in cases:
        a_solved, a_cost = _case_values(a_clusters[case])
        b_solved, b_cost = _case_values(b_clusters[case])
        per_case.append({"case": case, "a": a_solved, "b": b_solved})
        solved_differences.append(b_solved - a_solved)
        cost_differences.append(b_cost - a_cost)

    rng = random.Random(SEED)
    solved_samples = []
    cost_samples = []
    for _ in range(BOOTSTRAP if cases else 0):
        drawn_solved = []
        drawn_cost = []
        for _ in cases:
            case = cases[rng.randrange(len(cases))]
            a_solved, a_cost = _case_values(_draw(rng, a_clusters[case]))
            b_solved, b_cost = _case_values(_draw(rng, b_clusters[case]))
            drawn_solved.append(b_solved - a_solved)
            drawn_cost.append(b_cost - a_cost)
        solved_samples.append(_mean(drawn_solved))
        cost_samples.append(_mean(drawn_cost))

    solved_ci = _interval(solved_samples)
    cost_ci = _interval(cost_samples)
    resolution = None
    if solved_ci[0] is not None:
        resolution = (solved_ci[1] - solved_ci[0]) / 2
    return {
        "cases": len(cases),
        "solved_diff": {
            "mean": _mean(solved_differences),
            "ci": solved_ci,
            "verdict": _verdict(solved_ci),
            "resolution": resolution,
        },
        "cost_diff": {
            "mean": _mean(cost_differences),
            "ci": cost_ci,
            "verdict": _verdict(cost_ci, cost=True),
        },
        "per_case": per_case,
    }


def pareto(stats_by_variant: dict[str, dict]) -> set[str]:
    """Return variants not dominated on solved rate and cost per cell."""
    front = set()
    for variant, own in stats_by_variant.items():
        solved = own["solved"]["rate"]
        cost = own["cost_per_cell"]["mean"]
        if solved is None or cost is None:
            continue
        dominated = False
        for other_id, other in stats_by_variant.items():
            if other_id == variant:
                continue
            other_solved = other["solved"]["rate"]
            other_cost = other["cost_per_cell"]["mean"]
            if other_solved is None or other_cost is None:
                continue
            if (other_solved >= solved and other_cost <= cost
                    and (other_solved > solved or other_cost < cost)):
                dominated = True
                break
        if not dominated:
            front.add(variant)
    return front
