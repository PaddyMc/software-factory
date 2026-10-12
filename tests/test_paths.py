import pytest

from factory.contracts import check_path


@pytest.mark.parametrize("p", ["crates/node/src/lib.rs", "tools/factory/**", ".factory/core/policy.md",
                               ".github/workflows/**", "CLAUDE.md"])
def test_repo_relative_allowed_paths(p):
    assert check_path(p) is None


@pytest.mark.parametrize("p", ["/etc/passwd", "~/x", "../outside", "a/../../b", "**", "*", "**/x",
                               "./a", ".git/config", "a\\b"])
def test_reject_unbounded_or_escaping_paths(p):
    assert check_path(p) is not None
