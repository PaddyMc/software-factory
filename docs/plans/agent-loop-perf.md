# Plan for live evaluation of the agent loop

**Planned 2026-11-23.** Roadmap item 22. Each task produces one PR. The live evaluation runs on demand or on a maintainer's schedule.

## Execution Plan

### Locked Decisions

| Decision | Choice |
|---|---|
| Subject | Run the real agent loop with the models, prompts and step limits resolved by the checkout under evaluation. Cover the built-in `default` and `strict` flows. |
| Trigger | Give the maintainer one command suitable for a timer. PRs keep their existing checks and human merge process. |
| Correctness | Grade the produced change with executable checks held outside the agent worktree. Report a false pass when the factory verifies an incorrect change. |
| Performance | After correctness, judge typical elapsed time against the same flow on the same cases over repeats. A confirmed regression blocks recommending the candidate setup. |
| Cost | Report spend and cost per solved task. Every paid invocation requires an explicit budget. Results are advisory for choosing a configuration. |

### Milestones

| Milestone | Task | Deliverable and exit | Parallel work |
|---|---|---|---|
| M1 | `agent-loop-perf-t01` | Three versioned cases materialize offline. The base fails and the reference passes each independent check. | M2 |
| M2 | `agent-loop-perf-t02` | A completed cell explains how much time, money and work went into each role, including retries. | M1 |
| M3 | `agent-loop-perf-t03` | A saved comparison can be replayed offline and gives the expected verdict on known regressions, noise and incomplete data. | — |
| M4 | `agent-loop-perf-t04` | One budgeted command drives both real configurations, saves comparable evidence and prints the deciding case and role. A zero-spend dry run describes the same workload. | — |
| M5 | `agent-loop-perf-t05` | A maintainer records the first live baseline with the results table and enough provenance to repeat it. | — |

### Task Contracts

```yaml
- id: agent-loop-perf-t01
  goal: "Build the three pinned historical cases in benchmarks/agent-loop/ with independent executable checks and an offline exporter for the existing bench --cases interface."
  spec_refs: ["docs/plans/agent-loop-perf.md#reference-tasks", "factory/bench/cases.py", "docs/spec/09-spec.txt"]
  depends_on: [bench-t06]
  non_goals: ["Generic task mining, external datasets, live models, scoring model-generated prose with another model, modifying the five shipped fixtures"]
  acceptance:
    - "From a full local clone, export the three Reference tasks from recorded Git objects into native cases. Preserve the relevant source tree, visible contract checks and project tests. Document the mapping from historical task ID to native case contract ID. Agents receive only the starting tree, with no reference commit reachable in its Git history."
    - "Each case has a stable manifest with base, reference, extraction rules and held-out check identity. It materializes twice with the same digest independent of destination. The agent sandbox cannot read the evaluator checkout, sibling reference solutions or held-out files. Missing Git objects or locked offline dependencies name the missing prerequisite before a model can be called."
    - "The checks demonstrate a behavioral failure on base, pass on reference and reject one plausible wrong answer per case described in Reference tasks. A broken import caused by a missing dependency, a collection error or zero tests cannot qualify a case. The reference also passes the case's visible checks."
    - "Exercise export, solvability and rejection offline with small local Git fixtures. Record this task's dated session entry under docs/sessions/."
  verification:
    - "uv run --offline pytest -q tests/test_loop_perf_cases.py::test_pinned_cases_export_reproducibly tests/test_loop_perf_cases.py::test_base_reference_and_wrong_answer tests/test_loop_perf_cases.py::test_answers_and_future_commits_stay_out_of_the_cell"
    - "uv run --offline pytest -q tests/test_bench_cases.py"
  risk: medium

- id: agent-loop-perf-t02
  goal: "Add a read-only bench evidence reader under factory/bench/ that joins existing results, resolved role settings and each cell's run rows into a portable record."
  spec_refs: ["docs/plans/agent-loop-perf.md#evidence-per-run", "factory/bench/run.py", "factory/db.py"]
  depends_on: [strict-flow-t08]
  non_goals: ["Changing production instrumentation, adding a database migration, estimating missing cost, running models, changing the standard bench result or exit code"]
  acceptance:
    - "For each cell keep outcome, end-to-end seconds, attempts and spend. Enumerate every role invocation with flow step, role, recorded model, attempt, outcome, elapsed seconds, calls, input/output tokens and cost when known. Show totals by step across retries. Keep gate time distinct from verifier-report time and cell wall time distinct from summed role time."
    - "Join the resolved per-step model, prompt digest, step limit and flow options from the run manifest. Preserve differences between arms and expose missing or conflicting attribution. Older or interrupted runs remain readable. Mark missing records, elapsed time and unpriced calls as unknown."
    - "Read closed cell databases without modifying them and export aggregate evidence without prompts, transcripts, patches, credentials or model reasoning. Include this task's dated session entry under docs/sessions/."
  verification:
    - "uv run --offline pytest -q tests/test_loop_perf_evidence.py::test_role_time_includes_every_tester_pass tests/test_loop_perf_evidence.py::test_gate_is_distinct_from_verifier_report tests/test_loop_perf_evidence.py::test_missing_evidence_is_unknown_and_read_only"
    - "uv run --offline pytest -q tests/test_bench.py::test_compare_flags_changed_cases_models_and_prompts"
  risk: low

- id: agent-loop-perf-t03
  goal: "Implement the offline decision rule in factory/bench/loop_verdict.py so two saved samples can establish whether to recommend a candidate loop configuration."
  spec_refs: ["docs/plans/agent-loop-perf.md#decision-rule", "docs/plans/agent-loop-perf.md#evidence-per-run"]
  depends_on: [agent-loop-perf-t02]
  non_goals: ["Sampling providers, changing factory bench compare, ranking strict against default, statistical claims about all factory tasks"]
  acceptance:
    - "Apply the Decision rule independently to default and strict. Return pass, regression or inconclusive with the decisive flow, case counts, timing deltas and underlying reason. A false pass or repeated loss of solves takes precedence over improvements in time or cost."
    - "Compare matched solves on identical fixtures and settings under test as specified below. An absent repeat, interrupted run, budget stop, provider error, mismatched workload or missing timing never yields a pass. Detect reused samples offered as independent confirmation."
    - "Expose median time, paired ratios, absolute deltas, cost per solve including the spend on unsuccessful work, and the largest measured changes by step. Zero solves or incomplete pricing has an explicit unavailable value. Cover threshold boundaries and the two-window rule with deterministic tests. Add this task's dated session entry under docs/sessions/."
  verification:
    - "uv run --offline pytest -q tests/test_loop_perf_verdict.py::test_quality_precedes_speed tests/test_loop_perf_verdict.py::test_slowdown_needs_two_independent_windows tests/test_loop_perf_verdict.py::test_incomplete_or_unmatched_evidence_is_inconclusive tests/test_loop_perf_verdict.py::test_fast_failures_never_improve_latency"
  risk: medium

- id: agent-loop-perf-t04
  goal: "Deliver benchmarks/agent-loop/run.py and a short operator guide that run or rescore the evaluation on demand or from a timer, with a shared spending limit."
  spec_refs: ["docs/plans/agent-loop-perf.md#operating-the-evaluation", "docs/plans/agent-loop-perf.md#decision-rule", "factory/bench/run.py"]
  depends_on: [agent-loop-perf-t01, agent-loop-perf-t03]
  non_goals: ["Changing the review or merge queue, installing a timer, changing default prompts or models, opening PRs from cells, automatically promoting a baseline"]
  acceptance:
    - "Support preview, run and offline report, using the interface in Operating the evaluation. Pin both source revisions, run the bench from the correct install for each arm, and prove the resolved per-role config and prompt identities are from that revision. An optional second window can confirm a first window. Keep the initial baseline independently reproducible."
    - "Run all three cases and both flows with three repeats per arm, serially, counterbalancing arm order. Use the same sandbox, frozen case inputs and equally seeded offline dependency cache for each arm. Sandbox preflight validates every case before the first paid call. Outcomes and timings come from the real bench with publication disabled."
    - "Require an explicit positive shared budget for a live run and known prices for active models. Run one cell at a time against the remaining allowance, stop scheduling on exhaustion and record interrupted or partial results. Use separate result directories, preserve finished evidence, and prevent overlapping timer invocations on the same runner."
    - "Print and save the verdict for each flow, the changed role configuration, the time breakdown and spend. Explain the exit codes, setup of a provider-side spending ceiling, and opt-in scheduling in docs/agent-loop-perf.md. Offline tests drive the normal command with a fixture bench executable and assert both revisions and all configured roles are exercised. Add this task's dated session entry under docs/sessions/."
  verification:
    - "uv run --offline pytest -q tests/test_loop_perf_run.py::test_preview_resolves_both_real_configurations_without_calls tests/test_loop_perf_run.py::test_run_and_report_use_the_same_recorded_cells tests/test_loop_perf_run.py::test_budget_and_interruption_cannot_turn_green tests/test_loop_perf_run.py::test_schedule_overlap_does_not_start_a_second_run"
  risk: medium

- id: agent-loop-perf-t05
  goal: "Record a live-model calibration in docs/agent-loop-baseline.md using the same pinned baseline configuration for both arms, with per-flow correctness, timing, attribution and spend."
  spec_refs: ["docs/plans/agent-loop-perf.md#first-live-baseline", "docs/plans/agent-loop-perf.md#operating-the-evaluation"]
  depends_on: [agent-loop-perf-t04]
  non_goals: ["Launching paid calls from factory task verification, picking a new production model, activating a schedule, recording raw agent transcripts"]
  acceptance:
    - "Record the run date, output of factory version for the tested install, immutable baseline commit, profile digest, effective role models, prompt digests, repeats, run identifiers, authorized budget and observed spend. Publish the sanitized evidence for the completed window alongside the baseline note so another maintainer can reproduce its verdict offline."
    - "Show solved/planned and false passes by flow and case, typical elapsed time, time in the slowest role including retries and cost per solved task. Explain an inconclusive result. A partial or saturated sample is labelled with its coverage limits. Promote a timing reference only from a complete comparable window. A regression in the same-setup comparison is evidence to investigate before adoption."
    - "Add this task's dated session entry under docs/sessions/."
  verification:
    - "factory version"
    - "uv run --offline pytest -q tests/test_loop_perf_baseline.py::test_published_baseline_recomputes_from_recorded_cells"
    - "test -s docs/agent-loop-baseline.md"
  risk: medium
```

All `test_loop_perf_*.py` node IDs above are planned additions, owned by the task that verifies them. Existing `test_bench*.py` commands select tests already on main. A missing node, a skipped required check or an empty selection cannot verify a task. Each task writes `docs/sessions/<execution-date>-<task-id>.md`. The repository also runs `uv run pytest -q` as its unit gate.

**Prerequisite for `agent-loop-perf-t05`.** A maintainer supplies provider access, a runner with bubblewrap, prepared offline dependencies and an explicit spending allowance for the live sample. Do this task by hand. Capture `factory version` from the tested install. The factory refuses nested factory commands and will flag this contract as manual. Its pytest check verifies the published evidence offline and accepts an honestly recomputed inconclusive verdict for a complete sample. The first four tasks verify offline.

### Risks

1. **Provider variation.** A slow endpoint can affect one arm for an entire run. **Action.** Alternate arm order, keep runner and cache policy fixed and reproduce a slowdown in a fresh window.
2. **Easy or weak checks.** A suite can score perfectly while accepting a bad change. **Action.** For each case require red on base, green on reference and red on a deliberately wrong answer and publish the exact scope of the docs check.
3. **Budget or samples run out.** Fast failures can make a partial candidate look quick. **Action.** Keep every planned cell in the denominator, stop on budget exhaustion and mark missing evidence inconclusive.
4. **The evaluator moves with the candidate.** Editing the grader or grading inputs could improve a score. **Action.** Pin a common trusted suite, driver and decision rule for both arms. Changing them starts a new baseline series.

## Problem

In the saved live replay `20261122-231249`, both flows solved `pr-descriptions-t01` on their first build attempt. The default flow took 17.1 minutes and cost $0.90. Strict took 46.5 minutes and cost $2.09. The builder took 5.6 and 5.5 minutes respectively. Strict's tester spent 23.1 minutes on a pass that went out of scope and 7.3 minutes on the retry. Both reached 60 calls. One observation identifies where to investigate. Three repeats and a confirmation window can tell a maintainer whether the slowdown recurs. The earlier shipped-fixture run `20261116-220919` solved 60/60 cells.

At `4b89b00`, `factory/bench/run.py:119` records resolved step settings, `factory/bench/run.py:290` collects cell totals, and `factory/db.py:38` stores role-level runs. The ordinary bench exit code signals execution errors and budget stops. Failed and false-pass cells are reported as measured outcomes. [Bench semantics](../spec/09-spec.txt) · [Existing report](../../factory/bench/report.py)

## Goal

A maintainer can name two agent configurations and answer, for each flow, whether the candidate still solves the held-out tasks, whether it takes materially longer and which role accounts for the difference. The signal governs recommending a setup. Merging work continues through the existing human process.

## Design

### Reference tasks

Use a separately exported native `--cases` suite with three workloads. Materialize each starting tree from local Git objects using the first parent of the named merge and keep the merged result available only to the evaluator. Preserve source, tests, relevant guidance and historical task intent. Record any normalization needed for native case IDs, plan paths, session logs and offline commands. Pre-seed locked dependencies symmetrically. Export into a location hidden from the workload sandbox and probe readability there. The full source repository, modern plans, reference patches and later Git objects must also be inaccessible to the sandbox. Reuse the native benchmark's isolation and hidden scoring.

| Case | Pinned reference and starting point | What the external check observes |
|---|---|---|
| `loop-spec` | `factory-spec-t05`, `23ec03a` and its first parent `57e5ad2` | The chapter describes a failed visible gate, a false pass, and a solve with the correct outcome and denominator, and cites existing test nodes. Reject a plausible chapter that swaps the latter two outcomes while retaining the keywords. This grades the named claims. |
| `loop-prbody` | `pr-descriptions-t01`, `33e7a89` and its first parent `15df83c` | Exercise last-draft extraction and an overlong review through the PR-body formatter. Check length, retained final content, balanced fences and the usable pointer to the full report. Reject a cap that silently drops the pointer. |
| `loop-pytest` | Verification regression `d010ab8` and its first parent `d2e5876` | Give the agents the observed counting bug. Held-out captured output contains quoted misleading counts, a genuine final pytest summary and an actual empty run. Reject a parser that counts traceback text. |

Ship the manifests, graders and small tracking files. Generate the old repository trees on demand. The prototype under `/tmp` and its cached dependencies are historical evidence only. Its two starting commits differ from these first-parent snapshots, so its measurements do not establish the baseline. A full clone and a warm cache for the pinned lockfiles are operator prerequisites. Use tiny synthetic Git histories and local dependencies to run exporter tests offline even in shallow CI clones.

### Evidence per run

Keep a portable versioned record of driver and suite identity, runner class, cache policy, arm commit, factory version, actual command, case and holdout digests, run ID, repeats, sandbox setting and step settings. Resolve the built-ins against each arm's own `.factory/config.yaml` and shipped or overridden prompts. Leave the global `--model` override unset so the tester, builder, reviewer and verifier use their configured assignments. The default planner and strict tester are flow-specific roles. Capture the model actually observed in each role run, flag unexplained discrepancies, and retain the role's step limit and outcome. Missing role evidence makes attribution unavailable. A missing or unexpected required model identity makes configuration verification inconclusive.

For wall time use the native cell's `seconds`, which includes the agent loop, gates and hidden grading. Show gate and grader/setup time separately where measured and label the remaining unmeasured interval. A replacement role, retry, or step-limit outcome remains visible. Sum cost for all measured calls, including unsuccessful work, and divide by the number of solved tasks for cost per solve.

### Decision rule

One window is three workloads × three repetitions × two flows **per arm**. Compare `strict` with `strict` and `default` with `default`. Use the same suite and base SHA per case, repeats, sandbox, attempt cap, runner class and cache policy. Model assignments, prompts and the harness revision may differ intentionally and are printed. One fully fresh window contains 36 cells. A confirmation uses new observations for both arms and carries their run IDs. Rescoring is free.

1. **Validate the sample.** Include every planned cell. Unmatched cases, duplicated observations, missing required metadata, provider errors, stopped or skipped cells and budget exhaustion are inconclusive. Report proven quality failures even when another observation is missing. A false pass is credible only when the independent check ran and demonstrated a behavior failure. Infrastructure faults remain inconclusive.
2. **Judge correctness first.** Any credible candidate false pass yields `regression` and names the failed check. For each case compare solved counts with that flow's baseline. A lower solve count gives `inconclusive` pending confirmation. A lower count on the same case in two fresh comparable windows gives `regression`. Report all baseline false passes for inspection. If a case has no successful baseline observations it cannot support a passing comparison.
3. **Judge speed on paired solves.** Pair by case, flow and repeat. Require at least two paired solves per case. For each case take the median candidate/baseline duration ratio and the median signed difference in seconds (candidate minus baseline). Take the median of the three case ratios and of their three differences, giving each case equal weight. A window signals a slowdown when the ratio is at least **1.20** and the difference is at least **60 seconds**. Two independent windows signalling that for the same flow yield `regression`. A single signal or a mixed confirmation yields `inconclusive`. An adequate window with no quality loss or slowdown yields `pass`. These are initial operating tolerances for this suite.
4. **Summarize both flows.** Any demonstrated regression takes priority, followed by inconclusive, then pass only if both flows pass. Cost is diagnostic. List per-case results alongside the median so a severe outlier remains visible.

### Operating the evaluation

Use the repo-local entry point from a trusted driver checkout with trusted source revisions. The following are the proposed operator commands.

```sh
python3 benchmarks/agent-loop/run.py preview --baseline-ref BASE --candidate-ref CANDIDATE
python3 benchmarks/agent-loop/run.py run --baseline-ref BASE --candidate-ref CANDIDATE --max-cost USD
python3 benchmarks/agent-loop/run.py run --confirm FIRST.json --max-cost USD
python3 benchmarks/agent-loop/run.py report --evidence RESULT.json
```

Resolve refs once to immutable commits. Provision each arm's own locked install and run its native bench in its own checkout and state directory, even when the two refs resolve to the same commit. Keep fixtures, evaluator checks and policy fixed across both. Schedule one cell at a time and alternate baseline-first and candidate-first pairs. The dry run lists every case, role assignment, limit and cell count without credentials. An external timer may invoke the same command with a fixed reviewed baseline, trusted candidate ref, budget and one-run lock. No timer is activated by the workstream.

Save a machine-readable evidence file outside Git by default and print its location. For scoring commands use exits 0 for pass, 1 for regression and 2 for inconclusive or an unusable sample. Preview success indicates only a valid workload. Avoid starting a cell with unknown pricing or no remaining allowance. Native accounting updates after model work and an in-flight call can exceed an estimate. Document the provider-side hard ceiling for operators who need a strict invoice limit. Keep provider credentials in the operator environment outside the task sandbox.

### First live baseline

Run with the same pinned revision in both arms. Time and cost cover the complete attempt, including a failed solve. Publish the table, policy and sanitized evidence. The calibration note shows whether this small suite can distinguish quality and repeat timing and which step accounts for any large difference. A first-window warning can be confirmed later under a separate explicit budget. This plan makes no model or prompt selection from the November replay.

## Files Changed

| Task | Implementation surface |
|---|---|
| t01 | `benchmarks/agent-loop/cases/`, export helper beside the cases, `tests/test_loop_perf_cases.py` |
| t02 | `factory/bench/loop_evidence.py`, `tests/test_loop_perf_evidence.py` |
| t03 | `factory/bench/loop_verdict.py`, `tests/test_loop_perf_verdict.py` |
| t04 | `benchmarks/agent-loop/run.py`, `tests/test_loop_perf_run.py`, `docs/agent-loop-perf.md` |
| t05 | `docs/agent-loop-baseline.md`, `benchmarks/agent-loop/baseline.json`, `tests/test_loop_perf_baseline.py` |
| Each | A separate dated session log |

## Test Plan and Verification

The exact pytest node IDs are in the contracts. Use scripted bench output for the orchestration tests and a temporary read-only copy of a cell database for evidence tests. Exercise the command from preview through both arms to offline reporting, including a new run whose provider errors or exhausts the budget. Qualify each real case offline before the live sample. The independent case checks decide correctness. The live calls in t05 exercise the actual models and roles. A dry run, a successful unit test or an old replay cannot stand in for that sample.

## Cross-Workstream Coordination

- **Depends on** the shipped [bench](bench.md) case format and runner (`bench-t06`) and [strict-flow](strict-flow.md) step settings (`strict-flow-t08`). They have no further delivery prerequisite here.
- **Related work.** [Flow tuning](flow-tuning.md) compares candidate configurations to choose a default. This plan compares revisions within each flow and keeps production settings in the maintainer's hands. The [proposed evals plan](https://github.com/PaddyMc/software-factory/pull/85) covers generic mining, splits, reused baselines, confidence intervals and a ledger. This workstream uses three pinned workloads and the shipped bench interface, so it can run independently. The [external evaluations plan](https://github.com/PaddyMc/software-factory/pull/100) can provide broader coverage separately.
- **Downstream.** No open workstream depends on this one. Maintainers can use its results to assess future loop, prompt or role-model changes.

## Out of Scope

Changes to PR volume, publication, restacking, GitHub merge rules, production defaults and model-provider integrations are separate work. The benchmark describes the sampled workloads and observed provider behavior. It does not certify arbitrary future tasks.
