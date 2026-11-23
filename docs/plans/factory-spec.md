# Plan: Software factory specification

**Status:** Planned (2026-11-17). Roadmap [item 15](../../NEXT.md#15-specify-the-shipped-factory).

## Execution Plan

### Locked Decisions

| Decision | Choice |
|---|---|
| Audience and authority | An implementer can use the series to predict observable behavior. The first edition describes the factory shipped on `main` at `8bd7012`. Code and its behavioral tests establish each requirement. |
| Files and reading order | Publish plain text in `docs/spec/`, using the literal filenames `00-spec.txt` through `09-spec.txt`. `00` maps numbers to chapter titles. |
| Coverage | Cover the whole factory from project initialization to a merged PR, including local operations, the web board, statistics and benchmarks. |

### Milestones

| Milestone | Deliverable | Exit criterion | Parallel with |
|---|---|---|---|
| M1 | Nine topic chapters | Each topic has a numbered, readable chapter with rules, examples and implementation evidence. | The five M1 tasks have disjoint write scopes. |
| M2 | Overview and specification guide | A reader can trace one task through the factory and find every chapter by exact filename and title. | Begins once all M1 tasks have a PR or have merged. |

### Task Contracts

| Milestone | Task | Coverage |
|---|---|---|
| M1 | `factory-spec-t01` | 01 project inputs and contracts, 02 board and scheduling |
| M1 | `factory-spec-t02` | 03 flows and attempts, 04 isolation and authority |
| M1 | `factory-spec-t03` | 05 verification gates, 06 PR lifecycle and rework |
| M1 | `factory-spec-t04` | 07 operator interfaces, 08 observability and statistics |
| M1 | `factory-spec-t05` | 09 benchmarks and scoring |
| M2 | `factory-spec-t06` | 00 overview, glossary, reading guide and edition-wide reference check |

```yaml
- id: factory-spec-t01
  goal: Write docs/spec/01-spec.txt (project inputs and contracts) and 02-spec.txt (board and scheduling) for the shipped factory.
  spec_refs: [docs/plans/factory-spec.md#chapter-conventions, factory/scaffold.py, factory/config.py, factory/contracts.py, factory/db.py, factory/scheduler.py, docs/reference.md#task-contracts]
  depends_on: []
  non_goals: [Runtime or schema changes, prescribing database layout, writing other chapters]
  acceptance:
    - '01 explains init and repeat init, precedence of project settings and state location, plan discovery, the eight contract keys and their validation, cross-plan IDs, cycles, and manual-only verification. Include a valid contract and a rejected dependency example.'
    - '02 distinguishes stored states from derived readiness and liveness. Map sync, eligible dependencies, open PR stacking, parallel limits, holds, failures and reruns to board outcomes. Trace a failed prerequisite alongside an independent task.'
    - 'Both chapters follow Chapter conventions, cite source and named behavioral tests, and add a single session entry for this task at docs/sessions/YYYY-MM-DD-factory-spec-t01.md using the execution date.'
  verification:
    - 'test -s docs/spec/01-spec.txt && test -s docs/spec/02-spec.txt'
    - 'uv run --offline pytest -q tests/test_contract_schema.py::test_parse_contract_exact_8_keys tests/test_dependencies.py::test_reject_cycle_and_unknown_id tests/test_db.py::test_upsert_keeps_status_and_refreshes_contract tests/test_scheduler.py::test_a_failure_blocks_only_its_dependents'
  risk: low

- id: factory-spec-t02
  goal: Write docs/spec/03-spec.txt (flows and attempts) and 04-spec.txt (isolation and authority) for the shipped factory.
  spec_refs: [docs/plans/factory-spec.md#chapter-conventions, factory/flows.py, factory/agents.py, factory/pipeline.py, factory/tools.py, factory/sandbox.py, factory/github.py]
  depends_on: []
  non_goals: [Runtime or security changes, copying role prompts, documenting unmerged flow options]
  acceptance:
    - '03 gives the built-in order, configured selection and overrides, role outputs, verdict parsing, gate insertion and retry/stop conditions. Contrast the built-in default with a valid gates-before-review example and trace a rejected attempt.'
    - '04 maps each actor to its authority over the main checkout, worktree, dependency sources, cache, provider requests and GitHub. Document default shell isolation, file tool scope, network and sandbox overrides and their limits. Illustrate a refused write or command using an existing test.'
    - 'Both chapters follow Chapter conventions, cite source and named behavioral tests, and add docs/sessions/YYYY-MM-DD-factory-spec-t02.md using the execution date.'
  verification:
    - 'test -s docs/spec/03-spec.txt && test -s docs/spec/04-spec.txt'
    - 'uv run --offline pytest -q tests/test_flows.py::test_gates_go_after_the_last_review_unless_placed tests/test_flows.py::test_each_kind_gets_its_tools tests/test_tools.py::test_writes_go_anywhere_in_the_worktree_but_git tests/test_tools.py::test_reads_reach_dependency_sources_only'
  risk: medium

- id: factory-spec-t03
  goal: Write docs/spec/05-spec.txt (verification gates) and 06-spec.txt (PR lifecycle and rework) for the shipped factory.
  spec_refs: [docs/plans/factory-spec.md#chapter-conventions, factory/gates.py, factory/verification.py, factory/pipeline.py, factory/prbody.py, factory/cli.py, factory/stack.py, factory/reviews.py, factory/ci.py, factory/merges.py]
  depends_on: []
  non_goals: [Changes to gates or GitHub behavior, live GitHub checks, restating every board state]
  acceptance:
    - '05 lists gates in evaluation order, the candidate and base used, when checks apply or can be skipped, and how failed and inconclusive commands affect publication. Show a zero-test result and distinguish the session-log naming convention from what the gate enforces.'
    - '06 traces PR creation and verifier fallback, the no-PR path, dependency branches, bottom-up merging, refresh and restack. Specify the order of conflict, human review and CI rework, review eligibility and watermark, candidate ownership, leased update and failure outcomes. Explain how a restacked head relates to the last gated commit.'
    - 'Both chapters follow Chapter conventions, cite source and named behavioral tests, and add docs/sessions/YYYY-MM-DD-factory-spec-t03.md using the execution date.'
  verification:
    - 'test -s docs/spec/05-spec.txt && test -s docs/spec/06-spec.txt'
    - 'uv run --offline pytest -q tests/test_verification.py::test_zero_filtered_test_is_not_pass tests/test_ci.py::test_red_only_judges_the_factorys_own_candidate tests/test_reviews.py::test_addressed_reviews_no_longer_count'
  risk: medium

- id: factory-spec-t04
  goal: Write docs/spec/07-spec.txt (operator interfaces) and 08-spec.txt (observability and statistics) for the shipped factory.
  spec_refs: [docs/plans/factory-spec.md#chapter-conventions, factory/cli.py, factory/version.py, factory/web/server.py, factory/web/jobs.py, factory/web/views.py, factory/observe.py, factory/log.py, factory/prices.py, factory/stats.py, docs/reference.md#commands]
  depends_on: []
  non_goals: [New commands or web endpoints, reproducing help text, promising a stable SQLite or transcript serialization]
  acceptance:
    - '07 maps every shipped top-level CLI command to its observable effect or owning chapter. Cover task and plan targets, stop, clean, hold/requeue, read-only status versus refresh, version output, and how local web reads, action eligibility, request checks, run forms and background jobs relate to those commands.'
    - '08 distinguishes logs, traces, transcripts, task/run records and stats. Cover missing optional fields in older records, model-provided reasoning when available, token and cost accounting, prompt versions, merge outcomes, time and plan filters, and metric denominators. Give a small first-attempt pass-rate example that agrees with the stats tests.'
    - 'Both chapters follow Chapter conventions, cite source and named behavioral tests, and add docs/sessions/YYYY-MM-DD-factory-spec-t04.md using the execution date.'
  verification:
    - 'test -s docs/spec/07-spec.txt && test -s docs/spec/08-spec.txt'
    - 'uv run --offline pytest -q tests/test_web.py::test_each_action_runs_its_factory_command_as_a_job tests/test_observe.py::test_transcripts_without_thoughts_print_as_before tests/test_stats.py::test_first_attempt_pass_rate_and_attempts_per_pr'
  risk: low

- id: factory-spec-t05
  goal: Write docs/spec/09-spec.txt specifying how a shipped benchmark case is run, scored and compared.
  spec_refs: [docs/plans/factory-spec.md#chapter-conventions, factory/bench/cases.py, factory/bench/run.py, factory/bench/report.py, docs/architecture.md#evaluating-flows-factory-bench]
  depends_on: []
  non_goals: [Running paid benchmarks, changing fixtures or scoring, ranking providers]
  acceptance:
    - 'Cover case inputs, reference solutions, hidden tests and their visibility, variant/case/repeat cells, isolated state, budget and interruption semantics. Explain run/report/compare/list/cases, recorded results and what a changed case, prompt or model means for a comparison.'
    - 'Use a worked cell to distinguish gate failure, gates passing with hidden tests failing, and a solved cell. Use the exact outcome names and denominators in the implementation. Follow Chapter conventions, cite source and named tests, and add docs/sessions/YYYY-MM-DD-factory-spec-t05.md using the execution date.'
  verification:
    - 'test -s docs/spec/09-spec.txt'
    - 'uv run --offline pytest -q tests/test_bench_cases.py::test_hidden_and_solution_files_stay_out_of_the_starting_tree tests/test_bench.py::test_report_shows_solved_rates_per_variant_and_case tests/test_bench.py::test_compare_flags_changed_cases_models_and_prompts'
  risk: low

- id: factory-spec-t06
  goal: Publish docs/spec/00-spec.txt as the implementer's entry point to the complete numbered series.
  spec_refs: [docs/plans/factory-spec.md#chapter-conventions, docs/architecture.md#policy, docs/reference.md#commands]
  depends_on: [factory-spec-t01, factory-spec-t02, factory-spec-t03, factory-spec-t04, factory-spec-t05]
  non_goals: [New product behavior, a second command manual, rewriting historical plans]
  acceptance:
    - '00 states the audience, edition baseline and meaning of requirement words, defines the shared terms, and indexes each of 01 through 09 once in the reading guide by exact basename and title. Give separate reading paths for implementing a task run and diagnosing an operator-visible failure.'
    - 'Trace one example from contract discovery through a stacked PR and human merge. Identify the evidence and who can change state at each decision. Apply the same conventions as the topic chapters.'
    - 'Check every numbered filename and section cross-reference in the completed series, and check that cited source paths and test names exist. Limit integration fixes in 01 through 09 to reference, title and terminology corrections. Record the results in docs/sessions/YYYY-MM-DD-factory-spec-t06.md using the execution date.'
  verification:
    - >-
      python3 -c "from pathlib import Path; import re; d=Path('docs/spec'); names={f'{i:02}-spec.txt' for i in range(10)}; assert {p.name for p in d.glob('*.txt')} == names; book={n:(d/n).read_text(encoding='utf-8') for n in names}; assert all(s.strip() for s in book.values()); refs=lambda s:set(re.findall(r'\b[0-9]{2}-spec\.txt\b', s)); assert names-{'00-spec.txt'} <= refs(book['00-spec.txt']); assert all(refs(s) <= names for s in book.values())"
    - 'uv run --offline pytest -q tests/test_scheduler.py::test_one_run_gives_a_pr_per_task_with_dependents_stacked'
  risk: low
```

No external prerequisites. The five topic tasks can start together from the merged plan. The overview task reads their combined result and is the only task allowed to revise their cross-references.

### Risks

1. **A branch or roadmap proposal looks shipped.** **Action:** Use `8bd7012` as the first-edition baseline. Check contested claims against the code and tests at that revision. Keep future behavior in its workstream plan.
2. **A guide overstates a guarantee.** **Action:** In each chapter, give the default, the applicable override and a failure example. For instance, the configured session-log check examines changed paths under the log directory. The project's dated filename is a writing convention.
3. **Opaque filenames make a rule hard to find.** **Action:** Use the same title in the chapter and index, give each rule one home, and verify section references once all chapters are present.

## Problem

[README.md:5](../../README.md) points readers to an architectural explanation and a command reference. Following one rule across them can miss a condition. For example, `docs/architecture.md:589` describes the gates, `factory/gates.py:112` determines which checks apply, and `factory/verification.py` classifies command output. An implementer needs one place to find the required result for a clean candidate whose verification selects zero tests.

## Goal

A reader can look up the inputs, decision and visible outcome for a factory operation, and use a named test or source symbol to verify the rule. The overview provides a complete path through the system for readers who encounter the factory for the first time.

## Design

### Chapter conventions

Use UTF-8 plain text. Each file starts with its two-digit number and title, the first edition's baseline (`8bd7012`), a scope statement, and numbered sections. Use stable references such as `05-spec.txt section 2`. The overview introduces MUST, SHOULD and MAY for required, recommended and optional behavior. Describe examples and implementation notes separately from requirements. State observable preconditions and outcomes, including an unsuccessful or conditional path. Cite repository-relative source paths with symbol names and relevant pytest node IDs. Mark behavior evidenced solely by source as such.

The reference series in `did-spec/docs/spec` inspired the overview, reading guide, status, numbered sections and per-topic ownership. All instructions and verification inputs needed by the task worktrees are in this repository.

### Files changed by the contracts

| Path | Contents |
|---|---|
| `docs/spec/00-spec.txt` | Overview, reading guide, worked lifecycle and terminology |
| `docs/spec/01-spec.txt` through `docs/spec/09-spec.txt` | Topic chapters assigned in the milestone table |
| `docs/sessions/YYYY-MM-DD-factory-spec-tNN.md` | One entry per task, dated when executed |

## Test Plan and Verification

The chapters document existing behavior. Each topic contract checks its files and runs named existing behavioral tests offline. The overview adds a check for exact filenames, readable text, index coverage and unresolved chapter numbers. These checks establish structure and supporting behavior. The content review checks whether each example and normative statement follows from the cited code, including exceptions. No new unit or end-to-end tests are planned. Every task also gets the configured `uv run pytest -q` unit gate. The repository has no configured mandatory e2e gate. A pytest selection that runs zero tests fails verification.

## Cross-Workstream Coordination

- **Depends on:** shipped behavior at `8bd7012`. The edition has no cross-plan task dependencies.
- **Required by:** no existing workstream. Once published, future task contracts can cite numbered chapters and sections in `spec_refs`.
- **Related:** [strict-flow](strict-flow.md) changes flows, gates and bench. The [wiki plan](wiki.md) introduces a separately maintained knowledge base. Both are outside this edition's baseline. A later revision can cite their merged implementation and tests.

## Notes / Out of Scope

The product deliverable is the numbered specification. Operator tutorials, protocol changes, new runtime checks, speculative capabilities and changes to existing task contracts are outside this workstream.
