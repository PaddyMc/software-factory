"""evals-t01: bench statistics — case-clustered intervals, pass^k, verdicts, Pareto, --json.

These tests pin down the API of the new ``factory/bench/stats.py``:

  stats.BOOTSTRAP     the number of bootstrap resamples: 2000
  stats.SEED          the bootstrap's seed: 0, so the same cells always give the same interval

  stats.variant_stats(cells) -> dict
      Statistics for one variant's cells (results.json cell dicts):
      {"cases": cases with at least one eligible cell, "cells": eligible cells,
       "solved": {"rate", "ci"}, "pass_k": {"k", "rate"} or None,
       "cost_per_cell": {"mean", "ci"}, "cost_per_solved": mean cost of solved cells or None}
      "solved.rate" is the mean over cases of each case's solved share of its eligible
      cells; "ci" holds the 2.5th and 97.5th percentiles of the case-clustered bootstrap.

  stats.compare(a_cells, b_cells) -> dict
      B against A over the cases both variants have an eligible cell on:
      {"cases", "solved_diff": {"mean", "ci", "verdict", "resolution"},
       "cost_diff": {"mean", "ci", "verdict"}, "per_case": [{"case", "a", "b"}]}

  stats.pareto(stats_by_variant) -> set of the undominated variant ids
"""

import copy
import datetime as dt
import json

import pytest

from factory.bench import stats
from factory.cli import main


def _cell(variant, case, *, repeat=1, outcome="solved", cost=0.10, seconds=60.0):
    return {
        "variant": variant,
        "case": case,
        "repeat": repeat,
        "outcome": outcome,
        "attempts": 1,
        "cost_usd": cost,
        "seconds": seconds,
        "model_calls": 4,
        "tokens_in": 100,
        "tokens_out": 50,
        "review_changes": 0,
        "step_limit_stops": 0,
        "failed_gates": [],
        "dir": None,
    }


def _steps(model="fake:builder", prompt="a" * 64):
    return [{"name": "build", "kind": "build", "model": model,
             "max_steps": 20, "prompt_sha": prompt}]


def _write_run(home, run_id, cases, variants, cells, *, repeat=1):
    started = dt.datetime.strptime(run_id, "%Y%m%d-%H%M%S").replace(tzinfo=dt.timezone.utc)
    results = {
        "run": {
            "id": run_id, "started_at": started.isoformat(), "ended_at": started.isoformat(),
            "factory": "0.1.0", "sandbox": True, "max_cost": 5.0, "max_attempts": 3,
            "repeat": repeat,
        },
        "cases": {case: {"kind": "feature", "base": "0" * 40, "fixture_sha": sha}
                  for case, sha in cases.items()},
        "variants": {variant: {"flow": variant, "model": None, "steps": copy.deepcopy(steps)}
                     for variant, steps in variants.items()},
        "cells": cells,
    }
    run_dir = home / "bench" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "results.json").write_text(json.dumps(results, indent=2) + "\n")
    return run_dir


def _bounds(interval):
    """A percentile interval, whatever sequence the stats module returns, as a pair."""
    low, high = interval
    return float(low), float(high)


def test_solved_rate_has_a_case_clustered_interval(home, capsys):
    """evals-t01: the solved rate is the mean over cases of each case's share, and its
    95% interval comes from resampling cases and then each drawn case's cells."""
    cells = (
        [_cell("v", "easy", repeat=n) for n in (1, 2, 3)]
        + [_cell("v", "easy", repeat=4, outcome="error")]  # error cells are never eligible
        + [_cell("v", "hard", repeat=n, outcome="failed") for n in (1, 2, 3)]
        + [_cell("v", "mixed", repeat=1),
           _cell("v", "mixed", repeat=2, outcome="failed"),
           _cell("v", "mixed", repeat=3, outcome="false_pass"),
           _cell("v", "mixed", repeat=4, outcome="failed")]
    )
    variant = stats.variant_stats(cells)
    assert variant["cases"] == 3 and variant["cells"] == 10
    # A case with more repeats weighs no more: the pooled cell rate would be 4/10.
    assert variant["solved"]["rate"] == pytest.approx((1.0 + 0.0 + 0.25) / 3)
    low, high = _bounds(variant["solved"]["ci"])
    assert 0.0 <= low <= variant["solved"]["rate"] <= high <= 1.0

    # Case clustering: when every case's share sits at an extreme, every bootstrap draw is
    # a mean of whole-case shares, so the interval can only span the full range. Resampling
    # cells without the case structure keeps a pooled interval well inside (0, 1).
    degenerate = stats.variant_stats(
        [_cell("v", "clean", repeat=n) for n in (1, 2, 3)]
        + [_cell("v", "rough", repeat=n, outcome="failed") for n in (1, 2, 3)])
    assert degenerate["solved"]["rate"] == pytest.approx(0.5)
    assert _bounds(degenerate["solved"]["ci"]) == pytest.approx((0.0, 1.0))

    # The interval reaches the report's solved column: `12/15 80% [60–93]`.
    run_id = "20261123-120000"
    cells = []
    for case in ("c1", "c2"):
        for repeat in (1, 2):
            cells += [_cell("default", case, repeat=repeat, outcome="failed", cost=0.10),
                      _cell("lean", case, repeat=repeat, cost=0.30)]
    # spends solves the cheap case and fails the dear one: its cost per solved cell ($0.40)
    # differs from its cost per cell ($0.25), its cheapest cell and its total.
    cells += [_cell("spends", "c1", cost=0.40), _cell("spends", "c2", outcome="failed", cost=0.10)]
    _write_run(home, run_id, {"c1": "f" * 64, "c2": "f" * 64},
               {"default": _steps(), "lean": _steps(), "spends": _steps()}, cells, repeat=2)
    assert main(["bench", "report", run_id]) == 0
    out = capsys.readouterr().out
    lean = next(line for line in out.splitlines() if line.startswith("lean"))
    default = next(line for line in out.splitlines() if line.startswith("default"))
    assert "4/4 100% [100–100]" in lean
    assert "0/4 0% [0–0]" in default
    spends = next(line for line in out.splitlines() if line.startswith("spends"))
    assert "$0.40" in spends          # the cost per solved cell column ($0.40, not its $0.25/cell)



def test_the_bootstrap_is_seeded(home, capsys):
    """evals-t01: stats.BOOTSTRAP is 2000 resamples and stats.SEED (0) makes the same
    results give the same interval, in the library and through the CLI."""
    assert stats.BOOTSTRAP == 2000
    assert stats.SEED == 0

    cells = ([_cell("v", "all", repeat=n) for n in (1, 2)]
             + [_cell("v", "none", repeat=n, outcome="failed") for n in (1, 2)])
    first = stats.variant_stats(copy.deepcopy(cells))
    second = stats.variant_stats(copy.deepcopy(cells))
    assert first["solved"]["rate"] == second["solved"]["rate"]
    assert _bounds(first["solved"]["ci"]) == _bounds(second["solved"]["ci"])
    assert _bounds(first["cost_per_cell"]["ci"]) == _bounds(second["cost_per_cell"]["ci"])

    # Different cells still give a different interval, so the seed does not freeze output.
    flat = stats.variant_stats([_cell("v", "only")])
    assert _bounds(flat["solved"]["ci"]) == pytest.approx((1.0, 1.0))
    assert _bounds(flat["solved"]["ci"]) != _bounds(first["solved"]["ci"])

    run_id = "20261123-121000"
    _write_run(home, run_id, {"c": "f" * 64}, {"v": _steps()},
               [_cell("v", "c"), _cell("v", "c", repeat=2, outcome="failed")], repeat=2)
    assert main(["bench", "report", run_id, "--json"]) == 0
    once = capsys.readouterr().out
    assert main(["bench", "report", run_id, "--json"]) == 0
    assert capsys.readouterr().out == once


def test_pass_k_counts_cases_solved_on_every_repeat(home, capsys):
    """evals-t01: pass^k is the share of cases whose k eligible repeats were all solved,
    k being the smallest number of eligible repeats of any case, and it is omitted (None)
    when k is 1."""
    cells = (
        [_cell("v", "one", repeat=n) for n in (1, 2, 3)]
        + [_cell("v", "one", repeat=4, outcome="skipped")]  # only eligible repeats count
        + [_cell("v", "two", repeat=n) for n in (1, 2)]
        + [_cell("v", "two", repeat=3, outcome="failed")]
        + [_cell("v", "three", repeat=1),
           _cell("v", "three", repeat=2, outcome="failed"),
           _cell("v", "three", repeat=3, outcome="failed")]
    )
    variant = stats.variant_stats(cells)
    assert variant["pass_k"]["k"] == 3
    assert variant["pass_k"]["rate"] == pytest.approx(1 / 3)

    # With one repeat per case pass^k adds nothing over the solved rate, so it is omitted.
    singles = stats.variant_stats([_cell("v", "solo"), _cell("v", "duo", outcome="failed")])
    assert singles["pass_k"] is None

    # The report gains a pass^k column alongside the solved rate.
    run_id = "20261123-122000"
    cells = ([_cell("mixed", "c1", repeat=n) for n in (1, 2)]
             + [_cell("mixed", "c2"), _cell("mixed", "c2", repeat=2, outcome="failed")])
    _write_run(home, run_id, {"c1": "a" * 64, "c2": "b" * 64}, {"mixed": _steps()},
               cells, repeat=2)
    assert main(["bench", "report", run_id]) == 0
    out = capsys.readouterr().out
    header = next(line for line in out.splitlines() if line.startswith("variant"))
    assert "pass^" in header
    row = next(line for line in out.splitlines() if line.startswith("mixed"))
    assert "75%" in row          # the solved rate: cases share 1.0 and 0.5
    assert "50%" in row          # pass^2: one case of two solved every repeat


def test_a_paired_difference_gets_a_verdict():
    """evals-t01: a comparison pairs the cases both variants have, reports the mean
    difference with a 95% interval, and verdicts it better or worse on the interval
    bounds; the interval's half-width is the resolution."""
    a_cells = ([_cell("a", case, repeat=n, outcome="failed", cost=0.10)
                for case in ("x", "y", "z") for n in (1, 2)]
               + [_cell("a", "only-a")])
    b_cells = ([_cell("b", case, repeat=n, cost=0.10)
                for case in ("x", "y", "z") for n in (1, 2)]
               + [_cell("b", "only-b")])

    win = stats.compare(a_cells, b_cells)
    assert set(win) >= {"cases", "solved_diff", "cost_diff", "per_case"}
    assert win["cases"] == 3                       # only the cases both variants have
    assert win["solved_diff"]["verdict"] == "better"
    assert win["solved_diff"]["mean"] == pytest.approx(1.0)
    assert _bounds(win["solved_diff"]["ci"]) == (1.0, 1.0)
    assert win["solved_diff"]["resolution"] == pytest.approx(0.0)
    by_case = {row["case"]: row for row in win["per_case"]}
    assert set(by_case) == {"x", "y", "z"}
    assert all(row["a"] == 0.0 and row["b"] == 1.0 for row in by_case.values())

    loss = stats.compare(b_cells, a_cells)
    assert loss["solved_diff"]["verdict"] == "worse"
    assert loss["solved_diff"]["mean"] == pytest.approx(-1.0)
    assert _bounds(loss["solved_diff"]["ci"]) == (-1.0, -1.0)
    # The interval's half-width is the smallest difference this comparison can resolve.
    low, high = _bounds(win["solved_diff"]["ci"])
    assert win["solved_diff"]["resolution"] == pytest.approx((high - low) / 2)


def test_identical_variants_are_inconclusive(home, capsys):
    """evals-t01: when two variants cannot be told apart, both verdicts are inconclusive."""
    cells = ([_cell("same", "x", repeat=1, cost=0.10),
              _cell("same", "x", repeat=2, outcome="failed", cost=0.20),
              _cell("same", "y", cost=0.30),
              _cell("same", "y", repeat=2, outcome="failed", cost=0.40)])
    twin = [dict(cell, variant="twin") for cell in cells]

    comparison = stats.compare(cells, twin)
    assert comparison["solved_diff"]["verdict"] == "inconclusive"
    assert comparison["cost_diff"]["verdict"] == "inconclusive"
    assert comparison["solved_diff"]["mean"] == pytest.approx(0.0)
    assert comparison["per_case"] and all(row["a"] == row["b"] for row in comparison["per_case"])

    run_id = "20261123-124000"
    _write_run(home, run_id, {"x": "a" * 64, "y": "b" * 64}, {"same": _steps()}, cells, repeat=2)
    assert main(["bench", "compare", run_id, run_id]) == 0
    assert "inconclusive" in capsys.readouterr().out


def test_cost_has_its_own_verdict(home, capsys):
    """evals-t01: the cost difference gets its own cheaper/dearer/inconclusive verdict,
    separate from the solved rate's."""
    expensive = [_cell("default", case, repeat=n, cost=0.10)
                 for case in ("c1", "c2") for n in (1, 2)]
    cheap = [_cell("lean", case, repeat=n, cost=0.02) for case in ("c1", "c2") for n in (1, 2)]

    comparison = stats.compare(expensive, cheap)
    assert comparison["solved_diff"]["verdict"] == "inconclusive"   # the solved rate does not move
    assert comparison["cost_diff"]["verdict"] == "cheaper"
    assert comparison["cost_diff"]["mean"] == pytest.approx(0.02 - 0.10)
    assert _bounds(comparison["cost_diff"]["ci"]) == pytest.approx((0.02 - 0.10, 0.02 - 0.10))

    flipped = stats.compare(cheap, expensive)
    assert flipped["cost_diff"]["verdict"] == "dearer"

    run_id = "20261123-125000"
    _write_run(home, run_id, {"c1": "a" * 64, "c2": "b" * 64},
               {"default": _steps(), "lean": _steps()}, expensive + cheap, repeat=2)
    assert main(["bench", "report", run_id]) == 0
    line = next(line for line in capsys.readouterr().out.splitlines() if " pts " in line)
    assert "cost" in line and "cheaper" in line


def test_pareto_marks_undominated_variants(home, capsys):
    """evals-t01: a variant is on the cost/solved Pareto front when no other variant has a
    solved rate at least as high and a cost per cell at least as low, one strictly better."""
    cells = {
        "default": [_cell("default", "solo", cost=0.50)],                  # rate 1.0 at $0.50
        "twin": [_cell("twin", "solo", cost=0.50)],                        # the same point
        "cheap": [_cell("cheap", "x", cost=0.10),
                  _cell("cheap", "y", cost=0.10, outcome="failed")],       # rate 0.5 at $0.10
        "dear": [_cell("dear", "solo", cost=2.00)],                        # rate 1.0 at $2.00
    }
    stats_by_variant = {variant: stats.variant_stats(variant_cells)
                        for variant, variant_cells in cells.items()}
    assert stats.pareto(stats_by_variant) == {"default", "twin", "cheap"}   # dear is dominated
    assert stats.pareto({"only": stats_by_variant["default"]}) == {"only"}

    # The report marks Pareto-front variants with a `*`.
    run_id = "20261123-123000"
    _write_run(home, run_id, {"solo": "a" * 64, "x": "b" * 64, "y": "c" * 64},
               {variant: _steps() for variant in cells},
               [cell for variant_cells in cells.values() for cell in variant_cells])
    assert main(["bench", "report", run_id]) == 0
    out = capsys.readouterr().out
    for variant in ("default", "twin", "cheap"):
        row = next(line for line in out.splitlines()
                   if line.split() and line.split()[0].rstrip("*") == variant)
        assert "*" in row, f"{variant} should be marked as on the Pareto front"
    dear_row = next(line for line in out.splitlines()
                    if line.split() and line.split()[0].rstrip("*") == "dear")
    assert "*" not in dear_row


def test_compare_takes_run_and_variant_sides(home, capsys):
    """evals-t01: `factory bench compare` takes a run id or RUN:VARIANT per side; two run
    ids pair same-named variants, RUN:VARIANT compares exactly those two variants in one
    run or across runs, and the header lines stay."""
    A, B = "20261123-130000", "20261123-130500"

    def write(run_id, model, sha_c2):
        cases = {"c1": "a" * 64, "c2": sha_c2}
        variants = {"default": _steps(model), "default@scripted:good": _steps(model)}
        cells = [_cell(variant, case, cost=0.10) for variant in variants for case in cases]
        _write_run(home, run_id, cases, variants, cells)

    write(A, "fake:old", "a" * 64)
    write(B, "fake:new", "b" * 64)

    # Two run ids pair the same-named variants, one comparison line per pair.
    assert main(["bench", "compare", A, B]) == 0
    out = capsys.readouterr().out
    for expected in ("cases: 2 in both", "changed: c2", "variants: 2 in both",
                     "model fake:old → fake:new"):
        assert expected in out
    assert len([line for line in out.splitlines() if " pts " in line]) == 2

    # RUN:VARIANT sides compare exactly those two variants, across runs or in one run.
    assert main(["bench", "compare", f"{A}:default", f"{B}:default@scripted:good"]) == 0
    out = capsys.readouterr().out
    assert "cases:" in out and "variants:" in out
    assert len([line for line in out.splitlines() if " pts " in line]) == 1

    assert main(["bench", "compare", f"{A}:default", f"{A}:default@scripted:good"]) == 0
    out = capsys.readouterr().out
    assert len([line for line in out.splitlines() if " pts " in line]) == 1

    # Unknown sides are refused like an unknown run.
    assert main(["bench", "compare", "19990101-000000:default", A]) == 1
    assert "unknown bench run" in capsys.readouterr().err
    assert main(["bench", "compare", f"{A}:nope", A]) == 1
    assert "nope" in capsys.readouterr().err


def test_report_and_compare_print_json(home, capsys):
    """evals-t01: `--json` prints one JSON object with the runs, each variant's rates,
    intervals, pass^k, costs and Pareto flag, and each comparison's differences."""
    run_id = "20261123-090000"
    cells = []
    for case in ("c1", "c2"):
        for repeat in (1, 2):
            cells += [_cell("default", case, repeat=repeat, outcome="failed", cost=0.10),
                      _cell("lean", case, repeat=repeat, cost=0.30),
                      _cell("dear", case, repeat=repeat, cost=0.90)]
    _write_run(home, run_id, {"c1": "a" * 64, "c2": "b" * 64},
               {"default": _steps(), "lean": _steps(), "dear": _steps()}, cells, repeat=2)

    assert main(["bench", "report", run_id, "--json"]) == 0
    data = json.loads(capsys.readouterr().out)      # one JSON object, no text around it
    assert data["runs"] == [run_id]
    variants = data["variants"]
    assert set(variants) == {"default", "lean", "dear"}
    for entry in variants.values():
        assert set(entry) >= {"cases", "cells", "solved", "pass_k", "cost_per_cell",
                              "cost_per_solved", "pareto"}
    assert variants["default"]["cases"] == 2 and variants["default"]["cells"] == 4
    assert variants["default"]["solved"]["rate"] == pytest.approx(0.0)
    assert variants["default"]["cost_per_solved"] is None          # nothing was solved
    assert variants["default"]["pareto"] is True                  # cheapest, unsolved
    assert variants["lean"]["solved"]["rate"] == pytest.approx(1.0)
    assert _bounds(variants["lean"]["solved"]["ci"]) == pytest.approx((1.0, 1.0))
    assert variants["lean"]["pass_k"]["k"] == 2
    assert variants["lean"]["pass_k"]["rate"] == pytest.approx(1.0)
    assert variants["lean"]["cost_per_cell"]["mean"] == pytest.approx(0.30)
    assert _bounds(variants["lean"]["cost_per_cell"]["ci"]) == pytest.approx((0.30, 0.30))
    assert variants["lean"]["cost_per_solved"] == pytest.approx(0.30)
    assert variants["lean"]["pareto"] is True
    assert variants["dear"]["pareto"] is False                     # lean dominates it

    assert len(data["comparisons"]) == 2                           # each variant vs the first
    comparison = next(c for c in data["comparisons"] if "lean" in c["b"])
    assert set(comparison) >= {"a", "b", "cases", "solved_diff", "cost_diff", "per_case"}
    assert comparison["cases"] == 2
    assert comparison["solved_diff"]["mean"] == pytest.approx(1.0)
    assert comparison["solved_diff"]["verdict"] == "better"
    assert _bounds(comparison["solved_diff"]["ci"]) == pytest.approx((1.0, 1.0))
    assert comparison["solved_diff"]["resolution"] == pytest.approx(0.0)
    assert comparison["cost_diff"]["mean"] == pytest.approx(0.30 - 0.10)
    assert comparison["cost_diff"]["verdict"] == "dearer"
    by_case = {row["case"]: row for row in comparison["per_case"]}
    assert set(by_case) == {"c1", "c2"}
    assert all(row["a"] == 0.0 and row["b"] == 1.0 for row in by_case.values())

    # A single-repeat run omits pass^k, and a lone variant has no comparisons.
    single = "20261123-093000"
    _write_run(home, single, {"c": "a" * 64}, {"default": _steps()}, [_cell("default", "c")])
    assert main(["bench", "report", single, "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["variants"]["default"]["pass_k"] is None
    assert data["comparisons"] == []

    other = "20261123-091500"
    _write_run(home, other, {"c1": "a" * 64, "c2": "b" * 64},
               {"default": _steps(), "lean": _steps()},
               [cell for cell in copy.deepcopy(cells) if cell["variant"] in ("default", "lean")],
               repeat=2)
    assert main(["bench", "compare", run_id, other, "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert len(data["runs"]) == 2 and {run_id, other} <= set(data["runs"])
    assert data["comparisons"] and all(
        set(comparison) >= {"a", "b", "cases", "solved_diff", "cost_diff", "per_case"}
        for comparison in data["comparisons"])
