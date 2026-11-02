# Releases

Releases use annotated Git tags named `vMAJOR.MINOR.PATCH`, starting with `v0.1.0`.
The tag, `pyproject.toml` version, and this project's entry in `uv.lock` must agree.
Release only commits merged into `main`; tags stay on their original commits.

While the project is below 1.0, increment the minor version for features or breaking
changes and the patch version for fixes. Release notes call out breaking changes.

## Prepare a release

1. Create a branch from the latest `main` and set the version. For example:

   ```bash
   uv version 0.1.0 --no-sync
   ```

   This updates `pyproject.toml` and `uv.lock`. Open a PR with both files and a
   session-log entry. For later releases, substitute the next version throughout.

2. Let CI pass and review the PR. CI runs the tests with the lockfile, builds a
   source archive and a wheel, installs the wheel, and runs `factory init` in an
   empty repository to check the shipped templates and skill links.

3. Merge the PR, then tag its commit from a clean checkout:

   ```bash
   git switch main
   git pull --ff-only origin main
   git status --short                 # must be empty
   uv version --short                # must match the intended version
   git tag -a v0.1.0 -m "Software factory v0.1.0"
   git push origin refs/tags/v0.1.0
   ```

   Push the specific tag. Do not move or reuse a published tag; prepare the next
   patch release to correct a release.

## What the tag publishes

The `release` workflow reruns the same CI against the tagged commit. It also checks
that the tag is annotated, has the expected format, matches the package version,
and points to a commit on `main`. Only after all checks pass does it create a
GitHub release with generated notes, the wheel, source archive, and `SHA256SUMS`.
It uses the repository's `GITHUB_TOKEN`; no publishing credentials are needed.

Follow the tag's run in GitHub Actions and check the resulting
[release](https://github.com/PaddyMc/software-factory/releases). If a run fails,
rerun the failed jobs after resolving the cause. If a release was already published,
leave its tag and assets intact and prepare a new version for changes.

Install a specific release with:

```bash
uv tool install git+https://github.com/PaddyMc/software-factory@v0.1.0
```

The wheel is also available on the GitHub release page. Releases are distributed
through GitHub; publishing to PyPI would be a separate change.
