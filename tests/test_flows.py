"""Named agent flows: the `flow` and `flows` keys of .factory/config.yaml."""

import pytest
from langchain_core.messages import AIMessage

from factory import agents
from factory import config as C
from factory import flows as F
from factory.cli import main
from factory.contracts import parse_text
from factory.tools import ToolLog
from conftest import plan_text
from fake_model import ScriptedModel


def test_without_flows_the_default_flow_is_todays_pipeline():
    cfg = C.parse({})
    assert cfg.flow == "default" and cfg.flows == {"default": F.DEFAULT}
    assert [s.kind for s in F.DEFAULT.steps] == ["plan", "build", "review", "gates", "verify"]
    assert all(s.name == s.kind and s.model is None and s.max_steps is None for s in F.DEFAULT.steps)


def test_a_flow_is_a_list_of_steps_with_kinds_models_and_step_limits():
    cfg = C.parse({"flows": {"careful": [
        "plan", "build",
        {"name": "second-review", "kind": "review", "model": "anthropic:claude-opus-5-5", "max_steps": 30},
        "verify",
    ]}})
    flow = cfg.flows["careful"]
    assert flow.name == "careful"                                        # the gates step is inserted (see below)
    assert [s.name for s in flow.steps] == ["plan", "build", "second-review", "gates", "verify"]
    assert flow.steps[0] == F.Step("plan", "plan")                       # a string is the kind shorthand
    assert flow.steps[2] == F.Step("second-review", "review", model="anthropic:claude-opus-5-5", max_steps=30)
    assert cfg.flows["default"] is F.DEFAULT
    with pytest.raises(C.ConfigError, match="unknown key"):
        C.parse({"flows": {"f": ["build", {"kind": "review", "colour": "red"}]}})
    with pytest.raises(C.ConfigError, match="max_steps must be a positive integer"):
        C.parse({"flows": {"f": ["build", {"kind": "review", "max_steps": 0}]}})


def test_gates_go_after_the_last_review_unless_placed():
    def kinds(flow):
        return [s.kind for s in flow.steps]
    lean = F.parse_flow("lean", ["build", "review"])
    assert kinds(lean) == ["build", "review", "gates"]                   # inserted after the last review
    bare = F.parse_flow("bare", ["build"])
    assert kinds(bare) == ["build", "gates"]                             # no review: after the last build
    first = F.parse_flow("gates-first", ["plan", "build", "gates", "review", "verify"])
    assert kinds(first) == ["plan", "build", "gates", "review", "verify"]   # an explicit place is kept
    for flow in (lean, bare, first, F.DEFAULT):
        assert sum(s.kind == "gates" for s in flow.steps) == 1           # every flow holds exactly one
        assert flow.steps[kinds(flow).index("gates")].name == "gates"


@pytest.mark.parametrize("steps, bad", [
    (["plan", {"name": "plan-b", "kind": "plan"}, "build"], "plan-b"),   # two plan steps
    (["build", "plan"], "plan"),                                         # plan not first
    (["build", "review", {"name": "rebuild", "kind": "build"}], "rebuild"),   # builds split by a review
    (["review"], "review"),                                              # no build step
    (["build", "verify", {"name": "verify-again", "kind": "verify"}], "verify-again"),   # two verify steps
    (["build", "verify", "review"], "verify"),                           # verify not last
    (["build", "gates", "review", "gates"], "gates"),                    # two gates steps
])
def test_flow_order_rules_are_enforced(steps, bad):
    with pytest.raises(C.ConfigError) as e:
        C.parse({"flows": {"myflow": steps}})
    assert "myflow" in str(e.value) and bad in str(e.value)


def test_step_names_are_unique_and_not_reserved():
    def error(steps, name="myflow"):
        with pytest.raises(C.ConfigError) as e:
            C.parse({"flows": {name: steps}})
        return str(e.value)
    msg = error([{"name": "x", "kind": "build"}, {"name": "x", "kind": "review"}])
    assert "myflow" in msg and "x" in msg and "duplicate" in msg
    msg = error(["build", {"name": "planner", "kind": "plan"}])          # reserved, even on its own kind
    assert "myflow" in msg and "planner" in msg and "reserved" in msg
    msg = error([{"name": "build", "kind": "review"}])                   # named after another kind
    assert "myflow" in msg and "build" in msg and "kind" in msg
    msg = error(["build", {"name": "Bad_Name", "kind": "review"}])       # ^[a-z][a-z0-9-]*$ only
    assert "myflow" in msg and "Bad_Name" in msg
    assert "Careful" in error(["build"], name="Careful")                 # flow names follow the same pattern
    msg = error(["build", {"kind": "gates"}])                            # gates is only the bare string
    assert "myflow" in msg and "gates" in msg


def test_default_cannot_be_redefined_and_flow_must_name_a_flow():
    with pytest.raises(C.ConfigError, match="default"):
        C.parse({"flows": {"default": ["build", "review"]}})
    with pytest.raises(C.ConfigError, match="unknown flow nope"):
        C.parse({"flow": "nope"})
    with pytest.raises(C.ConfigError, match="unknown flow nope"):
        C.parse({"flow": "nope", "flows": {"lean": ["build", "review"]}})
    cfg = C.parse({"flow": "lean", "flows": {"lean": ["build", "review"]}})
    assert cfg.flow == "lean" and set(cfg.flows) == {"lean", "default"}


def test_factory_config_prints_the_flows(repo, monkeypatch, capsys):
    (repo / ".factory/config.yaml").write_text(
        "flow: careful\n"
        "flows:\n"
        "  careful:\n"
        "    - plan\n"
        "    - build\n"
        "    - {name: second-review, kind: review, model: 'anthropic:claude-opus-5-5', max_steps: 30}\n"
        "    - verify\n")
    monkeypatch.chdir(repo)
    assert main(["config"]) == 0
    out = capsys.readouterr().out
    assert "flow: careful" in out and "flows:" in out
    assert "default:" in out and "careful:" in out                       # the built-in flow is always printed
    for kind in ("plan", "build", "review", "gates", "verify"):
        assert f"kind: {kind}" in out
    assert "second-review" in out and "model: anthropic:claude-opus-5-5" in out and "max_steps: 30" in out


def _ctx(tmp_path, events, **kw):
    task = parse_text(plan_text(), "p.md")[0]
    return agents.Ctx(task=task, worktree=tmp_path, base_sha="0" * 40, attempt=1, sandbox=None,
                      record=events.append,
                      log=lambda tag, msg: events.append({"type": "log", "tag": tag, "msg": msg}), **kw)


def test_a_custom_step_uses_its_own_prompt_or_its_kinds(tmp_path):
    d = tmp_path / ".factory/agents"
    d.mkdir(parents=True)
    tests = F.Step("tests", "build")
    (d / "tests.md").write_text("You are the BUILDER of tests.\n")
    assert agents.step_prompt_source(tmp_path, tests) == d / "tests.md"          # the step's own prompt
    (d / "tests.md").unlink()
    (d / "builder.md").write_text("You are the BUILDER, overridden.\n")
    assert agents.step_prompt_source(tmp_path, tests) == d / "builder.md"        # else the kind's override
    (d / "builder.md").unlink()
    src = agents.step_prompt_source(tmp_path, tests)
    assert src.name == "builder.md" and ".factory" not in str(src)               # else the kind's shipped prompt
    (d / "build.md").write_text("You are a decoy.\n")                            # ignored: name == kind
    src = agents.step_prompt_source(tmp_path, F.Step("build", "build"))
    assert src.name == "builder.md"                                              # the kind's prompt, never <name>.md


def test_step_model_and_step_limit_precedence(tmp_path):
    d = tmp_path / ".factory/agents"
    d.mkdir(parents=True)
    (d / "reviewer.md").write_text("---\nmodel: fake:frontmatter\nmax_steps: 17\n---\nYou are the REVIEWER.\n")
    plain = F.Step("review", "review")
    custom = F.Step("second-review", "review", model="fake:step", max_steps=5)
    cfg = C.parse({"models": {"review": "fake:cfg"}, "max_steps": {"review": 23}})
    assert agents.step_model(tmp_path, custom, cfg, "fake:flag") == "fake:flag"  # --model beats everything
    assert agents.step_model(tmp_path, custom, cfg) == "fake:step"               # then the step's own
    assert agents.step_limit(custom, cfg, {}) == 5
    assert agents.step_model(tmp_path, plain, cfg) == "fake:cfg"                 # then the config's, by kind
    assert agents.step_limit(plain, cfg, {}) == 23
    cfg0 = C.parse({})
    assert agents.step_model(tmp_path, plain, cfg0) == "fake:frontmatter"        # then the prompt's frontmatter
    assert agents.step_limit(plain, cfg0, agents.load_step(tmp_path, plain)[0]) == 17
    (d / "reviewer.md").write_text("You are the REVIEWER.\n")
    assert agents.step_model(tmp_path, plain, cfg0) == agents.DEFAULT_MODEL      # then the default / 60
    assert agents.step_limit(plain, cfg0, {}) == 60
    flow = F.parse_flow("careful", ["plan", "build",
                                    {"name": "second-review", "kind": "review", "model": "fake:step", "max_steps": 5},
                                    "verify"])
    models = agents.flow_models(tmp_path, flow, cfg)
    assert set(models) == {"plan", "build", "second-review", "verify"}           # every agent step, no gates
    assert models["second-review"] == "fake:step"
    assert agents.flow_models(tmp_path, flow, cfg, "fake:flag") == {n: "fake:flag" for n in models}


def test_each_kind_gets_its_tools(tmp_path, monkeypatch):
    d = tmp_path / ".factory/agents"
    d.mkdir(parents=True)
    for name, who in (("planner", "PLANNER"), ("builder", "BUILDER"), ("reviewer", "REVIEWER"), ("verifier", "VERIFIER")):
        (d / f"{name}.md").write_text(f"You are the {who}.\n\nEnd with VERDICT: APPROVE or CHANGES.\n")
    plays = {"PLANNER": [AIMessage("the plan")], "BUILDER": [AIMessage("built it")],
             "REVIEWER": [AIMessage("looks good\n\nVERDICT: APPROVE")], "VERIFIER": [AIMessage("the report")],
             "_calls": [], "_verdicts": []}
    monkeypatch.setattr(agents, "build_model", lambda spec: ScriptedModel(plays=plays))
    toolsets, real_create_agent = [], agents.create_agent

    def capture(model, tools, **kw):
        toolsets.append([t.name for t in tools])
        return real_create_agent(model, tools, **kw)

    monkeypatch.setattr(agents, "create_agent", capture)
    roles = agents.LangChainRoles(tmp_path)
    read = ["read_file", "list_dir", "grep"]
    events = []

    def human():
        return [e["content"] for e in events if e["type"] == "human"][-1]

    roles.step(F.Step("plan", "plan"), _ctx(tmp_path, events))
    assert toolsets[-1] == read
    assert human() == "Plan task demo-t01."
    out = roles.step(F.Step("build", "build"), _ctx(tmp_path, events, plan="the plan"))
    assert toolsets[-1] == read + ["write_file", "edit_file", "run"]
    assert human() == "Implement task demo-t01 (attempt 1).\n\n# Plan\n\nthe plan"
    assert isinstance(out.log, ToolLog)                                          # the build run's writes/commands
    out = roles.step(F.Step("review", "review"), _ctx(tmp_path, events))
    assert toolsets[-1] == read + ["git_diff"]
    assert human() == "Review the change for task demo-t01. Start with git_diff(stat=True)."
    assert out.verdict == "APPROVE"                                              # parse_verdict's verdict
    roles.step(F.Step("verify", "verify"), _ctx(tmp_path, events, gates="ok  clean"))
    assert toolsets[-1] == read + ["git_diff", "run"]
    assert human() == ("All gates passed for task demo-t01. Write the PR report."
                       "\n\n# Gates\n\nok  clean")


def test_a_build_step_sees_the_earlier_build_steps(tmp_path, monkeypatch):
    d = tmp_path / ".factory/agents"
    d.mkdir(parents=True)
    (d / "builder.md").write_text("You are the BUILDER.\n")
    plays = {"BUILDER": [AIMessage("done")], "_calls": [], "_verdicts": []}
    monkeypatch.setattr(agents, "build_model", lambda spec: ScriptedModel(plays=plays))
    roles = agents.LangChainRoles(tmp_path)
    events = []
    roles.step(F.Step("build", "build"),
               _ctx(tmp_path, events, plan="the plan", earlier=("wrote the tests: greet_test.rs",)))
    human = [e["content"] for e in events if e["type"] == "human"][-1]
    assert "# Earlier build steps in this attempt" in human
    assert "1. wrote the tests: greet_test.rs" in human
    events = []
    roles.step(F.Step("build", "build"), _ctx(tmp_path, events, plan="the plan"))
    human = [e["content"] for e in events if e["type"] == "human"][-1]
    assert "Earlier build steps" not in human                                    # nothing earlier: no block


def test_a_review_prompt_without_a_verdict_line_is_warned_about(tmp_path, monkeypatch):
    d = tmp_path / ".factory/agents"
    d.mkdir(parents=True)
    (d / "reviewer.md").write_text("You are the REVIEWER. Judge harshly.\n")     # no VERDICT: line
    plays = {"REVIEWER": [AIMessage("looks off, but no verdict line")], "_calls": [], "_verdicts": []}
    monkeypatch.setattr(agents, "build_model", lambda spec: ScriptedModel(plays=plays))
    events = []
    out = agents.LangChainRoles(tmp_path).step(F.Step("review", "review"), _ctx(tmp_path, events))
    assert out.verdict == "CHANGES"                                              # parse_verdict fails safe
    warnings = [e["msg"] for e in events if e["type"] == "log" and "count as CHANGES" in e["msg"]]
    assert len(warnings) == 1 and "VERDICT:" in warnings[0]
    (d / "reviewer.md").write_text("You are the REVIEWER.\n\nEnd with VERDICT: APPROVE or CHANGES.\n")
    plays = {"REVIEWER": [AIMessage("fine\n\nVERDICT: APPROVE")], "_calls": [], "_verdicts": []}
    monkeypatch.setattr(agents, "build_model", lambda spec: ScriptedModel(plays=plays))
    events = []
    out = agents.LangChainRoles(tmp_path).step(F.Step("review", "review"), _ctx(tmp_path, events))
    assert out.verdict == "APPROVE"
    assert not any("count as CHANGES" in e.get("msg", "") for e in events)


def test_factory_prompt_prints_a_flow_step(repo, monkeypatch, capsys):
    (repo / ".factory/config.yaml").write_text(
        "flows:\n"
        "  careful:\n"
        "    - plan\n"
        "    - build\n"
        "    - {name: second-review, kind: review, model: 'anthropic:claude-opus-5-5', max_steps: 30}\n"
        "    - verify\n")
    monkeypatch.chdir(repo)
    assert main(["prompt", "second-review", "--flow", "careful"]) == 0
    out = capsys.readouterr().out
    assert "reviewer.md" in out                                                  # no custom file: the kind's prompt
    assert "model anthropic:claude-opus-5-5" in out and "max 30 steps" in out
    assert "You are the REVIEWER" in out
    d = repo / ".factory/agents"                                                 # a custom prompt of its own wins
    d.mkdir()
    (d / "second-review.md").write_text("You are the REVIEWER, second pass. Be terse.\n")
    assert main(["prompt", "second-review", "--flow", "careful"]) == 0
    captured = capsys.readouterr()
    assert "second-review.md" in captured.out and "You are the REVIEWER, second pass." in captured.out
    assert "every review will count as CHANGES" in captured.err                  # no VERDICT: line: warned
    assert main(["prompt", "reviewer"]) == 0                                     # a role name works as before
    assert "reviewer.md" in capsys.readouterr().out
    assert main(["prompt", "second-review"]) == 2                                # no such step in the default flow
    assert main(["prompt", "nope", "--flow", "careful"]) == 2
