# Plan: Which factory is this (`factory version`)

**Status:** Planned (2026-11-15). Workstream scoped; awaiting kickoff: t01 can run now. Roadmap: [NEXT.md item 13](../../NEXT.md#13-which-factory-is-this).

---

## Execution Plan

### Locked Decisions

| Decision | Choice |
|---|---|
| What `factory version` prints | **The package version, plus `git describe` when the factory runs from its own git checkout.** A release install prints `factory 0.1.0`. An editable install (`uv tool install --editable`) prints something like `factory 0.1.0 (v0.1.0-25-ge5f6b95-dirty)`, which names the commit its code comes from. How the version is set, built and released doesn't change |
| Where the version appears | **Only `factory version` and `factory --version`.** Runs, the board, `factory show`, the web pages and PR bodies don't record it |
| A new release | **No new tag in this workstream.** The next release follows [RELEASING.md](../../RELEASING.md) as usual, and an install of it then reports it |

### Milestones

| # | Deliverable | Exit criteria | Parallelizable with |
|---|---|---|---|
| **M1** | `factory version` and `--version` | The seven t01 tests in `tests/test_version.py` pass, and `uv run pytest -q` passes | — |
| **M2** | Docs | The reference, README, RELEASING.md, NEXT.md and the shipped factory-ops skill name the command. `tests/test_templates.py` passes | — |

**Sequence:** `M1 → M2`. The docs describe what t01 ships, so t02 waits for it.

### Task Contracts

| Milestone | Task IDs | Coverage |
|---|---|---|
| **M1** | `version-t01` | New `factory/version.py` (`describe`, `line`). The `version` subcommand and the lazy `--version` flag in `factory/cli.py`. New `tests/test_version.py` |
| **M2** | `version-t02` | `docs/reference.md`, `README.md`, `RELEASING.md`, `NEXT.md`, `factory/templates/skills/factory-ops/SKILL.md` |

```yaml
- id: version-t01
  goal: "`factory version` and `factory --version` print the factory's version: the installed package's version, followed by `git describe` of the factory's own git checkout when it runs from one, so an editable install also says which commit it runs"
  spec_refs:
    - "docs/plans/version.md#design"
    - "factory/cli.py"
    - "pyproject.toml"
    - "RELEASING.md"
  depends_on: []
  non_goals:
    - "Recording the version on runs, in the database, in `factory show`, on the web pages or in PR bodies"
    - "Changing how the version is set, built or released: pyproject.toml, uv.lock, the build backend, RELEASING.md and the CI workflows stay as they are"
    - "Creating, moving or pushing tags, or comparing the installed version with the releases on GitHub"
    - "Printing the checkout's path or branch, or a JSON form of the version"
    - "Adding a dependency"
    - "Editing any documentation other than this task's session log (version-t02 does that)"
  acceptance:
    - "New factory/version.py has `describe(package_dir)` and `line()`. When the directory above `package_dir` is the top level of a git work tree and its pyproject.toml declares the project `software-factory`, `describe` returns the output of `git describe --tags --match 'v[0-9]*' --always --dirty` run in that directory. Otherwise it returns None. So a clean checkout at a release tag gives `v0.1.0`, a later commit gives `v0.1.0-N-gSHA`, uncommitted edits to tracked files add `-dirty`, tags that don't start with `v` and a digit are ignored, and a checkout with no release tag gives the abbreviated commit hash"
    - "`describe` returns None without raising in each of these cases: git is missing, git fails or runs longer than 5 seconds, the directory is not in a git checkout, it is inside a checkout but not its top level (as for a package installed into a project's virtualenv), or it holds another project"
    - "`line()` returns `factory VERSION`, where VERSION is the version importlib.metadata reports for the `software-factory` distribution (`unknown` when it isn't installed). When `describe` of the imported `factory` package's directory is not None, ` (DESCRIBE)` follows. From this repository's editable install that reads like `factory 0.1.0 (v0.1.0-25-ge5f6b95)`, and from a wheel it reads `factory 0.1.0`"
    - "`factory version` prints line() on one line to stdout and exits 0. It also works outside a git repository and without .factory/config.yaml, since it reads neither the project config nor the board"
    - "`factory --version` prints the same line and exits 0 without a subcommand. No other command computes the version, so none of them runs an extra git command"
    - "factory/version.py runs on Python 3.10, the project's floor, so it doesn't import tomllib"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_version.py::test_version_prints_the_package_version_outside_a_repository tests/test_version.py::test_a_factory_checkout_adds_git_describe tests/test_version.py::test_describe_ignores_tags_that_are_not_releases tests/test_version.py::test_an_untagged_checkout_is_described_by_its_commit tests/test_version.py::test_describe_is_none_outside_a_factory_checkout tests/test_version.py::test_dash_dash_version_prints_the_same_line tests/test_version.py::test_other_commands_do_not_compute_the_version"
    - "uv run pytest -q"
  risk: low

- id: version-t02
  goal: "docs/reference.md, README.md, RELEASING.md, NEXT.md and the shipped factory-ops skill say how to see which factory version is running, and how to read the `git describe` part an editable install adds"
  spec_refs:
    - "docs/plans/version.md#design"
  depends_on:
    - version-t01
  non_goals:
    - "Changing code, or changing tests beyond what tests/test_templates.py needs for the new template text"
    - "Editing the installed skill copies under .claude/skills or .agents/skills, which `factory init --force` refreshes"
    - "Changing RELEASING.md's release steps, beyond the check this task adds"
  acceptance:
    - "docs/reference.md's Commands table has a row for `factory version` / `factory --version`. It says the command prints the installed version and that, from a git checkout of the factory (an editable install), it adds that checkout's `git describe`, read as: the last release tag, the commits since it, the commit, and `-dirty` for uncommitted edits. It says a checkout that hasn't fetched its tags (`git fetch --tags`) shows an older tag or just the commit"
    - "README.md's Install section says `factory version` shows what is installed, and that an editable install also shows the commit it runs"
    - "RELEASING.md says, after `Install a specific release with:`, that `factory version` then prints that release's version"
    - "factory/templates/skills/factory-ops/SKILL.md lists `factory version` among the read-only commands under `Ground in live state first`, for telling which factory code is running (an editable install runs whatever its checkout holds)"
    - "NEXT.md's table marks item 13 done, with a link to docs/reference.md#commands"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "grep -q 'factory[[:space:]]version' docs/reference.md"
    - "grep -q 'factory[[:space:]]version' README.md"
    - "grep -q 'factory[[:space:]]version' RELEASING.md"
    - "grep -q 'factory[[:space:]]version' factory/templates/skills/factory-ops/SKILL.md"
    - "grep -q 'reference.md#commands' NEXT.md"
    - "uv run pytest -q tests/test_templates.py"
  risk: low
```

Planned test additions:

| Task | Test | Kind |
|---|---|---|
| t01 | `tests/test_version.py` (new file): `test_version_prints_the_package_version_outside_a_repository`, `test_a_factory_checkout_adds_git_describe`, `test_describe_ignores_tags_that_are_not_releases`, `test_an_untagged_checkout_is_described_by_its_commit`, `test_describe_is_none_outside_a_factory_checkout` (parametrized over the five cases), `test_dash_dash_version_prints_the_same_line`, `test_other_commands_do_not_compute_the_version` | unit, CLI through `cli.main` |
| t02 | no new tests; reruns the existing `tests/test_templates.py` | regression |

Every verification filter names a test the task adds or an existing test file, so a run that selects zero tests fails the gate. Both tasks can run in the factory on this repository: their verification is `uv run pytest` and `grep`, offline. The grep patterns are written `factory[[:space:]]version` because the agents' `run` tool refuses a command containing `factory` followed by a space.

No task has a prerequisite. The factory is installed editable from the main checkout, so `factory version` exists once `version-t01` has merged and the main checkout is on that commit.

### Risks

1. **The wrong repository gets described.** If a wheel is installed inside some project's git repository, the factory could report that project's commit. **Action:** `describe` answers only when the package's parent directory is a git top level whose pyproject.toml names `software-factory`. `test_describe_is_none_outside_a_factory_checkout` covers a package nested inside a repository and a checkout of another project.
2. **Tags are stale or missing.** A checkout that hasn't fetched tags shows an old tag or only a commit. **Action:** `--always` falls back to the commit hash, so the line still names the code, and t02's reference row says to run `git fetch --tags`.
3. **A slow or missing git breaks the command.** **Action:** the git calls time out after 5 seconds, and any failure leaves out the describe part. Only `version` and `--version` run git, which `test_other_commands_do_not_compute_the_version` checks.
4. **The package version and the tag disagree.** Between a release bump merging and its tag being pushed, the line reads like `factory 0.2.0 (v0.1.0-30-g…)`. **Action:** that output is correct: it shows both parts, and RELEASING.md tags the bump's merge commit right after it merges.
5. **The edits conflict with in-flight plans.** `measure-t03` adds a subcommand to `factory/cli.py`, and the measure, bench and thoughts docs tasks edit `docs/reference.md`, `NEXT.md` and the factory-ops skill. **Action:** t01 adds one self-contained `add_parser` block and t02 adds a row or a line per file. The factory resolves the conflict on whichever PR merges second.

---

## Problem

You can't ask the factory which version it is.
- `factory/cli.py:1010` (`main`) has no `version` subcommand and no `--version` flag. argparse requires a subcommand, so `factory --version` is a usage error.
- The only version is the static `version = "0.1.0"` in `pyproject.toml:3`. [RELEASING.md](../../RELEASING.md) bumps it in a PR and then tags the merge commit (`v0.1.0` is the only tag so far, from 2026-11-01).
- The factory is usually installed editable, as [README.md](../../README.md#install) recommends for working on it and as this repository's maintainer does (`uv tool install --editable`), and an editable install runs whatever code its checkout holds. Its package metadata says `0.1.0` at every commit: `origin/main` is `v0.1.0-25-ge5f6b95`, 25 commits past the release, and nothing tells the two apart. A run's behaviour depends on which commit the checkout is on (for example, which PR-body layout or flow code it has), so "which factory did this?" has no answer today.

## Goal

`factory version` (or `factory --version`) prints one line saying which factory is running. A release install prints its release version. An editable install also prints its checkout's `git describe`, which says the last release, how many commits it is past it, the exact commit, and whether there are uncommitted edits.

## Design

### What runs

```
factory version  |  factory --version            (no other command computes it)
        │
        ▼
version.line()
  ├─ importlib.metadata.version("software-factory")         → "0.1.0"   ("unknown" if not installed)
  └─ version.describe(Path(factory.__file__).parent)
        root = package_dir.parent
        ├─ root/pyproject.toml declares name "software-factory"?   no → None
        ├─ git -C root rev-parse --show-toplevel == root?          no → None
        └─ git -C root describe --tags --match 'v[0-9]*' --always --dirty
                                                             → "v0.1.0-25-ge5f6b95-dirty"
        (git missing, failing, or over 5 s → None)
        ▼
"factory 0.1.0 (v0.1.0-25-ge5f6b95-dirty)"
```

### What each install prints

| Install | Prints |
|---|---|
| A release: `uv tool install git+https://github.com/PaddyMc/software-factory@v0.1.0`, or its wheel | `factory 0.1.0` |
| Editable, clean, at the `v0.1.0` tag | `factory 0.1.0 (v0.1.0)` |
| Editable, 25 commits later, with uncommitted edits | `factory 0.1.0 (v0.1.0-25-ge5f6b95-dirty)` |
| Editable, in a clone that never fetched tags | `factory 0.1.0 (e5f6b95)` |
| Imported from source without being installed | `factory unknown (…)` |

To read `v0.1.0-25-ge5f6b95-dirty`: the last release tag is `v0.1.0`, the code is 25 commits past it at commit `e5f6b95` (git puts `g` before the hash), and tracked files have uncommitted edits.

### Choices inside the design

- **Only release tags count.** `--match 'v[0-9]*'` skips any other tag. The release workflow accepts only `vMAJOR.MINOR.PATCH`.
- **Only the factory's own checkout counts.** A wheel in a project's `.venv/lib/…/site-packages/factory` sits inside that project's repository but isn't its top level, so the top-level check excludes it. The pyproject name check excludes a different project that happens to have a top-level `factory/` package. A git worktree of the factory counts, because its top level is the worktree.
- **`--version` is computed lazily.** argparse's built-in `action="version"` takes its string when the parser is built, which would run git on every command. A small `argparse.Action` that calls `line()` only when `--version` is given keeps the other commands as they are.
- **Python 3.10.** The project's floor is 3.10, and the virtualenv here runs 3.10.12, which has no `tomllib`. The pyproject check reads the name some other way, for example with a line match on the `[project]` table's `name`.
- **No config or board.** `factory version` doesn't call `repo_root()` or `config.load()`, so it works anywhere, including in a directory that isn't a repository.

## Files Changed

| File | Change |
|---|---|
| `factory/version.py` | New: `describe(package_dir)` and `line()` (t01) |
| `factory/cli.py` | `version` subcommand (`cmd_version`) and a lazy `--version` flag on the top-level parser (t01) |
| `tests/test_version.py` | New: the seven t01 tests (t01) |
| `docs/reference.md` | A Commands row for `factory version` / `--version` and how to read its output (t02) |
| `README.md` | Install: `factory version` shows what's installed (t02) |
| `RELEASING.md` | After installing a release, `factory version` prints it (t02) |
| `factory/templates/skills/factory-ops/SKILL.md` | `factory version` among the read-only grounding commands (t02) |
| `NEXT.md` | Item 13 marked done (t02) |
| `docs/sessions/<date>-version-t0N.md` | Each task's session log (t01, t02) |

## Test Plan

### Unit tests

All of these are in the new `tests/test_version.py` (t01). They build throwaway repositories shaped like the factory (a `pyproject.toml` naming `software-factory`, a `factory/__init__.py`) and use the `git_identity` fixture from `tests/conftest.py`.

- `test_version_prints_the_package_version_outside_a_repository`: from a non-git temporary directory, with `describe` pointed at a non-checkout, `cli.main(["version"])` returns 0 and prints exactly `factory ` plus `importlib.metadata.version("software-factory")`.
- `test_a_factory_checkout_adds_git_describe`: with an annotated `v1.2.3` tag on HEAD, `describe` gives `v1.2.3`. After one more commit it matches `v1.2.3-1-g[0-9a-f]+`. After an edit to a tracked file it ends in `-dirty`. `line()` ends with the describe in parentheses.
- `test_describe_ignores_tags_that_are_not_releases`: a lightweight `nightly` tag on a later commit doesn't replace `v1.2.3`.
- `test_an_untagged_checkout_is_described_by_its_commit`: with no tags, `describe` equals `git rev-parse --short HEAD`.
- `test_describe_is_none_outside_a_factory_checkout`, parametrized over five cases, each giving None: a directory outside git; a `factory/` package nested below a repository's top level; a top level whose pyproject.toml names another project; `PATH` without git; a git that runs past the timeout (a stub `git` on `PATH` that sleeps, with the timeout patched down).
- `test_dash_dash_version_prints_the_same_line`: `cli.main(["--version"])` exits with code 0 and prints the same line as `cli.main(["version"])`.
- `test_other_commands_do_not_compute_the_version`: with `version.line` and `version.describe` patched to raise, `cli.main(["check-output", …])` on a passing pytest log still returns 0.

### End-to-end tests

This repository configures no `e2e` gate. The CLI tests above go through `cli.main`, the same entry point the `factory` script calls.

## Verification

- `uv run pytest -q tests/test_version.py` passes the seven t01 tests, and `uv run pytest -q` passes the whole suite.
- After t01 merges and the main checkout is on its commit, `factory version` from any directory prints `factory 0.1.0 (v0.1.0-N-gSHA)` for this repository's editable install. `factory --version` prints the same line, and other commands behave as before.
- A wheel built with `uv build` and installed into a fresh virtualenv prints `factory 0.1.0` with nothing after it.
- After t02, `grep` finds `factory version` in docs/reference.md, README.md, RELEASING.md and the factory-ops skill, and NEXT.md item 13 is marked done.

## Cross-Workstream Coordination

- **Depends on:** nothing.
- **Required by:** nothing.
- **Shares files with:** [measure](measure.md) (`measure-t03` adds `factory stats` to `factory/cli.py`, and `measure-t04` edits `docs/reference.md`, `NEXT.md` and the factory-ops skill), and the [bench](bench.md) and [thoughts](thoughts.md) docs tasks (`docs/reference.md`, `NEXT.md`). There are no dependencies either way. The factory resolves the conflict on whichever PR merges second.

## Notes / Out of Scope

- **The version on runs and PRs.** We decided against recording the factory version on each run or in the PR footer. If it's wanted later, it would sit next to [measure](measure.md)'s prompt version in `runs` and could feed `factory stats`.
- **Versions taken from tags at build time** (hatch-vcs style). We decided against them: they change RELEASING.md, CI's tag check and `uv.lock`, and an editable install's metadata would still be stale until reinstalled.
- **Cutting the next release.** Not part of this workstream. It follows [RELEASING.md](../../RELEASING.md), and after it the release install reports the new version.
- **Comparing against the latest GitHub release**, `--json` output, and printing the checkout's path or branch.
