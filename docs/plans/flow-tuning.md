# Plan: Tune the agent flow

**Status:** Planned (2026-11-16). Workstream scoped; awaiting kickoff: t01 starts once `measure-t01` and `thoughts-t01` have PRs (both do), and t02 waits for `strict-flow-t08`. Roadmap: [NEXT.md item 14](../../NEXT.md#14-tune-the-agent-flow).

---

## Execution Plan

### Locked Decisions

| Decision | Choice |
|---|---|
| Scope | **Three improvements the other plans leave open.** A reviewer that ends without its verdict is asked once more; a build step can make several candidates and keep one; and a by-hand bench trial picks this repository's default flow from the results. Bounded builder context, locked tests and proving reviewers stay in [strict-flow](strict-flow.md) |
| A review still without a verdict | **Counts as CHANGES, as today.** The run is labelled `CHANGES (no verdict)`, and the builder is told no verdict came instead of getting the reviewer's unfinished reasoning as a rejection |
| Choosing among candidates | **The gates first, then a selector agent.** Candidates that fail any gate are out. When two or more pass, a selector compares their diffs against the contract and picks one; a missing or invalid choice falls back to the smallest passing diff |
| Running candidates | **One after another**, each in its own worktree from the same start. Nothing runs concurrently inside a task run; plan runs keep their `--parallel` |
| Sequencing | **The verdict fix first; candidates after strict-flow.** t01 stacks on `measure-t01` and `thoughts-t01` (they change `factory/agents.py` too), and `strict-flow-t01` waits for it. t02 waits for `strict-flow-t08`, so candidates can be chosen against strict's locked tests and compared with bench. `wiki-t01` now waits for this plan's last code task |
| Rollout | **Opt-in.** The re-ask is always on (it only changes what happens when a review has no verdict). Candidates are a build-step option, off unless a flow sets it, and no built-in flow uses them |

### Milestones

| # | Deliverable | Exit criteria | Parallelizable with |
|---|---|---|---|
| **M1** | A review without a verdict is asked once more | The t01 tests in `tests/test_agent_loop.py` and `tests/test_pipeline.py` pass; `CHANGES (no verdict)` is in the reference's troubleshooting | — |
| **M2** | Build candidates, chosen by the gates | `tests/test_candidates.py` (t02 tests) and the t02 tests in `tests/test_flows.py` pass; flows without the option run as before | — |
| **M3** | The selector | The t03 tests in `tests/test_candidates.py` and `tests/test_templates.py` pass | — |
| **M4** | Bench compares candidates | The t04 tests in `tests/test_bench.py` pass | — |
| **M5** | Docs | Architecture, reference, NEXT.md, the config template and the factory-ops skill describe candidates; `tests/test_templates.py` passes | M6 |
| **M6** | The trial (by hand) | `docs/flow-trials.md` records a bench run of six variants; `.factory/config.yaml` sets `flow:` by its rule | M5 |

**Sequence:** `(measure-t01 ∥ thoughts-t01) → M1 → strict-flow-t01 … strict-flow-t08 → M2 → M3 → M4 → (M5 after strict-flow-t09) ∥ M6`, then `M4 → wiki-t01` and `M5 → wiki-t07`. M2 to M4 run one after another: each changes `factory/flows.py`, `factory/pipeline.py` or `factory/bench/`.

### Task Contracts

| Milestone | Task IDs | Coverage |
|---|---|---|
| **M1** | `flow-tuning-t01` | The re-ask in `factory/agents.py`; the no-verdict feedback and outcome in `factory/pipeline.py`; a reviewer that omits its verdict in `tests/fake_model.py`; tests in `tests/test_agent_loop.py` and `tests/test_pipeline.py`; a troubleshooting row in `docs/reference.md`, a sentence in `docs/architecture.md`, and the factory-ops troubleshooting reference (template and this repository's copy) |
| **M2** | `flow-tuning-t02` | `candidates` in `factory/flows.py`; candidate worktrees, builds, gates and the gates' choice in `factory/pipeline.py`; the `candidate` runs column in `factory/db.py`; labels in `factory show` (`factory/cli.py`) and `factory clean`; new `tests/test_candidates.py`; tests in `tests/test_flows.py` |
| **M3** | `flow-tuning-t03` | `factory/prompts/selector.md`; the `select` role in `factory/agents.py` and `factory/config.py`; the selector's run and its fallback in `factory/pipeline.py`; the PR's Checks line in `factory/prbody.py`; the fake model's SELECTOR; tests in `tests/test_candidates.py` and `tests/test_templates.py` |
| **M4** | `flow-tuning-t04` | `candidates` in bench's results and compare, and the cell's candidate counts, in `factory/bench/`; tests in `tests/test_bench.py` |
| **M5** | `flow-tuning-t05` | `docs/architecture.md`, `docs/reference.md`, `NEXT.md`, `factory/templates/config.yaml`, the factory-ops skill template and this repository's copy |
| **M6** | `flow-tuning-t06` | By hand: the bench run, `docs/flow-trials.md`, and `flow:` in `.factory/config.yaml` |

```yaml
- id: flow-tuning-t01
  goal: "A review step that ends without a VERDICT line is asked once more for it in the same conversation; a review still without one counts as CHANGES, is recorded as `CHANGES (no verdict)`, and the builder is told that no verdict came"
  spec_refs:
    - "docs/plans/flow-tuning.md#asking-again-for-a-verdict"
    - "factory/agents.py"
    - "factory/pipeline.py"
  depends_on:
    - measure-t01
    - thoughts-t01
  non_goals:
    - "Changing the VERDICT line's format, parse_verdict's rule (the last VERDICT line wins), or the shipped reviewer prompt"
    - "Asking again more than once, or asking a plan, build or verify step again"
    - "Treating a review without a verdict as an approval, or rerunning the review from scratch"
    - "strict-flow's proof rules (strict-flow-t06)"
  acceptance:
    - "When a review step's final report has no line matching agents._VERDICT, including a review stopped by its step limit and one whose final message is empty, the factory sends one more message in the same conversation (the step's task message and everything the agent said and called so far), with the same tools, for at most agents.REASK_STEPS (3) more model calls. The message starts `Your review ended without a VERDICT line.` and asks for the report in the format the step's instructions give, ending with exactly one VERDICT line"
    - "The re-ask is logged as `⚠ no VERDICT line: asking once more` under the step's tag and recorded in the transcript as an event of type `reask`. Its model calls, tokens and cost count in the same run, and its messages are observed like the step's own (log lines, transcript `ai` and `tool` events)"
    - "When the reply has a VERDICT line, the step's report is the reply and its verdict is the reply's; the run's outcome reads `APPROVE (asked again)` or `CHANGES (asked again)`"
    - "When the reply has none, the verdict is CHANGES, the run's outcome reads `CHANGES (no verdict)`, and the builder's feedback for the next attempt starts `Reviewer gave no verdict, so the change counts as rejected.` (`Reviewer `NAME` gave …` for a step named other than its kind), followed by the last report, under which the builder is told to address any blocker or major finding it lists"
    - "A review whose report has a VERDICT line is not asked again: its run, report, verdict and outcome are as today, and tests/test_agent_loop.py, tests/test_pipeline.py and tests/test_flows.py pass unmodified apart from the tests this task adds"
    - "docs/reference.md's troubleshooting has a row for a review recorded as `CHANGES (no verdict)` or `(asked again)`; docs/architecture.md says, where it describes review steps, that a review without a verdict is asked once more; factory/templates/skills/factory-ops/references/troubleshooting.md has the same row, copied to .claude/skills/factory-ops/references/troubleshooting.md so tests/test_templates.py passes"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_agent_loop.py::test_a_review_without_a_verdict_is_asked_once_more tests/test_agent_loop.py::test_a_review_stopped_at_its_step_limit_is_asked_for_its_verdict tests/test_agent_loop.py::test_a_review_still_without_a_verdict_counts_as_changes tests/test_agent_loop.py::test_a_review_with_a_verdict_is_not_asked_again"
    - "uv run pytest -q tests/test_pipeline.py::test_a_review_without_a_verdict_tells_the_builder_none_came tests/test_pipeline.py::test_a_review_answered_when_asked_again_routes_on_its_verdict"
    - "grep -q 'CHANGES (no verdict)' docs/reference.md"
    - "grep -q 'CHANGES (no verdict)' factory/templates/skills/factory-ops/references/troubleshooting.md"
    - "uv run pytest -q tests/test_agent_loop.py tests/test_pipeline.py tests/test_flows.py tests/test_templates.py"
  risk: medium

- id: flow-tuning-t02
  goal: "A flow's build step can set `candidates: N` (2 to 5): on a fresh build's first attempt the factory builds N candidates one after another, each in its own worktree from the same start, runs the gates on each, and continues the flow with a passing candidate (the smallest passing diff), while later attempts and reworks build one change as today"
  spec_refs:
    - "docs/plans/flow-tuning.md#build-candidates"
    - "factory/flows.py"
    - "factory/pipeline.py"
  depends_on:
    - strict-flow-t08
  non_goals:
    - "The selector agent (flow-tuning-t03): this task chooses by the gates and the smallest diff only"
    - "Running candidates concurrently, or more than one candidate on a later attempt or a rework"
    - "Changing flows without `candidates`, the gates themselves, or factory/bench/ (flow-tuning-t04)"
    - "Editing documentation (flow-tuning-t05)"
  acceptance:
    - "A build step mapping accepts `candidates`, an integer from 2 to 5, kept on flows.Step (1 when unset). ConfigError, naming the flow and step, when it is on a step of another kind, isn't an integer in that range, is set in a flow with more than one build step, or is set in a flow whose gates step doesn't directly follow the build step. `factory config` prints it"
    - "On the first attempt of a fresh build, candidate 1 builds in the task's worktree and candidates 2 to N each build in `$FACTORY_HOME/worktrees/TASK.cK`, a detached worktree at the same start commit (the base, or the test step's commit under a flow with one). They run one after another with the same plan and task message, each with its commands in a sandbox over its own worktree, and each is committed and then gated like a single build"
    - "Each candidate's build and gates runs are recorded with the attempt number and a new runs column `candidate` (K, from 1 to N; NULL on runs without candidates), migrated into older boards. The log tags read `build#1.K` and `gates#1.K`"
    - "Among the candidates that pass every gate, the factory chooses the one with the fewest changed lines (insertions plus deletions against the start commit), ties going to the lower number. The task's branch is reset to the chosen commit, which becomes the candidate sha, and the flow goes on to the steps after the gates. The log says `chose candidate K of N (P passed the gates; smallest diff)`"
    - "When no candidate passes, the attempt fails as a gate failure would. The candidate with the fewest failing gates (ties going to the lower number) carries on: the branch is reset to it, its gate failures are the next attempt's feedback, and the next attempt builds one change on it. Under `loop: [resume]`, that attempt continues the carried candidate's conversation"
    - "Later attempts, and resolve, ci and human_review reworks, build one change, as a flow without the option does"
    - "Every candidate worktree is removed once the choice is made, and also when the run fails, errors or is stopped. `factory clean TASK` removes any left behind. --max-cost counts every candidate's runs, and reaching it stops the run as today"
    - "`factory show TASK` labels each candidate's runs `candidate K of N` and marks the chosen one"
    - "Flows without `candidates` behave as today: tests/test_pipeline.py, tests/test_flows.py and tests/test_db.py pass unmodified apart from the tests this task adds"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_flows.py::test_candidates_is_a_build_step_option tests/test_flows.py::test_candidates_needs_one_build_step_followed_by_the_gates"
    - "uv run pytest -q tests/test_candidates.py::test_each_candidate_builds_in_its_own_worktree_from_the_same_start tests/test_candidates.py::test_the_smallest_passing_candidate_is_chosen tests/test_candidates.py::test_when_none_pass_the_closest_candidate_carries_on tests/test_candidates.py::test_later_attempts_and_reworks_build_one_change tests/test_candidates.py::test_candidate_worktrees_are_removed_however_the_run_ends tests/test_candidates.py::test_show_labels_each_candidate_and_the_chosen_one"
    - "uv run pytest -q tests/test_candidates.py tests/test_pipeline.py tests/test_flows.py tests/test_db.py"
  risk: high

- id: flow-tuning-t03
  goal: "When two or more candidates pass the gates, a selector agent compares their diffs against the contract and picks one; a missing or invalid choice falls back to the smallest passing diff, and the PR says how its change was chosen"
  spec_refs:
    - "docs/plans/flow-tuning.md#the-selector"
    - "factory/agents.py"
    - "factory/pipeline.py"
  depends_on:
    - flow-tuning-t02
  non_goals:
    - "Running the flow's review steps on every candidate, or merging candidates into a new change"
    - "Giving the selector write or run tools"
    - "A selector step in flows: the selector runs because a build step has `candidates`, and its settings come from the `select` role"
    - "Editing documentation (flow-tuning-t05)"
  acceptance:
    - "A new role `select` has the shipped prompt factory/prompts/selector.md (frontmatter model openrouter:z-ai/glm-5.3, max_steps 30), which a repository can replace with .factory/agents/selector.md. `models.select` and `max_steps.select` set its model and step limit, `factory prompt select` prints it, and `select` and `selector` are reserved step names"
    - "With two or more passing candidates, the selector runs once, as a run with role `select` and step `select` recorded with the attempt. Its message has, for each passing candidate, its number, its diffstat, its diff against the start commit (each capped at pipeline.DIFF_LIMIT characters) and its gate table. The candidates appear in an order shuffled with the task id as the seed, so a position doesn't favour candidate 1. It has the read tools on the task's worktree at the start commit and no other tools"
    - "The factory takes the last line of the selector's report matching `CHOICE: K`. When K names a passing candidate, that candidate is chosen and the log says `chose candidate K of N (P passed the gates; selector)`. When the line is missing or names any other number, the smallest passing diff is chosen, the selector's run outcome is `fallback`, and the log says `selector gave no valid choice: smallest diff`"
    - "With one passing candidate, no selector runs and that candidate is chosen"
    - "The PR body's Checks paragraph says `Chosen from N candidates (P passed the gates; selector)` or `(…; smallest diff)` for a task whose first attempt made candidates"
    - "tests/fake_model.py has a SELECTOR script. tests/test_templates.py's role-prompt tests cover the selector prompt, and a new test checks that the prompt asks for the `CHOICE:` line the parser reads"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_candidates.py::test_the_selector_picks_among_passing_candidates tests/test_candidates.py::test_a_selector_without_a_valid_choice_falls_back_to_the_smallest_diff tests/test_candidates.py::test_one_passing_candidate_needs_no_selector tests/test_candidates.py::test_the_selector_sees_candidates_in_a_seeded_order tests/test_candidates.py::test_the_pr_says_how_its_change_was_chosen"
    - "uv run pytest -q tests/test_templates.py::test_role_prompts_ship_with_the_factory tests/test_templates.py::test_selector_prompt_matches_choice_parser"
    - "uv run pytest -q tests/test_candidates.py tests/test_pipeline.py tests/test_templates.py"
  risk: medium

- id: flow-tuning-t04
  goal: "`factory bench` can compare flows with and without candidates: results.json records each step's candidates, compare flags a change, and a cell under a flow with candidates records how many were built and passed and is scored on the chosen one"
  spec_refs:
    - "docs/plans/flow-tuning.md#comparing-with-bench"
    - "docs/plans/bench.md#results"
    - "factory/bench/"
  depends_on:
    - flow-tuning-t03
  non_goals:
    - "New cases, or changing any case's contract, hidden tests or solution"
    - "Changing how cells are scored: the hidden tests run on the chosen candidate, as on any cell's candidate"
    - "Running a bench with real models (flow-tuning-t06)"
    - "Editing documentation"
  acceptance:
    - "results.json records `candidates` for each step of each variant (1 when unset), and `factory bench compare` lists a step whose candidates differ between the two runs in its header, as it lists a changed model, prompt, loop or prove"
    - "Each cell records `candidates_built` and `candidates_passed` (0 and 0 for a variant without candidates), and `factory bench report --cells` shows them on cells that made candidates"
    - "A bench cell on the test-only case under a flow whose build step has candidates: 3, with scripted models, ends `solved` with one attempt, and its runs include three candidate builds, three candidate gates runs and the selector"
    - "The existing tests in tests/test_bench.py and tests/test_bench_cases.py pass unmodified"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_bench.py::test_results_record_candidates_and_compare_flags_a_change tests/test_bench.py::test_cells_count_the_candidates_built_and_passed tests/test_bench.py::test_a_candidates_cell_is_scored_on_the_chosen_candidate"
    - "uv run pytest -q tests/test_bench.py tests/test_bench_cases.py"
  risk: low

- id: flow-tuning-t05
  goal: "docs/architecture.md, docs/reference.md, NEXT.md, the shipped config template and the factory-ops skill describe build candidates and the selector"
  spec_refs:
    - "docs/plans/flow-tuning.md#design"
    - "docs/architecture.md#agent-flows"
  depends_on:
    - flow-tuning-t04
    - strict-flow-t09
  non_goals:
    - "Changing code, or tests beyond what tests/test_templates.py needs for the new template text"
    - "Rewriting sections unrelated to this plan, or editing README.md"
    - "Documenting the verdict re-ask again (flow-tuning-t01 did)"
  acceptance:
    - "docs/architecture.md: the Agent flows section has a `### Build candidates` subsection with a diagram of one first attempt with three candidates (build, gates, choice, the flow's later steps), and says how the choice is made, what carries on when none pass, that later attempts and reworks build one change, and what candidates cost. The Roles table has the selector"
    - "docs/reference.md: the flows documentation covers the build step key `candidates` with its rules and an example flow using it; the configuration table has the role `select` under models and max_steps; troubleshooting has rows for `candidates needs one build step followed by the gates` and a selector run recorded as `fallback`"
    - "NEXT.md marks item 14 done in its table, linking to docs/architecture.md#build-candidates"
    - "factory/templates/config.yaml has a commented example of a build step with candidates, with a one-line explanation. factory/templates/skills/factory-ops/SKILL.md covers choosing a flow with candidates and reading a task's candidate runs. The changed template files are copied to this repository's .claude/skills/factory-ops/, and .factory/config.yaml keeps every comment line of the template, so tests/test_templates.py passes"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "grep -q '^### Build candidates' docs/architecture.md"
    - "grep -q 'candidates' docs/reference.md"
    - "grep -q 'architecture.md#build-candidates' NEXT.md"
    - "grep -q 'candidates' factory/templates/config.yaml"
    - "grep -q 'candidates' factory/templates/skills/factory-ops/SKILL.md"
    - "uv run pytest -q tests/test_templates.py"
  risk: low

- id: flow-tuning-t06
  goal: "A bench trial on this repository compares six variants (default, gates-first, lean, strict, and gates-first and strict each with three candidates), its results are written up in docs/flow-trials.md, and `.factory/config.yaml` sets `flow:` to the variant the trial's rule picks"
  spec_refs:
    - "docs/plans/flow-tuning.md#the-trial"
    - "docs/plans/bench.md#results"
  depends_on:
    - flow-tuning-t04
  non_goals:
    - "Changing code, cases, prompts or models"
    - "A trial on cases beyond the shipped ones"
    - "Choosing a flow per task or by the contract's risk"
  acceptance:
    - ".factory/config.yaml defines `gates-first-x3` (plan, build with candidates: 3, gates, review, verify) and `strict-x3` (strict's steps with candidates: 3 on its build step), next to the existing gates-first and lean"
    - "One run of `factory bench run --flow default --flow gates-first --flow lean --flow strict --flow gates-first-x3 --flow strict-x3 --repeat 3 --max-cost 100` on the shipped cases has finished or reached its budget"
    - "docs/flow-trials.md has a section headed with the run's date that gives the factory version (`factory version`), the bench run id, the cases, the repeats and the budget, and a table with one row per variant: solved rate, false passes, mean attempts, cost per cell and minutes per cell, copied from `factory bench report`"
    - "The section applies the trial's rule and names its pick: the highest solved rate wins; variants within one solved cell of the best are compared by fewer false passes, then by lower cost per cell"
    - ".factory/config.yaml sets `flow:` to the pick, and tests/test_templates.py passes"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "factory bench report"
    - "grep -q '^## 20' docs/flow-trials.md"
    - "uv run pytest -q tests/test_templates.py"
  risk: low
```

Planned test additions:

| Task | Test | Kind |
|---|---|---|
| t01 | `tests/test_agent_loop.py`: the four tests named in its verification; `tests/test_pipeline.py`: two tests | unit, CLI end to end |
| t02 | `tests/test_flows.py`: two tests; `tests/test_candidates.py` (new file): six tests | unit, CLI end to end |
| t03 | `tests/test_candidates.py`: five tests; `tests/test_templates.py::test_selector_prompt_matches_choice_parser`; `tests/test_templates.py::test_role_prompts_ship_with_the_factory` (existing, now covering `select`) | CLI end to end, unit |
| t04 | `tests/test_bench.py`: three tests | unit, CLI end to end |
| t05 | none new: `tests/test_templates.py` (existing) | regression |
| t06 | none: by hand | — |

Every verification filter names a test the task adds, or an existing test file, so zero selected tests fails the gate. `tests/test_bench.py` doesn't exist on main yet: `bench-t03` adds it, and t04 runs after strict-flow, which waits for bench.

Tasks t01 to t05 are factory-runnable on this repository: their verification commands are `uv run pytest` and `grep`, and they run offline.

`flow-tuning-t06` is done by hand. It needs the network and a model budget, and its verification runs `factory bench report`, which the factory refuses, so `factory run` refuses the task and `factory run flow-tuning` lists it as manual. Run the bench, write docs/flow-trials.md and change the config on a branch, and open its PR yourself.

### Risks

1. **The re-ask doesn't fix it.** A model that rambled once may ramble again. **Action:** the outcome `CHANGES (no verdict)` is countable in `factory stats` and bench, and the reviewer's model is set in `.factory/config.yaml` (glm-5.3 since #50); a model that keeps failing is replaced there.
2. **Candidates multiply the cost of a task.** Three candidates are three first builds and three gates runs. **Action:** opt-in, at most five, on the first attempt only; `--max-cost` counts every candidate; bench reports cost per cell, and the trial compares each candidates flow with its single-build twin.
3. **The gates pass every candidate, so choosing adds little.** With builder-written tests, wrong changes pass too. **Action:** candidates come after strict-flow, whose locked tests are written by another agent; the selector compares the diffs against the contract; bench's false passes show whether the choice helps.
4. **The selector favours a position or the biggest diff.** **Action:** candidates are shown in an order seeded by the task id; the prompt judges fit to the contract, not size; the fallback and every choice are logged, and bench compares against the smallest-diff rule through the trial's `-x3` variants.
5. **Candidate worktrees are left behind.** A crash between builds leaves `TASK.cK` directories. **Action:** they are removed however the run ends, and `factory clean TASK` removes leftovers; a test covers each path.
6. **t01 can't stack on two open PRs that conflict.** `measure-t01` and `thoughts-t01` both change `factory/agents.py`. **Action:** merge both PRs (#55, #57) before running t01, so it builds on main; otherwise the factory refuses with `its open dependencies conflict`.
7. **Older docs tasks forbid editing the skill copies that #50's test now requires.** `bench-t06`, `measure-t04`, `strict-flow-t09` and `wiki-t07` had the non-goal "Editing the installed skill copies under .claude/skills". **Action:** this plan's PR rewrites that non-goal in the four contracts to require the copies, so their builders can pass `tests/test_templates.py`.
8. **The trial is expensive.** Six variants, five cases and three repeats are 90 cells, and the candidates variants cost more per cell. **Action:** `--max-cost 100` stops the run; results.json keeps every finished cell, and the trial's write-up names any variant that didn't finish.

---

## Problem

The flows now run gates-first on this repository (#50), but two weaknesses remain that no plan covers, and nothing yet turns bench's numbers into a choice.

- **A review without a verdict costs a rebuild.** `parse_verdict` (`factory/agents.py:80`) fails safe to CHANGES when a report has no `VERDICT:` line, and `LangChainRoles.step` keeps only the agent's last text (`factory/agents.py:339`). On this board, 4 of the 7 reviews that returned CHANGES had no verdict line: three ended on their own reasoning ("Final verdict: APPROVE", "End with VERDICT: APPROVE") and one was empty. Each one sent the build back with that reasoning as the rejection (`factory/pipeline.py:436`), and a build costs about $0.81 on this board. All four were `deepseek-v4-pro`, 4 of its 26 reviews.
- **A task gets one build per attempt.** `Pipeline.attempt` (`factory/pipeline.py:394`) runs the flow's build steps once in the task's only worktree (`create_worktree`, `factory/pipeline.py:196`). The largest measured gain in recent work on coding agents comes from building several candidates and picking one: one model went from 70.9% to 77.6% on SWE-bench Verified ([arXiv 2604.16529](https://arxiv.org/abs/2604.16529)), and an LLM verifier picking among three candidates scored 78.2% against their mean of 76.1% ([arXiv 2607.05391](https://arxiv.org/abs/2607.05391)). strict-flow left this out of scope until bench could measure it.
- **Nothing picks the default flow from data.** bench (`bench-t03` to `t06`) compares flows, but no task runs the comparison and acts on it. The flows research agrees on one method: add or remove one part at a time and measure ([Anthropic](https://www.anthropic.com/engineering/harness-design-long-running-apps)).

## Goal

A review that forgets its verdict is asked for it instead of costing a rebuild. A flow can build several candidates and keep the one that passes the gates and best fits the contract. A bench trial compares this repository's flows, with and without candidates, and its default flow is the one the trial picks.

## Design

### Asking again for a verdict

```text
review step ── report has VERDICT ──────────────────────────────▶ verdict as today
     │
     └─ no VERDICT line (incl. step limit, empty) ──▶ one more message, same conversation,
                                                      ≤ REASK_STEPS (3) model calls
            ├─ reply has VERDICT ──▶ that verdict, outcome "APPROVE (asked again)" / "CHANGES (asked again)"
            └─ still none ──────────▶ CHANGES, outcome "CHANGES (no verdict)",
                                      builder told: "Reviewer gave no verdict, so the change counts as rejected."
```

The re-ask continues the step's own conversation: the task message plus every message the agent produced, collected from the stream the step already reads. Its message:

```text
Your review ended without a VERDICT line. Reply with your report in the format your instructions give,
ending with exactly one line: VERDICT: APPROVE or VERDICT: CHANGES.
```

### Build candidates

```yaml
flows:
  gates-first-x3:
    - plan
    - {kind: build, candidates: 3}
    - gates                    # required directly after a build step with candidates
    - review
    - verify
```

```text
attempt 1:  build#1.1 (task worktree) ─▶ gates#1.1 ─┐
            build#1.2 (TASK.c2)       ─▶ gates#1.2 ─┼─▶ choose ─▶ reset branch ─▶ review ─▶ verify ─▶ PR
            build#1.3 (TASK.c3)       ─▶ gates#1.3 ─┘
                                                     none pass ─▶ closest candidate carries on
attempt 2+: one build on the chosen (or carried) candidate, as without candidates
```

| Case | What the factory does |
|---|---|
| No candidate passes the gates | The one with the fewest failing gates carries on, with its failures as feedback |
| One passes | It is chosen |
| Two or more pass | The selector chooses (t03); before t03, or when the selector gives no valid choice, the smallest diff wins |
| A later attempt or a rework | One build, as today |

A candidates flow needs exactly one build step, and the gates step directly after it, so every candidate is judged by the gates before anything else sees it. Under strict, the test step runs once before the candidates, and all of them build on its commit.

### The selector

A `select` role with its own prompt, like the four shipped roles. It reads the contract, and for each passing candidate its number, diffstat, diff and gate table, in an order seeded by the task id. It answers with findings per candidate and a last line `CHOICE: K`. It has read tools on the start commit and nothing else, and it runs once per task, only when two or more candidates pass.

### Comparing with bench

results.json records each step's `candidates`, and compare flags a change, as strict-flow-t08 does for `loop` and `prove`. Each cell records how many candidates were built and how many passed.

### The trial

| Variant | Steps |
|---|---|
| `default` | plan, build, review, gates, verify |
| `gates-first` | plan, build, gates, review, verify |
| `lean` | build, review, gates |
| `strict` | test, build (map, trim, nudge, resume), gates, review (prove, trim), verify |
| `gates-first-x3` | `gates-first` with candidates: 3 |
| `strict-x3` | `strict` with candidates: 3 |

`factory bench run --flow default --flow gates-first --flow lean --flow strict --flow gates-first-x3 --flow strict-x3 --repeat 3 --max-cost 100`, then `factory bench report`. The rule: the highest solved rate wins; variants within one solved cell of the best are compared by fewer false passes, then by lower cost per cell.

## Files Changed

| File | Change |
|---|---|
| `factory/agents.py` | The re-ask (t01); the `select` role, its tools and message (t03) |
| `factory/pipeline.py` | No-verdict feedback and outcomes (t01); candidate worktrees, builds, gates and choice (t02); the selector's run and fallback (t03) |
| `factory/flows.py` | The `candidates` build-step option and its rules (t02) |
| `factory/db.py` | The `candidate` runs column (t02) |
| `factory/cli.py` | Candidate labels in `factory show`, leftovers in `factory clean` (t02) |
| `factory/config.py` | The `select` role under models and max_steps (t03) |
| `factory/prompts/selector.md` | New: the selector's prompt (t03) |
| `factory/prbody.py` | The Checks line for a chosen candidate (t03) |
| `factory/bench/` | `candidates` in results and compare; per-cell candidate counts (t04) |
| `tests/fake_model.py` | A reviewer that omits its verdict (t01); a SELECTOR script (t03) |
| `tests/test_candidates.py` | New (t02, t03) |
| `docs/architecture.md`, `docs/reference.md`, `NEXT.md` | The re-ask (t01); candidates and the selector (t05) |
| `factory/templates/config.yaml`, `factory/templates/skills/factory-ops/`, `.claude/skills/factory-ops/` | Troubleshooting (t01); candidates (t05) |
| `docs/flow-trials.md`, `.factory/config.yaml` | The trial and the default flow it picks (t06, by hand) |

## Test Plan

### Unit tests

- `test_candidates_is_a_build_step_option`, `test_candidates_needs_one_build_step_followed_by_the_gates` (t02): parsing, range, kind, the one-build and gates-next rules, `factory config` output.
- `test_role_prompts_ship_with_the_factory` (existing, t03): now covers the selector prompt. `test_selector_prompt_matches_choice_parser` (t03): the prompt asks for the line the parser reads.

### End-to-end tests

Through `LangChainRoles` with scripted models (t01), and through `factory run` on the test suite's demo repository (t01 to t04):

- `test_a_review_without_a_verdict_is_asked_once_more`, `test_a_review_stopped_at_its_step_limit_is_asked_for_its_verdict`, `test_a_review_still_without_a_verdict_counts_as_changes`, `test_a_review_with_a_verdict_is_not_asked_again` (t01): the re-ask's message, limit, log and transcript event, and its outcomes.
- `test_a_review_without_a_verdict_tells_the_builder_none_came`, `test_a_review_answered_when_asked_again_routes_on_its_verdict` (t01): the builder's feedback, and the pipeline routing on the reply's verdict.
- `test_each_candidate_builds_in_its_own_worktree_from_the_same_start`, `test_the_smallest_passing_candidate_is_chosen`, `test_when_none_pass_the_closest_candidate_carries_on`, `test_later_attempts_and_reworks_build_one_change`, `test_candidate_worktrees_are_removed_however_the_run_ends`, `test_show_labels_each_candidate_and_the_chosen_one` (t02).
- `test_the_selector_picks_among_passing_candidates`, `test_a_selector_without_a_valid_choice_falls_back_to_the_smallest_diff`, `test_one_passing_candidate_needs_no_selector`, `test_the_selector_sees_candidates_in_a_seeded_order`, `test_the_pr_says_how_its_change_was_chosen` (t03).
- `test_results_record_candidates_and_compare_flags_a_change`, `test_cells_count_the_candidates_built_and_passed`, `test_a_candidates_cell_is_scored_on_the_chosen_candidate` (t04).

## Verification

1. `uv run pytest -q` passes after each task.
2. After t01, on a scratch board, a reviewer prompt override that never prints a VERDICT line gives a review run with outcome `CHANGES (no verdict)`, a `reask` event in its transcript, and a build attempt 2 whose feedback starts `Reviewer gave no verdict`.
3. After t03, `factory run demo-t01 --flow gates-first-x3 --no-pr` on a scratch repository shows three candidate builds and gates runs, then either the selector or `chose candidate K of 3 (1 passed the gates; smallest diff)`, and `factory show demo-t01` labels each candidate.
4. t06 is its own verification: `factory bench report` on the trial's run, the write-up in docs/flow-trials.md, and the `flow:` it sets.

## Cross-Workstream Coordination

- [Live agent-loop evaluation](agent-loop-perf.md) measures changes within each flow across revisions on a fixed suite. Its ongoing comparisons can inform this plan's separate trial to select a default. The two trials can run independently.

- **Depends on:** [measure](measure.md) (`measure-t01`, which t01 stacks on, and `factory stats` to count the new outcomes); [thoughts](thoughts.md) (`thoughts-t01`, which t01 stacks on); [strict-flow](strict-flow.md) (`strict-flow-t08` before t02, so candidates come after the step options, the locked tests and bench's step settings; `strict-flow-t09` before t05); [bench](bench.md) (the bench that t04 extends and t06 runs).
- **Required by:** [strict-flow](strict-flow.md) (`strict-flow-t01` now waits for t01, so the strict tasks' own reviews get the re-ask and their changes to `factory/agents.py` come after it); [wiki](wiki.md) (`wiki-t01` now waits for t04, the last code task here, and `wiki-t07` for t05); [security-review](security-review.md) (`security-review-t01` and `t02` wait for t04, and `security-review-t07` for t05: it changes the same `flows.py`, `agents.py`, `pipeline.py`, `config.py`, `db.py`, `cli.py` and docs, and adds a `security` step kind and role). [steer](steer.md) (`steer-t01` waits for t04: it adds a middleware and a Ctx field to `agents.py`, a `messages` table to `db.py`, and `factory say` to `cli.py`).

## Notes / Out of Scope

- **Running candidates concurrently.** Decided against for now: one after another keeps the board, the sandbox and the logs as they are. Revisit if the trial shows candidates pay off and their wall time is the problem.
- **Merging candidates into one change** (as [PatchFusion](https://arxiv.org/abs/2607.01597) does) or reviewing each candidate before choosing.
- **Candidates on later attempts or reworks**, and a candidate count chosen from the contract's `risk`.
- **Rerunning a review from scratch** when it gives no verdict twice, or treating it as an approval: decided against (see Locked Decisions).
- **A second reviewer.** Left out of this repository's flows in #50: no evidence it helps, and AI review comments are often wrong ([arXiv 2607.03316](https://arxiv.org/abs/2607.03316)).
