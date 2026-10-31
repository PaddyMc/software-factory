---
name: plan-workstream
description: PM-mode workstream planning for a repository run by the software factory. Grounds in the project's settings (.factory/config.yaml), roadmap, existing plans and code; locks strategic decisions with the user before writing; produces a plan doc whose fenced-YAML task contracts `factory run` can execute; updates the roadmap; and on request emits a handoff brief. Explicit-invocation only — invoke when the user selects this skill in Codex (`$plan-workstream` or `/skills`) or types `/plan-workstream`. Do not auto-trigger on phrases like "plan X" or "let's plan a workstream".
---

# Plan Workstream

## Overview

Invoke with `/plan-workstream` in Claude Code or OpenCode, or `$plan-workstream` (or select it through `/skills`) in Codex.

Plan a unit of work as a reviewable, hand-off-able artifact: a plan doc in the project's plans location, whose **task contracts** the software factory executes (`factory run <task-id>`: planner → builder → reviewer → verifier agents, ending in a PR only when every gate passes). Also update the project's roadmap or priority doc if it has one, and (on request) write a concise engineer brief.

Locking strategic decisions with the user **before** writing the plan is the core discipline. It prevents wishlist plans and scope creep.

## Workflow

Run these five phases in order. Skip a phase only with explicit user direction.

### Phase 1: Ground

Read before proposing anything:

- **Factory settings.** Run `factory config` (or read `.factory/config.yaml`). It tells you:
  - `plans`: where plan docs live;
  - `e2e`: whether every task must add a new test, where, and in which language;
  - `session_log`: whether every task must add a session entry;
  - `unit_tests`: what the unit gate runs.

  Contracts must satisfy all of these.
- **Roadmap.** The project's priority or roadmap doc, if any. Look for it from `README.md`, `CLAUDE.md` or `AGENTS.md`.
- **Specs** that govern the area being planned.
- **Existing plans**, open and done. Cross-link dependencies, and reuse their structure.
- **Source code** being changed: its current shape, packages, test targets and test names.

**Placement.** If plans are organized by area (for example `<plans-dir>/<area>/{implemented,unimplemented}/`), follow that layout. Otherwise put the new plan next to the existing ones.

Produce a short status summary (what works, what's missing, what's in flight) before going further. A 5-row markdown table is usually enough.

### Phase 2: Lock decisions

Identify 2-4 **strategic** decisions that shape the workstream: scope, sequencing, prerequisites, trust models, data structures. Ask the user (with the host's user-input tool where available):

- Frame each question with 2-3 mutually exclusive options.
- Mark the recommended option "(Recommended)" and give a one-sentence rationale per option.
- Do NOT ask about implementation details (library names, variable names, exact code shapes).
- Do NOT ask more than 4 questions in one batch.

After answers come back, summarize the locked decisions in a table and proceed.

### Phase 3: Produce the plan doc

Write `<plans-dir>/[<area>/unimplemented/]<workstream-slug>.md` using the template below.

The plan MUST include a detailed, bounded **Task Contracts** section. Every contract is one independently reviewable task with a stable, workstream-prefixed unique `id` (`<slug>-t01`). Do not hide implementation work only in milestone prose.

Use a fenced YAML list whose items contain exactly these keys and no others: `id`, `goal`, `spec_refs`, `depends_on`, `non_goals`, `acceptance`, `verification`, `risk`. Each contract is executed on its own by `factory run <id>`, so it must be self-contained.

- **Status lives in the factory database, not the plan.** `factory status` shows it.
- **Dependencies.** A task runs once each `depends_on` task is merged or has an open PR. On an open PR it is built on top of it (a stacked PR), and the human merges bottom-up.
  - IDs must resolve within this plan, or to explicitly linked tasks in other plans.
  - The dependency graph must be acyclic.
  - Tasks that touch the same files must be serialized through `depends_on`, not presented as parallel.
- **Prerequisites.** If a task needs a human decision or an external prerequisite before it can run, say so in prose immediately after the YAML ("Prerequisite for `<id>`: …"), never in a YAML field.
- **The human gate is the PR merge.** Never encode approval in a contract.
- **Bounded change.** The builder may write anywhere in the worktree, so bound each task by its goal, acceptance and non-goals; name the modules it touches. The reviewer treats unrelated edits as findings.
- **Honest risk and decided content.** Assign `risk: low | medium | high` honestly. Make `goal` and `acceptance` observable, and leave no unresolved product decisions in any task.
- **Milestone mapping.** Map every milestone to task IDs outside the YAML, in a table. Cover tests and docs where relevant.
- **Verification commands** are exact and runnable **offline in the sandbox** at the candidate commit:
  - grounded in real packages, targets and test names;
  - planned tests labelled as planned additions;
  - a filter that selects zero tests is a failure, not a pass.
- **Gate requirements from `.factory/config.yaml`:**
  - with `e2e`, every task adds a NEW test directly under `e2e.dir`;
  - with `session_log`, every task adds `<session_log>/<today>.md`.
- **Work the factory can't run.** For example, a change to the factory itself, or one needing secrets or spending money. Keep it as a contract and state in prose that it's done by hand. A contract whose verification runs a command the factory refuses (`sudo`, `gh`, `terraform apply`, the project's `denied_commands`) is refused by `factory run`, and `factory validate-plan` warns about it.

### Phase 4: Coordinate

- Slot the workstream into the project's roadmap or priority doc, if there is one. Give it a number, plus its dependencies and what depends on it.
- Cross-link related plans in their own "Cross-Workstream Coordination" sections so dependencies are bidirectional.
- Run `factory validate-plan <plan>`, then `factory sync` to load the new tasks.

### Phase 5: Hand off (on request)

When the user asks for an engineer brief, write one with the brief template below. The brief is a **synthesis** that points at the plan doc as the source of truth; it doesn't duplicate it.

## Plan-doc template

````markdown
# Plan: <Workstream Name>

**Status:** Planned (YYYY-MM-DD). Workstream scoped; awaiting kickoff.

---

## Execution Plan

### Locked Decisions

| Decision | Choice |
|---|---|
| <decision 1> | <choice with one-line rationale if non-obvious> |
| <decision 2> | <choice> |

### Milestones

| # | Deliverable | Exit criteria | Parallelizable with |
|---|---|---|---|
| **M0** | <prerequisite or spike, if any> | <how we know it's done> | <other Mn or —> |
| **M1** | <first real deliverable> | <concrete exit gate> | <other Mn or —> |

**Sequence:** `M0 → M1 ∥ M2 → M3` (`∥` parallel, `→` sequential).

### Task Contracts

| Milestone | Task IDs | Coverage |
|---|---|---|
| **M0** | `<workstream-slug>-t01` | <what this task covers> |
| **M1** | `<workstream-slug>-t02` | <what this task covers, including tests/docs> |

```yaml
- id: <workstream-slug>-t01
  goal: "<one observable deliverable>"
  spec_refs:
    - "<path/to/spec.md#section>"
  depends_on: []
  non_goals:
    - "<explicitly excluded behavior>"
  acceptance:
    - "<observable condition that proves this task is complete>"
  verification:
    - "<exact offline command that runs the named test>"
  risk: low
```

Planned test additions: <map each new test to its task>. Each verification filter must select the intended test; zero matching tests is not a pass.

Prerequisite for `<workstream-slug>-t02` (if any): <external prerequisite or decision needed before `factory run`>.

### Risks

1. **<Risk name>.** <One sentence.> **Action:** <concrete mitigation>.

---

## Problem

<What's broken, missing, or needed. Cite file paths and line numbers.>

## Goal

<What success looks like in 1-3 sentences.>

## Design

<Technical detail needed to make milestones actionable. Diagrams in ASCII art, code shapes in fenced blocks.>

## Files Changed

| File | Change |
|---|---|
| `<path>` | <one-line description> |

## Test Plan

### Unit tests
<Planned test names and what each asserts.>

### End-to-end tests
<Planned e2e test names and what each asserts, through the real entry points.>

## Verification

<Commands and manual checks that confirm the workstream is done.>

## Cross-Workstream Coordination

- **Depends on:** <other workstreams and which of their tasks>
- **Required by:** <workstreams that need this to land>

## Notes / Out of Scope

<What is explicitly deferred, specifically enough to revisit later.>
````

## Engineer-brief template

Plain text, not a file, roughly 200-300 words:

```
**Task: <Workstream title>**

Plan doc: `<path>` — read this first; locked decisions and milestones are in the Execution Plan section at the top.

**Context:** <2-3 sentences. What's broken/missing, why now.>

**Scope:** <One sentence on what's in vs. out.>

**Deliverables:**
1. `<slug>-t01` — <deliverable in one phrase>
2. `<slug>-t02` — <deliverable in one phrase>

**Ready to start:** <ready task IDs, or none with the blocking reason>.

**Dependencies:** <task IDs and prerequisites, including linked cross-plan tasks>.

**Out of scope:** <key deferrals>

**Done when:** <concrete acceptance criteria>
```

## Rules and anti-patterns

- **No plan without locked decisions.** If Phase 2 was skipped, the plan is half-baked.
- **Recommendations belong in the question, not the plan.** The plan records what was decided, not what was considered.
- **Status is a date, never "TBD".** Use today's date and the state (`Planned`, `In-flight`, `Implemented`).
- **Milestones have exit criteria.** "Implement X" is not one; "test Y passes" is.
- **Risks need mitigations.** Every numbered risk gets a concrete `**Action:**`.
- **One workstream, one plan doc.** Genuinely coupled work becomes sibling plans that cross-link.
- **Coordination is bidirectional.** A "depends on" link needs a matching "required by" link.
- **The brief is not the plan.** Point at the plan; don't restate it.

Before emitting a plan, check:

- **Completeness:** every milestone maps to task IDs, and every task belongs to a milestone.
- **Schema:** `factory validate-plan <plan>` passes. Each item has exactly the 9 keys.
- **Dependencies:** they resolve, the graph is acyclic, and shared write scopes are serialized.
- **Gate fit:** every factory-run task can satisfy the configured `e2e` requirement, and its verification commands run offline.
- **Readiness:** decisions are locked, prerequisites are stated in prose, risks are honest, and there are no placeholders.

## When to skip phases

- **Phase 2:** only when the user already gave every decision in this conversation.
- **Phase 4 roadmap update:** only for tiny fixes the user says should not appear in the roadmap.
- **Phase 5:** unless the user explicitly asks for a brief.
