import pytest

from factory import config as C
from factory.sandbox import Unsandboxed
from factory.tools import PathGuard, ToolLog, read_tools, run_tool, write_tools


@pytest.fixture
def wt(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src/a.rs").write_text("fn a() {}\n")
    return tmp_path


def _tools(wt, home=None):
    log, guard = ToolLog(), PathGuard(wt, C.Config().dependency_dirs(home) if home else ())
    ts = read_tools(wt, guard) + write_tools(wt, guard, log) + run_tool(Unsandboxed(wt), log)
    return {t.name: t for t in ts}, log


def test_writes_go_anywhere_in_the_worktree_but_git(wt):
    t, log = _tools(wt)
    assert t["write_file"].invoke({"path": "src/b.rs", "content": "x"}) == "wrote src/b.rs"
    assert t["write_file"].invoke({"path": "Cargo.toml", "content": "x"}) == "wrote Cargo.toml"
    assert t["write_file"].invoke({"path": ".git/config", "content": "x"}).startswith("refused")
    assert t["write_file"].invoke({"path": "../escape.txt", "content": "x"}).startswith("refused")
    assert not (wt.parent / "escape.txt").exists() and log.written == ["src/b.rs", "Cargo.toml"]


def test_edit_requires_unique_match(wt):
    t, _ = _tools(wt)
    assert t["edit_file"].invoke({"path": "src/a.rs", "old": "fn a", "new": "fn b"}) == "edited src/a.rs"
    assert "occurs 0 times" in t["edit_file"].invoke({"path": "src/a.rs", "old": "nope", "new": "x"})


def test_reads_cannot_escape_worktree(wt):
    t, _ = _tools(wt)
    assert "fn a" in t["read_file"].invoke({"path": "src/a.rs"})
    with pytest.raises(PermissionError):
        t["read_file"].invoke({"path": "../../etc/passwd"})


def test_reads_reach_dependency_sources_only(wt, tmp_path_factory):
    home = tmp_path_factory.mktemp("home")
    crate = home / ".cargo/registry/src/index.crates.io-x/serde-1.0.0/src"
    crate.mkdir(parents=True)
    (crate / "lib.rs").write_text("pub mod message;\n")
    (home / ".cargo/credentials.toml").write_text("token = 'secret'\n")
    t, _ = _tools(wt, home)
    assert t["read_file"].invoke({"path": str(crate / "lib.rs")}) == "1\tpub mod message;"
    assert t["list_dir"].invoke({"path": str(crate)}) == "lib.rs"
    assert "lib.rs:1:pub mod message;" in t["grep"].invoke({"pattern": "message", "path": str(crate)})
    for outside in (home / ".cargo/credentials.toml", home / ".cargo/registry/src/../../credentials.toml"):
        with pytest.raises(PermissionError, match="outside the worktree and the dependency sources"):
            t["read_file"].invoke({"path": str(outside)})
    assert t["write_file"].invoke({"path": str(crate / "lib.rs"), "content": "x"}).startswith("refused")


@pytest.mark.parametrize("cmd", ["git commit -am x", "git push origin x", "gh pr create", "sudo ls",
                                 "terraform apply", "factory status"])
def test_run_refuses_privileged_commands(wt, cmd):
    t, log = _tools(wt)
    assert t["run"].invoke({"command": cmd}).startswith("refused") and log.commands == []


def test_run_executes_in_worktree(wt):
    t, log = _tools(wt)
    assert t["run"].invoke({"command": "ls src"}).startswith("exit 0\na.rs")
    assert log.commands == [("ls src", 0)]
