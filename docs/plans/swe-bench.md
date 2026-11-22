# Plan: Measure the factory on SWE-bench Verified

**Status:** Planned (2026-11-18). Workstream scoped; awaiting kickoff: t01 can start now. This plan lives on the `experiment/swe-bench` branch only and never merges into `main`. Roadmap: none, by decision: nothing in this workstream goes to `main`, so `NEXT.md` is unchanged.

---

## Execution Plan

### Locked Decisions

| Decision | Choice |
|---|---|
| Where it lives | **A long-lived `experiment/swe-bench` branch, never merged into `main`.** It tests the factory; it doesn't change it. Every task is a PR into that branch |
| Environment and scoring | **SWE-bench's own Docker images, scored by the official harness.** Agents' commands and the gates run in the instance's image with no network. A verified candidate's patch is scored by `swebench.harness.run_evaluation`. The environments and the scorer are the ones published numbers use |
| Instances | **50 instances of SWE-bench Verified: a seeded sample, stratified by repository.** The sample's ids, seed and dataset hash are recorded. At about $1–3 a cell, one flow costs about $50–150 |
| Who builds it | **By hand, in PRs into the branch.** The tasks never go on the board, and nothing here is run with `factory run`. Network steps (the dataset, the images, the harness) are manual anyway |
| Keeping up with `main` | **Merge `origin/main` into the branch before each run.** The branch's changes stay additive: new modules plus small hooks in existing ones, and no `factory/cli.py`, `NEXT.md` or shared docs. Each run records the factory version line (`factory --version`), so the result names the commit it measured |

### Milestones

| # | Deliverable | Exit criteria | Parallelizable with |
|---|---|---|---|
| **M1** | A Docker sandbox | `tests/test_sandbox_docker.py` passes. By hand: a sandbox on a SWE-bench image runs `python -c 'import django'` from a worktree, and the container is gone afterwards | — |
| **M2** | SWE-bench cases | The prepare tests in `tests/test_swebench.py` and `test_django_runtests_and_sympy_bin_test_are_test_commands` pass. By hand: `prepare` writes 50 cases from Verified, and `factory bench cases --cases DIR` lists all 50 | — |
| **M3** | Official scoring | The scoring and check tests pass. By hand: the gold patches of two sampled instances score `resolved` through the scorer, an empty patch doesn't, and `check` passes for every sampled case or names the ones whose environment doesn't reproduce | — |
| **M4** | Summary and runbook | The summary tests pass, and `docs/swe-bench.md` takes a reader from an empty machine to a summary | — |
| **M5** | The first measurement | `docs/swe-bench-results.md` gives strict's resolved count out of 50 with its interval, cost, run id and factory version line | — |

**Sequence:** `M1 → M2 → M3 → M4 → M5`.

### Task Contracts

| Milestone | Task IDs | Coverage |
|---|---|---|
| **M1** | `swe-bench-t01` | `Docker` in `factory/sandbox.py`; `image`, `mount` and `seed` in `SandboxConfig` (`factory/config.py`); bench preflight and cell cleanup for Docker cases (`factory/bench/run.py`); new `tests/fake_docker.py` and `tests/test_sandbox_docker.py` |
| **M2** | `swe-bench-t02` | New `factory/bench/swebench.py` with `prepare`; the optional `swebench` case key (`factory/bench/cases.py`); `runtests.py` and `bin/test` as test commands (`factory/verification.py`); new `tests/test_swebench.py` and `tests/fake_swebench.py`; a test in `tests/test_verification.py` |
| **M3** | `swe-bench-t03` | Scoring verified cells with the harness, and `check`, in `factory/bench/swebench.py`; the scoring hook and the version line in `factory/bench/run.py`; tests in `tests/test_swebench.py` |
| **M4** | `swe-bench-t04` | `summary` and the predictions files in `factory/bench/swebench.py`; new `docs/swe-bench.md`; tests in `tests/test_swebench.py` |
| **M5** | `swe-bench-t05` | The first 50-instance run on `strict`, and new `docs/swe-bench-results.md` |

```yaml
- id: swe-bench-t01
  goal: "A sandbox config with an `image` runs every agent command and gate in a Docker container of that image, with the worktree mounted, no network and the host user's ids, and bench cells remove their containers"
  spec_refs:
    - "docs/plans/swe-bench.md#a-docker-sandbox"
    - "factory/sandbox.py"
  depends_on: []
  non_goals:
    - "Changing Bwrap or the behaviour of any config without `image`"
    - "Changing factory/cli.py, factory/pipeline.py, factory/gates.py or factory/agents.py"
    - "Anything SWE-bench specific: datasets, image names, scoring (swe-bench-t02, swe-bench-t03)"
    - "Pulling images: a missing image is refused, never fetched"
  acceptance:
    - "SandboxConfig gains `image` (a Docker image), `mount` (an absolute path where the worktree is also mounted inside the container) and `seed` (an absolute path inside the image whose git-ignored files are copied into the worktree when the container starts), all defaulting to none. config.parse rejects a relative `mount` or `seed`, and `mount` or `seed` without `image`"
    - "sandbox.make returns a Docker sandbox whenever the config has an `image`, with or without --no-sandbox, and a Bwrap or Unsandboxed one exactly as before otherwise"
    - "The first run starts one container per sandbox: `docker run -d` with `--network none` unless the sandbox has network, `--read-only`, a writable /tmp tmpfs, `--user` set to the host uid and gid, `--cap-drop ALL`, `--security-opt no-new-privileges`, a `factory.sandbox` label holding the worktree path, and bind mounts of the worktree at its own path and at `mount`, the git common dir read-only and the worktree's git admin dir writable. Nothing else from the host is mounted, and the Docker socket never is"
    - "Each run is `docker exec` in the worktree directory with HOME=/tmp, PATH from the config's `path` ahead of the image's PATH, the config's `env`, and the command under coreutils `timeout`, so a timed-out command is stopped inside the container and returns the same timeout Result as Bwrap"
    - "With `seed`, the container start first copies the image's git-ignored files under `seed`, leaving out `build/` and `__pycache__` directories, into the worktree without overwriting files the worktree already has"
    - "close() removes the container and can be called twice; containers still open at interpreter exit are removed. A bench cell closes the sandboxes it made for the pipeline and for hidden scoring, whether the cell succeeds, fails or raises"
    - "Bench preflight checks Docker instead of bubblewrap for cases whose config has an `image`: it refuses before creating the run directory when docker is missing or unreachable, or when the image isn't present locally, naming `docker pull` and the image. The `requires` check runs inside the case's container"
    - "tests/fake_docker.py stands in for the docker CLI in tests: it records each call's arguments and runs exec'd commands with bash in the given directory"
    - "docs/sessions/ has this task's session log entry"
  verification:
    - "uv run pytest -q tests/test_sandbox_docker.py::test_a_config_image_selects_the_docker_sandbox tests/test_sandbox_docker.py::test_docker_config_keys_are_validated tests/test_sandbox_docker.py::test_one_container_per_sandbox_with_no_network_and_the_host_user tests/test_sandbox_docker.py::test_only_the_worktree_and_its_git_dirs_are_mounted tests/test_sandbox_docker.py::test_commands_run_in_the_worktree_with_the_config_path_and_env tests/test_sandbox_docker.py::test_a_timed_out_command_is_stopped_in_the_container tests/test_sandbox_docker.py::test_seed_copies_the_images_ignored_files_without_overwriting tests/test_sandbox_docker.py::test_close_removes_the_container_once tests/test_sandbox_docker.py::test_a_bench_cell_removes_its_containers tests/test_sandbox_docker.py::test_bench_refuses_a_missing_docker_or_image_before_any_work"
    - "uv run pytest -q tests/test_sandbox.py tests/test_config.py tests/test_bench.py"
  risk: medium

- id: swe-bench-t02
  goal: "`python -m factory.bench.swebench prepare` turns a seeded, repository-stratified sample of a local SWE-bench dataset file into bench cases that run each instance's issue in its own Docker image, with the fix and its tests left out"
  spec_refs:
    - "docs/plans/swe-bench.md#a-swe-bench-case"
    - "docs/plans/swe-bench.md#the-sample"
    - "docs/plans/swe-bench.md#per-repository-templates"
  depends_on:
    - swe-bench-t01
  non_goals:
    - "Scoring candidates, or running the harness's evaluation (swe-bench-t03)"
    - "Downloading the dataset: prepare reads a local JSONL file"
    - "A `factory` subcommand: the entry point is the module, so factory/cli.py is unchanged"
    - "Changing the shipped fixture cases or the format of cases without a `swebench` key"
  acceptance:
    - "`prepare --dataset FILE --out DIR [--count 50] [--seed 1] [--instances ID ...]` reads SWE-bench instances from a JSONL file, picks the sample as the plan's sample section says (or exactly the given instance ids), and writes DIR/sample.json with the dataset's sha256, the seed, the count, the instance ids and each one's case id and image"
    - "Per instance it asks the harness (the Python interpreter in FACTORY_SWEBENCH_PYTHON) for the instance's image name, pulls the image when it is missing, and writes DIR/CASE/ where CASE is the instance id lowercased with each run of underscores turned into one hyphen. repo/ is `git archive HEAD` of the image's /testbed, refused unless that HEAD is the instance's base_commit"
    - "Each case.yaml has title REPO#NUMBER, kind bugfix, requires python and git, a `swebench` mapping with the instance id, the dataset file's absolute path and the image, an empty `hidden`, and the config and contract the plan's case section describes, using the template of the instance's repository. A repository without a template is refused, naming it"
    - "repo/.factory/issue.md holds the instance's problem statement and nothing else, and repo/.factory/guidance.md holds the template's guidance. Neither the gold patch, the test patch, the hints nor the FAIL_TO_PASS and PASS_TO_PASS test names appear anywhere under DIR except as the dataset path in case.yaml"
    - "cases.load_case accepts the optional `swebench` key: with it, `hidden` must be empty and hidden/ and solution/ may be absent; without it, every existing rule is unchanged"
    - "factory/verification.py treats commands that run `runtests.py` or sympy's `bin/test` as test commands, and counts sympy's `tests finished: N passed, M failed` summary, so a run of zero tests is inconclusive"
    - "tests/fake_swebench.py stands in for the harness's Python: it answers image names and writes evaluation reports from files the test supplies"
    - "docs/sessions/ has this task's session log entry"
  verification:
    - "uv run pytest -q tests/test_swebench.py::test_the_sample_is_seeded_stratified_and_recorded tests/test_swebench.py::test_prepare_writes_one_case_per_instance_from_its_image tests/test_swebench.py::test_prepare_refuses_an_image_whose_head_is_not_the_base_commit tests/test_swebench.py::test_prepared_cases_load_and_leave_out_the_fix_and_its_tests tests/test_swebench.py::test_issue_text_never_reaches_the_contract tests/test_swebench.py::test_every_verified_repository_has_a_template tests/test_swebench.py::test_a_swebench_case_needs_no_hidden_or_solution_files tests/test_verification.py::test_django_runtests_and_sympy_bin_test_are_test_commands"
    - "uv run pytest -q tests/test_bench_cases.py tests/test_verification.py"
  risk: medium

- id: swe-bench-t03
  goal: "A verified bench cell of a SWE-bench case is scored by the official harness: solved when the harness reports the instance resolved, false_pass when it doesn't; and `check` shows whether each case's Docker sandbox reproduces the instance's official test results"
  spec_refs:
    - "docs/plans/swe-bench.md#scoring"
    - "docs/plans/swe-bench.md#checking-the-environments"
  depends_on:
    - swe-bench-t02
  non_goals:
    - "Scoring the last candidate of a failed cell: only candidates the gates verified are scored"
    - "Re-implementing the harness's test-log parsing: the harness's report.json decides"
    - "Changing how cases without a `swebench` key are scored"
  acceptance:
    - "When a cell of a case with `swebench` ends verified, run_cell writes CELL/swebench/patch.diff (`git diff --binary` from the base to the candidate, leaving out .factory/ and docs/plans/) and a one-line predictions file, runs `run_evaluation` from the harness for that one instance with the case's dataset file, its image and a run id unique to the cell, and records solved when its report.json marks the instance resolved and false_pass otherwise. The harness log's tail goes to CELL/hidden.log"
    - "A harness that exits non-zero, times out or writes no report for the instance makes the cell `error`, never solved or false_pass"
    - "Bench preflight refuses SWE-bench cases before any work when FACTORY_SWEBENCH_PYTHON is unset or can't import swebench, or the dataset file is missing"
    - "results.json records the factory version line (version.line()) in its run header, and each SWE-bench case's instance id, image id and harness version in its cases entry"
    - "`python -m factory.bench.swebench check DIR [--cases CASE ...]` materializes each case, applies the instance's gold patch and test patch, runs its FAIL_TO_PASS and PASS_TO_PASS tests with the template's command in the case's Docker sandbox, and also on the base commit with only the test patch. It prints one line per case: ok when every test passes with the patches and every FAIL_TO_PASS test fails without the gold patch, and otherwise the tests that didn't, and exits 1 if any case isn't ok"
    - "docs/sessions/ has this task's session log entry"
  verification:
    - "uv run pytest -q tests/test_swebench.py::test_a_verified_swebench_cell_is_scored_by_the_harness tests/test_swebench.py::test_an_unresolved_report_is_a_false_pass tests/test_swebench.py::test_the_scored_patch_leaves_out_the_factory_files tests/test_swebench.py::test_a_failed_harness_run_is_an_error tests/test_swebench.py::test_bench_refuses_swebench_cases_without_the_harness tests/test_swebench.py::test_results_record_the_factory_version_and_the_harness tests/test_swebench.py::test_check_reports_cases_whose_environment_does_not_reproduce"
    - "uv run pytest -q tests/test_bench.py tests/test_bench_cases.py"
  risk: medium

- id: swe-bench-t04
  goal: "`python -m factory.bench.swebench summary RUN` reports each variant's resolved count over every sampled instance with its 95% interval and per-repository counts, and writes each variant's predictions file; docs/swe-bench.md is the runbook"
  spec_refs:
    - "docs/plans/swe-bench.md#reading-a-run"
    - "docs/plans/swe-bench.md#the-runbook"
  depends_on:
    - swe-bench-t03
  non_goals:
    - "Changing `factory bench report` or `factory bench compare`"
    - "Submitting predictions to the leaderboard"
    - "Editing README.md, NEXT.md, docs/architecture.md or docs/reference.md"
  acceptance:
    - "summary reads a run's results.json and counts every cell of a SWE-bench case: resolved is solved cells, and the denominator is all cells, so failed, false_pass, stopped, error and skipped all count as unresolved. Per variant it prints resolved k/n with the percentage and the Wilson 95% interval, the cells in each other outcome, cost per instance, minutes per instance, and the factory version line; then k/n per repository"
    - "summary writes RUN/swebench/predictions-VARIANT.jsonl with one line per sampled instance in the harness's predictions format: the scored patch for verified cells and an empty patch for the rest"
    - "A run with no SWE-bench cells, or a run directory without results.json, is refused with the reason"
    - "docs/swe-bench.md covers installing the harness into its own environment and setting FACTORY_SWEBENCH_PYTHON, writing the dataset to JSONL, `prepare`, `check`, a dry run, the run itself with its cost, `summary`, merging origin/main into the branch before a run, and removing the sample's images afterwards"
    - "docs/sessions/ has this task's session log entry"
  verification:
    - "uv run pytest -q tests/test_swebench.py::test_summary_counts_every_instance_like_the_leaderboard tests/test_swebench.py::test_summary_shows_the_interval_and_each_repository tests/test_swebench.py::test_predictions_hold_each_variants_patches tests/test_swebench.py::test_summary_refuses_a_run_without_swebench_cells"
    - "test -s docs/swe-bench.md"
  risk: low

- id: swe-bench-t05
  goal: "docs/swe-bench-results.md records the first measurement: the factory's strict flow on the 50-instance sample, as resolved out of 50 with its interval, cost and time, and the run id, sample seed and factory version line it came from"
  spec_refs:
    - "docs/plans/swe-bench.md#the-first-measurement"
  depends_on:
    - swe-bench-t04
  non_goals:
    - "Changing any code, prompt, flow or model to raise the score"
    - "Comparing flows or models: one run of the configured strict flow, once"
  acceptance:
    - "docs/swe-bench-results.md holds the summary's output for the run, the date, the run id, the dataset sha256 and seed from sample.json, the factory version line, the harness version, the total cost, and which sampled cases `check` didn't pass"
    - "It says in words what the number can and can't be compared with, as the plan's first-measurement section lists"
    - "docs/sessions/ has this task's session log entry"
  verification:
    - "grep -q 'resolved' docs/swe-bench-results.md"
    - "grep -Eq 'factory[[:space:]][0-9]' docs/swe-bench-results.md"
  risk: low
```

Planned test additions: `tests/fake_docker.py` and every test in `tests/test_sandbox_docker.py` (t01). `tests/fake_swebench.py`, `tests/test_swebench.py`'s prepare tests and `tests/test_verification.py::test_django_runtests_and_sympy_bin_test_are_test_commands` (t02). `tests/test_swebench.py`'s scoring and check tests (t03) and summary tests (t04). Each verification filter names the tests it must select; zero matching tests is not a pass.

**Every task is done by hand.** Each is a PR from `swe/<task-id>` into `experiment/swe-bench`, with its session log, and none of them goes on the board. Don't run `factory sync` with this branch checked out in the main checkout: it would load these tasks onto the main board, where nothing runs them.

Prerequisite for `swe-bench-t02`: the harness installed in its own environment (`uv venv` plus `uv pip install swebench`), with FACTORY_SWEBENCH_PYTHON pointing at that environment's Python, and SWE-bench Verified written to a JSONL file. Both need the network, so they're done by hand on the host.

Prerequisite for `swe-bench-t05`: `origin/main` merged into the branch and `uv run pytest -q` passing, a budget of up to $150 agreed for the run, and about 150 GB of free disk for the sample's images.

### Risks

1. **The fix leaks to the agents.** A SWE-bench image's /testbed can hold git history past the base commit, and the dataset file holds the gold patch and the tests. **Action:** the worktree is mounted over /testbed, so the image's own checkout and its .git are hidden. The cell's repository has one commit, and the dataset stays on the host, which the container can't see. t01 tests that only the worktree and its git dirs are mounted, and t02 tests that no patch, hint or test name is written under the cases directory.
2. **The factory's environment differs from the scorer's.** Commands run as the host user on a read-only root with the conda env on PATH, not as root after `conda activate`, so some tests may behave differently for the agents than for the harness. **Action:** `check` (t03) runs every sampled instance's official tests through the factory's own sandbox before a run. The results doc lists cases that don't reproduce, and the score itself always comes from the harness.
3. **The number gets compared with the wrong thing.** The factory submits only candidates its gates verified, bench's own solved rate leaves out stopped and error cells, and 50 instances give about ±13 points at a 95% interval. **Action:** summary divides by every sampled instance, shows the Wilson interval and the per-repository counts, and the results doc says what the number compares with.
4. **Cost.** 50 full strict runs on large repositories cost more than the fixture suite's $0.18 a cell. **Action:** a dry run first, `--max-cost 150` on the run, and the board's average of $1.77 a task as the estimate. A spent budget leaves the rest `skipped`, which summary counts as unresolved and shows.
5. **Disk.** Instance images are a few GB each, with shared layers. **Action:** prepare prints the images' total size, the runbook removes the sample's images with the list in sample.json, and the prerequisite asks for 150 GB free.
6. **Docker is root-equivalent on the host.** **Action:** only the factory's own process calls docker. Agents' commands run inside containers with no network, every capability dropped, no-new-privileges, a read-only root and the host user's ids, and the Docker socket is never mounted.
7. **Merging `main` gets harder over time.** **Action:** the branch only adds modules and small hooks in sandbox.py, config.py, verification.py and bench/; it never edits factory/cli.py, NEXT.md or the shared docs. Merge `origin/main` before each run, and rerun `uv run pytest -q`.

---

## Problem

The factory has no measurement that discriminates between setups or compares with anything outside this repository:

- **The shipped bench suite is saturated.** The 2026-11-16 bench run (`20261116-220919`) solved 60 of 60 cells across four variants (`gates-first` and `lean`, each on GLM 5.3 and Kimi K3.1 Pro). Five small standard-library cases can't tell those setups apart.
- **There's no outside reference.** strict-flow and flow-tuning cite SWE-bench Verified scores for the models this factory uses (`docs/plans/strict-flow.md:350`), but nothing says what the factory's own planner → builder → reviewer → verifier pipeline scores on those tasks.
- **bench can't run real repositories yet.** It takes cases from any directory (`--cases DIR`, `factory/bench/cases.py:131`), but cases run under bubblewrap with host paths bound at the same path (`factory/sandbox.py:59`), so a repository needing its own Python, compiled extensions and pinned dependencies has no environment. Hidden scoring also needs the case's own test files, while SWE-bench scores with its harness and its own test logs.

## Goal

One command prepares 50 SWE-bench Verified instances as bench cases, `factory bench run --cases DIR` runs the factory's strict flow on them in each instance's own image, and `summary` reports how many the official harness marks resolved, out of 50 with an interval, together with the factory version that produced it. All of this lives on `experiment/swe-bench`.

## Design

```text
SWE-bench Verified (JSONL, by hand) ──► prepare ──► DIR/CASE/{case.yaml, repo/}      DIR/sample.json
                                          │  image name: asked of the harness; image pulled
                                          │  repo/ = git archive of the image's /testbed at base_commit
                                          ▼
factory bench run --cases DIR --flow strict --max-cost 150 --parallel 4
   cell: materialize repo/ ─► Pipeline (test → build → gates → review → verify)
            every agent command and gate: docker exec in the instance's image, worktree at /testbed
            verified ─► patch.diff ─► swebench.harness.run_evaluation ─► resolved? solved : false_pass
            failed / stopped / error ─► not scored
                                          ▼
results.json ──► python -m factory.bench.swebench summary RUN ──► resolved k/50, interval, per repo
                                                               └─► predictions-VARIANT.jsonl
```

### A Docker sandbox

The bench cell already builds its sandbox from the case's config (`factory/bench/run.py:357`), and the pipeline, gates and agent tools only call `.run(cmd)` on it. A third class beside `Bwrap` and `Unsandboxed` slots in there:

```yaml
sandbox:
  image: swebench/sweb.eval.x86_64.django_1776_django-11099:latest   # the harness's name for it
  mount: /testbed            # the worktree is mounted here too, where the image's editable install points
  seed: /testbed             # copy the image's git-ignored files (built extensions, generated _version.py)
  path: ["/opt/miniconda3/envs/testbed/bin", "/opt/miniconda3/bin"]
  env: {}
```

- **One container per sandbox,** started on the first `run` and removed by `close()` or at exit. Commands run with `docker exec` in the worktree at its host path, so file tools and commands agree on paths. Python puts the current directory first on `sys.path`, so imports and tracebacks use those paths too. The same files are also at `mount`, which is where the image's editable install of the package points.
- **Isolation:** `--network none`, `--read-only` with a writable `/tmp`, `--cap-drop ALL`, `--security-opt no-new-privileges`, and the host's uid and gid, so files written in the worktree belong to the user. Only the worktree and its git dirs are mounted, the same set Bwrap binds writable.
- **Seeding:** mounting the worktree over /testbed hides the image's built files, so `seed` copies the image's git-ignored files into the worktree first. Those are compiled extensions and generated version files, leaving out `build/` and `__pycache__`. Ignored files never show in a diff, so the candidate stays clean.
- **Timeouts:** the command runs under coreutils `timeout` inside the container, so it doesn't outlive a timeout that only killed `docker exec`.
- `ro_binds`, `rw_binds`, `hide` and `cache_dirs` are bubblewrap settings and aren't used with an `image`.

### A SWE-bench case

The bench case format gains one optional key, so prepared cases run through `factory bench` unchanged. For `django__django-11099`:

```yaml
title: "django/django#11099"
kind: bugfix
requires: [python, git]
swebench: {instance_id: django__django-11099, dataset: /abs/path/verified.jsonl,
           image: "swebench/sweb.eval.x86_64.django_1776_django-11099:latest"}
config:
  test_paths: ["tests/**"]
  unit_tests: []                      # no suite gate: the full suite is slow, and naming tests leaks hints
  guidance: [".factory/guidance.md"]
  dependency_sources: []
  sandbox: {image: "…", mount: /testbed, seed: /testbed, path: ["/opt/miniconda3/envs/testbed/bin", "/opt/miniconda3/bin"]}
contract:
  id: django-django-11099-t01
  goal: "Fix the bug reported in the GitHub issue in .factory/issue.md (django/django#11099), with a test that reproduces it"
  spec_refs: [".factory/issue.md"]
  depends_on: []
  non_goals: ["Changing behaviour the issue doesn't ask to change", "Editing existing tests to make them pass"]
  acceptance:
    - "The behaviour .factory/issue.md reports is fixed in the library code"
    - "tests/factory_issue/tests.py has a test that fails on the base commit and passes with the fix"
    - "Existing tests of the code you changed still pass"
  verification: ["./tests/runtests.py --verbosity 2 --settings=test_sqlite --parallel 1 factory_issue"]
  risk: medium
hidden: []
```

- **The issue goes in a file, not the contract.** Problem statements contain `TODO`, `XXX` and `<FOO>`, which contract validation rejects as placeholders (`factory/contracts.py:28`). `.factory/issue.md` is in the base commit, listed in `spec_refs` and named in the goal. The tester and planner prompts already read spec references (`factory/prompts/tester.md:7`). Hints aren't included, as in SWE-bench's standard setting.
- **The new test has a fixed home per repository,** so the contract's verification is an exact command the strict flow's test step can turn red first, and nothing names the instance's real test files.
- **`.factory/guidance.md`** tells every agent what an agent harness usually says: the environment is installed, how to run a test file, and where the reproduction test goes.
- The base commit adds `.factory/` and `docs/plans/CASE.md`, which /testbed doesn't have; the scored patch leaves both out.

### The sample

From the dataset's instances, sorted by id: each repository gets its largest-remainder share of `--count`, and within a repository `random.Random(seed).sample` picks that many ids. With Verified's 500 instances and 50 to pick, that's about 23 django, 8 sympy, 4 sphinx, 3 each of matplotlib and scikit-learn, 2 each of xarray, pytest and astropy, and 1 each of pylint, requests and seaborn. `--instances` picks exact ids instead, which is useful for trying one. sample.json records what was picked, so a later run can use the same 50.

### Per-repository templates

| Repository | Reproduction test | Verification command | `test_paths` |
|---|---|---|---|
| django/django | `tests/factory_issue/tests.py` | `./tests/runtests.py --verbosity 2 --settings=test_sqlite --parallel 1 factory_issue` | `tests/**` |
| sympy/sympy | `sympy/core/tests/test_factory_issue.py` | `bin/test -C --verbose sympy/core/tests/test_factory_issue.py` | `sympy/**/tests/**` |
| pytest-dev/pytest | `testing/test_factory_issue.py` | `python -m pytest -rA testing/test_factory_issue.py` | `testing/**` |
| sphinx-doc/sphinx | `tests/test_factory_issue.py` | `python -m pytest -rA tests/test_factory_issue.py` | `tests/**` |
| matplotlib/matplotlib | `lib/matplotlib/tests/test_factory_issue.py` | `python -m pytest -rA lib/matplotlib/tests/test_factory_issue.py` | `lib/**/tests/**` |
| scikit-learn/scikit-learn | `sklearn/tests/test_factory_issue.py` | `python -m pytest -rA sklearn/tests/test_factory_issue.py` | `sklearn/**/tests/**` |
| pydata/xarray | `xarray/tests/test_factory_issue.py` | `python -m pytest -rA xarray/tests/test_factory_issue.py` | `xarray/tests/**` |
| astropy/astropy | `astropy/tests/test_factory_issue.py` | `python -m pytest -rA astropy/tests/test_factory_issue.py` | `astropy/**/tests/**` |
| pylint-dev/pylint | `tests/test_factory_issue.py` | `python -m pytest -rA tests/test_factory_issue.py` | `tests/**` |
| psf/requests | `test_factory_issue.py` | `python -m pytest -rA test_factory_issue.py` | `test_*.py`, `tests/**` |
| mwaskom/seaborn | `tests/test_factory_issue.py` | `python -m pytest -rA tests/test_factory_issue.py` | `tests/**` |
| pallets/flask | `tests/test_factory_issue.py` | `python -m pytest -rA tests/test_factory_issue.py` | `tests/**` |

Older requests releases keep their tests at the top level, hence its template. `runtests.py` already prints unittest's `Ran N tests`, so t02 only has to recognize the command; sympy's `bin/test` needs its summary line counted.

### Scoring

| Pipeline ends | Harness report | Cell outcome |
|---|---|---|
| `verified` | resolved | `solved` |
| `verified` | not resolved | `false_pass`: the factory's gates passed a patch SWE-bench's tests reject |
| `verified` | harness failed or no report | `error` |
| `failed`, cost limit, exception, budget spent | not run | `failed`, `stopped`, `error`, `skipped` as today |

The patch is `git diff --binary BASE CANDIDATE -- . ':!.factory' ':!docs/plans'`. The harness resets the test patch's files before applying it, so tests the agents wrote in those files don't count, and their new test files aren't run. The scorer runs the harness's Python (`FACTORY_SWEBENCH_PYTHON`) with `-m swebench.harness.run_evaluation` from `CELL/swebench/`. It passes the case's dataset file, a one-line predictions file, the instance id, `--max_workers 1` and the run id `bench-RUN-CELL`, then reads the instance's `report.json` from the harness's log directory. The harness runs its own container from the same image, separate from the agents' container.

### Checking the environments

`check` answers one question before money is spent: does the factory's sandbox give an instance's official tests the official results? It applies the gold patch and the test patch in a materialized case and runs FAIL_TO_PASS and PASS_TO_PASS with the template's command in the case's Docker sandbox. Then it runs FAIL_TO_PASS again with only the test patch, where those tests must fail. It reads only the dataset file on the host and never writes into the cases directory.

### Reading a run

```text
$ python -m factory.bench.swebench summary ~/.local/share/factory/software-factory/bench/20261120-091500
SWE-bench Verified · 50 instances (seed 1, dataset 3f9a…) · factory 0.4.0 (v0.4.0-12-gabc1234)

variant                          resolved           95% interval   false  failed  stop/err/skip  $/inst  min/inst
strict@configured                31/50  62%         48%–74%        6      11      1/1/0          2.14    18.3

repository      strict@configured
django          15/23
sympy           5/8
…
```

### The runbook

`docs/swe-bench.md` (t04) goes from an empty machine to a summary:

1. Install the harness in its own environment and export `FACTORY_SWEBENCH_PYTHON`.
2. Write Verified to JSONL with the harness's `datasets`.
3. Run `prepare`, then `check`.
4. Merge `origin/main` and run `uv run pytest -q`.
5. Do a `factory bench run --cases DIR --dry-run`, then the run itself, then `summary`.
6. Remove the sample's images.

### The first measurement

t05 runs `factory bench run --cases DIR --flow strict --max-cost 150 --parallel 4` once, on the configured models, and writes `docs/swe-bench-results.md`. The results doc states that the number:

- **Is comparable** with: later runs of the same sample on this branch, read with `factory bench compare` or summary.
- **Isn't directly comparable** with the leaderboard's full-500 scores. It's a 50-instance sample with an interval, a multi-agent pipeline with its own models per step, and a factory that submits nothing its gates didn't verify.

## Files Changed

All on `experiment/swe-bench`.

| File | Change |
|---|---|
| `factory/sandbox.py` | `Docker`; `make` picks it when the config has an `image` (t01) |
| `factory/config.py` | `image`, `mount`, `seed` in `SandboxConfig`, validated (t01) |
| `factory/bench/run.py` | Docker preflight and closing sandboxes (t01); harness scoring for `swebench` cases, the version line in results.json (t03) |
| `factory/bench/cases.py` | The optional `swebench` key (t02) |
| `factory/verification.py` | `runtests.py` and `bin/test` as test commands; sympy's summary counted (t02) |
| `factory/bench/swebench.py` | New: `prepare` (t02), scoring and `check` (t03), `summary` and predictions (t04) |
| `tests/fake_docker.py`, `tests/test_sandbox_docker.py` | New (t01) |
| `tests/fake_swebench.py`, `tests/test_swebench.py` | New (t02–t04) |
| `tests/test_verification.py` | `test_django_runtests_and_sympy_bin_test_are_test_commands` (t02) |
| `docs/swe-bench.md` | New: the runbook (t04) |
| `docs/swe-bench-results.md` | New: the first measurement (t05) |
| `docs/sessions/` | Every task's session log entry |

## Test Plan

### Unit tests

`tests/test_sandbox_docker.py` (t01) puts `tests/fake_docker.py` on PATH as `docker`. The fake records each call and runs exec'd commands with bash in the `-w` directory.

- `test_a_config_image_selects_the_docker_sandbox`: `make` returns Docker with and without `sandbox=False`, and Bwrap otherwise.
- `test_docker_config_keys_are_validated`: a relative `mount` or `seed`, and either without `image`, are rejected.
- `test_one_container_per_sandbox_with_no_network_and_the_host_user`: two runs make one `docker run`, with `--network none`, `--read-only`, `--cap-drop ALL`, `--user UID:GID` and the label.
- `test_only_the_worktree_and_its_git_dirs_are_mounted`: the mounts are exactly the worktree twice, the git common dir read-only and the admin dir, with no Docker socket.
- `test_commands_run_in_the_worktree_with_the_config_path_and_env`
- `test_a_timed_out_command_is_stopped_in_the_container`
- `test_seed_copies_the_images_ignored_files_without_overwriting`
- `test_close_removes_the_container_once`
- `test_a_bench_cell_removes_its_containers`: one cell with `ScriptedModel`, as in `tests/test_bench.py`, whose case has an `image`. No container is left after it, whether the cell solves or raises.
- `test_bench_refuses_a_missing_docker_or_image_before_any_work`

`tests/test_swebench.py` uses a three-instance JSONL from two repositories, fake docker serving a small git repository as the image's /testbed, and `tests/fake_swebench.py` as FACTORY_SWEBENCH_PYTHON.

- t02:
  - `test_the_sample_is_seeded_stratified_and_recorded`: the same seed gives the same ids, shares follow repository sizes, and sample.json records the hash and ids.
  - `test_prepare_writes_one_case_per_instance_from_its_image`
  - `test_prepare_refuses_an_image_whose_head_is_not_the_base_commit`
  - `test_prepared_cases_load_and_leave_out_the_fix_and_its_tests`: no gold patch line, test patch line, hint or test name anywhere under DIR.
  - `test_issue_text_never_reaches_the_contract`: a problem statement with `TODO` and `<FOO>` still loads.
  - `test_every_verified_repository_has_a_template`
  - `test_a_swebench_case_needs_no_hidden_or_solution_files`
- `tests/test_verification.py::test_django_runtests_and_sympy_bin_test_are_test_commands` (t02): both are test commands, `tests finished: 2 passed, 1 failed` counts 3, and zero tests is inconclusive.
- t03:
  - `test_a_verified_swebench_cell_is_scored_by_the_harness`: fake harness, resolved, gives `solved`.
  - `test_an_unresolved_report_is_a_false_pass`
  - `test_the_scored_patch_leaves_out_the_factory_files`
  - `test_a_failed_harness_run_is_an_error`
  - `test_bench_refuses_swebench_cases_without_the_harness`
  - `test_results_record_the_factory_version_and_the_harness`
  - `test_check_reports_cases_whose_environment_does_not_reproduce`
- t04: `test_summary_counts_every_instance_like_the_leaderboard`, `test_summary_shows_the_interval_and_each_repository`, `test_predictions_hold_each_variants_patches` and `test_summary_refuses_a_run_without_swebench_cells`, all working from written results.json files.

### End-to-end tests

These are by hand, with real Docker and the real harness:

- **t01:** a sandbox on one Verified image imports the package from a worktree, and `docker ps -a --filter label=factory.sandbox` is empty afterwards.
- **t03:** the scorer resolves two gold patches and rejects an empty one.
- **t05:** the full run.

## Verification

- Each task's verification commands, then `uv run pytest -q` on the branch.
- By hand, in order:
  1. `python -m factory.bench.swebench prepare --dataset verified.jsonl --out DIR` writes 50 cases and sample.json, and `factory bench cases --cases DIR` lists 50.
  2. `python -m factory.bench.swebench check DIR` passes, or names the cases whose environment doesn't reproduce.
  3. `factory bench run --cases DIR --flow strict --max-cost 150 --dry-run` lists 50 cells.
  4. The run, then `python -m factory.bench.swebench summary RUN`. `docs/swe-bench-results.md` holds its output.

## Cross-Workstream Coordination

- **Depends on (all merged on `main`):**
  - [bench](bench.md): the case format, `--cases`, cells, budget and results.json.
  - [strict-flow](strict-flow.md): the flow measured.
  - [version](version.md): the version line each run records.
- **Required by:** nothing on `main`. [flow-tuning](flow-tuning.md)'s trial (`flow-tuning-t06`) can run on these cases with `--cases DIR` once this branch has them. That's a use of the branch, not a dependency, so flow-tuning doesn't link back.
- **Links are one-way by decision.** This plan exists only on `experiment/swe-bench`, so no plan on `main` links to it.

## Notes / Out of Scope

- **Merging into `main`.** If the Docker sandbox proves useful beyond SWE-bench, it gets its own plan on `main`, written from what this branch learned.
- **The full 500 instances,** SWE-bench Lite, Multimodal or other languages. `prepare --count 500` works, but the cost and disk need their own decision.
- **Scoring failed candidates.** Scoring the last candidate of a `failed` cell would show what the gates throw away. It's a later column, not this plan.
- **Comparing flows or models.** bench's `--flow` and `--model` already do it on these cases, once the first measurement exists.
- **Hints, retrieval or repository-specific prompts** beyond the per-repository template's guidance.
- **Leaderboard submission.** summary writes predictions files in the harness's format, but submitting them isn't part of this plan.
