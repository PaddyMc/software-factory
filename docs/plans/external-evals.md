# Plan: Measure the factory on current SWE and security benchmarks

**Status:** Planned (2026-11-22). Workstream scoped; awaiting kickoff: t01 and t02 can run now; t03 waits for `evals-t07`. Roadmap: [NEXT.md item 21](../../NEXT.md#21-nothing-measures-the-factory-against-outside-benchmarks). It supersedes the `experiment/swe-bench` plan (PR #83, none of its tasks built), whose Docker sandbox design t01 reuses.

---

## Execution Plan

### Locked Decisions

| Decision | Choice |
|---|---|
| Where it lives | **On `main`, in `factory bench`.** The Docker sandbox and the benchmark adapters ship with the factory, so anyone can reproduce a number. This replaces the by-hand `experiment/swe-bench` branch, and its SWE-bench Verified target is dropped: OpenAI stopped reporting Verified in February 2026 as contaminated, and Epoch rates it "Flawed" |
| Harness | **Native bench adapters.** Each benchmark's instances become bench cases that run in the benchmark's own images, and the benchmark's official scorer decides `solved`. The factory is not packaged as a Harbor or Inspect agent: its worktrees, file tools and gates stay as they are, and evals' statistics, check, splits and ledger apply to the new cases unchanged |
| SWE suite | **SWE-bench Pro, public V2** (`ScaleAI/SWE-bench_Pro`, default config: 642 tasks in 11 repositories, Go, Python, JavaScript and TypeScript). It's scored by Pro's authoritative re-grade: Harbor's `patch_replay` agent runs each captured diff on a pristine image |
| Cyber suite | **Vulnerability patching on PatchEval-Verified** (`ByteDance/PatchEval`: 230 CVEs in Go, JavaScript and Python, Apache-2.0). It's scored by PatchEval's `run_evaluation.py`, which passes a patch when the image's `fix-run.sh` exits 0. Offensive work (CTFs, PoC generation, exploitation: Cybench, CyberGym, CVE-Bench) is out, because the factory's output is a PR, not an exploit |
| Sequencing | **After evals' code tasks.** Every task here that changes `factory/bench/` depends on `evals-t07`. t01 (the Docker sandbox) and t02 (Go and JavaScript test runners) touch no bench file and run now |
| Sample and budget | **50 Pro instances, stratified by repository, and 40 PatchEval CVEs, stratified by language**, both seeded. About ±13–15 points at 95%, about $250–400 per variant, and about 250 GB of images |
| Measurements | **By hand, two of them.** First the configured `strict` flow on both suites (t09). Then `secure` against `strict` once security-review's `secure` flow lands (t10), reusing t09's strict cells |

### Milestones

| # | Deliverable | Exit criteria | Parallelizable with |
|---|---|---|---|
| **M1** | Docker sandbox | `tests/test_sandbox_docker.py` passes; `tests/test_sandbox.py` and `tests/test_config.py` pass unmodified | M2 |
| **M2** | Go and JavaScript test runners | The t02 tests in `tests/test_verification.py` pass | M1 |
| **M3** | External cases in the bench | The t03 tests in `tests/test_bench_external.py` pass; the evals bench tests pass unmodified | — |
| **M4** | Checking external cases | The t04 tests in `tests/test_bench_external.py` pass | — |
| **M5** | SWE-bench Pro adapter | `tests/test_external_swebench_pro.py` passes | M6, M7 |
| **M6** | PatchEval adapter | `tests/test_external_patcheval.py` passes | M5, M7 |
| **M7** | Reading and exporting external runs | The t07 tests in `tests/test_bench_external.py` pass | M5, M6 |
| **M8** | Runbook and docs | `tests/test_external_docs.py` and `tests/test_templates.py` pass | — |
| **M9** | First measurement (by hand) | `docs/external-evals-results.md` gives strict's resolved k/50 and k/40 with intervals, cost, run id and factory version line, and the official re-grade agrees | — |
| **M10** | secure vs strict (by hand) | `docs/external-evals-results.md` has the paired comparison line for each suite | — |

**Sequence:** `(M1 ∥ M2) → [evals-t07 →] M3 → M4 → (M5 ∥ M6 ∥ M7) → [evals-t08 →] M8 → M9 → [security-review-t06 →] M10`.

### Task Contracts

| Milestone | Task IDs | Coverage |
|---|---|---|
| **M1** | `external-evals-t01` | `Docker` in `factory/sandbox.py`; `image`, `mount` and `seed` in `SandboxConfig` (`factory/config.py`); new `tests/fake_docker.py` and `tests/test_sandbox_docker.py` |
| **M2** | `external-evals-t02` | `go test`, jest, mocha and vitest in `factory/verification.py`; tests in `tests/test_verification.py` |
| **M3** | `external-evals-t03` | New `factory/bench/external/__init__.py` (the adapter interface, registry, sample and scoring); the `external` kind and key in `factory/bench/cases.py`; scoring, preflight and container cleanup in `factory/bench/run.py`; `factory bench prepare` in `factory/cli.py`; new `tests/external_toy.py` and `tests/test_bench_external.py` |
| **M4** | `external-evals-t04` | New `factory/bench/external/templates.py` (language templates and probes); external cases in `factory bench check` (`factory/bench/check.py`), the leak probe and template probe in `factory/bench/external/__init__.py`, refill in prepare; tests in `tests/test_bench_external.py` |
| **M5** | `external-evals-t05` | New `factory/bench/external/swebench_pro.py`; new `tests/fake_harbor.py` and `tests/test_external_swebench_pro.py` |
| **M6** | `external-evals-t06` | New `factory/bench/external/patcheval.py`; new `tests/fake_patcheval.py` and `tests/test_external_patcheval.py` |
| **M7** | `external-evals-t07` | The external section of `factory bench report` and `compare`, and `factory bench export`, in `factory/bench/report.py` and `factory/cli.py`; tests in `tests/test_bench_external.py` |
| **M8** | `external-evals-t08` | New `docs/external-evals.md`; `docs/architecture.md`, `docs/reference.md`, `NEXT.md`, the factory-ops skill template and its copy; new `tests/test_external_docs.py` |
| **M9** | `external-evals-t09` | By hand: the prepared suites, their check, the strict run, the official re-grade and new `docs/external-evals-results.md` |
| **M10** | `external-evals-t10` | By hand: the secure run against t09's baseline, in `docs/external-evals-results.md` |

```yaml
- id: external-evals-t01
  goal: "A sandbox config with an `image` runs every agent command and gate in a Docker container of that image, with the worktree mounted, no network, the host user's ids and the configured image paths hidden, and the container is removed when the sandbox closes"
  spec_refs:
    - "docs/plans/external-evals.md#a-docker-sandbox"
    - "factory/sandbox.py"
  depends_on: []
  non_goals:
    - "Changing Bwrap, Unsandboxed, or the behaviour of any config without `image`"
    - "Changing factory/bench/, factory/pipeline.py, factory/gates.py, factory/agents.py or factory/cli.py"
    - "Pulling images: a missing image is refused, never fetched"
    - "Anything benchmark specific: datasets, image names, scoring"
  acceptance:
    - "SandboxConfig gains `image` (a Docker image), `mount` (an absolute path inside the container where the worktree is also mounted) and `seed` (an absolute path inside the image whose git-ignored files are copied into the worktree before the container starts), all defaulting to none. config.parse rejects a relative `mount` or `seed`, and `mount` or `seed` without `image`. With `image` the bubblewrap defaults don't apply: `hide`, `path`, `env` and `offline_env` default to empty, `hide` holds absolute paths inside the image (a relative one is rejected), and ro_binds, rw_binds and cache_dirs are not used"
    - "sandbox.make returns a Docker sandbox whenever the config has an `image`, with or without --no-sandbox, and a Bwrap or Unsandboxed one exactly as before otherwise"
    - "The first run starts one container per sandbox with `docker run -d`: `--network none` unless the sandbox has network, `--read-only` with a writable /tmp tmpfs, `--user` set to the host uid and gid, `--cap-drop ALL`, `--security-opt no-new-privileges`, a `factory.sandbox` label holding the worktree path, and `sleep infinity` as its command in place of the image's entrypoint. Its mounts are the worktree at its own path and at `mount`, the git common dir read-only, the worktree's git admin dir writable, an empty read-only tmpfs over each hidden directory and /dev/null over each hidden file. Nothing else from the host is mounted, and the Docker socket never is"
    - "Each run is a `docker exec` in the worktree directory with HOME=/tmp, PATH set to the config's `path` ahead of the image's PATH, the config's `env` and, without network, its `offline_env`. The command runs under coreutils `timeout` inside the container, so a timed-out command is stopped in the container and returns the same timeout Result as Bwrap"
    - "With `seed`, before the sandbox's container starts, a short-lived container of the image with no network lists the files `git ls-files --others --ignored --exclude-standard` reports under `seed`, leaving out `build/` and `__pycache__` directories, and copies them into the worktree without overwriting files the worktree already has. That container is removed"
    - "close() removes the container and can be called twice. Containers still open at interpreter exit are removed"
    - "The first run refuses, naming the problem, when the docker command is missing or the daemon is unreachable, and when the image isn't present locally, naming `docker pull` and the image"
    - "tests/fake_docker.py stands in for the docker CLI in tests: it records each call's arguments, keeps fake images as directories, and runs exec'd commands with bash in the given directory"
    - "docs/sessions/ has this task's session log entry"
  verification:
    - "uv run pytest -q tests/test_sandbox_docker.py::test_a_config_image_selects_the_docker_sandbox tests/test_sandbox_docker.py::test_docker_config_keys_are_validated tests/test_sandbox_docker.py::test_one_container_per_sandbox_with_no_network_and_the_host_user tests/test_sandbox_docker.py::test_only_the_worktree_and_its_git_dirs_are_mounted tests/test_sandbox_docker.py::test_hidden_image_paths_are_overlaid tests/test_sandbox_docker.py::test_commands_run_in_the_worktree_with_the_config_path_and_env tests/test_sandbox_docker.py::test_a_timed_out_command_is_stopped_in_the_container tests/test_sandbox_docker.py::test_seed_copies_the_images_ignored_files_without_overwriting tests/test_sandbox_docker.py::test_close_removes_the_container_once tests/test_sandbox_docker.py::test_a_missing_docker_or_image_is_refused"
    - "uv run pytest -q tests/test_sandbox.py tests/test_config.py"
  risk: medium

- id: external-evals-t02
  goal: "Go and JavaScript test runs count as tests: `go test`, jest, mocha and vitest commands are test commands, their output gives the number of tests that ran, and a run that selects no tests is inconclusive, never a pass"
  spec_refs:
    - "docs/plans/external-evals.md#go-and-javascript-test-runners"
    - "factory/verification.py"
  depends_on: []
  non_goals:
    - "Changing how pytest, cargo or unittest commands and their output are classified"
    - "Recognizing `npm test`, `yarn test` or other script aliases whose runner the command doesn't name"
    - "Changes outside factory/verification.py, tests/test_verification.py and this task's session log"
  acceptance:
    - "verification.is_test_command is true for commands that run `go test`, `jest`, `mocha` or `vitest`, directly or through npx, yarn or pnpm, and stays true for every command it accepted before"
    - "verification.tests_run counts `go test -v` output as the number of `--- PASS:`, `--- FAIL:` and `--- SKIP:` lines, subtests included, and as 0 when every package line says `[no tests to run]` or the output has `testing: warning: no tests to run` and no such lines"
    - "tests_run counts jest from its `Tests:` summary line (the total), mocha from its `N passing`, `N failing` and `N pending` lines (their sum), and vitest from its `Tests` summary line (the total in parentheses), and returns 0 for jest's `No tests found`, mocha's `0 passing` with nothing failing, and vitest's `No test files found`"
    - "For go test, jest, mocha and vitest commands, verification.classify returns inconclusive when tests_run is 0, whatever the exit code, so the strict flow's red check rejects a command that selects no tests. A non-zero exit with tests counted is a fail, and a compile failure with no count is a fail"
    - "docs/sessions/ has this task's session log entry"
  verification:
    - "uv run pytest -q tests/test_verification.py::test_go_and_js_runners_are_test_commands tests/test_verification.py::test_go_test_counts_its_tests tests/test_verification.py::test_go_test_selecting_nothing_is_inconclusive tests/test_verification.py::test_jest_mocha_and_vitest_count_their_tests tests/test_verification.py::test_js_runners_finding_no_tests_are_inconclusive"
    - "uv run pytest -q tests/test_verification.py"
  risk: low

- id: external-evals-t03
  goal: "`factory bench` runs external cases: `factory bench prepare BENCHMARK` turns a seeded, stratified sample of a benchmark's instances into cases through that benchmark's adapter, and a verified cell of an external case is scored by the adapter's official scorer"
  spec_refs:
    - "docs/plans/external-evals.md#external-cases"
    - "docs/plans/external-evals.md#the-sample"
    - "docs/plans/external-evals.md#scoring"
  depends_on:
    - external-evals-t01
    - evals-t07
  non_goals:
    - "The SWE-bench Pro and PatchEval adapters themselves (external-evals-t05, external-evals-t06): this task tests with a toy adapter"
    - "Checking external cases (external-evals-t04), or the report's external section and export (external-evals-t07)"
    - "Downloading datasets: prepare reads local files"
    - "Changing how cases of other kinds load, run or score"
    - "Editing documentation"
  acceptance:
    - "New factory/bench/external/__init__.py defines the adapter interface the plan's external-cases section lists and the registry ADAPTERS, which maps `swebench-pro` to factory.bench.external.swebench_pro and `patcheval` to factory.bench.external.patcheval and imports a module only when it is used. An unknown benchmark, or one whose module isn't installed, is refused with the known names"
    - "case.yaml accepts kind `external` with an `external` mapping holding benchmark, instance, image, stratum and source (the absolute path of the dataset file). An external case has an empty `hidden` and needs no hidden/ or solution/. The rules for every other kind are unchanged, and `factory bench cases` shows an external case's benchmark and instance"
    - "`factory bench prepare BENCHMARK --source FILE --out DIR [--count N] [--seed S] [--instances ID ...]` picks the sample as the plan's sample section says (or exactly the given ids) and builds each case through the adapter. An instance the adapter refuses is recorded with its reason, and the next instance in its stratum's order takes its place; a stratum that runs out leaves its slots empty and says so. Case ids follow the plan's rule"
    - "prepare writes DIR/sample.json (benchmark, the source file's sha256, seed, count, each stratum's share and how many it filled, each picked instance with its case id, and each skipped instance with its reason) and DIR/suite.yaml in the format evals-t04 defines, with kind external and each case's benchmark, instance and image as its source. Running prepare again with the same arguments keeps the existing cases and changes no file"
    - "When a cell of an external case ends verified, run_cell writes CELL/external/patch.diff (`git diff --binary` from the base to the candidate, leaving out .factory/ and the case's plan file) and records the adapter's verdict: resolved is solved, unresolved is false_pass, and a scorer error, an exception or a run past external.SCORE_TIMEOUT (3600 seconds) is error. The scorer's log tail goes to CELL/hidden.log, and the cell record gains `external` with the verdict and its detail"
    - "Scorers run on the host, outside the agents' sandbox, with the environment minus every variable sandbox.SECRET_ENV matches. Nothing under the case's source file or a scorer's checkout is mounted into the agents' container"
    - "Bench preflight refuses before creating the run directory when a selected external case's docker is missing or unreachable, its image isn't present locally (naming `docker pull` and the image), or its adapter's scorer isn't available (with the adapter's reason). bubblewrap isn't required when every selected case has an image. The `requires` check runs in the case's container, and the hidden-file check is skipped for external cases"
    - "A cell closes every Docker sandbox it made, for the pipeline and for scoring, whether it succeeds, fails or raises"
    - "results.json records the factory version line (version.line()) in its run header, and each external case's benchmark, instance, image id (from `docker image inspect`) and the adapter's harness versions in its cases entry"
    - "tests/external_toy.py is a toy adapter for tests, registered by the tests, whose instances are small git repositories in fake images and whose scorer reads a verdict file the test supplies"
    - "docs/sessions/ has this task's session log entry"
  verification:
    - "uv run pytest -q tests/test_bench_external.py::test_an_external_case_loads_without_hidden_or_solution tests/test_bench_external.py::test_an_unknown_benchmark_is_refused_with_the_known_names tests/test_bench_external.py::test_prepare_samples_seeded_and_stratified tests/test_bench_external.py::test_prepare_skips_refused_instances_and_refills_the_stratum tests/test_bench_external.py::test_prepare_again_changes_nothing tests/test_bench_external.py::test_a_verified_external_cell_is_scored_by_its_adapter tests/test_bench_external.py::test_an_unresolved_verdict_is_a_false_pass_and_a_scorer_failure_an_error tests/test_bench_external.py::test_the_scored_patch_leaves_out_the_factory_files tests/test_bench_external.py::test_scorers_run_without_secrets tests/test_bench_external.py::test_bench_refuses_external_cases_without_docker_image_or_scorer tests/test_bench_external.py::test_a_cell_removes_its_containers tests/test_bench_external.py::test_results_record_the_benchmark_image_and_harness_versions"
    - "uv run pytest -q tests/test_bench.py tests/test_bench_cases.py tests/test_bench_mine.py"
  risk: high

- id: external-evals-t04
  goal: "`factory bench check` proves each external case sound before money is spent on it: its test template runs in the case's container, no copy of the fix is readable there, its benchmark's scorer resolves the gold patch and rejects an empty one, and prepare replaces cases the check marks broken"
  spec_refs:
    - "docs/plans/external-evals.md#checking-an-external-case"
    - "docs/plans/evals.md#checking-a-case"
  depends_on:
    - external-evals-t03
  non_goals:
    - "Mutants for external cases: their scorer, not the factory, owns their tests"
    - "Changing the check of cases of other kinds"
    - "Calling a model, or editing documentation"
  acceptance:
    - "New factory/bench/external/templates.py holds the plan's language templates for Python, Go and JavaScript (also used for TypeScript): each one's test path, verification command, `test_paths`, guidance, and a passing and a failing probe test. For JavaScript the runner is jest, mocha or vitest, whichever a package.json names first in that order among its dependencies and devDependencies, and a package.json that names none gets no template"
    - "For an external case, `factory bench check` materializes it and runs three checks in order. Template: with the adapter's passing probe test at the template's test path, the contract's verification commands classify pass with at least one test counted in the case's Docker sandbox, and with the failing probe they classify fail. Leak: inside the case's container, `grep -rIlF` over the filesystem, outside /proc, /sys, /dev and the worktree's mounts, finds none of the gold patch's distinctive added lines, at most five lines of 30 or more non-space characters that the base doesn't contain. Scorer: the adapter's scorer resolves the gold patch and doesn't resolve an empty patch"
    - "A failed template or scorer check, or a leak hit, makes the case `broken`, naming the check (and, for a leak, the path). A leak probe that runs past check.LEAK_TIMEOUT (300 seconds) makes it `weak`. Otherwise it's `ok`. The output line, exit code and `--json` are as evals-t03 defines them, and the result is written to the case's entry in suite.yaml"
    - "`factory bench check --parallel N` checks up to N external cases at once"
    - "Running prepare again removes the cases suite.yaml marks broken, records each in sample.json's skipped instances with the reason `check: ` followed by the failed check, and refills their strata from the next instances in order. Cases already marked ok or weak are kept"
    - "docs/sessions/ has this task's session log entry"
  verification:
    - "uv run pytest -q tests/test_bench_external.py::test_language_templates_pick_the_js_runner_from_package_json tests/test_bench_external.py::test_check_runs_the_template_probe_in_the_case_container tests/test_bench_external.py::test_a_template_that_counts_no_tests_is_broken tests/test_bench_external.py::test_a_leaked_gold_patch_is_broken tests/test_bench_external.py::test_a_leak_probe_timeout_is_weak tests/test_bench_external.py::test_gold_must_resolve_and_empty_must_not tests/test_bench_external.py::test_prepare_replaces_broken_cases_from_the_same_stratum tests/test_bench_external.py::test_check_runs_external_cases_in_parallel"
    - "uv run pytest -q tests/test_bench_check.py tests/test_bench_external.py"
  risk: medium

- id: external-evals-t05
  goal: "The `swebench-pro` adapter prepares SWE-bench Pro V2 instances as cases that run in each instance's own image with Pro's instruction, and scores a cell's patch with Pro's authoritative re-grade: Harbor's patch_replay agent on a pristine image"
  spec_refs:
    - "docs/plans/external-evals.md#swe-bench-pro"
    - "docs/plans/external-evals.md#language-templates"
  depends_on:
    - external-evals-t04
  non_goals:
    - "Pro's v1 harness (swe_bench_pro_eval.py), its commercial or held-out sets, or Modal"
    - "Pro's locked agent protocol: the factory's pipeline is the agent"
    - "Changes outside factory/bench/external/swebench_pro.py, its tests and this task's session log"
  acceptance:
    - "The adapter reads `--source` as a JSONL export of `ScaleAI/SWE-bench_Pro`'s default config and the environment variable FACTORY_SWEBENCH_PRO as a checkout of scaleapi/SWE-bench_Pro-os. Each row is an instance whose stratum is its `repo`"
    - "Building a case refuses an instance whose v2/tasks/ID directory is missing from the checkout, or whose environment/Dockerfile `FROM` image isn't the row's `docker_image`. It pulls the image when it's missing. The repository directory is /app when that is a git checkout in the image, else /testbed, else the instance is refused. repo/ holds the files `git ls-files --cached --others --exclude-standard` lists there, as they are in the image's working tree. An instance whose repository already has a .factory/ directory is refused"
    - "repo/.factory/issue.md is the task's instruction.md, unchanged, and repo/.factory/guidance.md is the language template's guidance. case.yaml has kind external, the plan's contract with the instance's language template, `test_paths` from the template, empty `unit_tests` and `dependency_sources`, and a sandbox with the image, `mount` and `seed` at the repository directory, and the template's `path` and `env`"
    - "Each case uses the template from factory/bench/external/templates.py for its row's `repo_language`; a JavaScript or TypeScript instance whose package.json names no supported runner is refused with that reason"
    - "None of the row's `patch`, `test_patch`, `fail_to_pass`, `pass_to_pass` or `selected_test_files_to_run`, nor any file of the task's solution/ or tests/ directories, appears anywhere under the cases directory"
    - "Scoring writes CELL/external/source/instance_1/result.json holding `task_name` (the instance id) and CELL/external/source/instance_1/agent/model.patch, then runs the Harbor executable (FACTORY_HARBOR, default `harbor`) as `run -p TASKS/ID -e docker -n 1 -a patch_replay:PatchReplayAgent -m replay --ak source_job=CELL/external/source --job-name JOB -o CELL/external/jobs`, with PYTHONPATH set to the checkout's v2/tooling and JOB unique to the cell. A reward of 1 at `verifier_result.rewards.reward` in the trial's result.json is resolved, and 0 is unresolved. A non-zero exit, no trial, `exception_info`, or a missing reward is an error, with the detail. The trial's replay.json `apply_rc` goes into the verdict detail"
    - "The adapter is available when FACTORY_SWEBENCH_PRO holds v2/tasks and v2/tooling/patch_replay.py and the Harbor executable runs. Its harness versions are Harbor's version and the checkout's commit. The gold patch for check is the row's `patch`"
    - "Export writes, per variant, the source-job layout patch_replay re-grades: one instance_N directory per sampled instance, with its result.json and agent/model.patch, and an empty patch for instances whose cell didn't end verified"
    - "tests/fake_harbor.py stands in for the Harbor executable: it records its arguments and writes a trial result.json and replay.json from files the test supplies"
    - "docs/sessions/ has this task's session log entry"
  verification:
    - "uv run pytest -q tests/test_external_swebench_pro.py::test_pro_instances_are_stratified_by_repository tests/test_external_swebench_pro.py::test_a_pro_case_runs_in_its_image_with_the_task_instruction tests/test_external_swebench_pro.py::test_the_repository_comes_from_the_images_working_tree tests/test_external_swebench_pro.py::test_a_pro_case_leaves_out_the_fix_and_its_tests tests/test_external_swebench_pro.py::test_js_cases_use_the_repositorys_test_runner tests/test_external_swebench_pro.py::test_pro_is_scored_by_harbor_patch_replay tests/test_external_swebench_pro.py::test_a_failed_harbor_trial_is_an_error tests/test_external_swebench_pro.py::test_pro_export_is_a_patch_replay_source_job"
    - "uv run pytest -q tests/test_bench_external.py"
  risk: medium

- id: external-evals-t06
  goal: "The `patcheval` adapter prepares PatchEval-Verified CVEs as cases that run in each CVE's image with PatchEval's own prompt and its validation files hidden, and scores a cell's patch with PatchEval's run_evaluation.py"
  spec_refs:
    - "docs/plans/external-evals.md#patcheval"
    - "docs/plans/external-evals.md#language-templates"
  depends_on:
    - external-evals-t04
  non_goals:
    - "PoC generation, vulnerability discovery, or any offensive task"
    - "PatchEval's own agent runners (codex, opencode, traecli)"
    - "Changes outside factory/bench/external/patcheval.py, its tests and this task's session log"
  acceptance:
    - "The adapter reads `--source` as PatchEval's dataset file (a JSON list or JSONL with cve_id, cve_description, programming_language, repo, image_url and fix_func), and the environment variables FACTORY_PATCHEVAL as a checkout of bytedance/PatchEval and FACTORY_PATCHEVAL_PYTHON as the interpreter with its requirements (default: the checkout's .venv/bin/python). Each CVE is an instance whose stratum is its programming_language"
    - "Building a case pulls image_url when it's missing. The repository directory is the first git checkout among /workspace/NAME, /workspace/ with NAME lowercased, and /workspace, where NAME is the last part of `repo` without `.git`; with none, the CVE is refused. repo/ holds the files `git ls-files --cached --others --exclude-standard` lists there, as in the image's working tree"
    - "The case's sandbox hides every top-level entry of /workspace other than the repository directory or a directory that contains it, so /workspace/fix.patch and /workspace/fix-run.sh can't be read by the agents"
    - "repo/.factory/issue.md is PatchEval's own prompt opening, `Please fix the vulnerabilities in the code repository based on the following information:`, followed by cve_description and nothing else: no cwe_info, vul_func, fix_func or patch_url. case.yaml has kind external and the plan's contract for a vulnerability, with the CVE's language template from factory/bench/external/templates.py"
    - "Scoring writes CELL/external/patches.jsonl, one line with `cve`, `fix_patch` and `language`, and runs FACTORY_PATCHEVAL_PYTHON `run_evaluation.py --output OUT --patch_file CELL/external/patches.jsonl --input_file SOURCE --max_workers 1` in the checkout's patcheval/evaluation, with OUT unique to the cell. It reads evaluation_output/OUT/summary.json: a CVE listed in `poc_evaluation.successful_cves` is resolved; one listed in `failure_analysis.failed_cves` is unresolved, with its validation type (apply_fail, compilation_fail, validation_fail) as the detail; one in `execution_errors` or absent is an error. The output directory is then moved into CELL/external/"
    - "The adapter is available when FACTORY_PATCHEVAL holds patcheval/evaluation/run_evaluation.py and its interpreter runs. Its harness version is the checkout's commit. The gold patch for check is the image's /workspace/fix.patch, read through a short-lived container, so a CVE whose original fix doesn't pass fix-run.sh fails the check, and the leak probe looks for fix_func's distinctive lines"
    - "Export writes, per variant, one patches.jsonl with a line for every sampled CVE and an empty fix_patch for CVEs whose cell didn't end verified"
    - "tests/fake_patcheval.py stands in for run_evaluation.py: it records its arguments and writes a summary.json from files the test supplies"
    - "docs/sessions/ has this task's session log entry"
  verification:
    - "uv run pytest -q tests/test_external_patcheval.py::test_patcheval_instances_are_stratified_by_language tests/test_external_patcheval.py::test_the_repository_is_found_under_workspace tests/test_external_patcheval.py::test_the_workspace_payload_is_hidden_from_agents tests/test_external_patcheval.py::test_the_issue_is_patchevals_prompt_and_nothing_else tests/test_external_patcheval.py::test_patcheval_scores_from_its_summary tests/test_external_patcheval.py::test_a_patcheval_execution_error_is_an_error tests/test_external_patcheval.py::test_the_gold_for_check_is_the_images_fix_patch tests/test_external_patcheval.py::test_patcheval_export_is_a_patch_file"
    - "uv run pytest -q tests/test_bench_external.py"
  risk: medium

- id: external-evals-t07
  goal: "`factory bench report` and `compare` give each benchmark's resolved rate over every sampled instance, as a leaderboard counts it, with its interval, strata, replaced cases and harness versions, and `factory bench export` writes a run's patches in each benchmark's submission format"
  spec_refs:
    - "docs/plans/external-evals.md#reading-an-external-run"
    - "docs/plans/evals.md#statistics"
  depends_on:
    - external-evals-t04
  non_goals:
    - "Changing how cells run or are scored, or evals' rates for other kinds"
    - "Submitting to a leaderboard"
    - "Editing documentation"
  acceptance:
    - "For a run with external cells, `factory bench report` adds a section per benchmark and variant. It shows resolved k/n, where k is solved cells and n is every cell of the benchmark's cases, so failed, false_pass, stopped, error and skipped cells count as unresolved, with the 95% interval from evals' stats over cases. It also shows k/n per stratum, cost and minutes per instance, how many cases sample.json says were replaced, counted by reason, and the factory version line and harness versions from results.json"
    - "`factory bench compare` adds one line per benchmark and variant pair with the resolved difference, its interval and evals' paired verdict, over the instances both runs have"
    - "`--json` on report and compare carries the same under an `external` key"
    - "`factory bench export RUN [--variant ID ...] --out DIR` writes each external benchmark's submission files for each variant through its adapter's export, and refuses a run with no external cells, with the reason"
    - "docs/sessions/ has this task's session log entry"
  verification:
    - "uv run pytest -q tests/test_bench_external.py::test_report_counts_resolved_over_every_sampled_instance tests/test_bench_external.py::test_report_shows_strata_replacements_and_harness_versions tests/test_bench_external.py::test_compare_gives_a_resolved_verdict_per_benchmark tests/test_bench_external.py::test_export_writes_each_benchmarks_submission tests/test_bench_external.py::test_export_refuses_a_run_without_external_cells"
    - "uv run pytest -q tests/test_bench.py tests/test_bench_stats.py tests/test_bench_external.py"
  risk: medium

- id: external-evals-t08
  goal: "docs/external-evals.md takes a reader from an empty machine to an exported, re-graded external run, and docs/architecture.md, docs/reference.md, NEXT.md and the factory-ops skill describe external suites and the Docker sandbox"
  spec_refs:
    - "docs/plans/external-evals.md#the-runbook"
    - "docs/architecture.md#evaluating-flows-factory-bench"
  depends_on:
    - external-evals-t05
    - external-evals-t06
    - external-evals-t07
    - evals-t08
  non_goals:
    - "Changing code, or tests beyond the new docs test and what tests/test_templates.py needs for the new template text"
    - "Rewriting sections unrelated to this plan, or editing README.md"
  acceptance:
    - "New docs/external-evals.md covers, in order: what each suite measures and why these were chosen (Verified's contamination; offensive tasks out of scope); installing Harbor 0.27.0 with `uv tool install harbor==0.27.0`; cloning SWE-bench_Pro-os and PatchEval and recording their commits; writing Pro's default config to JSONL; FACTORY_HARBOR, FACTORY_SWEBENCH_PRO, FACTORY_PATCHEVAL and FACTORY_PATCHEVAL_PYTHON; disk needs; the prepare, check and prepare-again loop; a dry run; the run with --max-cost; report; export, and re-grading an export with each benchmark's own tools; removing the sample's images; and what the numbers can and can't be compared with"
    - "docs/architecture.md's Evaluating flows section describes external cases, adapters, official scoring, the Docker sandbox and the external check, and links docs/external-evals.md. docs/reference.md covers `factory bench prepare` and `export` with every option, the `external` kind and case key, the sandbox keys `image`, `mount` and `seed`, the four environment variables, and troubleshooting rows for a missing image, an unavailable scorer, a broken template and a leak"
    - "NEXT.md marks item 21 done, linking docs/external-evals.md"
    - "factory/templates/skills/factory-ops/SKILL.md covers preparing, checking, running and exporting an external suite, and the changed template files are copied to .claude/skills/factory-ops/, so tests/test_templates.py passes"
    - "tests/test_external_docs.py checks that docs/external-evals.md names every option of `factory bench prepare` and `factory bench export`, read from the CLI's argument parser, and that docs/reference.md names the sandbox keys image, mount and seed"
    - "docs/sessions/ has this task's session log entry"
  verification:
    - "uv run pytest -q tests/test_external_docs.py::test_the_runbook_names_every_prepare_and_export_option tests/test_external_docs.py::test_the_reference_names_the_docker_sandbox_keys"
    - "uv run pytest -q tests/test_templates.py"
    - "grep -q 'docs/external-evals.md' NEXT.md"
  risk: low

- id: external-evals-t09
  goal: "docs/external-evals-results.md records the first measurement: the factory's strict flow on 50 SWE-bench Pro instances and 40 PatchEval CVEs, as resolved out of each with its interval, cost and time, the run id, seeds and factory version line it came from, and the benchmarks' own re-grade of the exported patches"
  spec_refs:
    - "docs/plans/external-evals.md#the-measurements"
  depends_on:
    - external-evals-t08
  non_goals:
    - "Changing any code, prompt, flow or model to raise the score"
    - "Comparing flows or models: one run of the configured strict flow"
  acceptance:
    - "Both suites are prepared and checked as the runbook says, and every case left is ok or weak. The run's ledger note names it the external baseline"
    - "docs/external-evals-results.md holds the report's external section for the run, the date, the run id, each suite's source sha256 and seed from sample.json, the replaced cases by reason, the factory version line, the harness versions, the total cost, and each case the check marked weak"
    - "The run's export, re-graded with each benchmark's own tools as the runbook says, gives the same resolved count as the report, or the doc lists every instance where they differ, with the reason"
    - "It says in words what the numbers can and can't be compared with, as the plan's measurements section lists"
    - "docs/sessions/ has this task's session log entry"
  verification:
    - "factory bench ledger"
    - "grep -q 'resolved' docs/external-evals-results.md"
    - "grep -q 'PatchEval' docs/external-evals-results.md"
    - "grep -Eq 'factory[[:space:]][0-9]' docs/external-evals-results.md"
  risk: low

- id: external-evals-t10
  goal: "docs/external-evals-results.md records whether the secure flow beats strict on each suite: secure's resolved rate on the same sampled cases, with evals' paired verdict against t09's strict cells"
  spec_refs:
    - "docs/plans/external-evals.md#the-measurements"
  depends_on:
    - external-evals-t09
    - security-review-t06
  non_goals:
    - "Changing any code, prompt, flow or model"
    - "Changing the default flow: the result informs that decision, it doesn't make it"
  acceptance:
    - "A run of the built-in secure flow on both suites, with `--baseline` set to t09's run so strict's cells are reused, has finished or reached its budget, and its ledger note names the comparison"
    - "docs/external-evals-results.md gains a section headed with the run's date. Per suite, it gives secure's resolved k/n with its interval, the compare line against strict with its verdict for resolved and for cost, the cells where the security step sent a build back, and the false passes of each flow"
    - "docs/sessions/ has this task's session log entry"
  verification:
    - "factory bench ledger"
    - "grep -q 'secure' docs/external-evals-results.md"
    - "grep -Eq '(better|worse|inconclusive)' docs/external-evals-results.md"
  risk: low
```

Planned test additions:

| Task | Tests | Kind |
|---|---|---|
| t01 | `tests/fake_docker.py` (new); `tests/test_sandbox_docker.py` (new): ten tests named in its verification | unit, through the fake docker CLI |
| t02 | `tests/test_verification.py`: five tests | unit |
| t03 | `tests/external_toy.py` (new toy adapter); `tests/test_bench_external.py` (new): twelve tests | CLI end to end, scripted models |
| t04 | `tests/test_bench_external.py`: eight tests | unit, CLI end to end |
| t05 | `tests/fake_harbor.py` (new); `tests/test_external_swebench_pro.py` (new): eight tests | unit, CLI end to end |
| t06 | `tests/fake_patcheval.py` (new); `tests/test_external_patcheval.py` (new): eight tests | unit, CLI end to end |
| t07 | `tests/test_bench_external.py`: five tests | CLI end to end |
| t08 | `tests/test_external_docs.py` (new): two tests | docs against the CLI's parser |
| t09, t10 | none: by hand | — |

Every verification command names tests the task adds, or a test file that exists when it runs, so a filter that selects nothing fails. No test needs Docker, the network, Harbor or PatchEval: `tests/fake_docker.py`, `tests/fake_harbor.py` and `tests/fake_patcheval.py` stand in for them, and the bench tests run cells with scripted models (`tests/fake_model.py`), as `tests/test_bench.py` does. Each of t01–t08 is factory-runnable on this repository under `strict`: its first verification command names only new tests, which fail before the change.

**t09 and t10 are done by hand.** They need the network (datasets, images, the scorers' own setup) and spend a model budget. Their verification runs `factory bench ledger`, which the factory refuses, so `factory run` refuses them and `factory run external-evals` lists them as manual.

Prerequisite for `external-evals-t03`: the [evals](evals.md) plan, in open PR #85, merged to `main`, and `evals-t07` merged. Until #85 merges, `factory sync` can't resolve this plan's `evals-t07` and `evals-t08` dependencies, so merge #85 before this plan's PR.

Prerequisite for `external-evals-t09`: Harbor 0.27.0, a SWE-bench_Pro-os checkout and a PatchEval checkout with its requirements installed (all need the network, so they're installed by hand on the host); a budget of up to $400 agreed; and about 250 GB of free disk for the sampled images.

Prerequisite for `external-evals-t10`: `security-review-t06` merged, so the built-in `secure` flow exists; a budget of up to $400 agreed.

### Risks

1. **The fix leaks to the agents.** Pro images keep a git history, PatchEval images keep the original fix at `/workspace/fix.patch`, and the datasets hold the gold patches. **Action:** the worktree is mounted over the image's repository, so the image's checkout and its `.git` are hidden. The cell's repository has one commit. PatchEval's `/workspace` payload is overlaid. Datasets and scorer checkouts stay on the host, where the container can't see them. t04's leak probe greps every case's container for the gold patch's lines before the case is used.
2. **The factory's environment differs from the scorer's.** Agents run as the host user on a read-only root, offline, with HOME=/tmp, while the scorers run as the image's user and Pro's verifier can fetch Go modules. Some tests may then behave differently for the agents. **Action:** t04's template probe runs every case's test command in the factory's own sandbox before a run. A case that fails it is replaced in its stratum, and the report says how many were replaced and why. The score itself always comes from the official scorer.
3. **Replacing cases biases the sample.** If whole repositories or languages fail the check, the sample stops representing the benchmark. **Action:** replacements stay within their stratum, an exhausted stratum is reported, not silently filled from others, and sample.json and the report list every replaced instance with its reason.
4. **The number is compared with the wrong thing.** The factory isn't Pro's locked protocol, it submits only candidates its gates verified, and 50 instances give about ±13 points. **Action:** report divides by every sampled instance, as leaderboards do, and shows the interval and the strata. The results doc says what the number compares with. t09 re-grades the export with the benchmarks' own tools.
5. **Cost.** Pro tasks change about 100 lines across about 4 files, much larger than this board's tasks (an average of $1.77). **Action:** a dry run first, `--max-cost 400`, and `--baseline` in t10, so strict's cells aren't paid for twice. A spent budget leaves the rest `skipped`, which counts as unresolved and is shown.
6. **Disk and time.** About 250 GB of images, scorer runs of several minutes each, and seeded `node_modules` copied into every JavaScript cell. **Action:** prepare prints the images' total size. `check --parallel` runs checks side by side. The runbook removes the sample's images using the list in sample.json.
7. **Harbor and PatchEval output formats change.** The scorers read `verifier_result.rewards.reward` (Harbor 0.27.0) and `summary.json`'s `successful_cves` (PatchEval at its recorded commit). **Action:** the runbook pins both. t04's scorer check (gold resolves, empty doesn't) fails loudly on a format change, and results.json records the harness versions.
8. **Docker is root-equivalent on the host.** **Action:** only the factory's own process calls docker. Agents' commands run inside containers with no network, every capability dropped, no-new-privileges, a read-only root and the host user's ids. The Docker socket is never mounted, and scorers run without secret-shaped environment variables.
9. **This plan collides with evals and web-tools in `factory/bench/`.** **Action:** t03 waits for `evals-t07`. `web-tools-t04` also changes bench fingerprints after `evals-t07`, so whichever lands second rebases. The factory's conflict rework handles it, and the coordination section names the overlap.

---

## Problem

Nothing measures the factory against an outside reference, or on security work:

- **The shipped bench suite is saturated.** Run `20261116-220919` solved 60 of 60 cells across four variants. Evals ([PR #85](https://github.com/PaddyMc/software-factory/pull/85)) adds mined cases from this repository and statistics that can rank flows, but it locked "no external benchmark is imported", so its numbers say how the factory does on its own code only.
- **The SWE reference the factory planned on is retired.** The `experiment/swe-bench` plan targets SWE-bench Verified. OpenAI stopped reporting Verified in February 2026: it's contaminated, and at least 59.4% of its audited hard problems have flawed tests. SWE-bench Pro is the recommended replacement, and it's multi-language: 642 public V2 tasks in Go, Python, JavaScript and TypeScript.
- **Nothing measures security.** [security-review](security-review.md) adds a `secure` flow, a security reviewer and two gates, but no suite says whether the factory fixes vulnerabilities, or whether `secure` helps it do so.
- **The bench can't run real repositories.** Cases run under bubblewrap with host paths bound in place (`factory/sandbox.py:45`), so a repository needing its own toolchain and pinned dependencies has no environment. A case must have hidden tests and a solution (`factory/bench/cases.py:137`), and scoring lays them over the candidate (`factory/bench/cases.py:182`, `factory/bench/run.py:370`), while external benchmarks score with their own harnesses.
- **Go and JavaScript tests don't count as tests.** `verification.is_test_command` (`factory/verification.py:41`) knows pytest, cargo and unittest only. So the strict flow's red check can't run on Go or JavaScript repositories, and a Go or jest run that selects nothing would pass.

## Goal

`factory bench prepare swebench-pro` and `factory bench prepare patcheval` each write a checked, seeded sample of cases. `factory bench run --cases DIR` runs the factory's flows on them in each instance's own image, and `factory bench report` gives each benchmark's resolved rate, as the official scorer judges it, out of every sampled instance with an interval. The first measurement of strict, and of secure against strict, is recorded in `docs/external-evals-results.md`.

## Design

```text
dataset file (by hand) ──► factory bench prepare BENCHMARK ──► DIR/CASE/{case.yaml, repo/}   DIR/sample.json   DIR/suite.yaml
                              │ adapter: instances, strata, build (image pulled; repo/ from the image's working tree)
                              ▼
                           factory bench check --cases DIR ──► template probe · leak probe · gold resolves, empty doesn't
                              │ broken ─► prepare again refills the stratum
                              ▼
factory bench run --cases DIR --flow strict --max-cost 400 --parallel 4
   cell: materialize repo/ ─► Pipeline (test → build → gates → review → verify)
            every agent command and gate: docker exec in the instance's image, worktree over the repository
            verified ─► patch.diff ─► adapter.score (official scorer, on the host) ─► resolved? solved : false_pass
            failed / stopped / error ─► not scored
                              ▼
results.json ──► factory bench report ──► resolved k/n per benchmark, interval, strata, replacements
             └─► factory bench export ──► Pro: patch_replay source job · PatchEval: patches.jsonl
```

### A Docker sandbox

The bench cell already builds its sandbox from the case's config (`factory/bench/run.py`), and the pipeline, gates and agent tools only call `.run(cmd)` on it. A third class beside `Bwrap` and `Unsandboxed` slots in there, and works for `factory run` on any project whose config sets an image:

```yaml
sandbox:
  image: ghcr.io/scaleapi/swe-bench_pro-v2:instance_nodebb__nodebb-04998908…   # the instance's image
  mount: /app          # the worktree is mounted here too, where the image's tooling expects the repository
  seed: /app           # copy the image's git-ignored files first (node_modules, built extensions, generated files)
  hide: []             # absolute paths inside the image to overlay (PatchEval: its /workspace payload)
  path: []
  env: {}
```

- **One container per sandbox,** started on the first `run` and removed by `close()` or at exit. Commands run with `docker exec` in the worktree at its host path, so file tools and commands agree on paths. The same files are also at `mount`, so the image's editable installs and configs that name the repository's path still work.
- **Isolation:** `--network none`, `--read-only` with a writable `/tmp`, `--cap-drop ALL`, `--security-opt no-new-privileges`, and the host's uid and gid, so files written in the worktree belong to the user. Only the worktree and its git dirs are mounted, the same set Bwrap binds writable.
- **Seeding:** mounting the worktree over the repository hides the image's ignored files, which are dependencies, built extensions and generated files. So before the container starts, a short-lived container copies them into the worktree. Ignored files never show in a diff, so the candidate stays clean.
- **Timeouts:** the command runs under coreutils `timeout` inside the container, so it doesn't outlive a timeout that only killed `docker exec`.

### Go and JavaScript test runners

| Runner | Recognized when the command runs | Count | Zero |
|---|---|---|---|
| go test | `go test` | `--- PASS:`, `--- FAIL:`, `--- SKIP:` lines under `-v` | every package `[no tests to run]`, or `testing: warning: no tests to run` with no result lines |
| jest | `jest` (also via npx, yarn, pnpm) | the `Tests:` line's total | `No tests found` |
| mocha | `mocha` | `N passing` + `N failing` + `N pending` | `0 passing`, nothing failing |
| vitest | `vitest` | the `Tests` line's total in parentheses | `No test files found` |

For these runners a counted zero is inconclusive whatever the exit code. jest exits 1 when it finds nothing, and that is not a failing test. This is useful beyond the bench: any Go or JavaScript repository on the strict flow needs it.

### External cases

An adapter is a module in `factory/bench/external/` that provides:

| Name | What it does |
|---|---|
| `NAME`, `PREFIX` | The benchmark's name (`swebench-pro`) and its case-id prefix (`pro`) |
| `instances(source)` | The dataset's instances, each with an id and a stratum |
| `build(instance, source, case_dir, docker)` | Writes one case: `case.yaml` and `repo/`. It raises a refusal with a reason for an instance it can't use |
| `available(env)` | None when the scorer can run, else the reason it can't |
| `versions(env)` | The harness versions to record |
| `score(case, patch, out_dir, env)` | The verdict (`resolved`, `unresolved` or `error`) with its detail and log tail |
| `gold(case)`, `probe_lines(case)` | The gold patch for check, and the lines the leak probe searches for |
| `export(case_cells, out_dir)` | One variant's submission files |

A prepared case, for Pro:

```yaml
title: "NodeBB/NodeBB: instance_nodebb__nodebb-0499…"
kind: external
requires: [git]
external: {benchmark: swebench-pro, instance: "instance_nodebb__nodebb-0499…", stratum: NodeBB/NodeBB,
           image: "ghcr.io/scaleapi/swe-bench_pro-v2:instance_nodebb__nodebb-0499…", source: /abs/pro-v2.jsonl}
config:
  test_paths: ["test/factory_issue.test.js"]
  unit_tests: []                      # no suite gate: the full suite is slow, and naming tests leaks hints
  guidance: [".factory/guidance.md"]
  dependency_sources: []
  sandbox: {image: "…", mount: /app, seed: /app, path: [], env: {}}
contract:
  id: pro-instance-nodebb-nodebb-0499…-t01
  goal: "Make the change .factory/issue.md asks for (NodeBB/NodeBB), with a test that shows it"
  spec_refs: [".factory/issue.md"]
  depends_on: []
  non_goals: ["Changing behaviour the issue doesn't ask to change", "Editing or deleting existing tests to make them pass"]
  acceptance:
    - "The behaviour .factory/issue.md asks for is implemented, including every requirement and interface it lists"
    - "test/factory_issue.test.js has a test that fails on the base commit and passes with the change"
    - "Existing tests of the code you changed still pass"
  verification: ["npx mocha test/factory_issue.test.js"]
  risk: medium
hidden: []
```

- **The issue goes in a file, not the contract.** Problem statements contain `TODO` and `<FOO>`-style text, which contract validation rejects as placeholders. `.factory/issue.md` is in the base commit, listed in `spec_refs` and named in the goal, and the tester and planner prompts read spec references.
- **A PatchEval contract** has the goal "Fix the vulnerability .factory/issue.md describes (CVE-ID), with a test that reproduces it". Its acceptance says the vulnerable behaviour is fixed without changing other behaviour, and that the template's test fails on the base and passes with the fix.
- **Case ids** are the adapter's prefix, a hyphen, and the instance id lowercased with each run of characters outside `[a-z0-9]` turned into one hyphen. An id longer than 64 characters keeps its first 55 characters plus a hyphen and the first 8 hex digits of the instance id's sha256.
- The base commit adds `.factory/` and `docs/plans/CASE.md`. The scored patch leaves both out.

### The sample

Each stratum gets its largest-remainder share of `--count`. Within a stratum, the order is the sorted instance ids shuffled by `random.Random(f"{seed}:{stratum}")`. Prepare walks that order until the stratum's share is built, skipping instances the adapter refuses or a check marked broken. Pro is stratified by repository (50 of 642, so about 4–5 per repository) and PatchEval by language (40 of 230 across Go, JavaScript and Python). `--instances` builds exact ids instead, for trying one. sample.json records what was picked and skipped, so a later run can use the same cases.

### Scoring

| Pipeline ends | Scorer says | Cell outcome |
|---|---|---|
| `verified` | resolved | `solved` |
| `verified` | unresolved | `false_pass`: the factory's gates passed a patch the benchmark rejects |
| `verified` | error, timeout, no verdict | `error` |
| `failed`, cost limit, exception, budget spent | not run | `failed`, `stopped`, `error`, `skipped`, as today |

The patch is `git diff --binary BASE CANDIDATE -- . ':!.factory' ':!docs/plans/CASE.md'`. Both scorers apply it in a fresh container of the instance's image and run their own tests. Tests the agents wrote may or may not run there, and they never decide the verdict.

### Checking an external case

| Check | Expect | Else |
|---|---|---|
| Template probe: the passing probe at the test path, then the failing probe, through the contract's verification in the case's sandbox | pass with ≥ 1 test, then fail | `broken: template` |
| Leak probe: `grep -rIlF` for up to five distinctive gold lines over the container's filesystem (not /proc, /sys, /dev or the worktree) | no hit | `broken: leak PATH`; past 300 s, `weak` |
| Scorer: the gold patch, then an empty patch | resolved, then not resolved | `broken: scorer` |

### Language templates

| Language | Test the agents add | Verification | `test_paths` |
|---|---|---|---|
| Python | `test_factory_issue.py` at the repository root | `python -m pytest -rA test_factory_issue.py` | `test_factory_issue.py` |
| Go | `factory_issue_test.go` in the package the change touches, with test names starting `TestFactoryIssue` | `go test -v -run '^TestFactoryIssue' ./...` | `**/factory_issue_test.go` |
| JavaScript, TypeScript | `test/factory_issue.test.js` | `npx jest --ci test/factory_issue.test.js`, `npx mocha test/factory_issue.test.js` or `npx vitest run test/factory_issue.test.js`, by the runner package.json names first | `test/factory_issue.test.js` |

Each template's guidance tells every agent what an agent harness usually says: the environment is installed and offline, the repository is also at `mount`, how to run the test, and where it goes. The probes are a one-line passing test and a one-line failing test for each runner.

### SWE-bench Pro

- **Inputs:** a JSONL export of `ScaleAI/SWE-bench_Pro`'s default config (`--source`) and a checkout of `scaleapi/SWE-bench_Pro-os` (FACTORY_SWEBENCH_PRO), whose `v2/tasks/ID/` are Harbor tasks with `instruction.md`, `environment/Dockerfile` (`FROM ghcr.io/scaleapi/swe-bench_pro-v2:ID`), `solution/` and `tests/`.
- **What agents see:** the task's `instruction.md` (the PR description, requirements and new interfaces, as Pro shows its agents), and the repository at `/app`, or `/testbed` for a few tasks.
- **Scoring is Pro's authoritative re-grade.** Its README says "fresh-sandbox re-grade = reported score", run as the `patch_replay` agent over a source job. The factory writes a one-instance source job and runs Harbor locally:

```text
CELL/external/source/instance_1/result.json        {"task_name": "ID"}
CELL/external/source/instance_1/agent/model.patch   the scored patch
PYTHONPATH=$FACTORY_SWEBENCH_PRO/v2/tooling $FACTORY_HARBOR run -p $FACTORY_SWEBENCH_PRO/v2/tasks/ID -e docker -n 1 \
    -a patch_replay:PatchReplayAgent -m replay --ak source_job=CELL/external/source \
    --job-name bench-RUN-CELL -o CELL/external/jobs
CELL/external/jobs/bench-RUN-CELL/TRIAL/result.json  verifier_result.rewards.reward: 1 resolved, 0 unresolved
```

### PatchEval

- **Inputs:** PatchEval's dataset file (`--source`), a checkout of `bytedance/PatchEval` (FACTORY_PATCHEVAL) and its interpreter (FACTORY_PATCHEVAL_PYTHON).
- **What agents see:** PatchEval's own prompt, which is its opening line plus `cve_description` and nothing more, and the repository at `/workspace/NAME`. Its own runner deletes the rest of `/workspace` before the agent starts. The factory overlays it instead, since the image's `/workspace/fix.patch` is the original fix and `fix-run.sh` is the validation.
- **Scoring:** `run_evaluation.py --output OUT --patch_file CELL/external/patches.jsonl --input_file SOURCE --max_workers 1`, which runs `cd /workspace && bash fix-run.sh` with the patch at `/workspace/fix.patch`; exit 0 passes. The verdict comes from `evaluation_output/OUT/summary.json`: `poc_evaluation.successful_cves` resolved, `failure_analysis.failed_cves` unresolved, `execution_errors` error.
- **Gold for check:** the image's own `/workspace/fix.patch`. PatchEval warns that with its strengthened PoCs some original fixes fail `fix-run.sh`. Those CVEs fail the check and are replaced, so every case left is one whose original fix passes.

### Reading an external run

```text
external · swebench-pro · strict     resolved 17/50  34% [22–47]   $3.90/instance  14.2 min/instance
                                     NodeBB/NodeBB 2/5 · ansible/ansible 1/4 · …
                                     replaced 6 (template 4, leak 0, scorer 2) · harbor 0.27.0 · SWE-bench_Pro-os 1a2b3c4
external · patcheval · strict        resolved 22/40  55% [40–70]   $1.20/instance   6.1 min/instance
                                     Go 8/13 · JavaScript 7/13 · Python 7/14
                                     replaced 9 (template 3, scorer 6) · PatchEval 5d6e7f8
```

(The numbers are illustrative.) The denominator is every cell of the benchmark's cases, so the rate is comparable in method with a leaderboard's, though not with Pro's locked protocol.

### The runbook

`docs/external-evals.md` (t08) is the path a reader follows: install Harbor 0.27.0 and the two checkouts, export the datasets, prepare, check and prepare again until stable, dry run, run, report, export and re-grade, clean up images.

### The measurements

- **t09:** `strict`, the repository's configured flow and models, once, on both suites, with `--max-cost 400`. The results doc says what the numbers compare with. Pro's leaderboard numbers come from a locked single-agent protocol on all 642 tasks, so a factory number is a pipeline on a 50-instance sample, scored the same way. Only verified candidates are submitted, so a stopped factory scores zero where a leaderboard agent would still submit its diff.
- **t10:** `secure` on the same cases with `--baseline` set to t09's run, and the compare line per suite. The question it answers: does the security step raise PatchEval's resolved rate, or cut its false passes, without lowering Pro's?

## Files Changed

| File | Change |
|---|---|
| `factory/sandbox.py` | `Docker` sandbox; `make` selects it for a config with `image` (t01) |
| `factory/config.py` | `image`, `mount`, `seed` in `SandboxConfig`, and validation (t01) |
| `factory/verification.py` | go test, jest, mocha, vitest (t02) |
| `factory/bench/external/__init__.py` | New: adapter interface, registry, sample, scoring, probes (t03, t04) |
| `factory/bench/external/templates.py` | New: language templates and probes (t04) |
| `factory/bench/external/swebench_pro.py` | New: the Pro adapter (t05) |
| `factory/bench/external/patcheval.py` | New: the PatchEval adapter (t06) |
| `factory/bench/cases.py` | Kind `external` and its key (t03) |
| `factory/bench/run.py` | External scoring, preflight, container cleanup, version records (t03) |
| `factory/bench/check.py` | External checks (t04) |
| `factory/bench/report.py` | External section and export (t07) |
| `factory/cli.py` | `bench prepare` (t03), `check --parallel` (t04), `bench export` (t07) |
| `tests/fake_docker.py`, `tests/fake_harbor.py`, `tests/fake_patcheval.py`, `tests/external_toy.py` | New test doubles (t01, t05, t06, t03) |
| `tests/test_sandbox_docker.py`, `tests/test_bench_external.py`, `tests/test_external_swebench_pro.py`, `tests/test_external_patcheval.py`, `tests/test_external_docs.py` | New tests |
| `tests/test_verification.py` | New tests (t02) |
| `docs/external-evals.md` | New: the runbook (t08) |
| `docs/architecture.md`, `docs/reference.md`, `NEXT.md`, factory-ops skill (template and copy) | t08 |
| `docs/external-evals-results.md` | New: the measurements (t09, t10, by hand) |

## Test Plan

### Unit tests

- `tests/test_sandbox_docker.py` (t01), through `tests/fake_docker.py`: config selection and validation; the `docker run` flags (no network, host user, dropped capabilities, read-only root, label); exactly the worktree and its git dirs mounted, plus hidden overlays; exec with the config's PATH and env; timeouts inside the container; seeding without overwriting; close idempotent; a missing docker or image refused.
- `tests/test_verification.py` (t02): recognition of the four runners, counts from real output samples, and zero counts that are inconclusive.

### End-to-end tests

Through `factory bench` with scripted models, the fake docker CLI and fake scorers:

- t03: prepare's sample, refusals and refill, idempotence; a verified cell scored solved, false_pass or error; the scored patch's exclusions; scorers without secrets; preflight refusals; containers removed; version records.
- t04: the JavaScript runner choice, the template probe, a template that counts nothing, a leak, a leak-probe timeout, gold and empty, refill after a broken check, parallel checks.
- t05 and t06: each adapter's instances, case building, hiding, issue text, scoring from its harness's real output format, errors and export.
- t07: resolved over every sampled instance, strata, replacements and versions in report; the compare verdict; export.
- t08: the runbook and reference against the CLI's own parser.

## Verification

- Each task's verification commands, and `uv run pytest -q` passing at each merge.
- By hand after t08: `factory bench prepare swebench-pro --source pro-v2.jsonl --out ~/suites/pro --count 50 --seed 1`, then `factory bench check --cases ~/suites/pro --parallel 4`, then prepare again until no case is broken. The same for `patcheval` with `--count 40`.
- By hand: `factory bench run --cases ~/suites/pro --cases ~/suites/patcheval --dry-run` lists 90 cells. t09's run and its re-grade then confirm the scorer path end to end.

## Cross-Workstream Coordination

- **Depends on:**
  - [evals](evals.md) (open PR #85). `external-evals-t03` depends on `evals-t07`, its last code task, and `external-evals-t08` on `evals-t08`, its docs task. External cases use evals' check verdicts and `--json` (t03 of evals), suite.yaml and splits (t04, t06), statistics and paired verdicts (t01), `--baseline` (t06) and the ledger (t07). This plan reverses evals' locked "no external benchmark is imported" for these two suites only. Its mined and synthetic suites are unchanged. The reverse link belongs in evals.md's coordination section, on #85.
  - [security-review](security-review.md). The by-hand `external-evals-t10` depends on `security-review-t06`, which ships the built-in `secure` flow.
  - [bench](bench.md), merged. External cases are bench cases with one new kind. The cell, the run directory and results.json keep their shape.
  - [strict-flow](strict-flow.md), merged. The language templates give the test step a test command that fails first, and t02 lets it count Go and JavaScript runs.
- **Required by:** none yet.
- **Overlaps without ordering:** `web-tools-t04` (in #85) also changes `factory/bench/run.py` after `evals-t07`, so whichever lands second rebases. `flow-tuning` and `security-review-t02` change `factory/config.py` beside t01. The factory's conflict rework handles these.
- **Supersedes:** the `experiment/swe-bench` plan (PR #83 into that branch). None of its tasks was built. Its Docker sandbox design is t01 here, its harness scoring became adapters, and its Verified target is dropped. The branch can be deleted once this plan merges.

## Notes / Out of Scope

- **Offensive security benchmarks:** Cybench and other CTFs, CyberGym and SEC-bench PoC generation, CVE-Bench and BountyBench exploitation. The factory's output is a PR, and these need networked targets and a non-PR output path. If the factory gains a security-audit crew, CyberGym-E2E's discovery track is the natural next suite.
- **Secure feature work:** BaxBench, SecRepoBench and SecureAgentBench, which ask whether a feature the factory builds ships a vulnerability. This is the next cyber suite once t10 says whether `secure` matters. It needs an adapter whose scorer runs the benchmark's security tests alongside its functional ones.
- **More SWE suites:** SWE-rebench (fresh monthly, decontaminated, Python), Multi-SWE-bench, and Pro's held-out set. Each is one adapter beside the two here. Terminal-Bench 2.x is a poor fit, because its result is a container's state, not a diff.
- **Harbor or Inspect as the driver:** not taken. Adapters keep the factory's own worktrees and gates. Harbor stays the scorer for Pro.
- **Leaderboard submission:** export writes each benchmark's format, but submitting is a human's call and outside this plan.
- **Full public sets** (642 Pro, 230 PatchEval): the same commands with a larger `--count` and budget, once the sample's numbers justify it.
