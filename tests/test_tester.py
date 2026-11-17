"""The optional test step: flow shape, tester configuration, prompt and scoped tools."""

import pytest

from factory import agents
from factory import config as C
from factory import flows as F
from factory.cli import main
from factory.contracts import parse_text
from conftest import plan_text


def test_a_test_step_goes_between_plan_and_build():
    flow = F.parse_flow("tested", ["plan", "test", "build", "review", "verify"])
    assert [s.kind for s in flow.steps] == ["plan", "test", "build", "review", "gates", "verify"]
    assert [s.kind for s in F.parse_flow("tested", ["test", "build"]).steps] == ["test", "build", "gates"]

    custom = F.parse_step("tested", {"kind": "test", "name": "acceptance", "model": "fake:tester",
                                    "max_steps": 9, "loop": ["trim", "map", "nudge"]})
    assert custom == F.Step("acceptance", "test", model="fake:tester", max_steps=9,
                            loop=("trim", "map", "nudge"))
    flow = F.parse_flow("tested", [{"kind": "test", "name": "acceptance", "model": "fake:tester",
                                    "max_steps": 9, "loop": ["trim", "map", "nudge"]}, "build"])
    assert flow.steps[0] == custom and [s.name for s in flow.steps] == ["acceptance", "build", "gates"]

    invalid = [
        (["test", {"name": "more-tests", "kind": "test"}, "build"], "more-tests", "at most one test step"),
        (["build", "test"], "test", "directly before the first build"),
        (["plan", "test", "review", "build"], "test", "directly before the first build"),
        ([{"kind": "test", "loop": ["resume"]}, "build"], "test", "only valid on build steps"),
        ([{"name": "tester", "kind": "test"}, "build"], "tester", "reserved step name"),
    ]
    for steps, name, error in invalid:
        with pytest.raises(C.ConfigError) as e:
            F.parse_flow("tested", steps)
        assert "tested" in str(e.value) and name in str(e.value) and error in str(e.value)


def test_test_paths_and_the_test_role_are_configurable(repo, monkeypatch, capsys):
    assert C.parse({}).test_paths == ()
    cfg = C.parse({"test_paths": ["tests/**", "specs/*.py"],
                   "models": {"test": "fake:tester"}, "max_steps": {"test": 9}})
    assert cfg.test_paths == ("tests/**", "specs/*.py")
    assert cfg.models["test"] == "fake:tester" and cfg.max_steps["test"] == 9
    with pytest.raises(C.ConfigError, match="test_paths must be a string or a list of strings"):
        C.parse({"test_paths": ["tests/**", 3]})
    with pytest.raises(C.ConfigError, match="unknown role"):
        C.parse({"models": {"testing": "fake:tester"}})

    (repo / ".factory/config.yaml").write_text("test_paths: ['tests/**']\nmodels: {test: 'fake:tester'}\n")
    monkeypatch.chdir(repo)
    assert main(["config"]) == 0
    out = capsys.readouterr().out
    assert "test_paths:" in out and "- tests/**" in out and "test: fake:tester" in out


def test_the_tester_writes_only_under_test_paths(tmp_path):
    task = parse_text(plan_text("""- id: demo-t01
  goal: "Add the greeting module"
  spec_refs: []
  depends_on: []
  non_goals: []
  acceptance: ["The greeting is greeted"]
  verification: ["uv run pytest -q tests/test_greet.py", "grep -q hello src/greet.txt"]
  risk: low
"""), "p.md")[0]
    ctx = agents.Ctx(task=task, worktree=tmp_path, base_sha="0" * 40, attempt=1, sandbox=None,
                     feedback="The previous try changed src/greet.txt.")
    roles = agents.LangChainRoles(tmp_path, cfg=C.parse({"test_paths": ["tests/**"]}))
    tools, message, log = roles._kit(F.Step("test", "test"), ctx)
    tools = {t.name: t for t in tools}

    assert list(tools) == ["read_file", "list_dir", "grep", "write_file", "edit_file", "run"]
    assert log is None
    assert "demo-t01" in message and "tests/**" in message
    assert "uv run pytest -q tests/test_greet.py" in message
    assert "grep -q hello src/greet.txt" not in message
    assert "# Feedback to address first" in message and "src/greet.txt" in message

    refused = "refused: src/main.py is outside test_paths (tests/**)"
    assert tools["write_file"].invoke({"path": "src/main.py", "content": "implementation"}) == refused
    assert tools["edit_file"].invoke({"path": "src/main.py", "old": "a", "new": "b"}) == refused
    assert not (tmp_path / "src/main.py").exists()
    assert tools["write_file"].invoke({"path": "tests/test_x.py", "content": "old"}) == "wrote tests/test_x.py"
    assert tools["edit_file"].invoke({"path": "tests/test_x.py", "old": "old", "new": "new"}) == \
        "edited tests/test_x.py"
    assert (tmp_path / "tests/test_x.py").read_text() == "new"


def test_the_tester_prompt_ships_and_can_be_overridden(repo, monkeypatch, capsys):
    meta, body = agents.load_role(repo, "test")
    assert meta == {"model": "openrouter:z-ai/glm-5.3", "max_steps": 60}
    assert body.startswith("You are the TESTER")
    assert "write only tests" in body.lower() and "never write the implementation" in body.lower()

    monkeypatch.chdir(repo)
    assert main(["prompt", "test"]) == 0
    out = capsys.readouterr().out
    assert "prompts/tester.md" in out and "model openrouter:z-ai/glm-5.3" in out
    assert "You are the TESTER" in out

    override = repo / ".factory/agents/tester.md"
    override.parent.mkdir(parents=True)
    override.write_text("---\nmodel: fake:tester\nmax_steps: 7\n---\nYou are the TESTER, overridden.\n")
    assert agents.prompt_source(repo, "test") == override
    assert agents.load_role(repo, "test") == ({"model": "fake:tester", "max_steps": 7},
                                               "You are the TESTER, overridden.\n")
    assert main(["prompt", "test"]) == 0
    out = capsys.readouterr().out
    assert str(override) in out and "model fake:tester" in out and "You are the TESTER, overridden." in out
