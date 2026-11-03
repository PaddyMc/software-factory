"""Named agent flows: the `flow` and `flows` keys of .factory/config.yaml."""

import pytest

from factory import config as C
from factory import flows as F
from factory.cli import main


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
