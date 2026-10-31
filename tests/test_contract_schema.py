import pytest

from factory.contracts import KEYS, ContractError, Task, parse_text, validate_tasks
from conftest import TASK, plan_text


def _one(**override) -> str:
    fields = {
        "id": "demo-t01", "goal": '"g"', "spec_refs": "[]", "depends_on": "[]",
        "non_goals": "[]", "acceptance": '["a"]', "verification": '["true"]',
        "risk": "low",
    }
    fields.update(override)
    lines = [f"  {k}: {v}" for k, v in fields.items() if v is not None]
    lines[0] = "- " + lines[0][2:]
    return plan_text("\n".join(lines) + "\n")


def test_parse_contract_exact_8_keys():
    tasks = parse_text(plan_text(TASK), "p.md")
    assert [t.id for t in tasks] == ["demo-t01", "demo-t02"]
    assert set(tasks[0].mapping()) == set(KEYS) and len(KEYS) == 8
    assert "status" not in KEYS and "approval" not in KEYS  # state lives in the factory db
    assert validate_tasks(tasks) == []


def test_reject_missing_key():
    with pytest.raises(ContractError, match=r"missing=\['risk'\]"):
        parse_text(_one(risk=None))


@pytest.mark.parametrize("legacy", ["status", "approval", "allowed_paths"])
def test_reject_legacy_state_keys(legacy):
    with pytest.raises(ContractError, match=rf"extra=\['{legacy}'\]"):
        parse_text(_one(**{legacy: "ready"}))


@pytest.mark.parametrize("field,value", [
    ("goal", "[]"), ("spec_refs", '"not-a-list"'), ("depends_on", "[1, 2]"),
    ("acceptance", "[]"), ("risk", "extreme"), ("id", "NoPrefix"),
])
def test_reject_wrong_field_types(field, value):
    with pytest.raises(ContractError):
        parse_text(_one(**{field: value}))


def test_placeholder_is_an_error():
    assert any("placeholder" in e for e in validate_tasks(parse_text(_one(goal='"TODO decide"'))))


@pytest.mark.parametrize("cmd", ["Run the tests", "uv run pytest -q -k", "cargo test --exact"])
def test_command_selection_errors(cmd):
    assert validate_tasks(parse_text(_one(verification=f'["{cmd}"]')))


def test_non_contract_yaml_blocks_are_ignored():
    assert len(parse_text("```yaml\nkey: value\n```\n" + plan_text(TASK))) == 2


def test_json_roundtrip():
    t = parse_text(plan_text(TASK), "p.md")[0]
    assert Task.from_json(t.to_json()) == t and Task.from_json(t.to_json()).plan == "p.md"
