"""Which GitHub identity the factory uses.

With GH_TOKEN or GITHUB_TOKEN set (gh's own order), everything the factory does on GitHub uses that
token, so each factory instance can run as its own account or app:
- `gh` reads it from the environment itself;
- git's fetches and pushes to github.com go over HTTPS with it, an SSH remote (`git@github.com:…`)
  rewritten for the call, so a PR and its commits come from the same identity.

Without one, nothing changes: `gh` uses your `gh auth login`, and git uses the remote and credentials
it has. The token stays in the environment: git asks a helper for it, so it is never on a command line
or written to disk, and agents never see it (both sandboxes drop *TOKEN* variables).
"""

from __future__ import annotations

from collections.abc import Mapping

TOKEN_VARS = ("GH_TOKEN", "GITHUB_TOKEN")

# Answers git's credential request for github.com from the environment, at the moment git asks.
_HELPER = '!f() { test "$1" = get && echo username=x-access-token && echo "password=${GH_TOKEN:-$GITHUB_TOKEN}"; }; f'


def token_var(env: Mapping[str, str]) -> str | None:
    """The variable the token comes from, or None when the factory uses the stored gh login."""
    return next((v for v in TOKEN_VARS if env.get(v)), None)


def describe(env: Mapping[str, str]) -> str:
    var = token_var(env)
    return f"token from ${var}" if var else "gh login"


def git_options(env: Mapping[str, str]) -> list[str]:
    """`git -c` options sending github.com traffic through the token; [] without one."""
    if not token_var(env):
        return []
    return ["-c", "url.https://github.com/.insteadOf=git@github.com:",
            "-c", "url.https://github.com/.insteadOf=ssh://git@github.com/",
            "-c", "credential.https://github.com.helper=",          # drop other helpers (gh, a keychain)
            "-c", f"credential.https://github.com.helper={_HELPER}"]
