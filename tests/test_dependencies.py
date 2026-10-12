from factory.contracts import check_dependencies, parse_text, validate_tasks
from conftest import TASK, plan_text


def test_reject_cycle_and_unknown_id():
    body = TASK.replace("depends_on: []", "depends_on: [demo-t02, demo-t99]")
    tasks = {t.id: t for t in parse_text(plan_text(body))}
    errs = check_dependencies(tasks)
    assert any("unknown dependency demo-t99" in e for e in errs)
    assert any("cycle" in e and "demo-t01" in e and "demo-t02" in e for e in errs)


def test_acyclic_graph_has_no_errors():
    tasks = {t.id: t for t in parse_text(plan_text(TASK))}
    assert check_dependencies(tasks) == []


def test_duplicate_ids_rejected():
    body = TASK.replace("id: demo-t02", "id: demo-t01").replace("depends_on: [demo-t01]", "depends_on: []")
    errs = validate_tasks(parse_text(plan_text(body)))
    assert "duplicate task id demo-t01" in errs


def test_cross_plan_dependency_resolves(repo, monkeypatch, capsys):
    from factory.cli import main
    other = TASK.replace("demo-t0", "other-t0").replace("depends_on: [other-t01]", "depends_on: [demo-t02]")
    (repo / "docs/plans/demo/other.md").write_text(plan_text(other))
    monkeypatch.chdir(repo)
    assert main(["validate-plan", "docs/plans/demo/other.md"]) == 0
    (repo / "docs/plans/demo/other.md").write_text(plan_text(other.replace("demo-t02", "nowhere-t01")))
    assert main(["validate-plan", "docs/plans/demo/other.md"]) == 1
    assert "unknown dependency nowhere-t01" in capsys.readouterr().out
