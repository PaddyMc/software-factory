import pytest

from factory.sandbox import Unsandboxed
from factory.tools import PathGuard, ToolLog, read_tools, run_tool, write_tools


@pytest.fixture
def wt(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src/a.rs").write_text("fn a() {}\n")
    return tmp_path


def _tools(wt, allowed=("src/**",)):
    log = ToolLog()
    ts = read_tools(wt, PathGuard(wt, ("**",))) + write_tools(wt, PathGuard(wt, allowed), log) + run_tool(Unsandboxed(wt), log)
    return {t.name: t for t in ts}, log


def test_writes_confined_to_allowed_paths(wt):
    t, log = _tools(wt)
    assert t["write_file"].invoke({"path": "src/b.rs", "content": "x"}) == "wrote src/b.rs"
    assert t["write_file"].invoke({"path": "Cargo.toml", "content": "x"}).startswith("refused")
    assert t["write_file"].invoke({"path": "../escape.txt", "content": "x"}).startswith("refused")
    assert not (wt.parent / "escape.txt").exists() and log.written == ["src/b.rs"]


def test_edit_requires_unique_match(wt):
    t, _ = _tools(wt)
    assert t["edit_file"].invoke({"path": "src/a.rs", "old": "fn a", "new": "fn b"}) == "edited src/a.rs"
    assert "occurs 0 times" in t["edit_file"].invoke({"path": "src/a.rs", "old": "nope", "new": "x"})


def test_reads_cannot_escape_worktree(wt):
    t, _ = _tools(wt)
    assert "fn a" in t["read_file"].invoke({"path": "src/a.rs"})
    with pytest.raises(PermissionError):
        t["read_file"].invoke({"path": "../../etc/passwd"})


@pytest.mark.parametrize("cmd", ["git commit -am x", "git push origin x", "gh pr create", "sudo ls",
                                 "terraform apply", "factory status"])
def test_run_refuses_privileged_commands(wt, cmd):
    t, log = _tools(wt)
    assert t["run"].invoke({"command": cmd}).startswith("refused") and log.commands == []


def test_run_executes_in_worktree(wt):
    t, log = _tools(wt)
    assert t["run"].invoke({"command": "ls src"}).startswith("exit 0\na.rs")
    assert log.commands == [("ls src", 0)]


@pytest.mark.parametrize("pattern,path,ok", [
    ("src/**", "src/x/y.rs", True), ("src/**", "srcx/y.rs", False), ("src/*.rs", "src/x/y.rs", False),
    ("crates/node/src/lib.rs", "crates/node/src/lib.rs", True), ("infra", "infra/main.tf", True),
])
def test_glob_semantics(tmp_path, pattern, path, ok):
    assert PathGuard(tmp_path, (pattern,)).allows(path) is ok
