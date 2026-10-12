from factory.contracts import discover_plans, load_all
from conftest import plan_text


def test_exclude_docs_user_from_backlog(repo):
    (repo / "docs/user").mkdir(parents=True)
    (repo / "docs/user/idea.md").write_text(plan_text().replace("demo-t0", "idea-t0"))
    plans = [str(p.relative_to(repo)) for p in discover_plans(repo)]
    assert plans == ["docs/plans/demo/demo.md"]
    assert set(load_all(repo)) == {"demo-t01", "demo-t02"}


def test_legacy_plan_without_contracts_yields_no_tasks(repo):
    (repo / "docs/plans/demo/legacy.md").write_text("# Legacy\n\n- [ ] do things\n")
    assert set(load_all(repo)) == {"demo-t01", "demo-t02"}
