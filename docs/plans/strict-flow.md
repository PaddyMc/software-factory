# Plan: A stricter agent flow

**Status:** Planned (2026-11-13). Workstream scoped; awaiting kickoff: t01 starts once `measure-t03` and `bench-t05` have PRs. Roadmap: [NEXT.md item 9](../../NEXT.md#9-a-stricter-agent-flow), which also closes most of [item 2](../../NEXT.md#2-the-builder-writes-the-test-that-judges-it).

---

## Execution Plan

### Locked Decisions

| Decision | Choice |
|---|---|
| Scope | **Four changes.** A builder loop that bounds its context and resumes its conversation across attempts; a `test` step that writes the task's tests before the build; a lock on those tests; a reviewer that must prove findings about behaviour. Parallel build candidates and choosing a flow from the contract's `risk` are out of scope |
| Acceptance tests | **Written by a separate flow step, visible and locked.** A `test` step, on its own model, writes tests from the contract before the first build attempt, and the factory commits them on the task's branch. They must fail before the change; the candidate passes them through the existing `verification` gate; and a new gate fails a candidate that changed or removed a line the step wrote. The 8-key contract doesn't change |
| Sequencing | **After [measure](measure.md) and [bench](bench.md), before [wiki](wiki.md).** t01 depends on `measure-t03` and `bench-t05`, the last code tasks of those plans, and the docs task on `measure-t04` and `bench-t06`. `wiki-t01` now also depends on this plan's last code task, and `wiki-t07` on its docs task |
| Rollout | **Opt-in.** Every new behaviour is a step option or a step kind, and a built-in flow `strict` turns them all on. `default` stays today's pipeline: without the new keys nothing changes, so `factory bench` can compare the two |

### Milestones

| # | Deliverable | Exit criteria | Parallelizable with |
|---|---|---|---|
| **M1** | Bounded context: `loop: [trim]` | The t01 tests in `tests/test_loop.py` pass; the agent-loop, flow and tool suites pass unmodified | — |
| **M2** | Repository map and nudges: `loop: [map, nudge]` | The t02 tests in `tests/test_loop.py` pass | — |
| **M3** | Resumed attempts: `loop: [resume]` | The t03 tests in `tests/test_loop.py` and the resume test in `tests/test_pipeline.py` pass | — |
| **M4** | The `test` step | `tests/test_tester.py` and the t04 tests in `tests/test_pipeline.py` pass; flows without a test step run as before | — |
| **M5** | Red check and lock | The t05 tests in `tests/test_pipeline.py` and `tests/test_gates.py` pass | — |
| **M6** | The proving reviewer: `prove: true` | `tests/test_prove.py` and the t06 tests in `tests/test_pipeline.py` pass | — |
| **M7** | The built-in `strict` flow | The strict-flow tests in `tests/test_flows.py` and `tests/test_pipeline.py` pass | — |
| **M8** | Bench can compare it | The t08 tests in `tests/test_bench_cases.py` and `tests/test_bench.py` pass | — |
| **M9** | Docs | Architecture, reference, NEXT.md, the config template and the factory-ops skill describe it; `tests/test_templates.py` passes | — |

**Sequence:** `(measure-t03 ∥ bench-t05) → M1 → M2 → M3 → M4 → M5 → M6 → M7 → M8 → [measure-t04, bench-t06 →] M9`, then `M8 → wiki-t01` and `M9 → wiki-t07`. The code tasks run one after another: each one changes `factory/flows.py` and `factory/agents.py`, or `factory/pipeline.py`.

### Task Contracts

| Milestone | Task IDs | Coverage |
|---|---|---|
| **M1** | `strict-flow-t01` | The `loop` step option in `factory/flows.py`; capped reads in `factory/tools.py`; batch clearing of old tool results in `factory/agents.py`; new `tests/test_loop.py` |
| **M2** | `strict-flow-t02` | `map` and `nudge` in `factory/flows.py` and `factory/agents.py`; tests in `tests/test_loop.py` |
| **M3** | `strict-flow-t03` | `resume` in `factory/flows.py` and `factory/agents.py`; tests in `tests/test_loop.py` and `tests/test_pipeline.py` |
| **M4** | `strict-flow-t04` | The `test` kind in `factory/flows.py`; `test_paths` and the `test` role in `factory/config.py`; `factory/prompts/tester.md`; the tester's tools and message in `factory/agents.py` and `factory/tools.py`; the test node in `factory/pipeline.py`; the `test` run role in `factory/db.py`; the pre-run check in `factory/cli.py`; `tests/fake_model.py`; new `tests/test_tester.py` |
| **M5** | `strict-flow-t05` | The red check and the builder's block in `factory/pipeline.py` and `factory/agents.py`; the `acceptance_untouched` gate in `factory/gates.py`; tests in `tests/test_pipeline.py` and `tests/test_gates.py` |
| **M6** | `strict-flow-t06` | `prove` in `factory/flows.py`; the reviewer's `run` tool, proof rules, REPRO re-run and verdict in `factory/agents.py`; the worktree restore in `factory/pipeline.py`; new `tests/test_prove.py` |
| **M7** | `strict-flow-t07` | `flows.STRICT` and its place in `factory/config.py`; the same-model warning in `factory/cli.py`; an end-to-end strict run in `tests/test_pipeline.py` |
| **M8** | `strict-flow-t08` | `test_paths` in the shipped cases under `factory/bench/fixtures/`; the test-paths refusal and the `loop` and `prove` fields in `factory/bench/`; tests in `tests/test_bench_cases.py` and `tests/test_bench.py` |
| **M9** | `strict-flow-t09` | `docs/architecture.md`, `docs/reference.md`, `NEXT.md`, `factory/templates/config.yaml`, the factory-ops skill template |

```yaml
- id: strict-flow-t01
  goal: "A flow step can set `loop: [trim]`: the agent's file reads are capped and old tool results are cleared from its conversation in batches, so a long run stays within a bounded context. Steps without `loop` run exactly as today"
  spec_refs:
    - "docs/plans/strict-flow.md#step-options"
    - "docs/plans/strict-flow.md#trim"
    - "docs/architecture.md#inside-one-agent-the-loop"
    - "factory/agents.py"
    - "factory/tools.py"
  depends_on:
    - measure-t03
    - bench-t05
  non_goals:
    - "The loop values map, nudge and resume (strict-flow-t02, strict-flow-t03): `loop` accepts only `trim` after this task"
    - "Summarizing old steps with a model call, or changing what grep, run or git_diff return"
    - "Changing factory/pipeline.py or factory/gates.py"
    - "Changing the default flow, the shipped prompts or any documentation"
  acceptance:
    - "factory/flows.py: Step gains `loop`, a tuple of behaviour names (default empty). A step mapping accepts `loop` as a list of names from flows.LOOP, which holds only `trim` after this task. An unknown name, a repeated name, a value that isn't a list, or `loop` on a gates step raises ConfigError naming the flow and step. `factory config` prints each step's loop"
    - "Reads are capped: under `trim`, read_file returns at most tools.READ_CAP (400) lines per call, starting at `start`. When lines remain, the result ends with one line giving how many more there are, the file's total, and the `start` to read on from. Without `trim`, read_file returns what it returns today"
    - "Old results are cleared in batches: under `trim`, before a model call whose conversation exceeds agents.TRIM_AT (60000) tokens by langchain's approximate count, the content of every tool result except the most recent agents.TRIM_KEEP (8) is replaced by a one-line placeholder that names the tool and its arguments and says to call it again if needed. A cleared result stays cleared for the rest of the conversation, and nothing more is cleared until the conversation, counted with its placeholders, exceeds TRIM_AT again"
    - "The model sees the trimmed conversation, and the transcript keeps every tool result in full as today. Each batch adds a transcript event of type `trim` with the number of results cleared and the approximate token counts before and after, and a log line under the step's tag"
    - "The run's steps, tokens, cost and step limit are counted as today. A step without `loop` builds its agent with the same middleware and tools as before: tests/test_agent_loop.py, tests/test_flows.py, tests/test_tools.py and tests/test_pipeline.py pass unmodified"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_loop.py::test_loop_is_a_list_of_known_behaviours tests/test_loop.py::test_trim_caps_a_read_and_says_how_to_read_on tests/test_loop.py::test_trim_clears_old_results_in_batches_and_keeps_the_latest tests/test_loop.py::test_cleared_results_stay_cleared_and_the_transcript_keeps_them tests/test_loop.py::test_without_loop_the_agent_is_built_as_today"
    - "uv run pytest -q tests/test_agent_loop.py tests/test_flows.py tests/test_tools.py"
  risk: medium

- id: strict-flow-t02
  goal: "A flow step can also set `loop: [map]`, which ends its task message with a map of the repository and the contract's spec references, and `loop: [nudge]`, which tells the agent once when it nears its step limit, keeps editing one file, or keeps running one failing command"
  spec_refs:
    - "docs/plans/strict-flow.md#map"
    - "docs/plans/strict-flow.md#nudge"
    - "factory/agents.py"
  depends_on:
    - strict-flow-t01
  non_goals:
    - "The loop value resume (strict-flow-t03)"
    - "Stopping a run that keeps looping: a nudge is a message, and the step limit still ends the run"
    - "Changing factory/pipeline.py, factory/gates.py or factory/tools.py's tools"
    - "Changing the default flow, the shipped prompts or any documentation"
  acceptance:
    - "flows.LOOP gains `map` and `nudge`, valid on every agent step"
    - "Under `map`, the step's task message ends with a `# Repository map` block built from the files git tracks in the worktree: top-level files by name, and every directory to depth 2 with its tracked-file count, in at most agents.MAP_LINES (120) lines with a last line counting what was left out. Under it, a `# Spec references` list gives each of the contract's spec_refs whose path (the part before any `#`) is a tracked file, with its line count, and marks the others `(not a file)`. In a directory that isn't a git work tree the block is left out"
    - "Under `nudge`, when the run has made three quarters of its allowed model calls (rounded up), the next model call is preceded by one human message giving the calls used and allowed, and telling the agent to finish, run its checks and write its final report"
    - "Under `nudge`, the agent gets one human message the first time write_file and edit_file have together written the same path agents.NUDGE_EDITS (6) times in the run, naming the path, and one the first time the same `run` command has exited non-zero agents.NUDGE_FAILS (3) times in a row, naming the command. Each path and each command is nudged at most once"
    - "Every nudge is recorded in the transcript as an event of type `nudge` with its kind (budget, edits or failing) and its text, and logged under the step's tag. A nudge isn't a model call: the run's steps are counted as today"
    - "A step without `map` or `nudge` gets the same messages as before: tests/test_agent_loop.py, tests/test_flows.py and tests/test_pipeline.py pass unmodified"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_loop.py::test_map_lists_the_tree_and_the_spec_references tests/test_loop.py::test_map_is_left_out_outside_a_git_work_tree tests/test_loop.py::test_nudge_warns_once_near_the_step_limit tests/test_loop.py::test_nudge_names_a_file_edited_again_and_again tests/test_loop.py::test_nudge_names_a_command_that_keeps_failing"
    - "uv run pytest -q tests/test_loop.py tests/test_agent_loop.py tests/test_flows.py"
  risk: medium

- id: strict-flow-t03
  goal: "A build step can set `loop: [resume]`: its second and later attempts in a run continue the first attempt's conversation with the new feedback, instead of starting again from the plan"
  spec_refs:
    - "docs/plans/strict-flow.md#resume"
    - "docs/architecture.md#lifecycle-of-one-task"
    - "factory/agents.py"
  depends_on:
    - strict-flow-t02
  non_goals:
    - "Resuming across separate `factory run` invocations (a rework or a rerun starts a fresh conversation), or after a conflict resolution"
    - "Resuming plan, review or verify steps"
    - "Changing --max-attempts, the no-progress stop, or what the feedback says"
    - "Changing factory/pipeline.py's graph, factory/gates.py, the default flow, the shipped prompts or any documentation"
  acceptance:
    - "flows.LOOP gains `resume`. It is valid only on build steps: on any other kind it raises ConfigError naming the flow and step"
    - "Under `resume`, attempt 1 of the step runs as today. On a later attempt of the same step in the same run, the model receives the messages of the step's earlier attempts (as `trim` left them, when it is set), followed by one new human message: a heading `# Attempt` with the attempt number, the feedback under `# Feedback to address first`, and the earlier build steps of this attempt when there are any. The plan and the repository map are not sent again"
    - "The step limit applies to each attempt on its own, and each attempt's run records only its own model calls, tokens and cost"
    - "The attempt's transcript starts with an event of type `resumed` giving the number of messages carried over, then the new human message; the earlier messages aren't written again"
    - "The step starts a fresh conversation, with a log line saying why, when there is nothing to resume: the run's first attempt of the step (so also the first attempt of a CI fix or a human-review rework), an attempt after a conflict resolution, or an earlier attempt that ended in an error. Hitting the step limit is not an error: the next attempt resumes"
    - "A flow whose build step has no `resume` behaves as today: tests/test_pipeline.py and tests/test_flows.py pass unmodified apart from the tests this task adds"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_loop.py::test_resume_is_for_build_steps_only tests/test_loop.py::test_a_resumed_attempt_continues_the_conversation_with_the_feedback tests/test_loop.py::test_each_attempt_has_its_own_step_limit_and_counts tests/test_loop.py::test_the_first_attempt_and_a_resolve_start_fresh tests/test_pipeline.py::test_a_resuming_builder_gets_gate_feedback_in_the_same_conversation"
    - "uv run pytest -q tests/test_loop.py tests/test_pipeline.py tests/test_flows.py"
  risk: high

- id: strict-flow-t04
  goal: "A flow can have a `test` step: once, before the first build attempt, a tester agent writes the task's tests under the repository's `test_paths`, and the factory commits them on the task's branch"
  spec_refs:
    - "docs/plans/strict-flow.md#the-test-step"
    - "docs/plans/strict-flow.md#step-options"
    - "factory/pipeline.py"
    - "factory/flows.py"
  depends_on:
    - strict-flow-t03
  non_goals:
    - "Checking that the tests fail before the change, locking them against the builder, or telling the builder about them (strict-flow-t05)"
    - "Running the test step in a conflict resolution, a CI fix or a human-review rework: like the plan step, it runs on fresh builds only"
    - "A built-in flow that uses the step (strict-flow-t07)"
    - "Changing the 8-key contract, the default flow or any documentation"
  acceptance:
    - "flows.KINDS gains `test`. The order becomes: an optional plan step, an optional test step, the build steps, then review steps and gates, then an optional verify step. There is at most one test step, directly before the first build step, and `tester` joins the reserved step names. A test step takes `model`, `max_steps` and `loop` (trim, map, nudge) like any agent step"
    - "Config gains `test_paths`, a list of path globs (default empty) in the syntax of `plans` and `exclude` (factory/globs.py), printed by `factory config`. `models` and `max_steps` accept the role `test`"
    - "A tester role ships as factory/prompts/tester.md (`You are the TESTER`, model openrouter:z-ai/glm-5.3, max_steps 60): it writes tests from the contract's acceptance criteria and verification commands, only tests, never the change itself. .factory/agents/tester.md overrides it, and `factory prompt test` prints it"
    - "A test step's agent has the read tools, write_file and edit_file limited to paths matching `test_paths` (any other path is refused, naming the globs), and the sandboxed `run`. Its task message names the task, the `test_paths` globs, and the contract's verification commands that verification.is_test_command recognizes"
    - "On a fresh build the pipeline runs the test step once, after the plan step when there is one and before attempt 1, with status `building`. It commits what the step left as `factory(ID): acceptance tests`, ID being the task id, and records a run with role `test` (db.ROLES gains it), the try number as its attempt, outcome `committed`, and the tester's final message as its report. Build attempts start from that commit: an attempt that leaves HEAD there counts as no changes, as leaving it at the base does today"
    - "A try that changes nothing, or changes a path outside `test_paths`, is discarded: the worktree goes back to the base and the step runs once more, with the reason and the offending paths as feedback in its task message. Each try is its own `test` run, with outcome `no-changes` or `out-of-scope`. After pipeline.TEST_TRIES (2) failed tries the task fails with the reason in its note, and no build runs"
    - "`factory run` refuses, before any work, a flow with a test step when `test_paths` is empty, with `flow NAME has a test step: set test_paths in .factory/config.yaml` (NAME being the flow), and checks the test step's provider key like any other step's"
    - "The PR body has an `Acceptance tests (NAME)` details block with the tester's report, NAME being the step's name, and its Flow line lists the step"
    - "Flows without a test step behave as today: the existing tests pass unmodified, and tests/fake_model.py gains a TESTER script without changing what the other roles play"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_tester.py::test_a_test_step_goes_between_plan_and_build tests/test_tester.py::test_test_paths_and_the_test_role_are_configurable tests/test_tester.py::test_the_tester_writes_only_under_test_paths tests/test_tester.py::test_the_tester_prompt_ships_and_can_be_overridden"
    - "uv run pytest -q tests/test_pipeline.py::test_a_test_step_commits_the_tests_before_the_first_build tests/test_pipeline.py::test_a_test_step_that_writes_outside_test_paths_is_retried_then_fails_the_task tests/test_pipeline.py::test_a_flow_with_a_test_step_needs_test_paths tests/test_pipeline.py::test_reworks_skip_the_test_step"
    - "uv run pytest -q tests/test_pipeline.py tests/test_flows.py tests/test_templates.py tests/test_db.py"
  risk: high

- id: strict-flow-t05
  goal: "The test step's tests are shown to fail before the change and are then locked: the factory runs the task's test commands at the test commit and requires a failure, tells the builder which tests it must make pass, and a new acceptance_untouched gate fails a candidate that changed or removed a line the test step wrote"
  spec_refs:
    - "docs/plans/strict-flow.md#the-red-check"
    - "docs/plans/strict-flow.md#the-lock"
    - "NEXT.md#2-the-builder-writes-the-test-that-judges-it"
    - "factory/gates.py"
    - "factory/verification.py"
  depends_on:
    - strict-flow-t04
  non_goals:
    - "A gate that runs the tests again with the change taken out of the candidate"
    - "Letting the builder dispute a test and have it rewritten in the same run: a task whose tests can't be met fails, and running it again writes new tests"
    - "Applying the lock to conflict resolutions, CI fixes or human-review reworks, where a reviewer may ask for a test to change"
    - "Changing the 8-key contract, the verification gate, the default flow or any documentation"
  acceptance:
    - "A task's acceptance commands are its verification commands that verification.is_test_command recognizes, plus, when the config has `e2e.run_new`, that command for each new e2e test the test step added (found as gates.new_e2e_tests finds them)"
    - "When a task has no verification test command and the config has no `e2e`, the test step doesn't run: a `test` run is recorded with outcome `skipped` and a one-line reason, nothing is committed, and the rest of the flow runs as if it had no test step"
    - "After committing a try, the pipeline runs every acceptance command in the sandbox at that commit. A command is red when it fails and didn't select zero tests (verification.classify gives fail and verification.tests_run isn't 0); a build or import error counts as red. The try fails when a command selects zero tests (`COMMAND selects no tests: write the tests it names`, COMMAND being the command) or when no command is red (`the tests pass before the change`). It then counts as a failed try under strict-flow-t04's retry rule, with outcome `not-red`. Otherwise the run's outcome is `committed`, and its report ends with the red commands and the commands that already pass"
    - "Every build message that starts a conversation (attempt 1, and a later attempt that doesn't resume) gains an `# Acceptance tests (locked)` block: the files the test step wrote, the red commands, the rule that those files may gain lines but none the test step wrote may change or go, and that a test contradicting the contract is reported in the final message with `RESULT: BLOCKED` and the reason"
    - "gates.run_gates accepts the test commit and its files and then adds an `acceptance_untouched` gate after `plan_untouched`. It passes when every file the test step wrote still exists at the candidate and the diff from the test commit to the candidate removes no line from them. Its detail lists the files and the red commands, or each file with removed lines. Without a test commit (a flow without a test step, a skipped step, `factory gates`, resolutions and reworks) the gate is absent"
    - "The PR body's Acceptance tests block lists the red commands, and its gate table shows acceptance_untouched"
    - "Runs without a test commit behave as today: tests/test_gates.py and tests/test_pipeline.py pass unmodified apart from the tests this task adds"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_pipeline.py::test_tests_that_pass_before_the_change_are_rejected tests/test_pipeline.py::test_a_verification_command_that_selects_no_tests_sends_the_tester_back tests/test_pipeline.py::test_the_builder_is_told_which_tests_are_locked tests/test_pipeline.py::test_a_builder_that_edits_a_locked_test_fails_the_gate tests/test_pipeline.py::test_a_task_without_test_commands_skips_the_test_step"
    - "uv run pytest -q tests/test_gates.py::test_acceptance_untouched_allows_added_lines_only tests/test_gates.py::test_acceptance_untouched_is_absent_without_a_test_commit"
    - "uv run pytest -q tests/test_pipeline.py tests/test_gates.py tests/test_tester.py"
  risk: high

- id: strict-flow-t06
  goal: "A review step can set `prove: true`: the reviewer gets the sandboxed `run` tool and backs each finding about behaviour with a REPRO command, the factory runs those commands again, and a CHANGES verdict counts only with a reproduced failure or a scope finding"
  spec_refs:
    - "docs/plans/strict-flow.md#the-proving-reviewer"
    - "factory/prompts/reviewer.md"
    - "factory/agents.py"
  depends_on:
    - strict-flow-t05
  non_goals:
    - "Judging whether a REPRO demonstrates the finding it sits under: the factory checks only that the command fails on the candidate"
    - "Changing review steps without `prove`, the shipped reviewer prompt, or how APPROVE and CHANGES route in the pipeline"
    - "Giving the reviewer write tools"
    - "Changing the default flow or any documentation"
  acceptance:
    - "A review step mapping accepts `prove`, a boolean (default false) kept on flows.Step. On any other kind, or with a value that isn't a boolean, it raises ConfigError naming the flow and step. `factory config` prints it"
    - "Under `prove`, the reviewer has the read tools, git_diff and the sandboxed `run` (denied commands are refused as for the builder), and its system prompt gains a `# Proof rules` block after the project rules. The rules: a blocker or major finding about what the code does when it runs carries a line `REPRO:` with one shell command that fails on the candidate; a finding about scope (a non-goal done, an acceptance criterion with no change behind it, an unrelated edit, documentation made untrue) is tagged `[scope]` and cites path:line; CHANGES counts only with a failing REPRO or a `[scope]` blocker or major"
    - "After the review, the factory runs each distinct REPRO command again in the sandbox: at most agents.PROVE_MAX (5) of them, each for at most agents.PROVE_TIMEOUT (300) seconds. A command is reproduced when it exits non-zero. One that passes, times out, or matches a denied pattern is unproven. The report gains a `## Proof` section with each command, its result and the last lines of its output"
    - "A reported CHANGES stands when at least one REPRO is reproduced, or the report has a blocker or major finding tagged `[scope]`. Otherwise the step's verdict is APPROVE, its run's outcome reads `APPROVE (unproven)`, and the findings stay in its report and in the PR body. A reported APPROVE stays APPROVE. A report with no VERDICT line counts as CHANGES, as today, whatever its proof"
    - "When CHANGES stands, the builder's feedback is the report with its Proof section, so the builder gets each reproduced command and its output"
    - "After a review step with `prove`, the pipeline puts the worktree back at the candidate (tracked files reset, untracked files removed, ignored files kept) and logs what it removed, so nothing the reviewer's commands wrote can fail the clean gate"
    - "Review steps without `prove` behave as today: tests/test_pipeline.py, tests/test_flows.py and tests/test_templates.py pass unmodified apart from the tests this task adds"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_prove.py::test_prove_is_a_review_step_option tests/test_prove.py::test_a_proving_reviewer_can_run_commands_and_gets_the_proof_rules tests/test_prove.py::test_changes_stands_on_a_reproduced_failure tests/test_prove.py::test_changes_stands_on_a_scope_finding tests/test_prove.py::test_unproven_changes_becomes_an_approval tests/test_prove.py::test_a_passing_timed_out_or_denied_repro_is_unproven tests/test_prove.py::test_a_missing_verdict_is_still_changes"
    - "uv run pytest -q tests/test_pipeline.py::test_a_proving_review_leaves_the_worktree_at_the_candidate tests/test_pipeline.py::test_an_unproven_review_does_not_send_the_build_back"
    - "uv run pytest -q tests/test_pipeline.py tests/test_flows.py tests/test_templates.py"
  risk: high

- id: strict-flow-t07
  goal: "A built-in flow `strict` turns the new behaviour on together: a test step, a build step that maps, trims, nudges and resumes, the gates, a proving review, and the verifier's report. `default` stays today's pipeline"
  spec_refs:
    - "docs/plans/strict-flow.md#the-strict-flow"
    - "docs/plans/agent-flows.md#a-flow"
    - "factory/flows.py"
  depends_on:
    - strict-flow-t06
  non_goals:
    - "Making strict the flow `factory run` uses when no flow is configured, or changing the default flow"
    - "A flow chosen per task, per plan or by the contract's risk"
    - "Changing factory/bench/ or any documentation (strict-flow-t08, strict-flow-t09)"
  acceptance:
    - "flows.STRICT is the flow `strict`: a test step with loop map, trim and nudge; a build step with loop map, trim, nudge and resume; the gates step; a review step with prove and loop trim; a verify step. Each step is named after its kind and takes its model and step limit from its kind. It has no plan step"
    - "Config.flows always holds `default` and `strict`. Defining a flow named `strict` raises ConfigError, as redefining `default` does. `flow: strict` and `factory run --flow strict` select it, a plan run passes it to its child runs, and `factory config` prints it"
    - "`factory run` warns, in the run log and on stderr, when a flow's test step and one of its build steps resolve to the same model, since the tests then share the builder's blind spots. The run goes ahead. `factory prompt test --flow strict` prints the same warning"
    - "A fresh build under strict on the test suite's demo repository, with `test_paths` set and a contract whose verification runs a test, ends in an open PR. Its runs are, in order: a test run, a build attempt whose gates fail, a second build attempt that resumes the first one's conversation, passing gates, a proving review, the verifier's report, and the PR"
    - "tests/test_flows.py::test_without_flows_the_default_flow_is_todays_pipeline and tests/test_pipeline.py::test_an_unknown_flow_is_refused_before_any_work are updated for the second built-in flow (the flows mapping, and the flow names listed in the refusal). Every other existing test passes unmodified"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_flows.py::test_strict_is_built_in_and_cannot_be_redefined tests/test_flows.py::test_without_flows_the_default_flow_is_todays_pipeline tests/test_pipeline.py::test_the_strict_flow_tests_builds_gates_and_proves_before_a_pr tests/test_pipeline.py::test_a_tester_and_builder_on_one_model_are_warned_about tests/test_pipeline.py::test_an_unknown_flow_is_refused_before_any_work tests/test_scheduler.py::test_a_plan_run_passes_its_flow_to_each_task"
    - "uv run pytest -q tests/test_flows.py tests/test_pipeline.py tests/test_scheduler.py"
  risk: medium

- id: strict-flow-t08
  goal: "`factory bench` can compare strict with other flows: the shipped cases declare their test_paths and are shown to work under a test step, and bench results record each step's loop and prove settings, so compare reports when they changed"
  spec_refs:
    - "docs/plans/strict-flow.md#comparing-with-bench"
    - "docs/plans/bench.md#a-case"
    - "docs/plans/bench.md#results"
  depends_on:
    - strict-flow-t07
  non_goals:
    - "New cases, or changing any case's contract, hidden tests or solution"
    - "Changing how cells run or how they are scored"
    - "Running a bench with real models: that is done by hand (see the plan's Verification)"
    - "Editing documentation"
  acceptance:
    - "Every case under factory/bench/fixtures/, and the test-only case under tests/bench_cases/, has `test_paths` in its case.yaml config, covering the test file its contract's verification names"
    - "For every shipped case: with the files of solution/ that match test_paths committed on the base as the test step's commit, the task's acceptance commands are red; with the whole solution on top, every gate passes, acceptance_untouched included"
    - "`factory bench run` refuses, before any cell starts, a variant whose flow has a test step for a case whose config has no test_paths, naming the case and the flow"
    - "results.json records `loop` and `prove` for each step of each variant, and `factory bench compare` lists a step whose loop or prove differs between the two runs in its header, as it lists a changed model or prompt"
    - "A bench cell under strict on the test-only case, with scripted models, ends `solved`, and its runs include the test step and the proving review"
    - "The existing tests in tests/test_bench.py and tests/test_bench_cases.py pass unmodified, except that an assertion pinning a case's fixture hash or base commit may be updated for the test_paths change"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_bench_cases.py::test_every_shipped_case_works_under_a_test_step tests/test_bench.py::test_a_flow_with_a_test_step_needs_the_cases_test_paths tests/test_bench.py::test_results_record_loop_and_prove_and_compare_flags_a_change tests/test_bench.py::test_a_strict_cell_is_scored_like_any_other"
    - "uv run pytest -q tests/test_bench_cases.py tests/test_bench.py"
  risk: medium

- id: strict-flow-t09
  goal: "docs/architecture.md, docs/reference.md, NEXT.md, the shipped config template and the factory-ops skill describe the stricter flow: the loop behaviours, the test step and its lock, the proving reviewer, and the built-in strict flow"
  spec_refs:
    - "docs/plans/strict-flow.md#design"
    - "docs/architecture.md#agent-flows"
  depends_on:
    - strict-flow-t08
    - measure-t04
    - bench-t06
  non_goals:
    - "Changing code, or tests beyond what tests/test_templates.py needs for the new template text"
    - "Editing the installed skill copies under .claude/skills or .agents/skills: `factory init --force` refreshes them"
    - "Rewriting sections unrelated to this plan, or editing README.md"
  acceptance:
    - "docs/architecture.md: the Agent flows section gives the order rule with the test step, a table of the step options (loop: trim, map, nudge, resume; prove), and a `### The strict flow` subsection that sets strict next to default with a diagram of one strict run (test, attempts that resume, gates, proving review, verify). `Inside one agent: the loop` describes trim, map and nudge with their limits. The Roles table has the tester, the Gates table has acceptance_untouched, and the handover table says what the builder gets from the test step"
    - "docs/architecture.md's Known limitations no longer lists as open what strict addresses (the reviewer running before the gates, whole files kept in context, the builder re-exploring what the planner read): it says the default flow keeps that behaviour and strict changes it"
    - "docs/reference.md: the configuration table has `test_paths` and the role `test` under models and max_steps. The flows documentation covers the step keys `loop` and `prove` and the kind `test`, with strict written out as a flow, and one example flow that adds a single behaviour to default for comparing with bench. Troubleshooting has rows for: a flow with a test step and no test_paths; `the tests pass before the change`; a command that selects no tests; a failed acceptance_untouched gate; a review recorded as `APPROVE (unproven)`"
    - "NEXT.md marks item 2 and item 9 done in its table, each linking to docs/architecture.md#the-strict-flow, and says what stays open from item 2: a gate that runs the tests without the change, and holdout tests"
    - "factory/templates/config.yaml has commented `test_paths` and `flow: strict` lines with one-line explanations. factory/templates/skills/factory-ops/SKILL.md covers choosing strict, and reading a failed test step, a failed acceptance_untouched gate and an unproven review"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "grep -q '^### The strict flow' docs/architecture.md"
    - "grep -q 'acceptance_untouched' docs/architecture.md"
    - "grep -q 'test_paths' docs/reference.md"
    - "grep -q 'APPROVE (unproven)' docs/reference.md"
    - "grep -q 'architecture.md#the-strict-flow' NEXT.md"
    - "grep -q 'test_paths' factory/templates/config.yaml"
    - "grep -q 'strict' factory/templates/skills/factory-ops/SKILL.md"
    - "uv run pytest -q tests/test_templates.py"
  risk: low
```

Planned test additions:

| Task | Test | Kind |
|---|---|---|
| t01 | `tests/test_loop.py` (new file): the five tests named in its verification; `tests/test_agent_loop.py`, `tests/test_flows.py`, `tests/test_tools.py` (existing, unmodified) as regression | unit |
| t02 | `tests/test_loop.py`: the five tests named in its verification | unit |
| t03 | `tests/test_loop.py`: four tests; `tests/test_pipeline.py::test_a_resuming_builder_gets_gate_feedback_in_the_same_conversation` | unit, CLI end to end |
| t04 | `tests/test_tester.py` (new file): four tests; `tests/test_pipeline.py`: four tests | unit, CLI end to end |
| t05 | `tests/test_pipeline.py`: five tests; `tests/test_gates.py`: two tests | CLI end to end, unit |
| t06 | `tests/test_prove.py` (new file): seven tests; `tests/test_pipeline.py`: two tests | unit, CLI end to end |
| t07 | `tests/test_flows.py::test_strict_is_built_in_and_cannot_be_redefined`; `tests/test_pipeline.py`: two tests; two existing tests updated | unit, CLI end to end |
| t08 | `tests/test_bench_cases.py::test_every_shipped_case_works_under_a_test_step`; `tests/test_bench.py`: three tests | unit, CLI end to end |
| t09 | none new: `tests/test_templates.py` (existing) | regression |

Every verification filter names a test the task adds, or an existing test file, so zero selected tests fails the gate. `tests/test_bench.py` and `tests/bench_cases/` don't exist on main yet: `bench-t03` adds them, and t01 depends on `bench-t05`.

Every task is factory-runnable on this repository: the verification commands are `uv run pytest` and `grep`, and they run offline.

Prerequisite for `strict-flow-t08`: the three cases `bench-t02` built (report-json, ini-refactor, rate-limiter) must be on main. As of 2026-11-13 they aren't: PR #24 was merged into `factory/bench-t01` one minute after that branch had merged into main, so main has only slugify and money-rounding, while the board shows `bench-t02` as merged. Land them on main first (a PR from `factory/bench-t02` to main), or t08's "every shipped case" covers two cases.

### Risks

1. **The tester writes a wrong test, and a correct build can't pass.** The tests are written before any code exists, from the contract alone. **Action:** the tests are visible, so the builder builds to them; the builder reports a contradiction with `RESULT: BLOCKED`, which lands in the failed task's note; running the task again writes new tests. The step is opt-in, and bench's `failed` cells under strict against default show how often it happens.
2. **Trimming drops something the agent still needed, or costs more than it saves.** Clearing a result changes the prompt prefix, and today about 96% of builder input is read from the provider's cache. **Action:** placeholders name the call to repeat; clearing happens in batches, so the prefix is stable between them; the transcript keeps everything. A flow with only `trim` added to default can be benched against default for cost per cell before anyone relies on it.
3. **A resumed builder keeps pushing a wrong approach.** A fresh attempt sometimes helps because it forgets. **Action:** `nudge` flags repeated edits and repeated failures; each attempt keeps its own step limit; running the task again starts fresh. `resume` is its own loop value, so bench can compare with and without it.
4. **The proof rule lets a real finding through.** Some bugs don't fit one failing command, and the factory can't tell whether a failing command shows the bug it claims to. **Action:** scope findings need no command; unproven findings stay in the PR for the human; the run records `APPROVE (unproven)`, so `factory stats` and bench count them; a missing verdict still fails safe to CHANGES.
5. **Cheap models don't follow the REPRO and `[scope]` format.** **Action:** the rules are generated into the system prompt, not left to each prompt file; `factory prompt` shows them; t06's tests pin the parser against the formats the shipped prompt asks for.
6. **`default` drifts.** Eight code tasks rewrite the files the default flow runs through. **Action:** every code task requires the existing suites to pass unmodified. t07 names the only two existing tests that change, and t08 lets only a pinned fixture hash move.
7. **A deep stack, and conflicts with measure, bench and wiki.** All four plans change `agents.py`, `pipeline.py` or `cli.py`. **Action:** t01 waits for `measure-t03` and `bench-t05`, t09 for both docs tasks, and wiki waits for this plan. Merge each PR as it opens instead of letting nine stack.
8. **Bench can't tell the flows apart.** Five small standard-library cases may be solved by every flow. **Action:** use `--repeat 3` and read `false_pass`, attempts and cost, not only solved rate; add harder cases with `--cases DIR`. Writing those cases is out of scope here.
9. **Cost per task rises.** strict adds a tester run and re-runs REPRO commands. **Action:** it drops the planner run; `--max-cost` still stops a task; bench reports cost per cell for both flows.

---

## Problem

The flow a task runs through is now configurable ([agent-flows](agent-flows.md)), but the steps themselves haven't changed since the first version, and four weaknesses are visible in the code and on this repository's own board.

- **The builder's context only grows, and every retry starts from nothing.** `LangChainRoles.step` (`factory/agents.py:239`) builds each agent with three middlewares: a step limit, a retry and tool-error handling. `read_file` returns whole files (`factory/tools.py:63`). Across this board's sixteen build runs, `read_file` returned 2.6 million characters, and one model call reached 201,000 input tokens. Each attempt is a new conversation (`factory/agents.py:255`, called from `factory/pipeline.py:379`), so a build sent back by the gates explores the repository again: on `agent-flows-t04`, a retry made its first edit at step 34.
- **The builder writes the tests that judge it.** The `verification` gate (`factory/gates.py:160`) runs the contract's commands, and the tests they run are the builder's own. Nothing checks that a test would fail without the change. This is [NEXT.md item 2](../../NEXT.md#2-the-builder-writes-the-test-that-judges-it).
- **The reviewer's word decides, without proof.** A review step has read tools and `git_diff` only (`factory/agents.py:294`), and one `VERDICT: CHANGES` line sends the build back. It can't run the code it is judging.
- **The planner's hand-over doesn't save the builder work.** On the agent-flows tasks, builders made their first edit at step 12 to 16 with a plan in hand. Across the board, builders read more file text than the planners had (2.6 against 2.2 million characters).

What others have measured points the same way:

| Finding | Source |
|---|---|
| With a minimal bash-only loop, the models this factory uses are within a point or two of the frontier on SWE-bench Verified (DeepSeek V4 Pro 0813 96.4%, GLM 5.3 95.4%, Claude Opus 5 97.0%, as of 2026-09-01). Adding roles is not where quality comes from | [Vals AI](https://www.vals.ai/benchmarks/swebench) |
| Changing only the harness took one model from 52.8% to 66.5% on Terminal-Bench 2.0. The gains came from forcing verification before the agent exits, giving it the environment up front, detecting loops, and reading traces | [LangChain](https://www.langchain.com/blog/improving-deep-agents-with-harness-engineering) |
| A planner should say what and why; detailed "how" cascades errors. A separate evaluator works, but is lenient toward generated work unless calibrated. Every harness part assumes a model weakness, so add or remove one at a time and measure | [Anthropic](https://www.anthropic.com/engineering/harness-design-long-running-apps) |
| Asking agents to write more or fewer tests didn't change resolve rates significantly, and their tests held more prints than assertions | [arXiv 2602.07900](https://arxiv.org/abs/2602.07900) |
| Developers rejected 56.3% of an AI reviewer's comments in the wild, mostly as invalid: false positives, redundant, or out of scope | [arXiv 2607.03316](https://arxiv.org/abs/2607.03316) |

## Goal

A repository can run its tasks through a flow in which the tests are written before the build by another model and can't be weakened, the builder works in a bounded context and keeps it across retries, the gates run before review, and a reviewer's CHANGES needs proof. It is one built-in flow, `strict`, made of options that each work on their own, so `factory bench` can show which of them help. With none of it configured, the factory behaves exactly as today.

## Design

### Step options

```yaml
flow: strict                      # or leave `default` and pick it per run: factory run --flow strict
test_paths: ["tests/**"]          # where the test step may write; required by a flow with a test step
flows:
  default-trim:                   # one behaviour added to today's pipeline, to bench it alone
    - plan
    - {kind: build, loop: [trim]}
    - review
    - verify
```

| Key or kind | On | Effect | Task |
|---|---|---|---|
| `loop: [trim]` | any agent step | Reads are capped, and old tool results are cleared in batches | t01 |
| `loop: [map]` | any agent step | The task message ends with a map of the repository and the spec references | t02 |
| `loop: [nudge]` | any agent step | One message near the step limit, on repeated edits to a file, on a command that keeps failing | t02 |
| `loop: [resume]` | build steps | Later attempts continue the first attempt's conversation | t03 |
| kind `test` | once, before the build steps | A tester writes the task's tests under `test_paths`; they are committed, shown to fail, then locked | t04, t05 |
| `prove: true` | review steps | The reviewer can run commands; CHANGES needs a reproduced failure or a scope finding | t06 |

The order rule becomes:

```text
[plan]?  [test]?  build+   ( review | gates )*   [verify]?
  once     once   contiguous   any order            last
```

### Trim

- **Capped reads.** `read_file` returns at most `READ_CAP` (400) lines per call and ends with how to read on. `grep` (200 lines), `run` (the last 200 lines) and `git_diff` (60,000 characters) already have caps.
- **Batch clearing.** Before a model call, when the conversation is over `TRIM_AT` (60,000 tokens, by langchain's approximate count), every tool result except the latest `TRIM_KEEP` (8) is replaced by a placeholder such as `[cleared: read_file(path='factory/agents.py', start=1): call it again if you need it]`. A cleared result stays cleared. Nothing more is cleared until the conversation passes `TRIM_AT` again, so between batches the prompt prefix a provider caches doesn't move.
- **The transcript is untouched.** It keeps every result in full, and gains a `trim` event per batch.

langchain 1.4, already in the lockfile, ships `ContextEditingMiddleware` and `ClearToolUsesEdit`. They clear with a fixed placeholder and a sliding window, so the placeholder text and the batching above need the factory's own middleware or edit on top.

### Map

Appended to the step's first task message:

```text
# Repository map
README.md  NEXT.md  pyproject.toml  …
factory/            24 files
factory/prompts/     5 files
tests/              22 files
…  (14 more directories)

# Spec references
- factory/agents.py (366 lines)
- docs/plans/strict-flow.md#trim (docs/plans/strict-flow.md, 410 lines)
- https://example.org/spec (not a file)
```

It comes from `git ls-files` in the worktree, so it costs no model call, and it is left out of a resumed attempt's message.

### Nudge

One human message before the next model call, each at most once:

| Kind | When | Says |
|---|---|---|
| `budget` | Three quarters of the step limit used | The calls used and allowed; finish, run the checks, write the final report |
| `edits` | One path written `NUDGE_EDITS` (6) times | Names the path; re-read the failing output and the contract first |
| `failing` | One `run` command non-zero `NUDGE_FAILS` (3) times in a row | Names the command; the approach isn't working |

### Resume

```text
attempt 1   [system] [task message: plan, map, locked tests]  … tool calls …  [final report]
              commit → gates fail
attempt 2   the same conversation, as trimmed, then
            [# Attempt 2 / # Feedback to address first / the gates' output]  … tool calls …  [final report]
```

- The conversation is kept in memory by the roles object, per build step, for the life of one `factory run`. A rework or a rerun is a new process and starts fresh.
- Each attempt has its own step limit, run record and transcript; the transcript opens with a `resumed` event.
- A conflict resolution doesn't seed a resume, and an attempt that ended in an error isn't resumed.

### The test step

```text
fresh build ──► plan step (if any) ──► TEST (once)                          ┌─ attempt N ───────────────┐
                                        tester writes under test_paths       │ build (resumes when N > 1) │
                                        commit "acceptance tests"            │ gates, reviews: flow order │
                                        red check (t05) ── fail ─► base,     └────────────────────────────┘
                                        one more try, then the task fails                 ▲
                                               │ pass                                     │
                                               └──────── files + red commands ────────────┘
rework entry (resolve | ci | human_review): no test step, no lock
```

- **Kind `test`**, role `test`, prompt `factory/prompts/tester.md`. Its write tools are limited to `test_paths`, and the pipeline checks the commit's paths too, since `run` could write anywhere in the worktree.
- **`test_paths`** is a config key, not a contract key: a list of globs such as `["tests/**"]` or `["crates/*/tests/**"]`. `factory run` refuses a flow with a test step when it is empty.
- **Tries.** A try that changes nothing, leaves `test_paths`, or isn't red is thrown away and the step runs once more with the reason. After `TEST_TRIES` (2) the task fails before any build.
- **Another model.** The tester's shipped model is `openrouter:z-ai/glm-5.3`, and the builder's is `openrouter:deepseek/deepseek-v4-pro-0813`. `factory run` warns when a flow puts both on one model (t07).

### The red check

The task's acceptance commands are the contract's verification commands that are test commands, plus `e2e.run_new` for each new e2e test when the project configures one. At the test commit:

| Result of a command | Meaning |
|---|---|
| Fails, and ran or tried to build tests | **Red.** This is what the builder must turn green |
| Selects zero tests | The tests the command names don't exist: the try fails |
| Passes | A regression check that already holds: noted |
| No command is red | The tests pass before the change: the try fails |

A task with no test command in its verification, in a project without `e2e`, skips the step: a docs task checked by `grep` has nothing for a tester to write.

The candidate must pass the same commands through the existing `verification` gate, so no new gate is needed for "green at the candidate".

### The lock

`acceptance_untouched`, after `plan_untouched`, on fresh builds that have a test commit:

- every file the test step wrote still exists at the candidate;
- the diff from the test commit to the candidate removes no line from those files.

The builder may add lines to those files, and may add other tests. It is told so in an `# Acceptance tests (locked)` block in its first message, with the files and the red commands.

### The proving reviewer

```text
## Findings
1. [blocker] textkit/slug.py:41 — an all-symbol title returns "-" instead of ""
   REPRO: python3 -c "from textkit.slug import slugify; assert slugify('!!!') == ''"
2. [major] [scope] README.md:12 — the usage section still documents the removed flag
3. [minor] textkit/slug.py:12 — a name shadows a builtin

VERDICT: CHANGES
```

- The reviewer gets `run`. Each `REPRO:` is one command, because every `run` call starts a new sandbox with an empty `/tmp`.
- After the review, the factory runs each distinct REPRO again (at most 5, 300 seconds each) and appends a `## Proof` section.

| Reported | Proof | Verdict | Run outcome |
|---|---|---|---|
| APPROVE | any | APPROVE | `APPROVE` |
| CHANGES | a REPRO fails again, or a blocker or major is tagged `[scope]` | CHANGES | `CHANGES` |
| CHANGES | neither | APPROVE | `APPROVE (unproven)` |
| no VERDICT line | any | CHANGES | `CHANGES` |

- The proof rules are generated into the system prompt, so they apply to a repository's own reviewer prompt too, and [measure](measure.md)'s prompt version changes with them.
- After the step, the pipeline resets the worktree to the candidate, so files a REPRO wrote can't fail the `clean` gate.

### The strict flow

```yaml
strict:                                        # built in, like `default`; it can't be redefined
  - {kind: test, loop: [map, trim, nudge]}
  - {kind: build, loop: [map, trim, nudge, resume]}
  - gates
  - {kind: review, prove: true, loop: [trim]}
  - verify
```

| | `default` | `strict` |
|---|---|---|
| Who plans | A planner agent | The builder, from the contract, the map and the locked tests |
| Who writes the tests that decide | The builder | The tester, on another model, before the build |
| A failed attempt | A new conversation | The same conversation, with the feedback |
| Context | Grows with every read | Capped reads, cleared in batches |
| Order after the build | review, gates | gates, review |
| A reviewer's CHANGES | Its word | A reproduced failure or a scope finding |

### Comparing with bench

- Each shipped case's `case.yaml` config gains `test_paths: ["tests/**"]`, and `factory bench run` refuses a flow with a test step for a case without it.
- `results.json` records `loop` and `prove` per step, so `factory bench compare` flags a run whose options changed.
- One behaviour at a time: define a flow that adds a single option to `default` (like `default-trim` above), and bench it against `default`.

## Files Changed

| File | Change |
|---|---|
| `factory/flows.py` | `Step.loop` and `LOOP` (t01–t03); the `test` kind and the order rule (t04); `Step.prove` (t06); `STRICT` (t07) |
| `factory/config.py` | `test_paths`, the `test` role (t04); `strict` always in `flows` (t07) |
| `factory/agents.py` | Trim (t01); map and nudges (t02); resume (t03); the tester's tools and message (t04); the locked-tests block (t05); proof rules, REPRO re-run and verdict (t06) |
| `factory/tools.py` | The read cap (t01); write tools limited to globs (t04) |
| `factory/pipeline.py` | The test node, its tries and commit (t04); the red check and the acceptance state (t05); the worktree restore after a proving review (t06) |
| `factory/gates.py` | `acceptance_untouched` (t05) |
| `factory/db.py` | The `test` run role (t04) |
| `factory/cli.py` | The `test_paths` pre-run check (t04); the same-model warning (t07) |
| `factory/prompts/tester.md` | New (t04) |
| `factory/bench/` | `test_paths` in the fixtures; the refusal; `loop` and `prove` in results and compare (t08) |
| `tests/fake_model.py` | Plays TESTER (t04) |
| `tests/test_loop.py`, `tests/test_tester.py`, `tests/test_prove.py` | New (t01–t03, t04, t06) |
| `tests/test_pipeline.py`, `tests/test_gates.py`, `tests/test_flows.py`, `tests/test_bench.py`, `tests/test_bench_cases.py` | New tests (t03–t08) |
| `docs/architecture.md`, `docs/reference.md`, `NEXT.md`, `factory/templates/config.yaml`, `factory/templates/skills/factory-ops/SKILL.md` | t09 |
| `docs/sessions/` | Every task's session log entry |

## Test Plan

### Unit tests

`tests/test_loop.py` (new):

- `test_loop_is_a_list_of_known_behaviours` (t01): parsing, and each rejected form with the flow and step in the error.
- `test_trim_caps_a_read_and_says_how_to_read_on` (t01)
- `test_trim_clears_old_results_in_batches_and_keeps_the_latest` (t01): with `TRIM_AT` lowered, the model's next call holds placeholders for all but the latest results.
- `test_cleared_results_stay_cleared_and_the_transcript_keeps_them` (t01)
- `test_without_loop_the_agent_is_built_as_today` (t01): the same middleware and tools as before.
- `test_map_lists_the_tree_and_the_spec_references`, `test_map_is_left_out_outside_a_git_work_tree` (t02)
- `test_nudge_warns_once_near_the_step_limit`, `test_nudge_names_a_file_edited_again_and_again`, `test_nudge_names_a_command_that_keeps_failing` (t02)
- `test_resume_is_for_build_steps_only`, `test_a_resumed_attempt_continues_the_conversation_with_the_feedback`, `test_each_attempt_has_its_own_step_limit_and_counts`, `test_the_first_attempt_and_a_resolve_start_fresh` (t03)

`tests/test_tester.py` (new, t04):

- `test_a_test_step_goes_between_plan_and_build`: the order rule and its errors.
- `test_test_paths_and_the_test_role_are_configurable`
- `test_the_tester_writes_only_under_test_paths`: a write elsewhere is refused, naming the globs.
- `test_the_tester_prompt_ships_and_can_be_overridden`

`tests/test_prove.py` (new, t06):

- `test_prove_is_a_review_step_option`
- `test_a_proving_reviewer_can_run_commands_and_gets_the_proof_rules`
- `test_changes_stands_on_a_reproduced_failure`, `test_changes_stands_on_a_scope_finding`
- `test_unproven_changes_becomes_an_approval`: the verdict, the outcome, and the findings kept.
- `test_a_passing_timed_out_or_denied_repro_is_unproven`
- `test_a_missing_verdict_is_still_changes`

`tests/test_gates.py` (t05): `test_acceptance_untouched_allows_added_lines_only`, `test_acceptance_untouched_is_absent_without_a_test_commit`.

`tests/test_flows.py` (t07): `test_strict_is_built_in_and_cannot_be_redefined`.

`tests/test_bench_cases.py` (t08): `test_every_shipped_case_works_under_a_test_step`.

### End-to-end tests

Through the real CLI, pipeline, agents, git, bubblewrap and fake `gh`, with `ScriptedModel`.

`tests/test_pipeline.py`:

- `test_a_resuming_builder_gets_gate_feedback_in_the_same_conversation` (t03)
- `test_a_test_step_commits_the_tests_before_the_first_build` (t04)
- `test_a_test_step_that_writes_outside_test_paths_is_retried_then_fails_the_task` (t04)
- `test_a_flow_with_a_test_step_needs_test_paths` (t04)
- `test_reworks_skip_the_test_step` (t04)
- `test_tests_that_pass_before_the_change_are_rejected` (t05)
- `test_a_verification_command_that_selects_no_tests_sends_the_tester_back` (t05)
- `test_the_builder_is_told_which_tests_are_locked` (t05)
- `test_a_builder_that_edits_a_locked_test_fails_the_gate` (t05)
- `test_a_task_without_test_commands_skips_the_test_step` (t05)
- `test_a_proving_review_leaves_the_worktree_at_the_candidate` (t06)
- `test_an_unproven_review_does_not_send_the_build_back` (t06)
- `test_the_strict_flow_tests_builds_gates_and_proves_before_a_pr` (t07)
- `test_a_tester_and_builder_on_one_model_are_warned_about` (t07)

`tests/test_bench.py` (t08):

- `test_a_flow_with_a_test_step_needs_the_cases_test_paths`
- `test_results_record_loop_and_prove_and_compare_flags_a_change`
- `test_a_strict_cell_is_scored_like_any_other`

## Verification

- Each task's verification commands, then `uv run pytest -q` (the unit gate).
- By hand after t08 merges, with real models and real money:
  1. `factory prompt test --flow strict` and `factory prompt review --flow strict` show the tester prompt and the reviewer prompt, with no same-model warning.
  2. `factory bench run --flow default --flow strict --repeat 3 --max-cost 30`, then `factory bench report`: compare solved rate, `false_pass`, attempts and cost per cell.
  3. Define flows that add one option each to `default` (`trim`, `resume`, a `test` step, `prove`), and bench each against `default`, to see which carry strict's difference.
  4. Run one real task of this repository with `factory run TASK --flow strict` and read its PR: the Acceptance tests block, the gate table with `acceptance_untouched`, and the reviewer's Proof section.
- Switch `flow:` to `strict` in `.factory/config.yaml` only if steps 2 to 4 favour it.

## Cross-Workstream Coordination

- **Depends on:**
  - [agent-flows](agent-flows.md), merged up to t04. This plan extends its `Step`, its order rule and its built-in flow, and keeps its promise that `default` is today's pipeline.
  - [measure](measure.md). `strict-flow-t01` depends on `measure-t03`, the last task to change `agents.py`, `pipeline.py`, `db.py` and `cli.py` there, and `strict-flow-t09` on `measure-t04`, which edits the same docs. Its prompt version covers the proof rules, since they are part of the system prompt, and `factory stats` sees the `test` role and the `APPROVE (unproven)` outcome as new values.
  - [bench](bench.md). `strict-flow-t01` depends on `bench-t05`, the last task to change `cli.py` there, `strict-flow-t08` changes its fixtures and results, and `strict-flow-t09` depends on `bench-t06`. Bench is how this plan's options are judged.
- **Required by:**
  - [wiki](wiki.md). `wiki-t01` depends on `strict-flow-t08` and `wiki-t07` on `strict-flow-t09`: wiki changes the same `agents.py`, `gates.py` and `tools.py`, and its role pages should describe the loop the task crew then runs. wiki-t03's `PathGuard` with writable prefixes builds on the glob-limited write tools t04 adds. A `test` step gets a role page only if the wiki has one for it.
  - [NEXT.md item 2](../../NEXT.md#2-the-builder-writes-the-test-that-judges-it), which t04 and t05 address.

## Notes / Out of Scope

- **Parallel build candidates.** Several builders on one task, with the gates picking a winner, lifted one model from 70.9% to 77.6% on SWE-bench Verified ([arXiv 2604.16529](https://arxiv.org/abs/2604.16529)). It needs several worktrees and branches per task, so it gets its own plan once bench shows what strict still fails.
- **A flow chosen by the contract's `risk`,** per task or per plan. agent-flows left a flow per task out; `--flow` and the config's `flow` stay the only ways to choose.
- **A gate that runs the tests with the change taken out** (NEXT.md item 2's sketch). The red check at the test commit and the lock cover a tester's vacuous test, but not a builder that makes a locked test pass through a new fixture or helper under `test_paths`. That gate needs a scratch worktree and a sandbox for it, as bench's hidden scoring has.
- **Holdout tests** the builder never sees. bench keeps them for scoring; in production the tests stay visible, so a builder can build to them.
- **A dispute path.** A builder can report a wrong test with `RESULT: BLOCKED`, but nothing rewrites the test in the same run. Revisit if bench's failed cells under strict are mostly locked tests the builder couldn't meet.
- **Summarizing old steps with a model.** Trim clears results; it doesn't write summaries.
- **Resuming across runs,** from the transcript, for reworks and reruns.
- **Calibrating the reviewer with examples** from merged PRs. The wiki's reviewer role page is the place for them.
- **External agent CLIs as steps,** as in agent-flows.
- **Making strict the default.** That is a config change by hand, after bench.
