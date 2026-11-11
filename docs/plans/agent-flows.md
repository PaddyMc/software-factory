# Plan: Reshape the agent flow

**Status:** Planned (2026-11-02). Workstream scoped; awaiting kickoff. Roadmap: [NEXT.md item 7](../../NEXT.md#7-reshape-the-agent-flow).

---

## Execution Plan

### Locked Decisions

| Decision | Choice |
|---|---|
| What is configurable | **The agents themselves.** A flow is a named, ordered list of agent steps. Each step has a kind (`plan`, `build`, `review`, `verify`), which fixes its tools and how its output is used, plus its own prompt, model and step limit. The `gates` step is always present, so gates still run on the candidate before any PR |
| Runners | **Only the built-in LangChain loop.** External agent CLIs (Claude Code, Codex, OpenCode) are out of scope. The sandbox stays offline and secret-free |
| Where a flow is chosen | **`flow:` in `.factory/config.yaml`, overridden by `factory run --flow NAME`** for one task or plan run. Without either, the built-in `default` flow runs, which is today's pipeline. Every run records its flow and step. The 8-key contract doesn't change |
| Reworks | **The rework entry points stay as they are; the steps after them follow the flow.** Conflict resolution, CI fixes and human-review reworks skip the plan step and build on the PR's head, as today. From there they run the flow's build steps, review steps, gates and verify step |

### Milestones

| # | Deliverable | Exit criteria | Parallelizable with |
|---|---|---|---|
| **M1** | Flows in the config | `tests/test_flows.py` passes its parsing and validation tests; `factory config` prints the flows | pr-review-rework (it doesn't touch `config.py`) |
| **M2** | One way to run any step | Every agent runs through `LangChainRoles.step`; the existing suite passes unmodified; the prompt, model and tool tests in `tests/test_flows.py` pass | — |
| **M3** | The pipeline runs a flow | The flow-shape tests in `tests/test_pipeline.py` pass, and the existing pipeline tests pass unmodified | — |
| **M4** | Choosing flows, and reworks under them | `--flow` and rework-under-flow tests pass in `tests/test_pipeline.py` and `tests/test_scheduler.py` | — |
| **M5** | Docs | `docs/architecture.md`, `docs/reference.md`, NEXT.md and the factory-ops skill describe flows; `tests/test_templates.py` passes | — |

**Sequence:** `M1 ∥ pr-review-rework → M2 → M3 → M4 → M5`. M1 touches only `config.py` and a new `flows.py`, so it can run now. From M2 on, the tasks change `agents.py`, `pipeline.py` and `cli.py`, which pr-review-rework is changing through its t04. So M2 depends on `pr-review-rework-t04`, and each task after that depends on the one before.

### Task Contracts

| Milestone | Task IDs | Coverage |
|---|---|---|
| **M1** | `agent-flows-t01` | New `factory/flows.py` (`Step`, `Flow`, parsing, validation, the `default` flow); the `flow` and `flows` keys in `factory/config.py`; new `tests/test_flows.py` |
| **M2** | `agent-flows-t02` | `LangChainRoles.step` in `factory/agents.py` (prompt, model, step limit, tools and message per kind; the `earlier` context); `factory prompt STEP --flow F`; the VERDICT warning; tests in `tests/test_flows.py` |
| **M3** | `agent-flows-t03` | `factory/pipeline.py` builds its graph from the flow for fresh builds; the `runs.flow` and `runs.step` columns in `factory/db.py`; PR body per step; the progress label; the configured flow's keys checked by `factory run`; tests in `tests/test_pipeline.py` |
| **M4** | `agent-flows-t04` | `factory run --flow` (task and plan run, passed to children), unknown-flow refusal; resolve, CI and human-review reworks run the flow's steps; `--step` on `show`, `trace` and `transcript`; tests in `tests/test_pipeline.py` and `tests/test_scheduler.py` |
| **M5** | `agent-flows-t05` | `docs/architecture.md` (an "Agent flows" section, components), `docs/reference.md` (config keys and examples, `--flow`, `--step`, `factory prompt`, troubleshooting), NEXT.md, the factory-ops skill template |

```yaml
- id: agent-flows-t01
  goal: "`.factory/config.yaml` can define named agent flows (`flows:`) and pick the default one (`flow:`); they are parsed and validated into factory/flows.py's Flow and Step, and the built-in `default` flow is today's plan, build, review, gates, verify"
  spec_refs:
    - "docs/plans/agent-flows.md#design"
    - "docs/reference.md#configure-a-project"
  depends_on: []
  non_goals:
    - "Running a flow: factory/agents.py, factory/pipeline.py and factory/cli.py are not changed"
    - "Reading prompt files or checking provider keys: validation works on the config alone"
    - "Changing the `models` or `max_steps` keys: they still take role names only"
    - "Editing documentation (README.md, docs/architecture.md, docs/reference.md, NEXT.md)"
  acceptance:
    - "factory/flows.py defines frozen dataclasses Step(name, kind, model, max_steps), where kind is plan, build, review, verify or gates and model and max_steps may be None, and Flow(name, steps). DEFAULT is the flow `default`: plan, build, review, gates, verify, each named after its kind"
    - "Config gains `flow` (default \"default\") and `flows` (name -> Flow), parsed in factory/config.py through factory/flows.py. A step is either a string (plan, build, review, verify or gates: the step named after its kind) or a mapping with `kind` (required) and optional `name`, `model` and `max_steps`, where `max_steps` is a positive integer. Unknown keys raise ConfigError"
    - "Validation raises ConfigError naming the flow and step when: a flow name or step name doesn't match ^[a-z][a-z0-9-]*$; a flow is named `default`; `flow` names no flow; a step name repeats within a flow; a step is named after a kind other than its own (plan, build, review, verify, gates); a step is named resolve, ci, pr, human_review, planner, builder, reviewer or verifier; a mapping step has kind gates; or the order isn't: at most one plan step, first; then one or more build steps, contiguous; then review steps and at most one gates step in any order; then at most one verify step, last"
    - "A flow without a gates step gets one inserted after its last review step, or after its last build step when it has none, so every Flow holds exactly one gates step"
    - "`factory config` prints `flow` and the effective `flows`, built-in `default` included"
    - "docs/sessions/<today>.md has an entry for this task"
  verification:
    - "uv run pytest -q tests/test_flows.py::test_without_flows_the_default_flow_is_todays_pipeline tests/test_flows.py::test_a_flow_is_a_list_of_steps_with_kinds_models_and_step_limits tests/test_flows.py::test_gates_go_after_the_last_review_unless_placed tests/test_flows.py::test_flow_order_rules_are_enforced tests/test_flows.py::test_step_names_are_unique_and_not_reserved tests/test_flows.py::test_default_cannot_be_redefined_and_flow_must_name_a_flow tests/test_flows.py::test_factory_config_prints_the_flows"
    - "uv run pytest -q tests/test_config.py"
  risk: low

- id: agent-flows-t02
  goal: "Every agent runs through one LangChainRoles.step(step, ctx): each kind gets its tools and task message, and each step its prompt, model and step limit, so a flow's custom steps can run. The existing role methods delegate to it, with no change in behavior"
  spec_refs:
    - "docs/plans/agent-flows.md#design"
    - "docs/architecture.md#roles"
  depends_on:
    - agent-flows-t01
    - pr-review-rework-t04
  non_goals:
    - "Changing the pipeline graph, run records or the PR body (agent-flows-t03)"
    - "Adding `factory run --flow` (agent-flows-t04)"
    - "Editing factory/prompts/*.md or any documentation"
    - "Changing what the built-in plan, build, resolve, review or verify agents see, use or return"
  acceptance:
    - "LangChainRoles.step(step, ctx) runs a step of any kind. Tools: plan gets the read tools; build gets the read, write and sandboxed run tools; review gets the read tools and git_diff, and its Output carries parse_verdict's verdict; verify gets the read tools, git_diff and sandboxed run. Each kind's task message is the one its role method sends today. A build step's message also lists ctx.earlier, the earlier build steps' final messages in this attempt, when there are any"
    - "A step's prompt is .factory/agents/<name>.md in the main checkout when the step's name isn't its kind and that file exists. Otherwise it is its kind's prompt: the repository's override, else the shipped one"
    - "A step's model: --model, then the step's `model`, then the config's models[kind], then its prompt's frontmatter `model`, then the default. Its step limit: the step's `max_steps`, then max_steps[kind], then the prompt's frontmatter, then 60. agents.flow_models(root, flow, cfg, override) maps every agent step of a flow to its model"
    - "The log tag and transcript label is the step name, with #attempt for build and review steps, so the default flow logs exactly as today"
    - "plan, build, resolve, review and verify keep their signatures and call step() with the default flow's steps (resolve with the build step and the resolve tag). The existing suite passes unmodified"
    - "`factory prompt STEP [--flow F]` prints a step's resolved prompt, model and step limit; a role name works as before. When a review step's prompt has no `VERDICT:` line, `factory prompt` and the step's run log print a warning that every review will count as CHANGES"
    - "docs/sessions/<today>.md has an entry for this task"
  verification:
    - "uv run pytest -q tests/test_flows.py::test_a_custom_step_uses_its_own_prompt_or_its_kinds tests/test_flows.py::test_step_model_and_step_limit_precedence tests/test_flows.py::test_each_kind_gets_its_tools tests/test_flows.py::test_a_build_step_sees_the_earlier_build_steps tests/test_flows.py::test_a_review_prompt_without_a_verdict_line_is_warned_about tests/test_flows.py::test_factory_prompt_prints_a_flow_step"
    - "uv run pytest -q tests/test_agent_loop.py tests/test_pipeline.py"
  risk: medium

- id: agent-flows-t03
  goal: "A fresh build runs the configured flow: its plan step once, then attempts of every build step followed by its review steps and gates in flow order, then its verify step and the PR. Each run records its flow and step, and the default flow behaves exactly as today"
  spec_refs:
    - "docs/plans/agent-flows.md#design"
    - "docs/architecture.md#lifecycle-of-one-task"
  depends_on:
    - agent-flows-t02
  non_goals:
    - "The --flow flag, plan runs choosing a flow, and reworks (resolve, ci, human_review) under a non-default flow: agent-flows-t04"
    - "Changing any gate, the loop limit (--max-attempts) or the no-progress rule"
    - "Editing factory/prompts/*.md or any documentation"
  acceptance:
    - "pipeline.Options has a `flow` (a flows.Flow, default flows.DEFAULT), and cli.cmd_run_one sets it from the config's `flow`. Pipeline.graph builds the fresh-build path from it: the plan step if any, then an attempt node that runs every build step in order (each commits what it leaves, through _commit), then the review steps and the gates step in flow order, then the verify step if any, then pr"
    - "In an attempt, the first review step that returns CHANGES, or a gates failure, ends the attempt: the next attempt starts again at the first build step, with that feedback. Feedback from a custom review step names it (`Reviewer `NAME` requested changes:`). When HEAD is still the start after every build step, the attempt ends with today's no-change feedback, and no review or gate runs. --max-attempts and the identical-gate-failure stop apply as today"
    - "Without a plan step, build steps get `(This flow has no plan step: plan from the contract.)` as the plan. Without a verify step, the PR body has no Verifier report section. The PR body has one Reviewer report block per review step, titled with the step name, and a line naming the flow and its steps in order"
    - "factory/db.py: runs gain `flow` and `step` columns, migrated into older databases. A run's role stays its kind (the gates run is role verify, step gates), so db.ROLES, last_report and `--role` filters are unchanged. The progress label in `factory top` uses the step name"
    - "`factory run` checks the keys of every step's model in the configured flow before any work starts (agents.flow_models with missing_keys)"
    - "Under the default flow, every existing test in tests/test_pipeline.py passes unmodified"
    - "docs/sessions/<today>.md has an entry for this task"
  verification:
    - "uv run pytest -q tests/test_pipeline.py::test_a_flow_without_planner_or_report_opens_a_pr_on_passing_gates tests/test_pipeline.py::test_a_second_reviewer_requesting_changes_sends_the_build_back tests/test_pipeline.py::test_gates_before_review_skip_the_reviewers_when_gates_fail tests/test_pipeline.py::test_two_build_steps_both_run_each_attempt tests/test_pipeline.py::test_runs_record_their_flow_and_step tests/test_pipeline.py::test_a_custom_steps_model_key_is_checked_before_the_run"
    - "uv run pytest -q tests/test_pipeline.py tests/test_db.py"
  risk: high

- id: agent-flows-t04
  goal: "`factory run --flow NAME` picks the flow for one task or a whole plan run, and conflict resolutions, CI fixes and human-review reworks run the chosen flow's build steps, review steps, gates and verify step after their own entry"
  spec_refs:
    - "docs/plans/agent-flows.md#design"
    - "docs/architecture.md#merge-conflicts"
    - "docs/architecture.md#ci-failures"
  depends_on:
    - agent-flows-t03
  non_goals:
    - "A flow per task or per plan in the config, or a contract key for it"
    - "Rework-specific steps in a flow: a rework's entry (resolve, ci, human_review) is fixed"
    - "Changing how conflicts, CI failures or review requests are detected"
    - "Editing factory/prompts/*.md or any documentation"
  acceptance:
    - "`factory run TASK --flow NAME` and `factory run PLAN --flow NAME` run with that flow instead of the configured one. A plan run passes --flow to every child run. An unknown name is refused before any work with `unknown flow NAME (flows: default, …)`, and the keys of the chosen flow's models are checked as in agent-flows-t03"
    - "A conflict resolution with conflicts runs the resolve agent (the flow's first build step's model and step limit, the resolve message and tag), then the flow's review steps and gates in order. A clean replay goes straight to the gates. Changes requested after that send it to the flow's build steps"
    - "A CI fix and a human-review rework skip the plan step, run every build step of the flow with the rework's brief as feedback on each attempt, then its review steps and gates in order. Every review step of a human-review rework gets the review brief that pr-review-rework-t04 gives the reviewer. Push leases, PR comments and run records of each rework kind are unchanged, apart from the flow and step columns"
    - "`factory show`, `factory trace` and `factory transcript` accept `--step NAME`, and `factory show` labels each run with its step and the flow it ran under"
    - "docs/sessions/<today>.md has an entry for this task"
  verification:
    - "uv run pytest -q tests/test_pipeline.py::test_the_flow_flag_overrides_the_configured_flow tests/test_pipeline.py::test_an_unknown_flow_is_refused_before_any_work tests/test_pipeline.py::test_a_ci_fix_runs_the_flows_build_and_review_steps tests/test_pipeline.py::test_a_conflict_resolution_is_reviewed_by_every_review_step tests/test_pipeline.py::test_a_review_rework_runs_every_review_step_with_the_brief tests/test_pipeline.py::test_show_filters_runs_by_step"
    - "uv run pytest -q tests/test_scheduler.py::test_a_plan_run_passes_its_flow_to_each_task"
    - "uv run pytest -q tests/test_pipeline.py tests/test_scheduler.py tests/test_ci.py"
  risk: medium

- id: agent-flows-t05
  goal: "docs/architecture.md, docs/reference.md, NEXT.md and the shipped factory-ops skill describe agent flows: defining them, choosing one, how a flow runs, and reworks under one"
  spec_refs:
    - "docs/plans/agent-flows.md#design"
  depends_on:
    - agent-flows-t04
    - pr-review-rework-t05
  non_goals:
    - "Changing code or tests"
    - "Editing the installed skill copies under .claude/skills or .agents/skills: `factory init --force` refreshes them"
    - "Rewriting sections unrelated to flows"
  acceptance:
    - "docs/architecture.md: a `## Agent flows` section after `## Inside one agent: the loop` has a diagram of a flow's plan step, attempt loop, gates position and verify step, the order rules, how CHANGES and gate failures end an attempt, where reworks enter, and what runs record (role is the kind; flow and step columns). The Components table has a `flows.py` row, and the Roles section says roles are step kinds"
    - "docs/reference.md: the configuration table has `flow` and `flows`, with four example flows (lean: build, review; careful: plan, build, review, a second review step on another model, verify; gates-first: plan, build, gates, review, verify; test-first: a `tests` build step before the `build` step). The commands table covers `factory run --flow`, `factory prompt STEP --flow F` and `--step` on show, trace and transcript. Troubleshooting has rows for an unknown flow, a flow-order error, and a review prompt without a VERDICT line"
    - "NEXT.md marks item 7 done in its table, with a link to docs/architecture.md#agent-flows"
    - "factory/templates/skills/factory-ops/SKILL.md mentions --flow under starting runs and the flow and step a run records under explaining a run"
    - "docs/sessions/<today>.md has an entry for this task"
  verification:
    - "grep -q '^## Agent flows' docs/architecture.md"
    - "grep -q -- '--flow' docs/reference.md"
    - "grep -q 'docs/architecture.md#agent-flows' NEXT.md"
    - "grep -q -- '--flow' factory/templates/skills/factory-ops/SKILL.md"
    - "uv run pytest -q tests/test_templates.py"
  risk: low
```

Planned test additions:

| Task | Test | Kind |
|---|---|---|
| t01 | `tests/test_flows.py` (new file): the seven tests named in its verification; `tests/test_config.py` (existing) as regression | unit |
| t02 | `tests/test_flows.py`: the six tests named in its verification; `tests/test_agent_loop.py` and `tests/test_pipeline.py` (existing, unmodified) as regression | unit, CLI |
| t03 | `tests/test_pipeline.py`: the six flow tests named in its verification; the existing pipeline tests and `tests/test_db.py`, unmodified | CLI end to end, unit |
| t04 | `tests/test_pipeline.py`: the six tests named in its verification; `tests/test_scheduler.py::test_a_plan_run_passes_its_flow_to_each_task` | CLI end to end, unit |
| t05 | none new: `tests/test_templates.py` (existing) | regression |

Every verification filter names a test the task adds, or an existing test file, so zero selected tests fails the gate. Custom steps in the tests use prompts under the test repository's `.factory/agents/` that start with `You are the REVIEWER` (or `BUILDER`), so `tests/fake_model.py` plays them without changes. The tests tell steps apart through the `runs.step` column and the transcripts.

Prerequisite for `agent-flows-t02`: `pr-review-rework-t04` must be merged, or have an open PR for t02 to stack on. `agent-flows-t01` has no prerequisite and can run now.

Like pr-review-rework, every task is factory-runnable on this repository: the verification commands are `uv run pytest` and `grep`, and they run offline.

### Risks

1. **The default flow drifts from today's pipeline.** Generalizing the graph can quietly change run records, log lines, feedback text or the PR body that tests and people rely on. **Action:** t02 and t03 require the existing tests to pass *unmodified* under the default flow, and the run's role stays its kind.
2. **Conflicts with pr-review-rework.** Both workstreams rewrite `pipeline.py`'s nodes, `agents.py`'s messages and `cli.py`'s run path. **Action:** t02 onwards depend on `pr-review-rework-t04`, and t05 on `pr-review-rework-t05`. Only t01 runs alongside, and it touches no file that pr-review-rework changes, apart from the session log.
3. **A custom review prompt without a `VERDICT:` line.** `parse_verdict` fails safe to CHANGES, so such a flow burns every attempt and fails. **Action:** t02 warns in `factory prompt` and in the run log, and t05 adds a troubleshooting row.
4. **Cost grows with steps.** A flow with two reviewers and two builders multiplies the per-attempt cost by up to `--max-attempts`. **Action:** `--max-cost` already stops a task. The flow and step recorded on each run (t03) let `factory show` and later `factory stats` (NEXT.md item 3) break cost down by step and flow.
5. **Deep stacks.** If t02 starts while pr-review-rework t02–t04 are still open PRs, it stacks four PRs deep, and every merge below it restacks it. **Action:** start t02 after `pr-review-rework-t04` merges, unless you're reviewing the whole stack together.

---

## Problem

The agents a task goes through are hard-wired:

- `Pipeline.graph()` (`factory/pipeline.py:416`) wires a fixed `plan → build → review → verify → pr` graph. The only branches are the resolve and CI entry points.
- `factory/agents.py:27` fixes four roles (`ROLE_FILES`), and `LangChainRoles` (`factory/agents.py:268`–`305`) has one method per role, each with its tools and task message baked in.
- `factory/config.py:23` closes the role set. `models` and `max_steps` can only retune those four.
- `factory/db.py:18` closes the set of run roles that `show`, `trace` and `last_report` filter on.

So you can't try a flow without a planner, a second reviewer on another model, gates before review, or a test-writing step before the builder, short of editing the factory itself. You can't compare such flows either, because runs don't record what shaped them.

## Goal

A repository can define named agent flows in `.factory/config.yaml` and choose one by default or per run with `--flow`. Each run records the flow and step it ran under. With no flow configured, the factory behaves exactly as today, and gates still decide every PR.

## Design

### A flow

```yaml
flow: careful                     # the default for `factory run`; unset = the built-in `default`
flows:
  lean:                           # no planner, gates decide, no verifier report
    - build
    - review
  careful:
    - plan
    - build
    - review
    - {name: second-review, kind: review, model: "anthropic:claude-opus-5-5"}
    - verify
  gates-first:
    - plan
    - build
    - gates                       # placed explicitly: reviewers only see changes that pass the gates
    - review
    - verify
  test-first:
    - plan
    - {name: tests, kind: build}  # prompt: .factory/agents/tests.md
    - build
    - review
```

`default` is built in and can't be redefined. It's `plan, build, review, gates, verify`.

### Step kinds

| Kind | Tools | Output | Default prompt (role) |
|---|---|---|---|
| `plan` | read | The plan text every build step gets | planner |
| `build` | read, write, sandboxed `run` | A commit, made by the pipeline | builder |
| `review` | read, `git_diff` | `VERDICT: APPROVE` or `CHANGES` (missing = CHANGES) | reviewer |
| `verify` | read, `git_diff`, sandboxed `run` | The PR report | verifier |
| `gates` | none, it's not an agent | The gate table; any failure ends the attempt | — |

A **custom step** is a mapping with a `name` that differs from its kind. Its prompt is `.factory/agents/<name>.md` in the main checkout, or its kind's prompt when that file doesn't exist. A second reviewer on another model therefore needs no prompt file.

Resolution order, highest first:

- **Model:** `--model`, the step's `model`, `models[kind]`, the prompt's frontmatter, the default.
- **Step limit:** the step's `max_steps`, `max_steps[kind]`, the prompt's frontmatter, 60.

### Order rules

```text
[plan]?   build+   ( review | gates )*   [verify]?       exactly one gates; inserted after the last
  once    contiguous  any order              last        review (else the last build) when omitted
```

### How a flow runs

```text
fresh build ──► plan step (once) ──┐
                                   ▼
rework entry ──────────────► ┌─ attempt N ──────────────────────────────────────────┐
(resolve | ci |              │ build₁ → build₂ → …   (each commits what it left)      │
 human_review: no plan step) │ then review steps and gates, in flow order:          │
                             │   first CHANGES or gate failure ──► feedback ─► N+1  │
                             └───────────────────────┬──────────────────────────────┘
                                                     │ all passed
                                                     ▼
                                    verify step (if any) ──► push + PR
```

- **Attempts.** An attempt reruns every build step, so a test-first flow rewrites its tests when a reviewer asks. Each later build step also gets the earlier build steps' final messages from the same attempt.
- **Limits.** `--max-attempts` counts attempts. The stop on the same gates failing with the same output twice is unchanged.
- **Conflict resolution** runs the resolve agent on the flow's first build step's model. Later attempts run the flow's build steps. A clean replay goes straight to the gates.
- **Gates stay last for the code.** Review and verify steps don't commit, so the candidate the gates pass is the one that's pushed.

### What runs record

`runs.role` stays the kind (`plan`, `build`, `review`, `verify`, and today's `resolve`, `ci`, `pr`, `human_review`). The gates run keeps role `verify`. Two new columns, `runs.flow` and `runs.step`, hold the flow name and the step name. The default flow's records match today's apart from the two new columns. `factory show --step NAME` filters by step, and the `factory top` progress label shows the step name.

### PR body

- One `Reviewer report (<step>)` block per review step.
- The Verifier report only when the flow has a verify step.
- The Plan block only when it has a plan step.
- A line naming the flow and its steps in order.

## Files Changed

| File | Change |
|---|---|
| `factory/flows.py` | New: `Step`, `Flow`, `DEFAULT`, parsing and validation (t01) |
| `factory/config.py` | `flow` and `flows` keys (t01) |
| `factory/agents.py` | `LangChainRoles.step`, prompt, model and step-limit resolution, `Ctx.earlier`, `flow_models`, the VERDICT warning (t02) |
| `factory/pipeline.py` | `Options.flow`; the graph built from the flow; per-step PR body; progress label (t03); rework entries into the flow (t04) |
| `factory/db.py` | `runs.flow`, `runs.step` columns (t03) |
| `factory/cli.py` | `factory prompt STEP --flow` (t02); the flow's keys checked, `Options.flow` from config (t03); `--flow` on run and plan runs, `--step` on show, trace and transcript (t04) |
| `tests/test_flows.py` | New (t01, t02) |
| `tests/test_pipeline.py`, `tests/test_scheduler.py` | New tests (t03, t04) |
| `docs/architecture.md`, `docs/reference.md`, `NEXT.md`, `factory/templates/skills/factory-ops/SKILL.md` | Docs (t05) |
| `docs/sessions/<date>.md` | An entry per task (all) |

## Test Plan

### Unit tests

`tests/test_flows.py`:

- `test_without_flows_the_default_flow_is_todays_pipeline`: an empty config gives `flow == "default"` and DEFAULT's five steps.
- `test_a_flow_is_a_list_of_steps_with_kinds_models_and_step_limits`: string and mapping steps parse into `Step`s with their model and step limit.
- `test_gates_go_after_the_last_review_unless_placed`: gates are inserted after the last review, or after the last build; an explicit position is kept.
- `test_flow_order_rules_are_enforced`: each order violation raises ConfigError naming the flow and step.
- `test_step_names_are_unique_and_not_reserved`: duplicates, reserved names on another kind, a mapping `gates`, and bad name patterns are rejected.
- `test_default_cannot_be_redefined_and_flow_must_name_a_flow`
- `test_factory_config_prints_the_flows`
- `test_a_custom_step_uses_its_own_prompt_or_its_kinds` (t02): `.factory/agents/<name>.md` when present, else the kind's override or the shipped prompt.
- `test_step_model_and_step_limit_precedence` (t02)
- `test_each_kind_gets_its_tools` (t02): the tool names each kind's agent is built with.
- `test_a_build_step_sees_the_earlier_build_steps` (t02)
- `test_a_review_prompt_without_a_verdict_line_is_warned_about` (t02)
- `test_factory_prompt_prints_a_flow_step` (t02)

### End-to-end tests

Through the real CLI, pipeline, agents, git, bubblewrap and fake `gh`, with `ScriptedModel`.

`tests/test_pipeline.py`, t03:

- `test_a_flow_without_planner_or_report_opens_a_pr_on_passing_gates`: no plan or verify runs; the PR body has no Verifier report.
- `test_a_second_reviewer_requesting_changes_sends_the_build_back`: the attempt ends at the second reviewer; attempt 2 runs both builders and reviewers.
- `test_gates_before_review_skip_the_reviewers_when_gates_fail`
- `test_two_build_steps_both_run_each_attempt`: each step commits; the second sees the first's message.
- `test_runs_record_their_flow_and_step`
- `test_a_custom_steps_model_key_is_checked_before_the_run`

`tests/test_pipeline.py`, t04:

- `test_the_flow_flag_overrides_the_configured_flow`
- `test_an_unknown_flow_is_refused_before_any_work`
- `test_a_ci_fix_runs_the_flows_build_and_review_steps`
- `test_a_conflict_resolution_is_reviewed_by_every_review_step`
- `test_a_review_rework_runs_every_review_step_with_the_brief`
- `test_show_filters_runs_by_step`

`tests/test_scheduler.py`, t04:

- `test_a_plan_run_passes_its_flow_to_each_task`

## Verification

- `uv run pytest -q tests` passes after each task.
- Define the four example flows above in a scratch repository's `.factory/config.yaml`. `factory config` should print them, and `factory prompt second-review --flow careful` should show the reviewer prompt on Opus.
- `factory run demo-t01 --flow lean --no-pr` should leave no plan or verify runs, and `factory show demo-t01` should list each run's step and flow.

## Cross-Workstream Coordination

- **Depends on:** [pr-review-rework](pr-review-rework.md). `agent-flows-t02` waits for `pr-review-rework-t04` (the same `pipeline.py`, `agents.py` and `cli.py` code), and `agent-flows-t05` waits for `pr-review-rework-t05` (the same docs).
- **Required by:** [bench](bench.md): `bench-t03` waits for `agent-flows-t04` and runs fixture cases under each flow, and `bench-t06` waits for `agent-flows-t05`. NEXT.md item 3, "Measure the factory", whose `factory stats` can then group by flow and step. NEXT.md item 2, "The builder writes the test that judges it", can use a test-first flow.

## Notes / Out of Scope

- **External agent runners** (Claude Code, Codex, OpenCode as a step). They need network and an API key in the sandbox, a policy change of its own. A `runner:` field on a step is the natural extension point.
- **A flow per task or per plan.** Only the config default and `--flow` are supported. A plan-glob mapping or a 9th contract key would need decisions of their own.
- **Rework-specific steps in a flow** (e.g. a different reviewer for CI fixes). Reworks use the flow's steps after their fixed entry.
- **Reviews between build steps**, more than one plan or verify step, and parallel steps. The order rules can be loosened later without changing what a flow means today.
- **Comparing flows.** The data is recorded, but the comparison itself is `factory stats` (NEXT.md item 3) and [bench](bench.md) (NEXT.md item 8).
