# Plan: A security review step and gates

**Status:** Planned (2026-11-17). Workstream scoped; awaiting kickoff: t01 and t02 start once `flow-tuning-t04` has a PR. Roadmap: [NEXT.md item 16](../../NEXT.md#16-nothing-reviews-a-change-for-security).

---

## Execution Plan

### Locked Decisions

| Decision | Choice |
|---|---|
| Scope | **A security step in the task flow.** The factory ships a security reviewer as a new step kind, adds two deterministic security gates, and adds a built-in flow `secure`, so a task's PR can carry a security verdict before it opens. A command that reviews any ref or PR, and a crew that audits the existing codebase and writes fix contracts, are out of scope |
| What a finding does | **The verdict is the factory's, computed from structured findings, and it blocks only above a threshold.** A security step sends the build back only for a critical or high finding with high confidence and an exploit scenario, and the builder gets only those findings. Everything below the threshold goes to a visible Security section in the PR, for the human who merges |
| Deterministic gates | **`secrets` and `guarded_paths`, both on when `security:` is set in `.factory/config.yaml`.** `secrets` fails on credential-shaped strings in added lines. `guarded_paths` fails on changes to files that steer agents or run with secrets after merge (CI, `.factory/`, skills, guidance, lockfiles, configured globs) unless the task's contract names the path. A contract is written by a human and kept from the agents by `plan_untouched`, so naming a path there is the human's authorization |
| Sequencing | **After [strict-flow](strict-flow.md) and [flow-tuning](flow-tuning.md), before [wiki](wiki.md).** strict-flow has merged. flow-tuning fills the same slot, after strict-flow and before wiki, and its candidate and selector tasks change the same `flows.py`, `agents.py`, `pipeline.py`, `config.py`, `db.py` and `cli.py`. So t01 and t02 depend on `flow-tuning-t04`, its last code task, and the docs task on `flow-tuning-t05`. `wiki-t01` now also depends on this plan's last code task (`security-review-t06`), and `wiki-t07` on its docs task |
| Guidance isolation | **Repository guidance is read from the main checkout, and the fix waits with the rest of the plan.** `factory/agents.py:521` reads `AGENTS.md` from the task worktree, so a builder can rewrite its own reviewer's system prompt. t01 fixes it, chained with the other tasks so that it doesn't conflict with the flow-tuning tasks in `agents.py` |

### Milestones

| # | Deliverable | Exit criteria | Parallelizable with |
|---|---|---|---|
| **M1** | Guidance from the main checkout | `tests/test_prompt_isolation.py` and the t01 test in `tests/test_pipeline.py` pass; the prompt-version suite passes unmodified | M2 |
| **M2** | `security:` config and the `secrets` gate | The t02 tests in `tests/test_security_gates.py` pass; `tests/test_gates.py` passes unmodified | M1 |
| **M3** | The `guarded_paths` gate | The t03 tests in `tests/test_security_gates.py` pass | — |
| **M4** | The security reviewer agent | `tests/test_security_review.py` passes | — |
| **M5** | Security steps in flows, the pipeline and the PR | The t05 tests in `tests/test_flows.py`, `tests/test_pipeline.py` and `tests/test_stats.py` pass; flows without a security step run as before | — |
| **M6** | The built-in `secure` flow | The t06 tests in `tests/test_flows.py` and `tests/test_pipeline.py` pass | — |
| **M7** | Docs and this repository's threat model | Architecture, reference, NEXT.md, the config template, the factory-ops skill and `docs/security.md` describe it; `tests/test_templates.py` passes | — |

**Sequence:** `flow-tuning-t04 → (M1 ∥ (M2 → M3)) → M4 → M5 → M6 → [flow-tuning-t05 →] M7`, then `M6 → wiki-t01` and `M7 → wiki-t07`. M1 changes only `agents.py`'s guidance read and M2 and M3 only `config.py`, `gates.py` and the new `security.py`, so M1 runs beside them. From M4 on, every task changes `agents.py`, `pipeline.py`, `flows.py` or `cli.py`, so they run one after another.

### Task Contracts

| Milestone | Task IDs | Coverage |
|---|---|---|
| **M1** | `security-review-t01` | The guidance read in `factory/agents.py`; new `tests/test_prompt_isolation.py`; one end-to-end test in `tests/test_pipeline.py` |
| **M2** | `security-review-t02` | `SecurityConfig` in `factory/config.py`; secret patterns and the diff scan in new `factory/security.py`; the `secrets` gate in `factory/gates.py`; new `tests/test_security_gates.py` |
| **M3** | `security-review-t03` | The guarded globs and the naming rule in `factory/security.py`; the `guarded_paths` gate in `factory/gates.py`; tests in `tests/test_security_gates.py` |
| **M4** | `security-review-t04` | `factory/prompts/security.md`; the `security` role in `factory/agents.py` and `factory/config.py`; the security rules and threat-model blocks; findings parsing and the verdict in `factory/security.py`; `tests/fake_model.py`; new `tests/test_security_review.py` |
| **M5** | `security-review-t05` | The `security` kind in `factory/flows.py`; security nodes, feedback and the PR's Security section in `factory/pipeline.py` and `factory/prbody.py`; the `security` run role in `factory/db.py`, `factory/cli.py` and `factory/web/views.py`; the rate in `factory/stats.py`; tests in `tests/test_flows.py`, `tests/test_pipeline.py`, `tests/test_stats.py` |
| **M6** | `security-review-t06` | `flows.SECURE` and its place in `factory/config.py`; the pre-run checks in `factory/cli.py`; tests in `tests/test_flows.py` and `tests/test_pipeline.py` |
| **M7** | `security-review-t07` | `docs/architecture.md`, `docs/reference.md`, `NEXT.md`, new `docs/security.md`, `factory/templates/config.yaml`, the factory-ops skill template and its installed copy, the config comments in `.factory/config.yaml` |

```yaml
- id: security-review-t01
  goal: "Every agent step's repository guidance (the first `guidance` file that exists, AGENTS.md by default) is read from the main checkout, where the config and prompt overrides are read, so a builder that edits AGENTS.md or adds CLAUDE.md in its worktree no longer changes the system prompt of its reviewer, its verifier or its next attempt"
  spec_refs:
    - "docs/plans/security-review.md#guidance-from-the-main-checkout"
    - "docs/architecture.md#policy"
    - "factory/agents.py"
  depends_on:
    - flow-tuning-t04
  non_goals:
    - "Changing which files `guidance` names, or the wording of the `# Repository guidance (NAME)` block"
    - "Changing what the read tools return, or how the strict-flow repository map lists worktree files"
    - "Changing factory/pipeline.py, factory/gates.py or any documentation (security-review-t07)"
  acceptance:
    - "LangChainRoles.step builds the `# Repository guidance (NAME)` block from the first `guidance` file that exists in LangChainRoles.root, the main checkout where .factory/config.yaml and .factory/agents/ are read, and never from ctx.worktree"
    - "When the worktree's AGENTS.md differs from the main checkout's, or the worktree adds a guidance file the main checkout lacks, every agent step gets the main checkout's guidance. With no guidance file in the main checkout, the block is left out whatever the worktree holds"
    - "In a run on the test suite's demo repository whose builder rewrites AGENTS.md, the system prompts recorded for the review step and the verify step hold the main checkout's AGENTS.md text, not the builder's"
    - "Prompt versions still cover the guidance: tests/test_prompt_versions.py, tests/test_flows.py and tests/test_agent_loop.py pass unmodified"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_prompt_isolation.py::test_guidance_comes_from_the_main_checkout_not_the_worktree tests/test_prompt_isolation.py::test_a_guidance_file_only_in_the_worktree_is_not_read tests/test_pipeline.py::test_a_builder_that_rewrites_agents_md_does_not_change_the_reviewers_prompt"
    - "uv run pytest -q tests/test_prompt_versions.py tests/test_flows.py tests/test_agent_loop.py"
  risk: low

- id: security-review-t02
  goal: "A `security:` section in .factory/config.yaml turns on a `secrets` gate. It fails a candidate whose added lines hold a credential-shaped string (a private key, or an AWS, GitHub, Anthropic, OpenAI, OpenRouter, Slack or Google key) and says where without repeating the string"
  spec_refs:
    - "docs/plans/security-review.md#the-security-config"
    - "docs/plans/security-review.md#the-secrets-gate"
    - "factory/gates.py"
    - "factory/config.py"
  depends_on:
    - flow-tuning-t04
  non_goals:
    - "The guarded_paths gate (security-review-t03) or the security step (security-review-t04)"
    - "Generic password or entropy heuristics, scanning lines the change didn't add, or scanning git history"
    - "Running an external scanner such as gitleaks, trufflehog or semgrep"
    - "Changing any gate when `security` is unset, or changing factory/agents.py, factory/pipeline.py or any documentation"
  acceptance:
    - "Config gains `security`, unset (None) by default, or a SecurityConfig parsed from a mapping with optional keys `guarded_paths` (a list of path globs, default empty), `allow_secrets` (a list of path globs, default empty) and `threat_model` (a repository-relative path, default none). `security: {}` turns it on with the defaults. An unknown key, or a value of the wrong type, raises ConfigError naming the key. `factory config` prints it"
    - "New factory/security.py has SECRET_PATTERNS, a tuple of (name, compiled regex) pairs that holds at least private-key, aws-access-key-id, github-token, anthropic-key, openai-key, openrouter-key, slack-token and google-api-key. It also has a function that returns (path, line number, pattern name) for each match in the added lines of a unified diff, with line numbers in the new file, skipping binary files"
    - "With `security` set, gates.run_gates adds a `secrets` gate directly after plan_untouched, or after acceptance_untouched when that gate is present. It scans the added lines of base..sha and passes when nothing matches outside `allow_secrets` paths. When it fails, its detail lists `path:line pattern-name` for each match (at most 20, then a count of the rest) and says to remove the credential and read it from the environment. Matches inside `allow_secrets` paths are counted in the detail and don't fail the gate. The detail never contains the matched text"
    - "`factory gates TASK --ref REF` runs the secrets gate too when `security` is set"
    - "No file the task adds or changes contains a string that a SECRET_PATTERNS regex matches: the tests build their sample keys at runtime, so this repository's own secrets gate would pass on the task"
    - "Without `security` the gates are today's: tests/test_gates.py and tests/test_config.py pass unmodified"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_security_gates.py::test_security_config_parses_and_rejects_unknown_keys tests/test_security_gates.py::test_secrets_gate_fails_on_an_added_key_and_does_not_repeat_it tests/test_security_gates.py::test_secrets_gate_reports_the_new_files_line_numbers tests/test_security_gates.py::test_allow_secrets_paths_are_counted_not_failed tests/test_security_gates.py::test_without_security_there_is_no_secrets_gate tests/test_security_gates.py::test_no_tracked_file_holds_a_literal_secret"
    - "uv run pytest -q tests/test_gates.py tests/test_config.py"
  risk: low

- id: security-review-t03
  goal: "With `security` set, a `guarded_paths` gate fails a candidate that changes, without the contract naming it, a file that steers agents or runs with secrets after merge: anything under .github/, .factory/, .claude/ or .agents/, .gitlab-ci.yml, the guidance files, lockfiles, and the configured globs"
  spec_refs:
    - "docs/plans/security-review.md#the-guarded-paths-gate"
    - "factory/gates.py"
    - "factory/globs.py"
  depends_on:
    - security-review-t02
  non_goals:
    - "Telling the security step which guarded paths changed (security-review-t04)"
    - "Guarding the plan doc, which plan_untouched already covers"
    - "Any approval besides the contract's text: no override flag, and no allowlist per run"
    - "Changing factory/agents.py, factory/pipeline.py or any documentation"
  acceptance:
    - "security.guarded_globs(cfg) returns the defaults in security.GUARDED (`.github/**`, `.gitlab-ci.yml`, `.factory/**`, `.claude/**`, `.agents/**`), then each `guidance` file, then each `lockfiles` name at any depth, then `security.guarded_paths`, all in factory/globs.py's glob syntax"
    - "With `security` set, gates.run_gates adds a `guarded_paths` gate directly after `secrets`. It reads the paths base..sha changes without rename detection, so a guarded file that is deleted or renamed away counts as changed"
    - "The contract names a changed guarded path when the path itself, or a directory prefix of it ending in `/`, appears in the task's goal, one of its spec_refs or one of its acceptance criteria. Non-goals and verification commands never name a path"
    - "The gate fails when the contract doesn't name a changed guarded path. Its detail lists each such path with the glob it matched, and says the change must leave the path alone unless the contract names it, which takes a human's edit to the plan. Otherwise it passes, and its detail lists the guarded paths the contract named or says that none changed"
    - "Without `security` there is no guarded_paths gate: tests/test_gates.py passes unmodified"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_security_gates.py::test_guarded_globs_are_the_defaults_guidance_lockfiles_and_config tests/test_security_gates.py::test_an_unnamed_guarded_change_fails_the_gate tests/test_security_gates.py::test_a_guarded_change_the_contract_names_passes tests/test_security_gates.py::test_a_directory_prefix_names_the_files_under_it tests/test_security_gates.py::test_non_goals_and_verification_do_not_name_a_path tests/test_security_gates.py::test_a_guarded_file_deleted_or_renamed_away_counts"
    - "uv run pytest -q tests/test_security_gates.py tests/test_gates.py"
  risk: medium

- id: security-review-t04
  goal: "A security reviewer agent ships with the factory. `LangChainRoles.step` runs a step of kind `security` with the read tools and git_diff, under a system prompt that carries generated security rules and the repository's threat model. The factory computes the step's verdict from its findings, and blocks only on a critical or high finding with high confidence and an exploit scenario"
  spec_refs:
    - "docs/plans/security-review.md#the-security-step"
    - "docs/plans/security-review.md#findings-and-the-verdict"
    - "factory/agents.py"
    - "factory/prompts/reviewer.md"
  depends_on:
    - security-review-t01
    - security-review-t03
  non_goals:
    - "Letting a flow name a security step, or running one in the pipeline (security-review-t05): flows.KINDS doesn't change in this task"
    - "Giving the security step `run`, write tools or `prove`"
    - "Changing the reviewer, its prompt or parse_verdict"
    - "Any documentation"
  acceptance:
    - "factory/prompts/security.md ships with `You are the SECURITY REVIEWER`, model openrouter:z-ai/glm-5.3 and max_steps 60. It tells the agent to judge the change, not the whole repository, for: injection (shell, SQL, path, template), broken authentication or authorization, unsafe deserialization, secrets handling, SSRF, weak cryptography, weakened sandboxing or isolation, new dependencies or install scripts, and text in the change addressed to an AI agent or reviewer. It rates exploitability by who controls the input. agents.ROLE_FILES maps `security` to the prompt, `.factory/agents/security.md` overrides it, `factory prompt security` prints it, and `models` and `max_steps` in .factory/config.yaml accept the role `security`"
    - "A security step's system prompt gains a `# Security rules` block after the project rules, generated by the factory whatever the prompt file says. It gives the findings format, the blocking rule, the fact that any VERDICT line is ignored, and, when `security` is set, the guarded globs. When `security.threat_model` names a file in the main checkout, a `# Threat model (PATH)` block follows, holding the file's text cut at security.THREAT_MODEL_CAP (8000) characters, with a line saying so when it was cut. Both blocks count toward the step's prompt version"
    - "The step's tools are the read tools and git_diff. Its task message is `Security-review the change for task ID. Start with git_diff(stat=True).`. When `security` is set and the change touches guarded paths, a `# Guarded paths in this change` block listing them follows"
    - "security.parse_findings reads the report's `## Findings` section. Each finding is a numbered line `[SEVERITY] [confidence: LEVEL] LOCATION — TITLE`, with optional `Exploit:` and `Fix:` lines under it; severity is critical, high, medium or low, and level is high, medium or low. `None.` under the heading means no findings. A numbered line it can't parse is kept as an unrated finding, which never blocks"
    - "security.verdict(report) returns the verdict and the run outcome. With N findings that are critical or high, with confidence high and a non-empty Exploit line: CHANGES, outcome `CHANGES (N blocking)`. With no findings: APPROVE, outcome `APPROVE`. With N findings and none blocking: APPROVE, outcome `APPROVE (N below threshold)`. With no `## Findings` heading: CHANGES, outcome `CHANGES (unparsed)`. A VERDICT line in the report changes nothing. For a security step, LangChainRoles.step sets Output.verdict from it; the pipeline records the outcome (security-review-t05)"
    - "tests/fake_model.py gains a SECURITY script without changing what the other roles play"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_security_review.py::test_the_security_prompt_ships_and_can_be_overridden tests/test_security_review.py::test_security_rules_and_the_threat_model_join_the_system_prompt tests/test_security_review.py::test_a_long_threat_model_is_cut_and_says_so tests/test_security_review.py::test_the_security_step_reads_and_diffs_but_cannot_write_or_run tests/test_security_review.py::test_guarded_paths_in_the_change_are_listed_in_the_task_message tests/test_security_review.py::test_findings_are_parsed_with_severity_confidence_and_exploit tests/test_security_review.py::test_only_confident_high_findings_with_an_exploit_block tests/test_security_review.py::test_a_report_without_findings_counts_as_changes_unparsed tests/test_security_review.py::test_a_verdict_line_is_ignored"
    - "uv run pytest -q tests/test_flows.py tests/test_agent_loop.py tests/test_prompt_versions.py tests/test_config.py tests/test_templates.py"
  risk: medium

- id: security-review-t05
  goal: "A flow can have security steps, which run among its review steps and gates. A blocking finding sends the build back with only the blocking findings as feedback, and findings below the threshold reach a visible Security section in the PR instead of the builder"
  spec_refs:
    - "docs/plans/security-review.md#the-security-step-in-a-flow"
    - "docs/plans/security-review.md#the-pr"
    - "docs/architecture.md#agent-flows"
    - "factory/pipeline.py"
  depends_on:
    - security-review-t04
  non_goals:
    - "A built-in flow with a security step, or warnings about how one is set up (security-review-t06)"
    - "Giving the security step the human review brief in a human-review rework: it judges security only"
    - "Asking a security step again when its report has no findings section, as flow-tuning-t01 asks a reviewer again for a missing verdict: such a report counts as CHANGES (unparsed) at once"
    - "Changing how review steps, the gates or the verifier decide"
    - "Any documentation"
  acceptance:
    - "flows.KINDS gains `security`, and the order rule becomes `[plan]? [test]? build+ (review | security | gates)* [verify]?`. A security step takes `model`, `max_steps` and `loop` (trim, map, nudge) as a review step does, and `prove` on it raises ConfigError naming the flow and step. A flow without a gates step gets one after its last review or security step"
    - "The pipeline runs each security step as a node among the post-build steps, in flow order, on fresh builds and on every rework entry (conflict resolution, CI fix, human-review rework). APPROVE moves on. CHANGES ends the attempt, and the next attempt's feedback starts `Security reviewer found N blocking issue(s):` (with `Security reviewer `NAME`` for a step not named `security`), followed by only the blocking findings, each with its Exploit and Fix lines. After a `CHANGES (unparsed)` review, the feedback says the report had no findings section and gives the report, capped"
    - "Each security step records a run with role `security` (db.ROLES gains it), the step's name, its report, and its outcome from security.verdict, computed in the pipeline's security node as review_step computes a proving review's `APPROVE (unproven)`. `factory show`, `factory trace` and `factory transcript` accept `--role security`, and the web page calls the role `security reviewer`"
    - "The verifier's task message includes each security step's report, under the step's name, with the reviewer reports"
    - "A PR whose flow has a security step, or whose change touches guarded paths the contract named, has a `## Security` section after What to check. It holds one bullet per finding of each security step's last run on the pushed candidate (severity, confidence, location and title, cut at 300 characters), at most security.PR_FINDINGS (20) with a line counting the rest. When `security` is set, a bullet names the guarded paths the contract let the change touch. With nothing to list, the section reads `Nothing flagged.`. Each security step also gets a collapsed `Security report (NAME)` block after the reviewer blocks, capped and shrunk under the body limit as reviewer blocks are, and the Checks paragraph gives its outcome"
    - "`factory stats` reports a `security CHANGES rate` over security runs (key `security_changes_rate` in --json) next to the reviewer CHANGES rate, which still counts only review runs"
    - "Flows without a security step behave as today: tests/test_pipeline.py, tests/test_flows.py, tests/test_prbody.py, tests/test_stats.py and tests/test_web.py pass unmodified apart from the tests this task adds"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_flows.py::test_a_security_step_goes_with_the_review_steps tests/test_pipeline.py::test_a_blocking_security_finding_sends_back_only_the_blocking_findings tests/test_pipeline.py::test_findings_below_the_threshold_go_to_the_prs_security_section tests/test_pipeline.py::test_an_unparsed_security_report_sends_the_build_back tests/test_pipeline.py::test_a_ci_fix_runs_the_flows_security_step tests/test_stats.py::test_stats_report_the_security_changes_rate"
    - "uv run pytest -q tests/test_pipeline.py tests/test_flows.py tests/test_prbody.py tests/test_stats.py tests/test_db.py tests/test_web.py"
  risk: high

- id: security-review-t06
  goal: "A built-in flow `secure` runs plan, build, gates, review, a security step and verify. Before any work, `factory run` refuses a threat model file that doesn't exist, and warns when the security gates are off or a security step shares a build step's model"
  spec_refs:
    - "docs/plans/security-review.md#the-secure-flow"
    - "factory/flows.py"
    - "factory/cli.py"
  depends_on:
    - security-review-t05
  non_goals:
    - "Making secure the flow used when none is configured, or changing default or strict"
    - "Turning on `security` or `flow: secure` in this repository's .factory/config.yaml, which is done by hand (see the plan's Verification)"
    - "Changing factory/bench/ or any documentation"
  acceptance:
    - "flows.SECURE is the flow `secure`: plan, build, gates, review, security, verify, each step named after its kind and taking its model and step limit from its kind. Config.flows always holds default, strict and secure, and defining a flow named `secure` raises ConfigError, as redefining default or strict does. `flow: secure` and `factory run --flow secure` select it, a plan run passes it to its child runs, and `factory config` prints it"
    - "`factory run` refuses, before any work, a run whose config sets `security.threat_model` to a path that isn't a file in the main checkout, with `security.threat_model: PATH is not a file in the main checkout`"
    - "`factory run` warns in the run log and on stderr when the run's flow has a security step and `security` is unset (`flow NAME has a security step but security is not configured: the secrets and guarded_paths gates won't run`), and when a security step resolves to the same model as one of the flow's build steps. The run goes ahead"
    - "A fresh build under secure on the test suite's demo repository, with `security: {}` set, ends in an open PR. Its runs are, in order: plan, build, gates (with secrets and guarded_paths passing), review, security, verify and the PR, and its body has the Security section"
    - "tests/test_flows.py::test_without_flows_the_default_flow_is_todays_pipeline and tests/test_pipeline.py::test_an_unknown_flow_is_refused_before_any_work are updated for the third built-in flow. Every other existing test passes unmodified"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_flows.py::test_secure_is_built_in_and_cannot_be_redefined tests/test_flows.py::test_without_flows_the_default_flow_is_todays_pipeline tests/test_pipeline.py::test_the_secure_flow_gates_reviews_and_security_reviews_before_a_pr tests/test_pipeline.py::test_a_missing_threat_model_is_refused_before_any_work tests/test_pipeline.py::test_a_security_step_without_security_config_is_warned_about tests/test_pipeline.py::test_a_security_step_on_the_builders_model_is_warned_about tests/test_pipeline.py::test_an_unknown_flow_is_refused_before_any_work tests/test_scheduler.py::test_a_plan_run_passes_its_flow_to_each_task"
    - "uv run pytest -q tests/test_flows.py tests/test_pipeline.py tests/test_scheduler.py"
  risk: medium

- id: security-review-t07
  goal: "docs/architecture.md, docs/reference.md, NEXT.md, the shipped config template and the factory-ops skill describe the security step, the security gates and the secure flow, and docs/security.md gives this repository's own threat model for `security.threat_model`"
  spec_refs:
    - "docs/plans/security-review.md#design"
    - "docs/architecture.md#policy"
    - "docs/architecture.md#sandbox"
  depends_on:
    - security-review-t06
    - flow-tuning-t05
  non_goals:
    - "Changing code, or tests beyond test_the_docs_describe_the_security_review and what tests/test_templates.py needs for the new template text"
    - "Turning on `security` or `flow: secure` in .factory/config.yaml: only the template's new comment lines are copied there"
    - "Rewriting sections unrelated to this plan, or editing README.md"
  acceptance:
    - "docs/architecture.md: Policy says agent guidance also comes from the main checkout. The Gates table has secrets and guarded_paths, marked configured, and the Roles table has the security reviewer. A `## Security review` section covers the security step, the findings format, the blocking rule and its outcomes, what reaches the builder and what reaches the PR, and has a `### The secure flow` subsection that sets secure next to default and strict"
    - "docs/reference.md: the configuration table has `security` with guarded_paths, allow_secrets and threat_model, and the role `security` under models and max_steps. The flows documentation has the kind `security` and secure written out as a flow. Troubleshooting has rows for a failed secrets gate, a failed guarded_paths gate, a missing threat model, a review recorded as `CHANGES (unparsed)`, and one recorded as `APPROVE (N below threshold)`"
    - "docs/security.md is this repository's threat model, under 8000 characters. It covers what the factory protects (the maintainer's credentials and checkout, the trunk); what is untrusted (agent output, the repository and dependency content agents read, PR comments); the trust boundaries (the sandbox, settings from the main checkout, the gates, the merge); and which changes here deserve a security reviewer's attention (sandbox.py, the path guard and denied commands in tools.py, github.py, how prompts are assembled in agents.py)"
    - "NEXT.md marks item 16 done in its table, linking to docs/architecture.md#security-review"
    - "tests/test_templates.py::test_the_docs_describe_the_security_review checks what the grep commands below check, so it fails before this task's docs change and passes after it"
    - "factory/templates/config.yaml has a commented `security:` block with its three keys, and a commented `flow: secure` line, each with a one-line explanation. factory/templates/skills/factory-ops/SKILL.md covers choosing secure, reading a failed secrets or guarded_paths gate, and reading a security review's outcome. As tests/test_templates.py requires, the skill change is copied to .claude/skills/factory-ops/SKILL.md and the template's new prose comment lines to .factory/config.yaml"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "grep -q '^## Security review' docs/architecture.md"
    - "grep -q 'guarded_paths' docs/architecture.md"
    - "grep -q 'allow_secrets' docs/reference.md"
    - "grep -q 'CHANGES (unparsed)' docs/reference.md"
    - 'test -s docs/security.md && test "$(wc -c < docs/security.md)" -lt 8000'
    - "grep -q 'architecture.md#security-review' NEXT.md"
    - "grep -q 'threat_model' factory/templates/config.yaml"
    - "grep -q 'guarded_paths' factory/templates/skills/factory-ops/SKILL.md"
    - "uv run pytest -q tests/test_templates.py::test_the_docs_describe_the_security_review"
    - "uv run pytest -q tests/test_templates.py"
  risk: low
```

Planned test additions:

| Task | Test | Kind |
|---|---|---|
| t01 | `tests/test_prompt_isolation.py` (new file): two tests; `tests/test_pipeline.py::test_a_builder_that_rewrites_agents_md_does_not_change_the_reviewers_prompt` | unit, CLI end to end |
| t02 | `tests/test_security_gates.py` (new file): the six tests named in its verification | unit |
| t03 | `tests/test_security_gates.py`: six tests | unit |
| t04 | `tests/test_security_review.py` (new file): nine tests | unit |
| t05 | `tests/test_flows.py`: one test; `tests/test_pipeline.py`: four tests; `tests/test_stats.py`: one test | unit, CLI end to end |
| t06 | `tests/test_flows.py::test_secure_is_built_in_and_cannot_be_redefined`; `tests/test_pipeline.py`: four tests; two existing tests updated | unit, CLI end to end |
| t07 | `tests/test_templates.py::test_the_docs_describe_the_security_review`; `tests/test_templates.py` (existing) | unit, regression |

Every verification filter names a test the task adds or an existing test file, so a filter that selects zero tests fails the gate. `tests/test_scheduler.py::test_a_plan_run_passes_its_flow_to_each_task`, `tests/test_pipeline.py::test_an_unknown_flow_is_refused_before_any_work` and `tests/test_flows.py::test_without_flows_the_default_flow_is_todays_pipeline` exist on main today.

Every task can be run by the factory on this repository: the verification commands are `uv run pytest`, `grep` and `test`, and they run offline. This repository runs the `strict` flow (#80), whose test step needs at least one of a task's test commands to fail before the change. Every task names a new test for that reason, and t07 has a docs test.

### Risks

1. **The security reviewer cries wolf, and builds loop.** AI reviewers' comments are often rejected as false positives ([arXiv 2607.03316](https://arxiv.org/abs/2607.03316), cited in strict-flow), and every CHANGES costs a build. **Action:** only critical or high findings with high confidence and an exploit scenario block. The builder sees only those. Everything else goes to the PR. `factory stats` reports the security CHANGES rate, and the run's outcome records how many findings fell below the threshold.
2. **A real vulnerability is rated below the threshold and the PR opens anyway.** **Action:** every finding below the threshold is listed in a visible Security section of the PR, not a collapsed block, so the human who merges sees it. Merging stays the approval.
3. **The model doesn't follow the findings format.** **Action:** the format is generated into the system prompt, not left to the prompt file, so a repository's override keeps it. A report without a findings heading fails safe to CHANGES and is recorded as `CHANGES (unparsed)`, which `factory stats` counts. t04's tests pin the parser against the shipped format.
4. **`guarded_paths` blocks legitimate work.** A task that must edit CI or AGENTS.md fails the gate. **Action:** a contract that names the path lets the change through, and the gate's detail says so. The plan is the human's document, and `plan_untouched` keeps it out of an agent's reach. The gates are opt-in through `security:`.
5. **Secret patterns miss a credential, or flag a fixture.** **Action:** the patterns are high-precision provider formats. The security reviewer covers what they can't, and `allow_secrets` exempts fixture paths. The gate never repeats what it found, so a failing gate's detail is safe to show in a log or PR.
6. **Prompt injection through the change itself.** A builder can write comments that address the security reviewer, as it could address any reviewer. **Action:** t01 keeps the system prompt out of the worktree's reach. The security prompt treats text in the change that addresses an AI agent as a finding, and the deterministic gates don't read prose.
7. **A deep chain behind flow-tuning, and more conflicts in shared files.** **Action:** t01 and t02 wait for `flow-tuning-t04`, t07 for `flow-tuning-t05`, and wiki waits for this plan. Within the plan, M1 and M2 touch no common file, and from M4 on the tasks run one after another. Merge each PR as it opens.

---

## Problem

The factory now lets a repository reshape its agent flow ([agent-flows](agent-flows.md)) and is making each step stricter ([strict-flow](strict-flow.md)). But nothing in it looks at a change for security, and one part of its own isolation leaks.

- **No step looks for vulnerabilities.** The reviewer's checklist (`factory/prompts/reviewer.md`) has one line on "unchecked external input" under correctness. A repository can add a custom review step today (`{name: security, kind: review}` plus `.factory/agents/security.md`), but the factory ships no security prompt. Such a step decides by its own `VERDICT:` line (`factory/agents.py:87`), so it either blocks on every speculative finding or lets every finding through.
- **No gate checks for credentials or sensitive files.** `gates.run_gates` (`factory/gates.py:114`) checks conflict markers, the plan, strict-flow's locked tests, the session log, the e2e test and the commands. Lockfile changes are only noted in the `diff` gate's detail (`factory/gates.py:128`). Nothing stops a candidate that adds a private key, or that edits `.github/workflows/`, `.factory/`, a skill, or AGENTS.md. After merge, those files run with the repository's secrets or become later agents' instructions. The sandbox protects the run, but nothing protects the merge from a builder that was prompt-injected by content it read.
- **A builder can rewrite its own reviewer's instructions.** `_repo_guidance` (`factory/agents.py:153`) reads the first `guidance` file from `ctx.worktree` (`factory/agents.py:521`), and the builder writes there. A builder that edits AGENTS.md changes the system prompt of the review step, the verify step and its own next attempt in the same run. That contradicts the stated policy: "Settings come from the main checkout, never from a task worktree, so an agent can't weaken its own gates or change its own prompt" (`docs/architecture.md`, Policy).

## Goal

A repository can opt in to a security review of every task. Gates fail a candidate that adds a credential, or that changes a file steering agents or CI that its contract doesn't name. A security reviewer, on its own model, sends the build back only for a confident, exploitable, high-severity finding, and puts everything else in front of the human in the PR. The built-in `secure` flow turns it on, and no agent can change the instructions of the agents that judge it. With none of it configured, the factory behaves as today, apart from the guidance fix.

## Design

### Guidance from the main checkout

```text
before:  system prompt = role prompt (main) + contract + project rules (main config) + guidance (WORKTREE)
after:   system prompt = role prompt (main) + contract + project rules (main config) + guidance (main)
```

`LangChainRoles` already holds `root`, the main checkout from which it reads `.factory/agents/`. t01 reads the guidance from there too, which matches the Policy. A repository whose task changes AGENTS.md still gets the change once it merges. Bench cells pass their own case root, so bench is unaffected.

### The security config

```yaml
security:                          # any mapping turns it on; `security: {}` uses the defaults
  guarded_paths: ["deploy/**"]     # more globs for the guarded_paths gate, added to the defaults
  allow_secrets: ["tests/fixtures/keys/**"]   # paths the secrets gate counts but doesn't fail
  threat_model: docs/security.md   # read from the main checkout into every security step's prompt
```

It turns on the two gates in every flow, and gives security steps their rules and threat model. A security step runs without it, with the default rules and no threat model, and t06 warns about that.

### The secrets gate

High-precision provider formats only, scanned in the added lines of `base..sha`:

| Name | Shape |
|---|---|
| `private-key` | a `-----BEGIN … PRIVATE KEY-----` line |
| `aws-access-key-id` | `AKIA` or `ASIA` and 16 upper-case characters or digits |
| `github-token` | `ghp_`, `gho_`, `ghu_`, `ghs_`, `ghr_` or `github_pat_` and a long token |
| `anthropic-key`, `openrouter-key`, `openai-key` | `sk-ant-`, `sk-or-v1-`, `sk-` / `sk-proj-` and a long token |
| `slack-token` | `xoxa-`, `xoxb-`, `xoxp-`, `xoxr-`, `xoxs-` |
| `google-api-key` | `AIza` and 35 characters |

```text
| secrets | FAIL | factory/demo.py:12 openrouter-key<br>remove the credential and read it from the environment |
```

The detail gives the path, the line and the pattern, never the match. Tests build their sample keys at runtime, for example `"sk-or-v1-" + "0" * 64`, so this repository's own gate passes on the task that adds them.

### The guarded paths gate

| Default glob | Why |
|---|---|
| `.github/**`, `.gitlab-ci.yml` | CI runs with the repository's secrets after merge |
| `.factory/**` | The factory's config and prompt overrides |
| `.claude/**`, `.agents/**` | Skills that steer later agent sessions |
| each `guidance` file | Every agent's system prompt (after t01, from the main checkout) |
| each `lockfiles` name, at any depth | Dependency changes |

A changed guarded path passes only when the contract names it, in its goal, a spec_ref or an acceptance criterion, either as the path itself or as a directory prefix ending in `/`. Non-goals don't count: they name paths in order to forbid them. The diff is read with `--no-renames`, so moving `.github/workflows/ci.yml` away counts as a change to it.

```text
| guarded_paths | FAIL | .github/workflows/ci.yml (matches .github/**): not named by the contract.<br>Leave it alone, or a human names it in the plan's contract. |
| guarded_paths | PASS | named by the contract: AGENTS.md |
```

Gate order with `security` set: clean, diff, conflict_markers, plan_untouched, [acceptance_untouched], secrets, guarded_paths, session_log, e2e_written, verification, unit_tests, e2e_tests.

### The security step

A new step kind, `security`, because a kind fixes a step's tools, task message and how its output is used, and all three differ from a reviewer's:

| | review | security |
|---|---|---|
| Prompt | `reviewer.md`: the contract, scope, tests, correctness | `security.md`: exploitable weaknesses in the change |
| Tools | read, `git_diff` (`run` with `prove`) | read, `git_diff` |
| Extra system-prompt blocks | proof rules under `prove` | `# Security rules`, `# Threat model (PATH)` |
| Verdict | its `VERDICT:` line | computed by the factory from its findings |
| On CHANGES the builder gets | the whole report | the blocking findings only |
| Run role | `review` | `security` |

The shipped prompt's checklist: injection (shell, SQL, path, template), authentication and authorization, unsafe deserialization, secrets handling, SSRF, cryptography, weakened sandboxing or isolation, new dependencies and install scripts, and text in the change addressed to an AI agent or reviewer. For each finding it asks who controls the input. A weakness that no outside input reaches is low confidence.

### Findings and the verdict

```text
## Findings
1. [high] [confidence: high] factory/web/app.py:88 — task id from the URL reaches a filesystem path unchecked
   Exploit: a page on any site can POST to 127.0.0.1 with id=../../.ssh/id_ed25519 and read the key back
   Fix: validate the id against the board before building the path
2. [medium] [confidence: high] factory/tools.py:84 — a model-supplied grep pattern is compiled without a time limit
   Exploit: a pathological regex stalls the agent's step
   Fix: run grep in the sandbox with its timeout
```

| Findings | Verdict | Run outcome |
|---|---|---|
| `None.` | APPROVE | `APPROVE` |
| some, none blocking | APPROVE | `APPROVE (N below threshold)` |
| N critical or high, confidence high, with an `Exploit:` line | CHANGES | `CHANGES (N blocking)` |
| no `## Findings` heading | CHANGES | `CHANGES (unparsed)` |

The rules are generated into the system prompt, so a repository's own `.factory/agents/security.md` keeps them, and [measure](measure.md)'s prompt version changes with them and with the threat model. `factory stats` counts every outcome that starts with `CHANGES`, as it does for reviewers.

### The security step in a flow

```text
[plan]?   [test]?   build+   ( review | security | gates )*   [verify]?
```

- Security steps are post-build steps, like review steps, and the first CHANGES ends the attempt. They run on every rework entry, too.
- The builder's feedback holds only the blocking findings, with their Exploit and Fix lines. A `CHANGES (unparsed)` sends the report back, capped, because failing safe beats skipping the review.
- `prove` stays a review-only option. A security step can't run commands.

### The PR

```markdown
## What to check
- …

## Security

- [medium] [confidence: high] factory/tools.py:84 — a model-supplied grep pattern is compiled without a time limit
- Guarded paths named by the contract: `AGENTS.md`

## Checks

All 11 gates passed on 3f2a… after 1 build attempt. … Reviewed by review: APPROVE. Reviewed by security: APPROVE (1 below threshold).

<details><summary>Security report (security)</summary> … </details>
```

The Security section is visible because it lists what the factory let through. The full report is collapsed and shrinks under the body limit like a reviewer's.

### The secure flow

```yaml
secure:                     # built in, like default and strict; it can't be redefined
  - plan
  - build
  - gates
  - review
  - security
  - verify
```

It is this repository's `gates-first` flow plus a security step. Since strict's options and the security step are independent, a repository that wants both writes its own flow:

```yaml
flows:
  strict-secure:
    - {kind: test, loop: [map, trim, nudge]}
    - {kind: build, loop: [map, trim, nudge, resume]}
    - gates
    - {kind: review, prove: true, loop: [trim]}
    - {kind: security, model: "openrouter:z-ai/glm-5.3"}
    - verify
```

Before any work, `factory run` refuses a missing threat model file. It warns when a flow's security step runs without `security:` set, and when the security step resolves to a build step's model, since it then shares the builder's blind spots.

## Files Changed

| File | Change |
|---|---|
| `factory/agents.py` | Guidance from `root` (t01); the `security` role, its tools, task message, rules and threat-model blocks, and verdict (t04) |
| `factory/security.py` | New: secret patterns and diff scan (t02); guarded globs and the naming rule (t03); findings parser and verdict (t04); PR findings cap (t05) |
| `factory/config.py` | `SecurityConfig` (t02); the `security` role in `models` and `max_steps` (t04); `secure` among the built-in flows (t06) |
| `factory/gates.py` | The `secrets` (t02) and `guarded_paths` (t03) gates |
| `factory/prompts/security.md` | New: the security reviewer (t04) |
| `factory/flows.py` | The `security` kind and order rule (t05); `SECURE` (t06) |
| `factory/pipeline.py` | Security nodes, feedback, the verifier's input and the PR's Security section and block (t05) |
| `factory/prbody.py` | The Security section and the security block in the body's shrink order (t05) |
| `factory/db.py` | The `security` run role (t05) |
| `factory/stats.py` | `security CHANGES rate` (t05) |
| `factory/cli.py` | `--role security` (t05); the threat-model refusal and security warnings (t06) |
| `factory/web/views.py` | The role's display name (t05) |
| `tests/fake_model.py` | A SECURITY script (t04) |
| `tests/test_prompt_isolation.py`, `tests/test_security_gates.py`, `tests/test_security_review.py` | New test files (t01, t02–t03, t04) |
| `tests/test_pipeline.py`, `tests/test_flows.py`, `tests/test_stats.py` | Added tests (t01, t05, t06); two existing tests updated for the third built-in flow (t06) |
| `docs/architecture.md`, `docs/reference.md`, `NEXT.md`, `docs/security.md` | Docs and this repository's threat model (t07) |
| `factory/templates/config.yaml`, `factory/templates/skills/factory-ops/SKILL.md`, `.claude/skills/factory-ops/SKILL.md`, `.factory/config.yaml` (comments only) | Template text and its installed copies (t07) |

## Test Plan

### Unit tests

- **t01** `tests/test_prompt_isolation.py`:
  - `test_guidance_comes_from_the_main_checkout_not_the_worktree`: a step's system prompt holds the root's AGENTS.md when the worktree's differs.
  - `test_a_guidance_file_only_in_the_worktree_is_not_read`: a CLAUDE.md added only in the worktree never appears.
- **t02** `tests/test_security_gates.py`:
  - `test_security_config_parses_and_rejects_unknown_keys`
  - `test_secrets_gate_fails_on_an_added_key_and_does_not_repeat_it`: one test per pattern name; the detail holds `path:line name` and not the key.
  - `test_secrets_gate_reports_the_new_files_line_numbers`
  - `test_allow_secrets_paths_are_counted_not_failed`
  - `test_without_security_there_is_no_secrets_gate`
  - `test_no_tracked_file_holds_a_literal_secret`: runs SECRET_PATTERNS over `git ls-files`, so the repository itself stays clean.
- **t03** `tests/test_security_gates.py`:
  - `test_guarded_globs_are_the_defaults_guidance_lockfiles_and_config`
  - `test_an_unnamed_guarded_change_fails_the_gate`
  - `test_a_guarded_change_the_contract_names_passes`
  - `test_a_directory_prefix_names_the_files_under_it`
  - `test_non_goals_and_verification_do_not_name_a_path`
  - `test_a_guarded_file_deleted_or_renamed_away_counts`
- **t04** `tests/test_security_review.py`:
  - `test_the_security_prompt_ships_and_can_be_overridden`
  - `test_security_rules_and_the_threat_model_join_the_system_prompt`: the rules survive an override prompt without them, and the prompt version changes with the threat model.
  - `test_a_long_threat_model_is_cut_and_says_so`
  - `test_the_security_step_reads_and_diffs_but_cannot_write_or_run`
  - `test_guarded_paths_in_the_change_are_listed_in_the_task_message`
  - `test_findings_are_parsed_with_severity_confidence_and_exploit`
  - `test_only_confident_high_findings_with_an_exploit_block`: a table of findings against verdicts and outcomes.
  - `test_a_report_without_findings_counts_as_changes_unparsed`
  - `test_a_verdict_line_is_ignored`
- **t05**:
  - `tests/test_flows.py::test_a_security_step_goes_with_the_review_steps`: the order rule, `loop` accepted, `prove` refused, gates inserted after it.
  - `tests/test_stats.py::test_stats_report_the_security_changes_rate`
- **t06** `tests/test_flows.py::test_secure_is_built_in_and_cannot_be_redefined`
- **t07** `tests/test_templates.py::test_the_docs_describe_the_security_review`: the architecture and reference sections, `docs/security.md` under 8000 characters, NEXT.md's link, and the template and skill text.

### End-to-end tests

These run in `tests/test_pipeline.py`, driving the real CLI, pipeline, agents, git, sandbox and fake `gh`, with only the model scripted:

- **t01** `test_a_builder_that_rewrites_agents_md_does_not_change_the_reviewers_prompt`
- **t05**:
  - `test_a_blocking_security_finding_sends_back_only_the_blocking_findings`: attempt 2's feedback holds the high finding and not the medium one; the PR opens after attempt 2.
  - `test_findings_below_the_threshold_go_to_the_prs_security_section`: the body has `## Security` with the finding, the Checks paragraph has `APPROVE (1 below threshold)`, and the run's role is `security`.
  - `test_an_unparsed_security_report_sends_the_build_back`
  - `test_a_ci_fix_runs_the_flows_security_step`
- **t06**:
  - `test_the_secure_flow_gates_reviews_and_security_reviews_before_a_pr`
  - `test_a_missing_threat_model_is_refused_before_any_work`
  - `test_a_security_step_without_security_config_is_warned_about`
  - `test_a_security_step_on_the_builders_model_is_warned_about`

## Verification

- Each task's verification commands, then `uv run pytest -q` (the unit gate).
- By hand after t06 merges, with real models and real money:
  1. `factory prompt security --flow secure` prints the shipped prompt, and `factory config` shows the flow and no `security` yet.
  2. Turn it on for this repository by hand (this edits `.factory/`, which the gate guards, so an agent can't): `security: {threat_model: docs/security.md}` after t07 lands, and keep `flow: gates-first`.
  3. Run one real task with `factory run TASK --flow secure` and read its PR: the gate table with secrets and guarded_paths, the Security section and the security report.
  4. Plant a known flaw in a scratch task (a path built from request input in `factory/web/`), run it under secure, and check that it comes back `CHANGES (1 blocking)` and is fixed on attempt 2.
  5. After a week of real runs, read `factory stats` for the security CHANGES rate, and the PRs' Security sections for findings that should have blocked or shouldn't have been raised.
- Switch `flow:` to `secure` only if steps 3 to 5 show the step pays for its cost.

## Cross-Workstream Coordination

- **Depends on:**
  - [flow-tuning](flow-tuning.md). `security-review-t01` and `t02` depend on `flow-tuning-t04`, the last task there to change `flows.py`, `agents.py`, `pipeline.py`, `config.py`, `db.py` and `cli.py`, and `security-review-t07` on `flow-tuning-t05`, which edits the same docs. The `security` role joins `config.py`'s roles beside its `select` role. Its re-ask for a missing verdict applies to review steps only.
  - [strict-flow](strict-flow.md), merged, reached through flow-tuning. This plan's order rule includes strict's `test` kind. Its gate order places `secrets` after `acceptance_untouched`. Its security kind refuses `prove` and accepts `loop`. Its built-in `secure` sits beside `strict`, and t06 updates the two tests that strict-flow-t07 updates for `strict`.
  - [agent-flows](agent-flows.md), merged. A security step is a flow step; custom steps and per-step models work as for any kind.
  - [measure](measure.md), merged. The security rules and threat model count toward the prompt version, and `factory stats` gains the security CHANGES rate.
  - [pr-descriptions](pr-descriptions.md), merged. The Security section and block are placed in, and shrink with, its body layout.
- **Required by:**
  - [wiki](wiki.md). `wiki-t01` depends on `security-review-t06` and `wiki-t07` on `security-review-t07`. Wiki changes the same `agents.py`, `gates.py`, `cli.py` and docs, and its task agents' guidance comes from t01's main-checkout read. A `security` step gets a role page only if the wiki has one for it.

## Notes / Out of Scope

- **Reviewing any ref or PR** (`factory security-review REF|PR`), human-written PRs included. The step needs a contract today. A contract-less mode can reuse t04's agent and t02–t03's gates once this lands.
- **An audit crew** that scans the existing codebase by area, triages its findings, and writes fix contracts into a plan doc for the factory to run. That is the wiki's crew pattern applied to security, and it gets its own plan.
- **`prove` on security steps.** A reproduced exploit would be the strongest proof, but many findings (authorization, secrets handling) don't fit one failing command. Revisit if `factory stats` shows security CHANGES that the human overturns.
- **A configurable threshold** (block on medium, or on medium confidence). Every repository gets the same rule until the stats show it's wrong somewhere.
- **External scanners** (semgrep, gitleaks, pip-audit) as gates. A repository can already add an offline scanner command to `unit_tests`. pip-audit-style checks need the network, which the sandbox doesn't have.
- **A bench case with a planted vulnerability,** to measure the security step against default with `factory bench`. It needs a case whose hidden tests check the vulnerability, and that should be its own task once the step exists.
- **Choosing secure by the contract's `risk`.** As in strict-flow, `--flow` and `flow:` stay the only ways to choose.
