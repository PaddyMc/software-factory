"""GitHub identity: a GH_TOKEN/GITHUB_TOKEN, when set, is what git and gh use; otherwise nothing changes."""

import os
import shutil
import subprocess

import pytest

from factory import github
from factory.cli import main
from factory.pipeline import git as factory_git
from factory.sandbox import make
from conftest import git


@pytest.fixture(autouse=True)
def no_token(monkeypatch):
    for var in github.TOKEN_VARS:
        monkeypatch.delenv(var, raising=False)


def test_the_token_comes_from_gh_token_first_then_github_token():
    assert github.token_var({}) is None and github.git_options({}) == []
    assert github.token_var({"GITHUB_TOKEN": "b"}) == "GITHUB_TOKEN"
    assert github.token_var({"GH_TOKEN": "a", "GITHUB_TOKEN": "b"}) == "GH_TOKEN"
    assert github.token_var({"GH_TOKEN": "", "GITHUB_TOKEN": "b"}) == "GITHUB_TOKEN"


@pytest.mark.parametrize("remote", ["git@github.com:o/r.git", "ssh://git@github.com/o/r.git"])
def test_with_a_token_github_ssh_remotes_go_over_https(repo, monkeypatch, remote):
    git(repo, "remote", "set-url", "origin", remote)
    assert factory_git(repo, "ls-remote", "--get-url", "origin") == remote
    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    assert factory_git(repo, "ls-remote", "--get-url", "origin") == "https://github.com/o/r.git"


def test_git_gets_the_token_from_the_environment_for_github_only(repo):
    env = {**os.environ, "GH_TOKEN": "s3cret-token"}
    opts = github.git_options(env)
    assert "s3cret-token" not in " ".join(opts)     # never on a command line

    def fill(host):
        p = subprocess.run(["git", *opts, "credential", "fill"], cwd=repo, capture_output=True, text=True,
                           input=f"protocol=https\nhost={host}\n\n", env={**env, "GIT_TERMINAL_PROMPT": "0"})
        return p.stdout

    assert "username=x-access-token\npassword=s3cret-token" in fill("github.com")
    assert "s3cret-token" not in fill("example.com")


def test_a_token_leaves_other_remotes_alone(repo, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    (repo / "x.txt").write_text("x\n")
    git(repo, "add", "x.txt")
    git(repo, "commit", "-q", "-m", "x")
    factory_git(repo, "push", "-q", "origin", "HEAD:refs/heads/main")      # the local bare origin
    factory_git(repo, "fetch", "-q", "origin", "main")
    assert factory_git(repo, "rev-parse", "origin/main") == git(repo, "rev-parse", "HEAD")


def test_factory_config_names_the_github_identity(repo, home, monkeypatch, capsys):
    monkeypatch.chdir(repo)
    assert main(["config"]) == 0 and "GitHub: gh login" in capsys.readouterr().out.splitlines()[0]
    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    assert main(["config"]) == 0 and "GitHub: token from $GITHUB_TOKEN" in capsys.readouterr().out.splitlines()[0]


@pytest.mark.parametrize("sandboxed", [True, False])
def test_agents_never_see_the_token(tmp_path, monkeypatch, sandboxed):
    if sandboxed and shutil.which("bwrap") is None:
        pytest.skip("bubblewrap not installed")
    monkeypatch.setenv("GH_TOKEN", "s3cret-a")
    monkeypatch.setenv("GITHUB_TOKEN", "s3cret-b")
    (tmp_path / "wt").mkdir()
    out = make(tmp_path / "wt", tmp_path / "cache", sandbox=sandboxed).run("env").output
    assert "s3cret" not in out
