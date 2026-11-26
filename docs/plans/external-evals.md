# Plan: Measure the factory on SWE-rebench

**Status:** Planned (2026-11-22), reworked 2026-11-23 to a single benchmark. Workstream scoped; awaiting kickoff: t01 can run now; t02 waits for `evals-t07`. Roadmap: [NEXT.md item 21](../../NEXT.md#21-nothing-measures-the-factory-against-an-outside-benchmark). It supersedes the `experiment/swe-bench` plan (PR #83, none of its tasks built), whose Docker sandbox design t01 reuses.

---

## Execution Plan

### Locked Decisions

| Decision | Choice |
|---|---|
| Benchmark | **One: the [SWE-rebench leaderboard](https://huggingface.co/datasets/nebius/SWE-rebench-leaderboard) set** (`nebius/SWE-rebench-leaderboard`, CC-BY-4.0). It's Python only, with real GitHub issues and PRs collected every month, so the newest month postdates the models' training. Every task has a prebuilt public image (`docker_image`) and the leaderboard at [swe-rebench.com](https://swe-rebench.com/) scores bare models on the same months. SWE-bench Verified (contaminated), SWE-bench Pro (four languages, Harbor scoring, about 250 GB of images) and PatchEval (security only) are out |
| Scoring | **The factory grades, as SWE-bench does.** In a fresh container of the task's image, the test patch's files are laid over the candidate, the task's `test_cmd` runs on them, and pytest's `-rA` lines are parsed as SWE-bench 4.0.3's `parse_log_pytest` does. Resolved means every `FAIL_TO_PASS` and `PASS_TO_PASS` test passed. `factory bench export` writes SWE-bench predictions, so a run can be re-graded by hand with SWE-rebench's own harness. No external tool runs per cell |
| Tasks | **One whole month.** `factory bench prepare --month YYYY-MM` builds every task created that month (the dataset's monthly splits hold 30 to 110). There is no sampling, and the result lines up with the leaderboard's window for that month |
| Measurement | **By hand, once: the configured `strict` flow, one repeat, on the newest month** (t06), with `--max-cost 300`. There is no flow comparison and no security measurement |
| Sequencing | **After evals' code tasks.** t01 (the Docker sandbox) touches no bench file and runs now. Every task that changes `factory/bench/` waits for `evals-t07`, and the docs task for `evals-t08` |

### Milestones

| # | Deliverable | Exit criteria | Parallelizable with |
|---|---|---|---|
| **M1** | Docker sandbox | `tests/test_sandbox_docker.py` passes; `tests/test_sandbox.py` and `tests/test_config.py` pass unmodified | — |
| **M2** | SWE-rebench cases graded as SWE-bench grades them | The t02 tests in `tests/test_bench_swe_rebench.py` pass; the evals bench tests pass unmodified | — |
| **M3** | A month prepared and checked | The t03 tests in `tests/test_bench_swe_rebench.py` pass | — |
| **M4** | Report and export | The t04 tests in `tests/test_bench_swe_rebench.py` pass | — |
| **M5** | Runbook and docs | `tests/test_swe_rebench_docs.py` and `tests/test_templates.py` pass | — |
| **M6** | First measurement (by hand) | `docs/swe-rebench-results.md` gives strict's resolved k/n on one month with its interval, cost, run id and factory version line, and the official re-grade agrees | — |

**Sequence:** `M1 → [evals-t07 →] M2 → M3 → M4 → [evals-t08 →] M5 → M6`.

### Task Contracts

| Milestone | Task IDs | Coverage |
|---|---|---|
| **M1** | `external-evals-t01` | `Docker` in `factory/sandbox.py`; `image` and `mount` in `SandboxConfig` (`factory/config.py`); new `tests/fake_docker.py` and `tests/test_sandbox_docker.py` |
| **M2** | `external-evals-t02` | The `swe-rebench` kind and `swe_rebench` key in `factory/bench/cases.py`; per-test grading in new `factory/bench/swe_rebench.py`; scoring, patch.diff, preflight and container cleanup in `factory/bench/run.py`; new `tests/test_bench_swe_rebench.py` |
| **M3** | `external-evals-t03` | `factory bench prepare` and the swe-rebench check in `factory/bench/swe_rebench.py`, `factory/bench/check.py` and `factory/cli.py`; `tests/fake_docker.py` extended for images; tests in `tests/test_bench_swe_rebench.py` |
| **M4** | `external-evals-t04` | The swe-rebench line of `factory bench report` in `factory/bench/report.py`, and `factory bench export` in `factory/cli.py`; tests in `tests/test_bench_swe_rebench.py` |
| **M5** | `external-evals-t05` | New `docs/swe-rebench.md`; `docs/architecture.md`, `docs/reference.md`, `NEXT.md`, the factory-ops skill template and its copy; new `tests/test_swe_rebench_docs.py` |
| **M6** | `external-evals-t06` | By hand: the prepared month, the strict run, the official re-grade and new `docs/swe-rebench-results.md` |

```yaml
- id: external-evals-t01
  goal: "A sandbox config with an `image` runs every agent command and gate in a Docker container of that image, with the worktree mounted, no network and the host user's ids, seeds the image's git-ignored files into the worktree when a `mount` is set, and removes the container when the sandbox closes"
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
    - "SandboxConfig gains `image` (a Docker image) and `mount` (an absolute path inside the container where the worktree is also mounted), both defaulting to none. config.parse rejects a relative `mount`, and `mount` without `image`. With `image`, the bubblewrap defaults don't apply: `path`, `env` and `offline_env` default to empty, and ro_binds, rw_binds, hide and cache_dirs are not used"
    - "sandbox.make returns a Docker sandbox whenever the config has an `image`, with or without --no-sandbox, and a Bwrap or Unsandboxed one exactly as before otherwise"
    - "The first run starts one container per sandbox with `docker run -d`: `--network none` unless the sandbox has network, `--read-only` with a writable /tmp tmpfs, `--user` set to the host uid and gid, `--cap-drop ALL`, `--security-opt no-new-privileges`, a `factory.sandbox` label holding the worktree path, and `sleep infinity` as its command in place of the image's entrypoint. Its mounts are the worktree at its own path and at `mount`, the git common dir read-only and the worktree's git admin dir writable. Nothing else from the host is mounted, and the Docker socket never is"
    - "Each run is a `docker exec` in the worktree directory with HOME=/tmp, PATH set to the config's `path` ahead of the image's PATH, the config's `env` and, without network, its `offline_env`. The command runs under coreutils `timeout` inside the container, so a timed-out command is stopped in the container and returns the same timeout Result as Bwrap"
    - "With `mount`, before the sandbox's container starts, a short-lived container of the image with no network, running as the host user, copies into the worktree the files that `git ls-files --others --ignored --exclude-standard` lists under `mount` in the image (leaving out `build/` and `__pycache__` directories), without overwriting files the worktree already has. That container is removed"
    - "close() removes the container and can be called twice. Containers still open at interpreter exit are removed"
    - "The first run refuses, naming the problem, when the docker command is missing or the daemon is unreachable, and when the image isn't present locally, naming `docker pull` and the image"
    - "tests/fake_docker.py stands in for the docker CLI in tests: it records each call's arguments, keeps fake images as directories that hold an image's filesystem, and runs exec'd commands with bash in the given directory"
    - "docs/sessions/ has this task's session log entry"
  verification:
    - "uv run pytest -q tests/test_sandbox_docker.py::test_a_config_image_selects_the_docker_sandbox tests/test_sandbox_docker.py::test_docker_config_keys_are_validated tests/test_sandbox_docker.py::test_one_container_per_sandbox_with_no_network_and_the_host_user tests/test_sandbox_docker.py::test_only_the_worktree_and_its_git_dirs_are_mounted tests/test_sandbox_docker.py::test_commands_run_in_the_worktree_with_the_config_path_and_env tests/test_sandbox_docker.py::test_a_timed_out_command_is_stopped_in_the_container tests/test_sandbox_docker.py::test_mount_seeds_the_images_ignored_files_without_overwriting tests/test_sandbox_docker.py::test_close_removes_the_container_once tests/test_sandbox_docker.py::test_a_missing_docker_or_image_is_refused"
    - "uv run pytest -q tests/test_sandbox.py tests/test_config.py"
  risk: medium

- id: external-evals-t02
  goal: "`factory bench` runs SWE-rebench cases: a case of kind `swe-rebench` runs in its task's image, and a verified cell is graded as SWE-bench grades it, solved only when every listed fail-to-pass and pass-to-pass test passes"
  spec_refs:
    - "docs/plans/external-evals.md#a-swe-rebench-case"
    - "docs/plans/external-evals.md#grading"
    - "docs/plans/evals.md#grading"
  depends_on:
    - external-evals-t01
    - evals-t07
  non_goals:
    - "Building cases from the dataset (external-evals-t03): this task's tests write small cases by hand"
    - "The report line and export (external-evals-t04)"
    - "Log parsers other than parse_log_pytest, or running SWE-rebench's own harness"
    - "Changing how cases of other kinds load, run or score"
    - "Editing documentation"
  acceptance:
    - "case.yaml accepts kind `swe-rebench`, which requires a `swe_rebench` mapping with `instance`, `image`, `created_at`, `fail_to_pass` (a non-empty list of test ids) and `pass_to_pass` (a list of test ids), exactly one `hidden` command, and a config whose sandbox `image` equals `swe_rebench.image`. The `swe_rebench` key is refused on every other kind, and the rules for other kinds are unchanged. `factory bench cases` shows a swe-rebench case's instance and its counts of fail-to-pass and pass-to-pass tests"
    - "New factory/bench/swe_rebench.py parses test output as SWE-bench 4.0.3's parse_log_pytest does: each line that starts with PASSED, FAILED, SKIPPED, ERROR or XFAIL gives a status, with ` - ` replaced by a space on FAILED lines, then split on whitespace; the first field is the status and the second the test id, and a line with fewer than two fields is skipped. A test passes when its status is PASSED or XFAIL. A test missing from the output hasn't passed"
    - "A verified candidate of a swe-rebench case is scored by laying hidden/ over it in a scratch worktree, as for every case, and running the hidden command once in a sandbox of the case's config, with its exit code ignored. The outcome is `false_pass` when any fail_to_pass test hasn't passed, else `regressed` when any pass_to_pass test hasn't passed, else `solved`. evals' tampered check and the case's top-level pass_to_pass commands apply as for every kind"
    - "The cell's hidden.log holds the command's output and a summary: fail-to-pass passed k/n, pass-to-pass passed k/n, and up to 20 test ids that didn't pass. The cell record gains `swe_rebench` with both counts"
    - "When a swe-rebench cell ends verified, run_cell writes CELL/patch.diff: `git diff --binary` from the base to the candidate, leaving out .factory/ and the case's plan file"
    - "Bench preflight refuses before creating the run directory when a selected case has a sandbox image and the docker command is missing, the daemon is unreachable, or the image isn't present locally (naming `docker pull` and the image). bubblewrap isn't required when every selected case has an image. The requires and hidden-file checks run in the case's container"
    - "A cell closes every Docker sandbox it made, for the pipeline and for scoring, whether it succeeds, fails or raises"
    - "results.json records, in each swe-rebench case's entry, its instance and its image id from `docker image inspect`"
    - "docs/sessions/ has this task's session log entry"
  verification:
    - "uv run pytest -q tests/test_bench_swe_rebench.py::test_a_swe_rebench_case_loads_and_shows_its_instance tests/test_bench_swe_rebench.py::test_swe_rebench_keys_are_validated tests/test_bench_swe_rebench.py::test_pytest_statuses_are_parsed_as_swe_bench_does tests/test_bench_swe_rebench.py::test_a_verified_cell_is_solved_when_every_listed_test_passes tests/test_bench_swe_rebench.py::test_a_fail_to_pass_test_that_fails_is_a_false_pass tests/test_bench_swe_rebench.py::test_a_pass_to_pass_test_that_fails_is_regressed tests/test_bench_swe_rebench.py::test_the_scored_patch_leaves_out_the_factory_files tests/test_bench_swe_rebench.py::test_bench_refuses_a_missing_docker_or_image tests/test_bench_swe_rebench.py::test_a_cell_removes_its_containers"
    - "uv run pytest -q tests/test_bench.py tests/test_bench_cases.py tests/test_bench_mine.py"
  risk: high

- id: external-evals-t03
  goal: "`factory bench prepare` turns one month of SWE-rebench leaderboard tasks into checked bench cases: each case is its task's repository from the task's image, with the issue as its spec, the test patch as hidden tests and the gold patch as its solution, and a case whose gold patch doesn't resolve in the factory's sandbox is dropped"
  spec_refs:
    - "docs/plans/external-evals.md#preparing-a-month"
    - "docs/plans/external-evals.md#checking-a-case"
    - "docs/plans/evals.md#checking-a-case"
  depends_on:
    - external-evals-t02
  non_goals:
    - "Downloading the dataset: prepare reads a local file"
    - "Sampling: prepare builds every task of the month, or exactly the given instances"
    - "Mutants for swe-rebench cases: the benchmark owns their tests"
    - "Changing how other kinds are mined or checked"
    - "Editing documentation"
  acceptance:
    - "`factory bench prepare --source FILE --month YYYY-MM --out DIR [--instances ID ...]` reads FILE as JSONL, or a JSON list, of nebius/SWE-rebench-leaderboard rows, accepting FAIL_TO_PASS and PASS_TO_PASS as lists or as JSON-encoded strings. It selects the rows whose `created_at` starts with the month, or exactly the given instance ids"
    - "A row is refused, with its reason recorded and no case written, when its install_config's log_parser isn't parse_log_pytest, it has no docker_image, its patch or test_patch deletes, renames or binary-patches a file, its FAIL_TO_PASS is empty, its image can't be pulled, the image's /testbed isn't a git checkout whose HEAD is the row's base_commit, or the repository already has .factory/ or docs/plans/. prepare pulls an image that isn't present locally; it is the only bench command that pulls"
    - "A case's id is `rebench-` followed by the instance id lowercased, with each run of characters outside [a-z0-9] turned into one hyphen and hyphens trimmed from the ends. An id longer than 64 characters keeps its first 55 characters, then a hyphen and the first 8 hex digits of the instance id's sha256"
    - "Each case directory holds: repo/, the files `git ls-files --cached --others --exclude-standard` lists in the image's /testbed, as they are in its working tree; repo/.factory/issue.md, the row's problem_statement unchanged; repo/.factory/guidance.md, the guidance the plan's case section gives; hidden/, the files test_patch adds or changes, as they are after applying it; solution/, the files patch adds or changes, as they are after applying it; and case.yaml with kind swe-rebench, the `swe_rebench` mapping from the row, the contract and config the plan's case section gives, and one hidden command: the row's test_cmd followed by the paths test_patch changes, leaving out those ending in .json, .png, csv, .txt, .md, .jpg, .jpeg, .pkl, .yml, .yaml or .toml"
    - "Nothing from the row's patch or test_patch, and none of its hints_text, appears under repo/"
    - "Every written case is checked, and a case that fails any check is removed and recorded with the reason `check: ` and the check's name. template: with a one-line passing test at test_factory_issue.py the contract's verification classifies pass with at least one test counted in the case's sandbox, and with a one-line failing test it classifies fail. base: the base, graded as external-evals-t02 grades a candidate, isn't solved. gold: the solution laid over the base is solved"
    - "`factory bench check` on swe-rebench cases runs the same three checks, with no mutants, and prints and exits as evals-t03 defines"
    - "prepare writes DIR/suite.yaml in the format evals-t04 defines, with every case's split `holdout`, its kind, a source of benchmark swe-rebench with the instance and image, the row's created_at as its date, and its check result. It also writes DIR/prepare.json: the source file's sha256, the month, the number of rows in the month, the case ids written, each refused or dropped instance with its reason, and the total size of the cases' images"
    - "Running prepare again with the same arguments keeps the existing cases and changes no file"
    - "tests/fake_docker.py also fakes `docker pull`, `docker image inspect` and reading files from a fake image, so these tests need neither Docker nor the network"
    - "docs/sessions/ has this task's session log entry"
  verification:
    - "uv run pytest -q tests/test_bench_swe_rebench.py::test_prepare_builds_every_task_of_the_month tests/test_bench_swe_rebench.py::test_prepare_refuses_unusable_rows_with_reasons tests/test_bench_swe_rebench.py::test_a_prepared_case_hides_the_fix_and_its_tests tests/test_bench_swe_rebench.py::test_the_hidden_command_runs_the_test_patch_files tests/test_bench_swe_rebench.py::test_a_case_whose_gold_patch_fails_is_dropped tests/test_bench_swe_rebench.py::test_a_case_whose_template_counts_no_tests_is_dropped tests/test_bench_swe_rebench.py::test_bench_check_runs_the_swe_rebench_checks tests/test_bench_swe_rebench.py::test_prepare_again_changes_nothing tests/test_bench_swe_rebench.py::test_prepared_cases_are_holdout_in_the_suite_manifest"
    - "uv run pytest -q tests/test_bench_check.py tests/test_bench_swe_rebench.py"
  risk: medium

- id: external-evals-t04
  goal: "`factory bench report` gives a run's SWE-rebench resolved rate over every task it ran, as the leaderboard counts it, with its interval and the month's refused tasks, and `factory bench export` writes a run's patches as SWE-bench predictions for an official re-grade"
  spec_refs:
    - "docs/plans/external-evals.md#reading-a-run"
    - "docs/plans/evals.md#statistics"
  depends_on:
    - external-evals-t03
  non_goals:
    - "Changing how cells run or are graded, or evals' rates for other kinds"
    - "A comparison line for swe-rebench in `factory bench compare`: evals' compare already covers its cases"
    - "Submitting to the leaderboard"
    - "Editing documentation"
  acceptance:
    - "For each variant with swe-rebench cells, `factory bench report` prints `swe-rebench resolved k/n (P%) [LO–HI]`. k is solved cells, and n is every swe-rebench cell, so failed, false_pass, regressed, tampered, stopped, error and skipped cells count as unresolved. The interval comes from evals' clustered bootstrap with every cell counted. The report also shows false passes, regressions, and cost and minutes per task"
    - "When the run's cases directory has a prepare.json, the report also prints the month, the rows in the month, the refused and dropped instances counted by reason, and k over the rows in the month"
    - "`--json` on report carries the same under a `swe_rebench` key"
    - "`factory bench export RUN --out FILE [--variant ID]` writes one JSONL line per swe-rebench case of the run: `instance_id`, `model_name_or_path` as `factory-` followed by the variant id, and `model_patch` as the first repeat's patch.diff, or an empty string when that cell didn't end verified. It refuses a run with no swe-rebench cells, and a run with more than one variant when --variant isn't given, with the reason"
    - "docs/sessions/ has this task's session log entry"
  verification:
    - "uv run pytest -q tests/test_bench_swe_rebench.py::test_report_counts_resolved_over_every_task tests/test_bench_swe_rebench.py::test_report_shows_the_month_and_its_refused_tasks tests/test_bench_swe_rebench.py::test_export_writes_swe_bench_predictions tests/test_bench_swe_rebench.py::test_export_refuses_a_run_without_swe_rebench_cells"
    - "uv run pytest -q tests/test_bench.py tests/test_bench_stats.py tests/test_bench_swe_rebench.py"
  risk: low

- id: external-evals-t05
  goal: "docs/swe-rebench.md takes a reader from an empty machine to a re-graded SWE-rebench run, and docs/architecture.md, docs/reference.md, NEXT.md and the factory-ops skill describe SWE-rebench cases and the Docker sandbox"
  spec_refs:
    - "docs/plans/external-evals.md#the-runbook"
    - "docs/architecture.md#evaluating-flows-factory-bench"
  depends_on:
    - external-evals-t04
    - evals-t08
  non_goals:
    - "Changing code, or tests beyond the new docs test and what tests/test_templates.py needs for the new template text"
    - "Rewriting sections unrelated to this plan, or editing README.md"
  acceptance:
    - "New docs/swe-rebench.md covers, in order: what SWE-rebench measures and why it was chosen; the host it needs (x86_64, Docker, the disk the month's images take); exporting one month of nebius/SWE-rebench-leaderboard to JSONL with the `datasets` library; prepare and reading prepare.json; a dry run; the run with --max-cost; report; export, and re-grading the export with SWE-rebench's SWE-bench fork; removing the month's images; and what the number can and can't be compared with"
    - "docs/architecture.md's Evaluating flows section describes swe-rebench cases, their grading, their check and the Docker sandbox, and links docs/swe-rebench.md. docs/reference.md covers `factory bench prepare` and `factory bench export` with every option, the `swe-rebench` kind and `swe_rebench` key, the sandbox keys `image` and `mount`, and troubleshooting rows for a missing image, an unreachable Docker daemon, a refused row and a dropped case"
    - "NEXT.md marks item 21 done, linking docs/swe-rebench.md"
    - "factory/templates/skills/factory-ops/SKILL.md covers preparing, running, reporting and exporting a SWE-rebench month, and the changed template files are copied to .claude/skills/factory-ops/, so tests/test_templates.py passes"
    - "tests/test_swe_rebench_docs.py checks that docs/swe-rebench.md names every option of `factory bench prepare` and `factory bench export`, read from the CLI's argument parser, and that docs/reference.md names the sandbox keys image and mount"
    - "docs/sessions/ has this task's session log entry"
  verification:
    - "uv run pytest -q tests/test_swe_rebench_docs.py::test_the_runbook_names_every_prepare_and_export_option tests/test_swe_rebench_docs.py::test_the_reference_names_the_docker_sandbox_keys"
    - "uv run pytest -q tests/test_templates.py"
    - "grep -q 'docs/swe-rebench.md' NEXT.md"
  risk: low

- id: external-evals-t06
  goal: "docs/swe-rebench-results.md records the first measurement: the factory's configured strict flow on one whole month of SWE-rebench, as resolved out of the month's tasks with its interval, cost and time, the run id and factory version line it came from, and SWE-rebench's own re-grade of the exported patches"
  spec_refs:
    - "docs/plans/external-evals.md#the-measurement"
  depends_on:
    - external-evals-t05
  non_goals:
    - "Changing any code, prompt, flow or model to raise the score"
    - "Comparing flows or models: one run of the configured strict flow"
  acceptance:
    - "The newest monthly split of nebius/SWE-rebench-leaderboard is prepared as the runbook says, and one run of `factory bench run --cases DIR --flow strict --repeat 1 --max-cost 300` on it has finished or reached its budget, with a ledger note naming the month"
    - "docs/swe-rebench-results.md has a section headed with the run's date that gives the factory version line, the run id, the month, the source file's sha256, the rows in the month, the refused and dropped instances by reason, the report's swe-rebench line, k over the rows in the month, the false passes and regressions, the total cost, and cost and minutes per task"
    - "The run's export, re-graded with SWE-rebench's own harness as the runbook says, gives the same resolved count as the report, or the section lists every instance where they differ, with the reason"
    - "The section gives the leaderboard's resolved rate for the same month for the listed models closest to the configured ones, and says in words what differs: the leaderboard runs one model in one agent scaffold, while the factory runs its pipeline and submits only gate-verified candidates. For each configured model it says whether the month's tasks were created after the model's release"
    - "docs/sessions/ has this task's session log entry"
  verification:
    - "factory bench report"
    - "grep -q 'resolved' docs/swe-rebench-results.md"
    - "grep -Eq 'factory[[:space:]][0-9]' docs/swe-rebench-results.md"
  risk: low
```

Planned test additions:

| Task | Tests | Kind |
|---|---|---|
| t01 | `tests/fake_docker.py` (new); `tests/test_sandbox_docker.py` (new): nine tests named in its verification | unit, through the fake docker CLI |
| t02 | `tests/test_bench_swe_rebench.py` (new): nine tests | unit, CLI end to end with scripted models |
| t03 | `tests/test_bench_swe_rebench.py`: nine tests; `tests/fake_docker.py` extended | unit, CLI end to end |
| t04 | `tests/test_bench_swe_rebench.py`: four tests | CLI end to end |
| t05 | `tests/test_swe_rebench_docs.py` (new): two tests | docs against the CLI's parser |
| t06 | none: by hand | — |

Every verification command names tests the task adds, or a test file that exists when it runs, so a filter that selects nothing fails. No test needs Docker or the network: `tests/fake_docker.py` stands in for docker, and the bench tests run cells with scripted models (`tests/fake_model.py`), as `tests/test_bench.py` does. Each of t01–t05 can be run by the factory on this repository under `strict`: its first verification command names only new tests, which fail before the change.

**t06 is done by hand.** It needs the network (the dataset, the images, SWE-rebench's harness) and spends a model budget. Its verification runs `factory bench report`, which the factory refuses, so `factory run` refuses it and `factory run external-evals` lists it as manual. Do it on branch `factory/external-evals-t06`, so `factory status --refresh` adopts its PR.

Prerequisite for `external-evals-t06`: an x86_64 host with Docker and room for the month's images (prepare.json gives their total); the newest month of nebius/SWE-rebench-leaderboard exported to JSONL; SWE-rebench's SWE-bench fork installed on the host for the re-grade; and a budget of up to $300 agreed.

### Risks

1. **The factory's sandbox isn't the official harness.** Agents and scoring run offline, as the host user, on a read-only root, with the conda environment on PATH instead of activated, while SWE-rebench grades as root in a writable container. Some tests may then behave differently. **Action:** t03's base and gold checks grade in the factory's own sandbox, so a task whose gold patch doesn't resolve there is dropped and listed. t06 re-grades the export with SWE-rebench's harness and lists every disagreement.
2. **Dropped tasks bias the month.** **Action:** prepare.json lists every refused and dropped instance with its reason. The report gives k over the rows in the month next to k/n, and the results doc gives both.
3. **The fix leaks to the agents.** An image's /testbed keeps the repository's git history, which can hold the fix. **Action:** the worktree is mounted over /testbed, so the image's checkout and `.git` are hidden. The cell's repository has one commit, the case directory is never mounted, and issue.md is the problem statement only.
4. **The month predates a model.** A task created before a model's release may be in its training data. **Action:** t06 uses the newest month and says, for each configured model, whether the month postdates it.
5. **The number is compared with the wrong thing.** The leaderboard scores one model in one scaffold, while the factory is a pipeline that submits only verified candidates, and a month of 30 to 110 tasks gives about ±9–17 points at 95%. **Action:** the report divides by every task, as the leaderboard does, and shows the interval. The results doc says what the number compares with.
6. **Cost.** **Action:** a dry run first, and `--max-cost 300`. A spent budget leaves the rest `skipped`, which counts as unresolved and is shown.
7. **Disk.** Each task has its own image of a few GB. **Action:** prepare.json gives the images' total size, and the runbook removes them afterwards.
8. **Docker is root-equivalent on the host.** **Action:** only the factory's own process calls docker. Agents' commands run in containers with no network, every capability dropped, no-new-privileges, a read-only root and the host user's ids. The Docker socket is never mounted.
9. **This plan collides with evals and web-tools in `factory/bench/`.** **Action:** t02 waits for `evals-t07`. `web-tools-t04` also changes bench fingerprints after `evals-t07`, so whichever lands second rebases. The factory's conflict rework handles it.

---

## Problem

Nothing measures the factory against an outside reference:

- **The bench only knows this repository.** The shipped suite is saturated (run `20261116-220919` solved 60 of 60 cells), and [evals](evals.md) mines this repository's own merged tasks, which says how the factory does on its own code only.
- **The SWE reference the factory planned on is retired.** The by-hand `experiment/swe-bench` plan targets SWE-bench Verified, which OpenAI stopped reporting in February 2026 as contaminated.
- **The bench can't run real repositories.** Cases run under bubblewrap with host paths bound in place (`factory/sandbox.py:45`), so a repository that needs its own Python and installed dependencies has no environment.
- **The first version of this plan was too big.** It measured two benchmarks with an adapter registry, Harbor and PatchEval scorers, Go and JavaScript test runners, leak probes, two export formats and two paid runs, in ten tasks.

## Goal

`factory bench prepare` turns one month of SWE-rebench into checked cases, `factory bench run --cases DIR` runs the factory's flows on them in each task's own image, and `factory bench report` gives the resolved rate out of every task, graded as SWE-bench grades it, with an interval. The first measurement of strict is recorded in `docs/swe-rebench-results.md` and confirmed by SWE-rebench's own harness.

## Design

```text
month JSONL (by hand) ──► factory bench prepare --month M ──► DIR/CASE/{case.yaml, repo/, hidden/, solution/}
                             │ per row: pull image, copy /testbed, split the patches, write the case     DIR/suite.yaml
                             │ check: template probe · base not solved · gold solved (else dropped)       DIR/prepare.json
                             ▼
factory bench run --cases DIR --flow strict --repeat 1 --max-cost 300
   cell: materialize repo/ ─► Pipeline (test → build → gates → review → verify)
            every agent command and gate: docker exec in the task's image, worktree over /testbed
            verified ─► patch.diff ─► hidden/ over the candidate, test_cmd in a fresh container
                       ─► parse_log_pytest ─► every FAIL_TO_PASS and PASS_TO_PASS passed? solved
                                              else false_pass / regressed
            failed / stopped / error ─► not graded
                             ▼
results.json ──► factory bench report ──► swe-rebench resolved k/n [interval], k over the month's rows
             └─► factory bench export ──► predictions.jsonl ──► SWE-rebench's harness (by hand)
```

### A Docker sandbox

The bench cell already builds its sandbox from the case's config (`factory/bench/run.py`), and the pipeline, gates and agent tools only call `.run(cmd)` on it. A third class beside `Bwrap` and `Unsandboxed` slots in there, and works for `factory run` on any project whose config sets an image:

```yaml
sandbox:
  image: swerebench/sweb.eval.x86_64.0b01001001_1776_spectree-64   # the task's image
  mount: /testbed       # the worktree is also mounted here; the image's git-ignored files under it are copied in first
  path: [/opt/miniconda3/envs/testbed/bin]
  env: {}
```

- **One container per sandbox,** started on the first `run` and removed by `close()` or at exit. Commands run with `docker exec` in the worktree at its host path, so file tools and commands agree on paths. The same files are also at `mount`, so the image's editable install and configs that name /testbed still work.
- **Isolation:** `--network none`, `--read-only` with a writable `/tmp`, `--cap-drop ALL`, `--security-opt no-new-privileges`, and the host's uid and gid, so files written in the worktree belong to the user. Only the worktree and its git dirs are mounted, the same set Bwrap binds writable.
- **Seeding:** mounting the worktree over /testbed hides the image's git-ignored files, such as `*.egg-info` and built extensions. So before the container starts, a short-lived container copies them into the worktree. git refuses to read a repository owned by another user unless it is marked safe, so that container runs git with `safe.directory` set. Ignored files never show in a diff, so the candidate stays clean.
- **Timeouts:** the command runs under coreutils `timeout` inside the container, so it doesn't outlive a timeout that only killed `docker exec`.

### A SWE-rebench case

```yaml
title: "0b01001001/spectree: 0b01001001__spectree-64"
kind: swe-rebench
requires: []
swe_rebench: {instance: 0b01001001__spectree-64, image: "swerebench/sweb.eval.x86_64.0b01001001_1776_spectree-64",
              created_at: "2026-03-04T10:11:12Z", fail_to_pass: ["tests/test_plugin.py::test_x"], pass_to_pass: [...]}
config:
  test_paths: ["test_factory_issue.py"]
  unit_tests: []                      # no suite gate: the full suite is slow, and naming its tests leaks hints
  guidance: [".factory/guidance.md"]
  dependency_sources: []
  sandbox: {image: "swerebench/sweb.eval.x86_64.0b01001001_1776_spectree-64", mount: /testbed,
            path: [/opt/miniconda3/envs/testbed/bin], env: {}}
contract:
  id: rebench-0b01001001-spectree-64-t01
  goal: "Make the change .factory/issue.md asks for in 0b01001001/spectree, with a test that shows it"
  spec_refs: [".factory/issue.md"]
  depends_on: []
  non_goals: ["Changing behaviour the issue doesn't ask to change", "Editing or deleting existing tests to make them pass"]
  acceptance:
    - "The behaviour .factory/issue.md asks for is implemented"
    - "test_factory_issue.py has a test that fails on the base commit and passes with the change"
    - "Existing tests of the code you changed still pass"
  verification: ["pytest --no-header -rA --tb=line --color=no -p no:cacheprovider test_factory_issue.py"]   # test_cmd + the file
  risk: medium
hidden: ["pytest --no-header -rA --tb=line --color=no -p no:cacheprovider tests/test_plugin.py"]   # test_cmd + test_patch's files
```

(The instance, dates and test command are illustrative.)

- **The issue goes in a file, not the contract.** Problem statements contain `TODO` and `<FOO>`-style text, which contract validation rejects as placeholders. `.factory/issue.md` is in the base commit, listed in `spec_refs` and named in the goal, and the tester and planner prompts read spec references. It is the problem statement only: no `hints_text`, as in SWE-bench's standard setting.
- **The agents' test** goes in `test_factory_issue.py` at the repository's root. pytest collects a file named on its command line whatever its `python_files` setting, so this works in any layout. The guidance (`.factory/guidance.md`) says what an agent harness usually does: the environment is installed and offline, the repository is also at /testbed, the test goes in `test_factory_issue.py`, and the contract's verification runs it.
- **path:** `/opt/miniconda3/envs/testbed/bin` when the image has that directory (SWE-bench's conda environment), else empty.
- The base commit adds `.factory/` and `docs/plans/CASE.md`. The scored patch leaves both out.

### Grading

| Pipeline ends | Every FAIL_TO_PASS passed? | Every PASS_TO_PASS passed? | Cell outcome |
|---|---|---|---|
| `verified` | yes | yes | `solved` |
| `verified` | no | — | `false_pass`: the factory's gates passed a patch the benchmark rejects |
| `verified` | yes | no | `regressed` |
| `failed`, cost limit, exception, budget spent | not graded | — | `failed`, `stopped`, `error`, `skipped`, as today |

SWE-bench resets the test patch's files and applies the test patch before it runs the tests. Laying hidden/ (those files, as after the test patch) over the candidate does the same. The test files the agents wrote stay in the candidate but aren't run, so they never decide the verdict.

### Checking a case

| Check | Expect | Else |
|---|---|---|
| template: a one-line passing, then failing, test at `test_factory_issue.py`, through the contract's verification in the case's sandbox | pass with ≥ 1 test, then fail | dropped: `check: template` |
| base: the base, graded | not solved | dropped: `check: base` (the tests don't need the change) |
| gold: solution/ over the base, graded | solved | dropped: `check: gold` (the factory's sandbox can't run the tests) |

### Preparing a month

The source is a local export of the leaderboard dataset, for example `load_dataset("nebius/SWE-rebench-leaderboard", split="2026_03").to_json("2026-03.jsonl")`. Its monthly splits (`2025_01` … `2026_03` at the time of writing, 30 to 110 tasks each) are its rows grouped by `created_at`, so `--month` filters on that field. Every case goes in suite.yaml's `holdout` split. A goal loop following [evals](evals.md)' protocol never tunes on an outside month, and evals warns when the holdout is overused.

### Reading a run

```text
swe-rebench · strict    resolved 31/104  30% [21–39]    $2.10/task   11.4 min/task
                        month 2026-03: 110 rows, 6 refused or dropped (log_parser 2, image 1, check: gold 3) → 31/110 (28%)
                        false passes 7 · regressed 4
```

(The numbers are illustrative.) n counts every cell, so the rate is comparable in method with the leaderboard's, though the leaderboard averages several runs of a single agent.

### The runbook

`docs/swe-rebench.md` (t05) is the path a reader follows: host needs, exporting a month, prepare, dry run, run, report, export and re-grade with [SWE-rebench's SWE-bench fork](https://github.com/SWE-rebench/SWE-bench-fork), and cleaning up images.

### The measurement

t06 runs the configured `strict` flow with its models once on the newest month, with `--max-cost 300`. The results doc says what the number compares with. The leaderboard scores bare models in a fixed scaffold, so a factory number is a pipeline on the same tasks, scored the same way. Only verified candidates are submitted, so a stopped factory scores zero where a leaderboard agent would still submit its diff.

## Files Changed

| File | Change |
|---|---|
| `factory/sandbox.py` | `Docker` sandbox; `make` picks it when the config has an image (t01) |
| `factory/config.py` | `image` and `mount` in `SandboxConfig`, validated (t01) |
| `factory/bench/swe_rebench.py` | New: parse_log_pytest grading (t02); prepare, case ids and checks (t03) |
| `factory/bench/cases.py` | The `swe-rebench` kind and `swe_rebench` key; per-test grading for that kind (t02) |
| `factory/bench/run.py` | patch.diff, Docker preflight, container cleanup, image ids in results (t02) |
| `factory/bench/check.py` | The swe-rebench checks in `factory bench check` (t03) |
| `factory/bench/report.py` | The swe-rebench resolved line (t04) |
| `factory/cli.py` | `factory bench prepare` (t03) and `factory bench export` (t04) |
| `tests/fake_docker.py`, `tests/test_sandbox_docker.py` | New (t01); fake images extended (t03) |
| `tests/test_bench_swe_rebench.py` | New (t02), extended (t03, t04) |
| `tests/test_swe_rebench_docs.py` | New (t05) |
| `docs/swe-rebench.md`, `docs/architecture.md`, `docs/reference.md`, `NEXT.md`, `factory/templates/skills/factory-ops/SKILL.md`, `.claude/skills/factory-ops/SKILL.md` | Runbook and docs (t05) |
| `docs/swe-rebench-results.md` | New: the first measurement (t06, by hand) |
| `docs/sessions/` | One entry per task |

## Test Plan

### Unit tests

- **t01** (`tests/test_sandbox_docker.py`, through `tests/fake_docker.py`): an image selects Docker, even with --no-sandbox; `mount` must be absolute and needs `image`; one container per sandbox with `--network none`, the host uid and gid, every capability dropped and a read-only root; only the worktree, its git common dir and its admin dir are mounted; commands run in the worktree with the config's PATH and env; a timed-out command is stopped inside the container; seeding copies ignored files and leaves existing ones alone; close() removes the container once; a missing docker, daemon or image is refused, naming `docker pull`.
- **t02** (`tests/test_bench_swe_rebench.py`): parse_log_pytest's rules on real `-rA` output, including FAILED lines with ` - ` and XFAIL counted as passed; key validation for the new kind.

### End-to-end tests

Through `factory bench run` with scripted models and the fake docker CLI:

- **t02:** a verified cell is solved when every listed test passes, `false_pass` when a fail-to-pass test fails and `regressed` when a pass-to-pass test fails. patch.diff leaves out .factory/ and the plan file. Preflight refuses a missing image, and a cell removes its containers.
- **t03:** `factory bench prepare` on a JSONL of fake rows builds every task of the month, refuses unusable rows with reasons, keeps the fix and its tests out of repo/, builds the hidden command from test_patch's files, drops cases that fail the template or gold check, marks cases holdout, and changes nothing the second time. `factory bench check` runs the same checks.
- **t04:** report divides by every task and shows the month's refused tasks; export writes predictions and refuses runs without swe-rebench cells.
- **t05:** the runbook names every option of prepare and export, read from the CLI's parser.

## Verification

- t01–t05: each contract's commands, then `uv run pytest -q`.
- t06: `factory bench report` on the run shows the swe-rebench line, `docs/swe-rebench-results.md` records it, and SWE-rebench's harness agrees on the export.

## Cross-Workstream Coordination

- **Depends on:** [evals](evals.md). t02 depends on `evals-t07`, the last evals task to change `factory/bench/`, and t05 on `evals-t08`, its docs task. These cases use evals' outcomes (`regressed`, `tampered`), its check output (`factory bench check`), suite.yaml and its holdout split, its clustered intervals (t01) and the ledger's `--note` (t07). evals locked "no external benchmark is imported" for its own suites, and named an importer for the SWE-bench format as the natural follow-up: this is that follow-up, as a separate suite.
- **Required by:** none.
- **Overlaps without ordering:** `web-tools-t04` also changes `factory/bench/run.py` after `evals-t07`, so whichever lands second rebases. `security-review-t02` changes `factory/config.py` beside t01. The factory's conflict rework handles these.

## Notes / Out of Scope

- **SWE-bench Pro and PatchEval**, the first version's suites. Pro needs Go and JavaScript test runners, Harbor's patch_replay scorer and about 250 GB of images. PatchEval measures CVE patching only. Revisit Pro once SWE-rebench runs cleanly, and PatchEval when the `secure` flow ([security-review](security-review.md)) needs a measurement.
- **Go and JavaScript test runners** in `factory/verification.py`. They're needed for strict on any Go or JavaScript repository, not only a benchmark, so they belong in their own plan.
- **Leak probes** that search a whole image for the gold patch. The SWE-bench images build the environment at the base commit, and the mount hides the only known copy of the fix (the git history).
- **Running SWE-rebench's harness per cell.** The export and a by-hand re-grade check the factory's grading instead.
- **Sampling, several months, repeats, and comparing flows.** One whole month, one run. A later trial can compare flows on the same prepared month with `--baseline`.
- **Harbor or Inspect packaging** of the factory as an agent.
