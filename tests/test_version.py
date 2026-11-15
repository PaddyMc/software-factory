"""Version output from installed package metadata and the factory's own git checkout."""

import importlib.metadata
import os
import re
import sys

import pytest

from factory import version
from factory.cli import main
from conftest import git


def _installed() -> str:
    try:
        return importlib.metadata.version("software-factory")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def _checkout(tmp_path, name="software-factory"):
    root = tmp_path / "checkout"
    (root / "factory").mkdir(parents=True)
    (root / "pyproject.toml").write_text(f'[project]\nname = "{name}"\nversion = "9.9.9"\n')
    (root / "factory" / "__init__.py").write_text("")
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "init")
    return root


def test_version_prints_the_package_version_outside_a_repository(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(version, "_package_dir", lambda: tmp_path / "plain" / "factory")

    assert main(["version"]) == 0
    captured = capsys.readouterr()
    assert captured.out == f"factory {_installed()}\n"
    assert captured.err == ""


def test_a_factory_checkout_adds_git_describe(tmp_path, monkeypatch):
    root = _checkout(tmp_path)
    package = root / "factory"
    git(root, "tag", "-a", "v1.2.3", "-m", "v1.2.3")
    assert version.describe(package) == "v1.2.3"

    (package / "__init__.py").write_text("VALUE = 1\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "change")
    described = version.describe(package)
    assert re.fullmatch(r"v1\.2\.3-1-g[0-9a-f]+", described)

    (package / "__init__.py").write_text("VALUE = 2\n")
    dirty = version.describe(package)
    assert dirty and dirty.endswith("-dirty")

    monkeypatch.setattr(version, "_package_dir", lambda: package)
    assert version.line() == f"factory {_installed()} ({version.describe(package)})"


def test_describe_ignores_tags_that_are_not_releases(tmp_path):
    root = _checkout(tmp_path)
    git(root, "tag", "v1.2.3")
    (root / "factory" / "__init__.py").write_text("VALUE = 1\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "change")
    git(root, "tag", "nightly")

    assert re.fullmatch(r"v1\.2\.3-1-g[0-9a-f]+", version.describe(root / "factory"))


def test_an_untagged_checkout_is_described_by_its_commit(tmp_path):
    root = _checkout(tmp_path)
    assert version.describe(root / "factory") == git(root, "rev-parse", "--short", "HEAD")


@pytest.mark.parametrize("case", ["no_git_checkout", "nested_below_top_level", "another_project",
                                  "git_missing", "git_fails", "git_times_out"])
def test_describe_is_none_outside_a_factory_checkout(case, tmp_path, monkeypatch):
    if case == "no_git_checkout":
        root = tmp_path / "plain"
        (root / "factory").mkdir(parents=True)
        (root / "pyproject.toml").write_text('[project]\nname = "software-factory"\nversion = "9.9.9"\n')
        (root / "factory" / "__init__.py").write_text("")
    elif case == "nested_below_top_level":
        root = _checkout(tmp_path)
        nested = root / "nested"
        (nested / "factory").mkdir(parents=True)
        (nested / "pyproject.toml").write_text('[project]\nname = "software-factory"\nversion = "9.9.9"\n')
        (nested / "factory" / "__init__.py").write_text("")
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "nested package")
        root = nested
    else:
        root = _checkout(tmp_path, name="other-project" if case == "another_project" else "software-factory")
        if case == "git_missing":
            empty = tmp_path / "empty-bin"
            empty.mkdir()
            monkeypatch.setenv("PATH", str(empty))
        elif case in ("git_fails", "git_times_out"):
            bindir = tmp_path / "bin"
            bindir.mkdir()
            stub = bindir / "git"
            body = "import sys\nsys.exit(1)\n" if case == "git_fails" else "import time\ntime.sleep(5)\n"
            stub.write_text(f"#!{sys.executable}\n{body}")
            stub.chmod(0o755)
            monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")
            if case == "git_times_out":
                monkeypatch.setattr(version, "_GIT_TIMEOUT", 0.2)

    assert version.describe(root / "factory") is None


def test_dash_dash_version_prints_the_same_line(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(version, "_package_dir", lambda: tmp_path / "plain" / "factory")

    with pytest.raises(SystemExit) as e:
        main(["--version"])
    assert e.value.code == 0
    flag = capsys.readouterr()

    assert main(["version"]) == 0
    command = capsys.readouterr()
    assert flag.out == command.out == f"factory {_installed()}\n"
    assert flag.err == command.err == ""


def test_other_commands_do_not_compute_the_version(tmp_path, monkeypatch):
    def boom(*args):
        raise AssertionError("another command computed the version")

    monkeypatch.setattr(version, "line", boom)
    monkeypatch.setattr(version, "describe", boom)
    log = tmp_path / "pytest.log"
    log.write_text("7 passed in 0.01s\n")

    assert main(["check-output", "--cmd", "uv run pytest -q tests/test_version.py", "--exit", "0", str(log)]) == 0
