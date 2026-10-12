import shutil

import pytest

from factory.sandbox import Bwrap

pytestmark = pytest.mark.skipif(shutil.which("bwrap") is None, reason="bubblewrap not installed")


@pytest.fixture
def sbx(tmp_path, monkeypatch):
    monkeypatch.setenv("FACTORY_TEST_SECRET_TOKEN", "leak")
    wt = tmp_path / "wt"
    wt.mkdir()
    return Bwrap(wt, tmp_path / "cache")


def test_worktree_is_writable(sbx):
    r = sbx.run("echo hi > out.txt && cat out.txt")
    assert r.code == 0 and r.output.strip() == "hi"
    assert (sbx.worktree / "out.txt").read_text() == "hi\n"


def test_home_and_secrets_are_hidden(sbx):
    r = sbx.run("ls -A ~ ; env")
    assert "FACTORY_TEST_SECRET_TOKEN" not in r.output and "leak" not in r.output
    for hidden in (".ssh", ".config", ".aws", ".local/share/factory"):
        assert sbx.run(f"test -e ~/{hidden}").code != 0, hidden


def test_host_filesystem_is_read_only(sbx):
    assert sbx.run("touch /etc/factory-test").code != 0
    assert sbx.run("touch /usr/factory-test").code != 0


def test_no_network_by_default(sbx):
    r = sbx.run("cat /proc/net/dev | tail -n +3 | cut -d: -f1 | tr -d ' '")
    assert r.output.split() == ["lo"]


def test_network_when_asked(tmp_path):
    wt = tmp_path / "wt2"
    wt.mkdir()
    r = Bwrap(wt, tmp_path / "cache", network=True).run("cat /proc/net/dev | tail -n +3 | wc -l")
    assert int(r.output.strip()) >= 1


def test_sandbox_settings_come_from_config(tmp_path, monkeypatch):
    from factory.config import SandboxConfig
    home = tmp_path / "home"
    (home / ".tool").mkdir(parents=True)
    (home / ".tool/secret").write_text("x")
    monkeypatch.setattr("factory.sandbox._home", lambda: home)
    wt = tmp_path / "wt3"
    wt.mkdir()
    cfg = SandboxConfig(ro_binds=("~/.tool", "~/.absent"), rw_binds=(), hide=("~/.tool/secret",), path=("~/.tool/bin",),
                        env={"TOOL_CACHE": "{cache}/tool"}, offline_env={"TOOL_OFFLINE": "1"}, cache_dirs=("tool",))
    b = Bwrap(wt, tmp_path / "cache", cfg=cfg)
    argv = b.argv("true")
    assert ["--ro-bind", str(home / ".tool"), str(home / ".tool")] == argv[argv.index(str(home / ".tool")) - 1:][:3]
    assert str(home / ".absent") not in argv                                   # missing paths are skipped
    assert ["--ro-bind", "/dev/null", str(home / ".tool/secret")] == argv[argv.index("/dev/null") - 1:][:3]
    env = b.env()
    assert env["TOOL_CACHE"] == str(tmp_path / "cache/tool") and env["TOOL_OFFLINE"] == "1"
    assert env["PATH"].startswith(f"{home}/.tool/bin:") and "CARGO_HOME" not in env
    assert (tmp_path / "cache/tool").is_dir()
    assert "TOOL_OFFLINE" not in Bwrap(wt, tmp_path / "cache", network=True, cfg=cfg).env()
