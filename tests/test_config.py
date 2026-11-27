"""Per-project settings: .factory/config.yaml."""

from pathlib import Path

import pytest

from factory import config as C
from factory.agents import project_rules
from factory.contracts import discover_plans
from conftest import plan_text


def test_defaults_without_a_file(tmp_path):
    cfg = C.load(tmp_path)
    assert cfg.name == tmp_path.name and cfg.plans == ("docs/plans/**/*.md",)
    assert cfg.e2e is None and cfg.session_log is None and cfg.unit_tests == ()
    assert cfg.guidance == ("AGENTS.md", "CLAUDE.md") and "Cargo.lock" in cfg.lockfiles


def test_full_config_parses():
    cfg = C.parse({
        "name": "shop", "plans": "plans/*.md", "exclude": ["plans/drafts/**"], "guidance": ["AGENTS.md"],
        "session_log": "notes/", "unit_tests": "make test", "lockfiles": ["yarn.lock"],
        "dependency_sources": ["~/.cache/pip/src", "/opt/vendor"],
        "denied_commands": [r"\bkubectl\b"],
        "e2e": {"dir": "tests/e2e", "language": "python", "run_new": "pytest {path}::{name}",
                "run_all": "pytest tests/e2e", "run_all_when": ["^src/core/"]},
        "sandbox": {"ro_binds": ["~/.pyenv"], "rw_binds": [], "env": {"PIP_CACHE_DIR": "{cache}/pip"}},
    })
    assert cfg.plans == ("plans/*.md",) and cfg.unit_tests == ("make test",)
    assert cfg.e2e.dir == "tests/e2e/" and cfg.e2e.suffix == ".py" and cfg.e2e.run_all_when == ("^src/core/",)
    assert cfg.lockfiles == ("yarn.lock",)
    assert cfg.dependency_dirs(Path("/home/me")) == (Path("/home/me/.cache/pip/src"), Path("/opt/vendor"))
    assert cfg.sandbox.ro_binds == ("~/.pyenv",) and cfg.sandbox.rw_binds == ()
    assert cfg.sandbox.env == {"PIP_CACHE_DIR": "{cache}/pip"}
    assert cfg.sandbox.offline_env == C.SandboxConfig().offline_env       # unspecified keys keep defaults


@pytest.mark.parametrize("data, error", [
    ({"plan": ["x"]}, "unknown key"),
    ({"e2e": {"language": "rust"}}, "at least `dir`"),
    ({"e2e": {"dir": "t", "language": "go"}}, "e2e.language"),
    ({"e2e": {"dir": "t", "colour": "red"}}, "unknown key"),
    ({"denied_commands": ["("]}, "invalid regex"),
    ({"unit_tests": [1]}, "list of strings"),
    ({"sandbox": {"env": ["A=1"]}}, "must be a mapping"),
])
def test_bad_config_is_rejected(data, error):
    with pytest.raises(C.ConfigError, match=error):
        C.parse(data)


def test_home_precedence(tmp_path, monkeypatch):
    monkeypatch.delenv("FACTORY_HOME", raising=False)
    assert C.parse({"name": "shop"}).home_dir() == Path.home() / ".local/share/factory/shop"
    assert C.parse({"home": str(tmp_path / "h")}).home_dir() == tmp_path / "h"
    monkeypatch.setenv("FACTORY_HOME", str(tmp_path / "env"))
    assert C.parse({"home": str(tmp_path / "h")}).home_dir() == tmp_path / "env"


def test_plans_and_exclude_globs(tmp_path):
    (tmp_path / ".factory").mkdir()
    (tmp_path / ".factory/config.yaml").write_text('plans: ["work/**/*.md", "ROADMAP.md"]\nexclude: ["work/ideas/**"]\n')
    for rel in ("work/a/one.md", "work/ideas/maybe.md", "ROADMAP.md", "docs/plans/ignored.md"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(plan_text())
    assert [p.relative_to(tmp_path).as_posix() for p in discover_plans(tmp_path)] == ["ROADMAP.md", "work/a/one.md"]


def test_project_rules_describe_the_configured_gates():
    bare = project_rules(C.parse({}))
    assert "session log" not in bare and "end-to-end" not in bare and "verification commands" in bare
    rules = project_rules(C.parse({"session_log": "docs/sessions", "unit_tests": ["make test"],
                                   "e2e": {"dir": "tests/e2e", "language": "python"}}))
    assert "`docs/sessions/<today>-<task id>.md`" in rules and "`def test_*`" in rules and "`tests/e2e/`" in rules
    assert "`make test`" in rules


def test_trunk_and_land_are_read_with_their_defaults():
    cfg = C.parse({})
    assert cfg.trunk is None and cfg.land is None

    cfg = C.parse({"trunk": "dev"})
    assert cfg.trunk == "dev" and cfg.land is None

    cfg = C.parse({"trunk": "dev", "land": {}})
    assert cfg.land.release == "main" and cfg.land.method == "squash"
    assert cfg.land.max_holds == 2 and cfg.land.require_checks is True

    cfg = C.parse({"trunk": "dev", "land": {"release": "release", "max_holds": 0,
                                           "require_checks": False}})
    assert cfg.land.release == "release" and cfg.land.max_holds == 0
    assert cfg.land.require_checks is False
    for method in ("squash", "merge", "rebase"):
        assert C.parse({"trunk": "dev", "land": {"method": method}}).land.method == method


def test_land_needs_a_trunk_that_is_not_the_release_branch():
    with pytest.raises(C.ConfigError,
                       match="land needs trunk: the branch factory PRs target and factory land merges into"):
        C.parse({"land": {}})
    with pytest.raises(C.ConfigError, match=r"land\.release must differ from trunk \(dev\): "
                                             "landing would merge into the release branch unattended"):
        C.parse({"trunk": "dev", "land": {"release": "dev"}})


@pytest.mark.parametrize("land, error", [
    ({"method": "fast-forward"}, "land.method must be squash, merge or rebase"),
    ({"colour": "red"}, "land: unknown key"),
    ({"max_holds": -1}, "max_holds"),
    ({"max_holds": "two"}, "max_holds"),
    ({"require_checks": "yes"}, "require_checks"),
])
def test_bad_land_settings_are_rejected(land, error):
    with pytest.raises(C.ConfigError, match=error):
        C.parse({"trunk": "dev", "land": land})


def test_land_is_a_role_for_models_and_max_steps():
    assert "land" in C.ROLES
    assert C.parse({"models": {"land": "openrouter:z-ai/glm-5.3"}}).models == {"land": "openrouter:z-ai/glm-5.3"}
    assert C.parse({"max_steps": {"land": 3}}).max_steps == {"land": 3}
    with pytest.raises(C.ConfigError, match=r"unknown role\(s\) pilot \(roles: .*\bland\b\)"):
        C.parse({"models": {"pilot": "x"}})
