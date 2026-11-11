# Plan: Evaluate flows and setups (factory bench)

**Status:** Planned (2026-11-11). Workstream scoped; awaiting kickoff: t01 can run now. Roadmap: [NEXT.md item 8](../../NEXT.md#8-compare-flows-and-setups), the `factory bench` half of [item 3](../../NEXT.md#3-nothing-measures-the-factory-itself).

---

## Execution Plan

### Locked Decisions

| Decision | Choice |
|---|---|
| What an eval runs on | **Synthetic fixture repositories shipped with the factory.** Each case is a small standard-library Python project with one task contract, hidden tests and a reference solution. `--cases DIR` runs a directory of your own cases in the same format. Replaying merged tasks from the board is out of scope |
| How a candidate is scored | **Gates plus hidden tests.** A cell is solved when the case's gates pass on the candidate and the case's hidden tests, laid over the candidate afterwards, pass too. The builder never sees the hidden tests, so it can't grade itself. Attempts, cost, time, model calls and reviewer verdicts are recorded for every cell |
| What a setup is | **A flow, optionally with one model for every step.** Variants are `--flow` × `--model`. Flows come from the invoking repository's `.factory/config.yaml`, and prompts, models and step limits resolve as `factory run` would resolve them there. There's no second config surface |
| Sequencing | **Independent of [measure](https://github.com/PaddyMc/software-factory/pull/18).** bench computes its own per-cell metrics. t01 and t02 touch only new files and run now. t03 waits for `agent-flows-t04` (flows in the pipeline, and the same `cli.py`), and the docs wait for `agent-flows-t05` |

### Milestones

| # | Deliverable | Exit criteria | Parallelizable with |
|---|---|---|---|
| **M1** | The case format and two cases | `tests/test_bench_cases.py` passes: each case loads, materializes to the same base commit every time, is solved by its reference solution under its own gates, and isn't already solved | agent-flows t04–t05 |
| **M2** | The five-case suite | `test_the_shipped_suite_has_five_cases_of_five_kinds` and the M1 checks pass for all five cases | M3 |
| **M3** | `factory bench run` | The run tests in `tests/test_bench.py` pass: scoring, variants, isolation, budget, refusals, dry run | M2 |
| **M4** | Reading results | The report, compare, list and inspection tests in `tests/test_bench.py` pass | — |
| **M5** | Parallel cells | The parallel tests pass, and the whole of `tests/test_bench.py` passes unmodified | — |
| **M6** | Docs | Architecture, reference, NEXT.md and the factory-ops skill describe bench; `tests/test_templates.py` passes | — |

**Sequence:** `M1 → (M2 ∥ [agent-flows-t04 →] M3) → M4 → M5 → [agent-flows-t05 →] M6`.

### Task Contracts

| Milestone | Task IDs | Coverage |
|---|---|---|
| **M1** | `bench-t01` | New `factory/bench/cases.py` (load, materialize, score hidden) and `factory/bench/fixtures/` with `slugify` and `money-rounding`; unittest counts in `factory/verification.py`; the wheel check in `.github/workflows/ci.yml`; new `tests/test_bench_cases.py` |
| **M2** | `bench-t02` | `report-json`, `ini-refactor` and `rate-limiter` in `factory/bench/fixtures/`; the suite-size test |
| **M3** | `bench-t03` | New `factory/bench/run.py` and `factory/bench/report.py`; `factory bench run` in `factory/cli.py`; new `tests/test_bench.py` with a test-only case under `tests/bench_cases/` |
| **M4** | `bench-t04` | `factory bench report`, `compare`, `list` and `cases`; cells inspectable with `factory show`; tests in `tests/test_bench.py` |
| **M5** | `bench-t05` | `--parallel N` with one process per cell; tests in `tests/test_bench.py` |
| **M6** | `bench-t06` | `docs/architecture.md`, `docs/reference.md`, `NEXT.md`, the factory-ops skill template |

```yaml
- id: bench-t01
  goal: "factory/bench/ ships a fixture case format with its first two cases (slugify, money-rounding): each case materializes into a git repository with a deterministic base commit, and is scored by laying its hidden tests over a candidate and running its hidden commands in the case's sandbox"
  spec_refs:
    - "docs/plans/bench.md#a-case"
    - "docs/plans/bench.md#the-shipped-suite"
    - "docs/plans/bench.md#scoring"
  depends_on: []
  non_goals:
    - "Running agents or the pipeline on a case, or any `factory bench` command (bench-t03, bench-t04)"
    - "The other three shipped cases (bench-t02)"
    - "Changing factory/pipeline.py, factory/agents.py, factory/cli.py, factory/config.py or factory/gates.py"
    - "Editing documentation (README.md, docs/architecture.md, docs/reference.md, NEXT.md)"
  acceptance:
    - "factory/bench/cases.py loads a case from a directory named after the case id, holding case.yaml, repo/, hidden/ and solution/. case.yaml has exactly the keys title, kind (feature, bugfix, multi-file, refactor or algorithm), requires (commands that must exist in the sandbox), config (the case's .factory/config.yaml as a mapping), contract (one 8-key task contract whose id is the case id followed by -t01) and hidden (the commands that score it)"
    - "load_cases(dirs=None) returns the shipped cases under factory/bench/fixtures/, sorted by id, or the cases found in the given directories. A bad case raises an error naming the case and the problem: a missing or unknown key, an id not matching ^[a-z][a-z0-9-]*$, a contract that contracts.validate_tasks rejects, a config that config.parse rejects, an empty hidden/ or solution/, or a hidden command that verification.is_test_command doesn't recognize"
    - "materialize(case, dest) creates a git repository at dest with one commit on main: repo/, plus .factory/config.yaml written from `config` and docs/plans/ID.md holding `contract` in a fenced YAML block, where ID is the case id. Author, committer and dates are fixed, so the same case always gives the same base commit sha. Nothing from hidden/ or solution/ is in the repository"
    - "score_hidden(case, repo, sha, sandbox) checks sha out into a scratch worktree of repo, copies hidden/ over it (same relative paths, overwriting), runs each hidden command there through the given sandbox, and returns whether every command classifies as a pass, with each command's output. The scratch worktree is removed afterwards"
    - "factory/verification.py recognizes unittest: a command that runs unittest is a test command, and its `Ran N tests` line gives the count, so a unittest run of zero tests is inconclusive, never a pass"
    - "The cases slugify (kind feature) and money-rounding (kind bugfix) are as the plan's shipped-suite table describes: small Python projects using only the standard library (Python 3.10 or later), tested with `python3 -m unittest`. Each contract names the public functions the hidden tests call, and its verification runs a visible test that the builder is to add. Each case's config sets empty sandbox ro_binds, rw_binds and path, empty dependency_sources, and no session_log or e2e"
    - "For every shipped case, score_hidden on the base commit is not a pass. On a commit that lays solution/ over the base, every gate of the case's config passes (gates.run_gates for the case's contract) and score_hidden passes"
    - "The release smoke job in .github/workflows/ci.yml imports factory.bench.cases from the installed wheel and asserts that every shipped case loads and has files in hidden/ and solution/"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_bench_cases.py::test_every_shipped_case_loads_with_a_valid_contract_and_config tests/test_bench_cases.py::test_every_case_is_solvable_and_not_already_solved tests/test_bench_cases.py::test_a_case_materializes_to_the_same_base_commit_every_time tests/test_bench_cases.py::test_hidden_and_solution_files_stay_out_of_the_starting_tree tests/test_bench_cases.py::test_hidden_scoring_lays_the_hidden_files_over_the_candidate tests/test_bench_cases.py::test_bad_cases_are_rejected_with_the_reason tests/test_verification.py::test_unittest_output_counts_tests"
    - "uv run pytest -q tests/test_verification.py tests/test_gates.py"
    - "grep -q 'factory.bench.cases' .github/workflows/ci.yml"
  risk: medium

- id: bench-t02
  goal: "Three more shipped cases, report-json (multi-file), ini-refactor (refactor) and rate-limiter (algorithm), complete the five-case fixture suite"
  spec_refs:
    - "docs/plans/bench.md#the-shipped-suite"
    - "docs/plans/bench.md#a-case"
  depends_on:
    - bench-t01
  non_goals:
    - "Changing the case format, load_cases, materialize or score_hidden in factory/bench/cases.py"
    - "Changing the slugify or money-rounding cases"
    - "Changes outside factory/bench/fixtures/, tests/test_bench_cases.py and this task's session log"
  acceptance:
    - "factory/bench/fixtures/ holds report-json (kind multi-file), ini-refactor (kind refactor) and rate-limiter (kind algorithm) in the format bench-t01 defined, each as the plan's shipped-suite table describes, using only the Python 3.10 standard library"
    - "Each passes the bench-t01 checks: it loads; score_hidden on its base commit is not a pass; and on its base with solution/ laid over it, every gate of its config passes and score_hidden passes"
    - "Each hidden test calls only what its case's contract names (functions, command-line flags, output formats), so any solution that meets the contract can pass. ini-refactor's hidden tests also check that the existing public functions keep their names and their behavior"
    - "tests/test_bench_cases.py::test_the_shipped_suite_has_five_cases_of_five_kinds checks that load_cases() returns exactly slugify, money-rounding, report-json, ini-refactor and rate-limiter, one of each kind"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_bench_cases.py::test_the_shipped_suite_has_five_cases_of_five_kinds tests/test_bench_cases.py::test_every_case_is_solvable_and_not_already_solved tests/test_bench_cases.py::test_every_shipped_case_loads_with_a_valid_contract_and_config"
  risk: low

- id: bench-t03
  goal: "`factory bench run` runs every selected case under every variant (a flow from the repository's config, optionally with one model for all its steps) in an isolated cell, scores each cell with the case's gates and hidden tests within a required budget, and writes results.json and a per-variant table"
  spec_refs:
    - "docs/plans/bench.md#a-bench-run"
    - "docs/plans/bench.md#scoring"
    - "docs/plans/bench.md#results"
    - "docs/plans/bench.md#keeping-the-hidden-tests-hidden"
  depends_on:
    - bench-t01
    - agent-flows-t04
  non_goals:
    - "Running cells in parallel (bench-t05)"
    - "The report, compare, list and cases commands (bench-t04)"
    - "Replaying merged tasks from the board, or an LLM judge"
    - "Changing how `factory run` builds, gates or records a task"
    - "Editing factory/prompts/*.md or any documentation"
  acceptance:
    - "`factory bench run` takes --case ID (repeatable; default every case), --cases DIR (load the cases from DIR instead of the shipped suite), --flow NAME (repeatable; default the config's `flow`), --model SPEC (repeatable), --repeat N (default 1), --max-cost USD, --max-attempts N (default 3), --dry-run and --no-sandbox. The variants are each flow once per --model, with that model on every step, or once with its configured models when no --model is given. A variant's id is the flow name, or FLOW@MODEL"
    - "Before any work it refuses, naming the problem, when: --max-cost is missing without --dry-run; a flow is unknown (`unknown flow NAME (flows: default, …)`) or a case id is; a case doesn't load; a provider key for any variant's models is missing; bubblewrap is missing without --no-sandbox; a command in a case's `requires` is missing from its sandbox; or a case's hidden/ or solution/ files are readable inside its sandbox or under its config's dependency_sources. It warns that --max-cost can't limit a model that has no price"
    - "--dry-run prints the cells, each variant's model per step and the provider keys it needs, then exits 0 without creating any file or calling a model"
    - "A run's directory is $FACTORY_HOME/bench/RUN, where RUN is the UTC start time as YYYYMMDD-HHMMSS. Each cell (variant, case, repeat) has a directory under it that is a factory home of its own: its factory.db, the case materialized as repo/, and its worktrees, logs and transcripts"
    - "A cell runs pipeline.Pipeline on the case's contract with open_pr off, the variant's flow and model, --max-attempts, and the case's config with the invoking repository's flow, flows, models and max_steps laid over it. Prompts load from the invoking repository (its .factory/agents/ overrides, else the shipped prompts), as `factory run` there would load them"
    - "A bench run never writes the invoking repository's factory.db, never creates a branch or worktree in the invoking repository, never pushes and never calls gh. A cell's repo has no remote"
    - "A cell's outcome is one of: solved (the pipeline ended `verified` and score_hidden passed on the commit the gates passed); false_pass (it ended `verified` and score_hidden failed); failed (the pipeline failed); stopped (the pipeline hit its cost limit); error (an exception or an interruption ended it); skipped (the budget was spent before it started). Each cell records its attempts, cost, model calls, tokens in and out, reviewer CHANGES verdicts, step-limit stops, the gates that failed last, wall time and its directory. The hidden commands' output goes to the cell's hidden.log"
    - "Each cell's pipeline gets the budget left as its cost limit, and no cell starts once the run's recorded cost reaches --max-cost"
    - "results.json at the top of the run directory holds: the run (id, start and end, factory version, sandbox on or off, max cost, max attempts, repeat); each case (kind, base commit sha, and fixture_sha, a SHA-256 over the case directory's files); each variant (flow, model override, and for each agent step its name, kind, model, step limit and prompt_sha, a SHA-256 of the prompt text it loads); and every cell. It is rewritten after every cell, so an interrupted run keeps the cells that finished"
    - "At the end the run prints one row per variant: cells; solved, as a count and as a percentage of the cells that ended solved, false_pass or failed; false passes; failed; errors, stopped and skipped; mean attempts; mean cost per cell; total cost; and mean minutes. Then it prints solved counts per case and variant. It exits 0 when no cell ended error, stopped or skipped, else 1"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_bench.py::test_a_bench_run_scores_each_cell_with_gates_and_hidden_tests tests/test_bench.py::test_each_variant_runs_its_flow_and_model tests/test_bench.py::test_prompts_and_flows_come_from_the_invoking_repository tests/test_bench.py::test_a_bench_run_leaves_the_board_and_the_repository_alone tests/test_bench.py::test_the_budget_caps_cells_and_stops_starting_new_ones tests/test_bench.py::test_bench_run_refuses_before_any_work tests/test_bench.py::test_hidden_files_readable_in_the_sandbox_are_refused tests/test_bench.py::test_dry_run_prints_the_cells_and_creates_nothing tests/test_bench.py::test_results_are_written_after_every_cell"
    - "uv run pytest -q tests/test_pipeline.py tests/test_bench_cases.py"
  risk: high

- id: bench-t04
  goal: "`factory bench report`, `compare`, `list` and `cases` read bench results: one run's scores per variant and case, two runs side by side with what changed between them, past runs, and the available cases. Each cell can be inspected with `factory show`, `trace` and `transcript`"
  spec_refs:
    - "docs/plans/bench.md#reading-results"
    - "docs/plans/bench.md#results"
  depends_on:
    - bench-t03
  non_goals:
    - "Changing how a bench run runs or scores cells, or what results.json records"
    - "An exit code that fails on a regression, statistics beyond counts and means, charts, or JSON output (results.json is the machine-readable form)"
    - "Editing documentation"
  acceptance:
    - "`factory bench report [RUN]` (default: the newest run) prints the table bench-t03 prints at the end of a run, under a header naming the run, its cases, variants and repeats, its cost against its budget, and the factory version. When the run had no sandbox, the header also says `unsandboxed: agents could read the hidden tests`. Cells missing from results.json (an interrupted run) count as `not run`. `--cells` adds one line per cell: variant, case, repeat, outcome, attempts, cost, minutes and its directory"
    - "`factory bench compare RUN_A RUN_B` prints, for each variant id in both runs, solved, false passes, mean cost per cell, mean attempts and mean minutes as A → B, then per case and variant solved A → B. Its header lists: cases whose fixture_sha differs, or that are in only one run; variants in only one run; and, per variant, the steps whose model or prompt_sha differs between the runs"
    - "`factory bench list` prints past runs newest first: id, start time, cases, variants, cells ended out of the total, and cost. `factory bench cases [--cases DIR]` prints each case's id, kind and title"
    - "An unknown run id is refused with the known ids. A results.json that doesn't parse is reported with its path, and the other runs still list"
    - "With FACTORY_HOME set to a cell's directory, `factory show`, `factory trace` and `factory transcript` work on that cell's task, whose id is the case's contract id"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_bench.py::test_report_shows_solved_rates_per_variant_and_case tests/test_bench.py::test_report_cells_lists_each_cell_and_its_directory tests/test_bench.py::test_report_of_an_interrupted_run_counts_cells_not_run tests/test_bench.py::test_compare_pairs_variants_and_cases_across_runs tests/test_bench.py::test_compare_flags_changed_cases_models_and_prompts tests/test_bench.py::test_list_shows_runs_newest_first_and_cases_lists_the_suite tests/test_bench.py::test_a_cell_can_be_inspected_with_factory_show"
  risk: low

- id: bench-t05
  goal: "`factory bench run --parallel N` runs up to N cells at once, each in its own process, with the same results and budget rules as a sequential run"
  spec_refs:
    - "docs/plans/bench.md#a-bench-run"
  depends_on:
    - bench-t04
  non_goals:
    - "Changing what a cell runs or how it is scored"
    - "Resuming an interrupted run"
    - "Parallelism inside a cell, or cells sharing a repository"
    - "Editing documentation"
  acceptance:
    - "--parallel N (default 1) keeps up to N cells running. Each cell is a child process, started as the scheduler starts task runs (no stdin, its own session), that runs one cell and writes its result to the cell's directory. The parent records each finished cell in results.json and prints its line as it ends"
    - "A cell starts only while the recorded cost of finished and running cells is below --max-cost, and gets --max-cost minus that cost as its cost limit. Cells still waiting when the budget is reached are skipped"
    - "A child process that dies without writing its result leaves its cell `error`, with the exit status and the last lines of its stderr. The other cells carry on"
    - "Ctrl-C stops starting cells, terminates the running children, records their cells as `error` (interrupted) and writes results.json before exiting"
    - "With --parallel 1 a run behaves as in bench-t03: the bench-t03 and bench-t04 tests pass unmodified"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_bench.py::test_parallel_cells_run_at_once_and_all_finish tests/test_bench.py::test_parallel_runs_keep_to_the_budget tests/test_bench.py::test_a_crashed_cell_process_is_recorded_as_an_error"
    - "uv run pytest -q tests/test_bench.py"
  risk: medium

- id: bench-t06
  goal: "docs/architecture.md, docs/reference.md, NEXT.md and the shipped factory-ops skill describe `factory bench`: the case format, what a run does and how it scores, the budget, reading and comparing results, and writing your own cases"
  spec_refs:
    - "docs/plans/bench.md#design"
  depends_on:
    - bench-t02
    - bench-t05
    - agent-flows-t05
  non_goals:
    - "Changing code, or tests beyond what tests/test_templates.py needs for the new template text"
    - "Editing the installed skill copies under .claude/skills or .agents/skills: `factory init --force` refreshes them"
    - "Rewriting sections unrelated to bench"
  acceptance:
    - "docs/architecture.md has an `## Evaluating flows (factory bench)` section with: a diagram of a run (cases × variants × repeats into isolated cells, each a pipeline run without a PR, then hidden scoring); the cell outcomes; how the hidden tests are kept from agents; the budget; and what results.json records. The Components table has a factory/bench/ row, and Known limitations say that a few cases and repeats make comparisons noisy"
    - "docs/reference.md documents `factory bench run`, `report`, `compare`, `list` and `cases` with every flag; the case directory format (case.yaml keys, repo/, hidden/, solution/), and how to write and check a case of your own; the five shipped cases; and troubleshooting rows for hidden files readable in the sandbox, a missing required command, and a run stopped by its budget"
    - "NEXT.md marks item 8 done in its table, with a link to the architecture section, and item 3's mention of `factory bench` links to item 8"
    - "factory/templates/skills/factory-ops/SKILL.md says how to compare flows or models with `factory bench`, and that a bench run spends real money, capped by --max-cost"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "grep -q '^## Evaluating flows' docs/architecture.md"
    - "grep -q 'factory[[:space:]]bench[[:space:]]compare' docs/reference.md"
    - "grep -q 'docs/architecture.md#evaluating-flows-factory-bench' NEXT.md"
    - "grep -q 'factory[[:space:]]bench' factory/templates/skills/factory-ops/SKILL.md"
    - "uv run pytest -q tests/test_templates.py"
  risk: low
```

Planned test additions:

| Task | Test | Kind |
|---|---|---|
| t01 | `tests/test_bench_cases.py` (new file): the six tests named in its verification; `tests/test_verification.py::test_unittest_output_counts_tests`; `tests/test_verification.py` and `tests/test_gates.py` (existing) as regression | unit, sandboxed |
| t02 | `tests/test_bench_cases.py::test_the_shipped_suite_has_five_cases_of_five_kinds`; the t01 tests, which are parametrized over every shipped case and so cover the new ones | unit, sandboxed |
| t03 | `tests/test_bench.py` (new file): the nine tests named in its verification; `tests/test_pipeline.py` and `tests/test_bench_cases.py` (existing) as regression | CLI end to end |
| t04 | `tests/test_bench.py`: the seven tests named in its verification | CLI, unit |
| t05 | `tests/test_bench.py`: the three tests named in its verification; the whole file as regression | CLI end to end |
| t06 | none new: `tests/test_templates.py` (existing) | regression |

Every verification filter names a test the task adds, or an existing test file, so zero selected tests fails the gate. Tests that need bubblewrap run unsandboxed when it's missing, as `tests/test_pipeline.py` does, except `test_hidden_files_readable_in_the_sandbox_are_refused`, which skips without it (CI installs it).

Every task is factory-runnable on this repository: its verification is `uv run pytest` and `grep`, offline. The bench runs themselves spend money on real models and are run by hand, never by a task's gates. The tests use `ScriptedModel`.

Prerequisite for `bench-t03`: `agent-flows-t04` must be merged, or have an open PR for t03 to stack on. On 2026-11-11 it had failed on OpenRouter credits, and `agent-flows-t02` and `t03` (PRs #20 and #21) had been merged into their stack branches rather than main. Those need to reach main first.

### Risks

1. **The hidden tests leak to the agents.** The sandbox mounts the host read-only and binds parts of `$HOME` back in (`factory/sandbox.py:70`), and the default config binds `~/.local/share/uv` (`factory/config.py:56`), where a `uv tool install` puts the shipped fixtures. A builder that can read the hidden tests or the solution scores meaninglessly. **Action:** shipped cases bind nothing from `$HOME`. t03 refuses a case whose hidden or solution files are readable inside its sandbox or under its dependency sources. `--no-sandbox` is recorded, and the report says the scores can't be trusted.
2. **Noise.** Five cases and one repeat can't tell two good flows apart. **Action:** `--repeat N`; tables show counts (`4/6`) next to percentages; compare shows A → B counts, not a verdict. The docs recommend at least 3 repeats before acting on a difference.
3. **Cost.** A run costs cases × variants × repeats full pipeline runs. **Action:** `--max-cost` is required; each cell's cost limit is the budget left; `--dry-run` shows the cells first; models without a price get a warning.
4. **Cases that don't discriminate.** If every variant solves every case, or none does, the suite says nothing. **Action:** five kinds of task; t01's checks prove each case can be solved under its own gates and isn't already solved; you review the cases in the t01 and t02 PRs; `--cases DIR` runs your own.
5. **Hidden tests that demand one implementation.** A valid solution fails if the hidden tests call internals the contract never named. **Action:** t01 and t02 require hidden tests to use only what the contract names. The reviewer checks it, and `false_pass` cells are worth reading before trusting a result.
6. **Comparing runs whose setup drifted.** Prompts, models or cases can change between two runs under the same variant id. **Action:** results record each step's model and `prompt_sha` and each case's `fixture_sha`, and compare lists every difference in its header.
7. **Conflicts with agent-flows and measure.** All three change `factory/cli.py` and the docs. **Action:** t03 waits for `agent-flows-t04`, and t06 for `agent-flows-t05`. If measure ([#18](https://github.com/PaddyMc/software-factory/pull/18)) lands alongside, whichever PR merges second shows `conflict` on refresh, and the factory resolves it. This plan's NEXT.md change adds new lines only.

---

## Problem

Nothing tells you whether one agent setup is better than another:

- **The tests check plumbing, not agents.** The suite drives `ScriptedModel` (`tests/fake_model.py:36`), so a prompt edit, a model swap or a new flow from [agent-flows](agent-flows.md) passes or fails the same. NEXT.md item 3 calls this gap out.
- **Real runs aren't comparable.** Every task on the board is different, so a better pass rate after a change may just reflect easier tasks. `factory run --no-pr` (`factory/pipeline.py:408`) can't run one task under two setups either. It writes the board's row for the task and resets the `factory/<task>` branch in your checkout (`factory/pipeline.py:163`, `:167`).
- **The gates grade the builder's own tests.** A candidate passes when the verification commands pass, and the builder writes the tests those commands run (NEXT.md item 2). Comparing setups by gate pass rate rewards weak tests.

## Goal

`factory bench run --flow default --flow lean --max-cost 10` runs a fixed suite of small tasks under each setup, in isolation from your board and checkout. It scores each candidate against tests the agents never saw, and `factory bench compare` shows what a prompt, model or flow change did to solved rate, cost and attempts.

## Design

```text
cases (shipped fixtures, or --cases DIR)     variants: --flow × --model        × --repeat
            │                                          │
            └──────────────────┬───────────────────────┘
                               ▼
            cell = (variant, case, repeat)   $FACTORY_HOME/bench/RUN/cells/…   (a factory home)
            ┌──────────────────────────────────────────────────────────────────────────────┐
            │ materialize the case → repo/ (fixed base commit, no hidden/ or solution/)      │
            │ Pipeline: the variant's flow and model, the case's gates, no PR               │
            │   verified ──► lay hidden/ over the candidate ──► hidden commands in sandbox  │
            │                    pass: solved          fail: false_pass                     │
            │   failed / cost limit / exception ──► failed / stopped / error                │
            └──────────────────────────────────────────────────────────────────────────────┘
                               ▼
            results.json (rewritten after every cell) ──► report · compare · list
```

### A case

```text
factory/bench/fixtures/slugify/
  case.yaml        title, kind, requires, config, contract, hidden
  repo/            the starting tree: AGENTS.md, the package, its existing tests
  hidden/          files laid over the candidate to score it, e.g. bench_hidden/test_slugify.py
  solution/        files laid over the starting tree that solve it (used by the factory's own tests)
```

```yaml
title: Slugify titles for URLs
kind: feature                     # feature | bugfix | multi-file | refactor | algorithm
requires: [python3]               # checked in the case's sandbox before a run
config:                           # written to .factory/config.yaml in the base commit
  unit_tests: ["python3 -m unittest -q"]
  dependency_sources: []
  sandbox: {ro_binds: [], rw_binds: [], path: [], hide: []}
contract:                         # written to docs/plans/slugify.md; the usual 8 keys
  id: slugify-t01
  goal: "textkit.slug.slugify(title, max_length=64) turns a title into a URL slug"
  # … spec_refs, depends_on, non_goals, acceptance, verification, risk
hidden:
  - python3 -m unittest -v bench_hidden.test_slugify
```

`config` and `contract` live in `case.yaml` rather than as files under `repo/`. That way the package ships no dot-directories, and the loader validates them up front. `materialize` commits with a fixed author, committer and date, so a case's base commit sha is identical across runs and machines. That sha is recorded with the case's `fixture_sha` (a hash of every file in the case directory).

### The shipped suite

| Case | Kind | The task | The hidden tests check |
|---|---|---|---|
| `slugify` (t01) | feature | Add `slugify(title, max_length=64)` to a small text package: lowercase, accents folded to ASCII, runs of other characters collapsed to one `-`, trimmed, and cut at a word boundary within `max_length` | Accents, punctuation runs, empty and all-symbol titles, the length cut |
| `money-rounding` (t01) | bugfix | Ledger totals drift because amounts are summed as floats. Totals and balances must be exact to the cent, with half-cent amounts rounded half to even | Sums that drift under floats, half-cent amounts, existing behavior unchanged |
| `report-json` (t02) | multi-file | A `report` command-line tool gains `--format json` next to its table output. The change touches the argument parser, a formatter and the README's usage | The JSON shape through the real entry point; the default table output unchanged byte for byte |
| `ini-refactor` (t02) | refactor | Two modules each carry their own copy of a parser for the same `key = value` settings format. Extract one shared parser with behavior unchanged | Both modules' behavior, edge cases (comments, blank lines, duplicate keys), and the public functions' names |
| `rate-limiter` (t02) | algorithm | A token-bucket rate limiter with an injectable clock: capacity, refill rate, `try_acquire(n=1)` | Bursts, refills over fractional time, requests larger than the capacity, no refill beyond capacity |

All of them use the standard library only, so they run offline in the sandbox with the host's `python3`, version 3.10 or later. Each contract's verification runs a visible test the builder adds, so the production gates apply as they do in a real repository.

### A bench run

```text
$ factory bench run --flow default --flow lean --model openrouter:z-ai/glm-5.3 --repeat 2 --max-cost 12
bench 20261111-140215: 5 cases × 2 variants × 2 = 20 cells, budget $12.00
[1/20] default@openrouter:z-ai/glm-5.3 · slugify #1: solved in 1 attempt, $0.21, 3m41s
…
```

- **Variants.** Each `--flow` (default: the config's `flow`) runs once per `--model` with that model on every step, or once with its configured models. Flows, `models`, `max_steps` and prompt overrides come from the repository you run it in, exactly as `factory run` resolves them there. Comparing a prompt edit takes no new mechanism: put the edited prompt in `.factory/agents/builder-v2.md`, define a flow with `{name: builder-v2, kind: build}`, and bench it against `default`.
- **Cells.** A cell is one (variant, case, repeat). Its directory is a factory home of its own (`factory.db`, `repo/`, `worktrees/`, `logs/`, `transcripts/`, `hidden.log`), so `FACTORY_HOME=<cell> factory show slugify-t01` inspects it. The cell's repository has no remote, so nothing can be pushed. The cell runs `Pipeline` with `open_pr` off and the case's config, with the invoking repository's `flow`, `flows`, `models` and `max_steps` laid over it.
- **Isolation.** A run never touches the invoking repository's board, branches or worktrees, and never calls `gh`.
- **Budget.** `--max-cost` is required. Each cell's cost limit is the budget left, and no cell starts once the budget is spent. With `--parallel N` (t05), the total can overshoot by what the cells already running spend before their own limits stop them.
- **Refused before any work:** unknown flows or cases, missing provider keys, missing bubblewrap, a case's missing `requires`, and hidden files the sandbox can see.

### Scoring

| Pipeline ends | Hidden tests | Cell outcome | Counted in solved rate |
|---|---|---|---|
| `verified` (gates passed) | pass | `solved` | yes |
| `verified` | fail | `false_pass`: the gates passed, so the builder's own tests missed it | yes |
| `failed` (review or gates, out of attempts) | not run | `failed` | yes |
| cost limit hit | not run | `stopped` | no |
| exception or interrupted | not run | `error` | no |
| never started (budget spent) | not run | `skipped` | no |

The hidden tests run on the commit the gates passed. They're laid over a scratch worktree of that commit, and run by the case's `hidden` commands in the case's sandbox. A unittest run of zero tests is inconclusive, never a pass: t01 teaches `factory/verification.py` (`is_test_command`, line 29) unittest's `Ran N tests`. The solved rate leaves out `stopped`, `error` and `skipped` cells, so a provider outage or a spent budget doesn't count against a variant. Those cells are shown separately.

### Results

`$FACTORY_HOME/bench/RUN/results.json`:

```json
{
  "run": {"id": "20261111-140215", "started_at": "…", "ended_at": "…", "factory": "0.1.0",
          "sandbox": true, "max_cost": 12.0, "max_attempts": 3, "repeat": 2},
  "cases": {"slugify": {"kind": "feature", "base": "4be1…", "fixture_sha": "9a0c…"}},
  "variants": {"lean": {"flow": "lean", "model": null,
               "steps": [{"name": "build", "kind": "build", "model": "openrouter:…", "max_steps": 60,
                          "prompt_sha": "3f2a9c1e0b7d"}, …]}},
  "cells": [{"variant": "lean", "case": "slugify", "repeat": 1, "outcome": "solved", "attempts": 1,
             "cost_usd": 0.21, "seconds": 221, "model_calls": 38, "tokens_in": 91234, "tokens_out": 4410,
             "review_changes": 0, "step_limit_stops": 0, "failed_gates": [], "dir": "cells/…"}]
}
```

### Reading results

```text
$ factory bench report
bench 20261111-140215 · 5 cases · 2 variants × 2 · $9.84 of $12.00 · factory 0.1.0

variant                          cells  solved      false  failed  err/stop/skip  attempts  cost/cell  min/cell
default@openrouter:z-ai/glm-5.3  10     8/10  80%   1      1       0/0/0          1.4       $0.52      6.1
lean@openrouter:z-ai/glm-5.3     10     6/10  60%   3      1       0/0/0          1.9       $0.46      4.0

case             default@…  lean@…
slugify          2/2        2/2
money-rounding   2/2        1/2
…

$ factory bench compare 20261104-091000 20261111-140215
cases: 5 in both, unchanged · prompts changed: default@… build 3f2a9c1e0b7d → 9be04d17aa21

variant     solved          false   cost/cell        attempts
default@…   7/10 → 8/10     2 → 1   $0.55 → $0.52    1.6 → 1.4
```

### Keeping the hidden tests hidden

| Path to the hidden files | Guard |
|---|---|
| The repository the agents work in | `materialize` never copies `hidden/` or `solution/`, and scoring uses a scratch worktree made after the pipeline ends |
| The installed package, readable in the sandbox through a bind (`~/.local/share/uv`) or a system-wide install | Shipped cases bind nothing from `$HOME`. Before a run, t03 checks from inside each case's sandbox that its hidden and solution files can't be read, and refuses if they can |
| The agents' file tools (`dependency_sources`) | The same check refuses a case whose dependency sources contain its files |
| `--no-sandbox` | Allowed, recorded in results.json, and flagged in every report header |

## Files Changed

| File | Change |
|---|---|
| `factory/bench/__init__.py`, `factory/bench/cases.py` | New: case loading, `materialize`, `score_hidden` (t01) |
| `factory/bench/fixtures/` | New: `slugify`, `money-rounding` (t01); `report-json`, `ini-refactor`, `rate-limiter` (t02) |
| `factory/verification.py` | unittest is a test command, and its count is read (t01) |
| `.github/workflows/ci.yml` | The release smoke job loads the shipped cases from the wheel (t01) |
| `factory/bench/run.py` | New: variants, preflight, cells, budget, results.json (t03); child processes (t05) |
| `factory/bench/report.py` | New: the run table (t03); report, compare, list (t04) |
| `factory/cli.py` | `factory bench run` (t03); `report`, `compare`, `list`, `cases` (t04); `--parallel` (t05) |
| `tests/test_bench_cases.py` | New (t01, t02) |
| `tests/test_bench.py`, `tests/bench_cases/` | New: run tests and a test-only case (t03–t05) |
| `tests/test_verification.py` | `test_unittest_output_counts_tests` (t01) |
| `docs/architecture.md`, `docs/reference.md`, `NEXT.md`, `factory/templates/skills/factory-ops/SKILL.md` | Docs (t06) |
| `docs/sessions/` | Every task's session log entry |

## Test Plan

### Unit tests

`tests/test_bench_cases.py` (t01, t02), against the shipped cases, sandboxed when bubblewrap is present:

- `test_every_shipped_case_loads_with_a_valid_contract_and_config`: parametrized over the cases.
- `test_every_case_is_solvable_and_not_already_solved`: parametrized. `score_hidden` fails on the base commit; with `solution/` laid over the base, `gates.run_gates` passes every gate and `score_hidden` passes.
- `test_a_case_materializes_to_the_same_base_commit_every_time`: two materializations, one sha.
- `test_hidden_and_solution_files_stay_out_of_the_starting_tree`
- `test_hidden_scoring_lays_the_hidden_files_over_the_candidate`: a hidden file that overwrites a builder's file of the same path wins, and the scratch worktree is gone afterwards.
- `test_bad_cases_are_rejected_with_the_reason`: one bad case per rule.
- `test_the_shipped_suite_has_five_cases_of_five_kinds` (t02).

`tests/test_verification.py::test_unittest_output_counts_tests` (t01): `Ran 3 tests` counts 3, and `Ran 0 tests … OK` with exit 0 is inconclusive.

### End-to-end tests

`tests/test_bench.py` drives `factory bench` through `cli.main` with the real pipeline, LangChain agents, git and bubblewrap when present, using `ScriptedModel`. `build_model` is patched to return a scripted model per spec, so `--model scripted:good` writes a test-only case's `solution/` files and `scripted:bad` writes code that passes the visible test but fails the hidden one. The test-only case `tests/bench_cases/adder/` is run with `--cases`, which covers that flag too.

- t03:
  - `test_a_bench_run_scores_each_cell_with_gates_and_hidden_tests`: good is `solved`, bad is `false_pass`, and both have their fields in results.json.
  - `test_each_variant_runs_its_flow_and_model`: `--flow default --flow lean` gives `lean` cells no plan or verify runs; each cell's runs record their flow and step.
  - `test_prompts_and_flows_come_from_the_invoking_repository`: the invoking repository's `.factory/agents/builder.md` is the build step's system prompt in the cell's transcript, and its `prompt_sha` is in results.json.
  - `test_a_bench_run_leaves_the_board_and_the_repository_alone`: the invoking board's rows, `git for-each-ref` and `git worktree list` are unchanged.
  - `test_the_budget_caps_cells_and_stops_starting_new_ones`: `prices.cost` is patched to $0.40 per call (as in `test_max_cost_aborts_a_run`). Later cells are `skipped`, and the exit code is 1.
  - `test_bench_run_refuses_before_any_work`: no `--max-cost`, an unknown flow, an unknown case, a missing key, a missing `requires` command.
  - `test_hidden_files_readable_in_the_sandbox_are_refused`: a case whose config binds its own directory. Skips without bubblewrap.
  - `test_dry_run_prints_the_cells_and_creates_nothing`
  - `test_results_are_written_after_every_cell`
- t04: `test_report_shows_solved_rates_per_variant_and_case`, `test_report_cells_lists_each_cell_and_its_directory`, `test_report_of_an_interrupted_run_counts_cells_not_run`, `test_compare_pairs_variants_and_cases_across_runs`, `test_compare_flags_changed_cases_models_and_prompts` and `test_list_shows_runs_newest_first_and_cases_lists_the_suite` all work from written results.json files. `test_a_cell_can_be_inspected_with_factory_show` runs one real cell.
- t05:
  - `test_parallel_cells_run_at_once_and_all_finish`: 4 cells with `--parallel 2`. The cells overlap in time, and the results match a sequential run's.
  - `test_parallel_runs_keep_to_the_budget`
  - `test_a_crashed_cell_process_is_recorded_as_an_error`

## Verification

- Each task's verification commands, then `uv run pytest -q` (the unit gate).
- By hand after t05 merges, with real models and real money:
  1. In this repository, `factory bench run --dry-run --flow default` lists 5 cells and the keys needed.
  2. `factory bench run --case slugify --flow default --max-cost 2` ends with one cell, and `factory bench report --cells` shows it. Its `FACTORY_HOME=<cell> factory transcript slugify-t01` shows the run.
  3. Define a `lean` flow (`[build, review]`), then run `factory bench run --flow default --flow lean --repeat 2 --max-cost 15`. Afterwards, `factory bench compare` against the previous run lists the changed variants.

## Cross-Workstream Coordination

- **Depends on:** [agent-flows](agent-flows.md). `bench-t03` waits for `agent-flows-t04`: it runs `Pipeline` with a flow and reads `runs.flow` and `runs.step` (agent-flows-t02, t03), and t04 is the last task to change `factory/cli.py`'s run path. `bench-t06` waits for `agent-flows-t05`, which edits the same docs.
- **Required by:** NEXT.md item 4, "Learn from feedback", which needs a controlled way to check whether a proposed prompt change helps. NEXT.md item 2, "The builder writes the test that judges it": `false_pass` cells measure exactly that gap, across flows.
- **Related:** measure ([PR #18](https://github.com/PaddyMc/software-factory/pull/18), not yet on main). It's independent: `factory stats` reads the board, and bench reads its own cells. Bench runs the real pipeline, so once `measure-t01` lands, every cell's runs carry prompt versions too. measure's "Required by: `factory bench` (not yet planned)" and its NEXT.md line saying bench isn't planned should point here once both plans are on main.

## Notes / Out of Scope

- **Replaying merged tasks** from the board (NEXT.md item 3's original sketch). Real tasks would be more representative, but they need a reference PR's tests to be separable, and their cost grows with the board. A `--cases` directory of exported merged tasks is the natural extension, since it uses the same format.
- **An LLM judge** comparing a candidate with the reference solution. Hidden tests are deterministic. A judge can be added as another scoring column later.
- **Comparing factory versions** (pipeline code or shipped prompts at another git ref). Copy a prompt into `.factory/agents/` and give it a flow step instead. Code changes need a second install.
- **Cases in other languages.** The shipped suite is Python standard library only. A Rust or Node case works under `--cases DIR`, with `requires` and a sandbox config that binds its toolchain.
- **Statistical tests, regression exit codes, charts and JSON output.** Reports show counts and means, and results.json is the machine-readable form.
- **Resuming an interrupted run.** Run it again. Cells that finished are kept in the old run's results.
