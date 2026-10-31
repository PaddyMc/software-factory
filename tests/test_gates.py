from dataclasses import replace

from factory import config as C
from factory import gates as G
from factory.contracts import parse_plan
from factory.sandbox import Unsandboxed
from conftest import git

E2E = "#[test]\nfn greeting_e2e() {\n    assert!(true);\n}\n"
SKIP = ("unit_tests", "e2e_tests")


def _task(repo):
    return parse_plan(repo / "docs/plans/demo/demo.md", repo)[0]


def _commit(repo, files: dict[str, str]) -> tuple[str, str]:
    base = git(repo, "rev-parse", "HEAD")
    for path, text in files.items():
        p = repo / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "change")
    return base, git(repo, "rev-parse", "HEAD")


def _by_name(gs):
    return {g.name: g for g in gs}


GOOD = {"src/greet.txt": "hello\n", "crates/e2e/tests/greet.rs": E2E, "docs/sessions/2026-10-09.md": "## log\n"}


def test_good_change_passes_all_cheap_gates_and_verification(repo):
    base, sha = _commit(repo, GOOD)
    gs = G.run_gates(_task(repo), repo, base, sha, Unsandboxed(repo), C.load(repo), skip=SKIP)
    assert G.passed(gs), G.table(gs)
    assert _by_name(gs)["e2e_written"].detail == "greet::greeting_e2e"
    assert _by_name(gs)["unit_tests"].ok is None


def test_any_file_may_change_but_the_plan(repo):
    task = _task(repo)
    base, sha = _commit(repo, {**GOOD, "README.md": "x", "Cargo.lock": "x", "docs/plans/demo/demo.md": "edited"})
    g = _by_name(G.run_gates(task, repo, base, sha, Unsandboxed(repo), C.load(repo), skip=SKIP))
    assert "scope" not in g and g["diff"].ok and "lockfile changes: Cargo.lock" in g["diff"].detail
    assert not g["plan_untouched"].ok


def test_a_verification_the_factory_refuses_makes_a_task_manual(repo):
    task = _task(repo)
    cfg = C.load(repo)
    assert G.manual_reason(task, cfg) == ""
    manual = replace(task, verification=("terraform -chdir=infra apply -auto-approve",))
    assert "which the factory refuses; run it by hand" in G.manual_reason(manual, cfg)
    project = replace(task, verification=("kubectl delete ns demo",))
    assert G.manual_reason(project, cfg) == ""
    assert "kubectl delete" in G.manual_reason(project, C.parse({"denied_commands": [r"\bkubectl\s+delete\b"]}))


def test_missing_e2e_and_session_log_fail(repo):
    base, sha = _commit(repo, {"src/greet.txt": "hello\n"})
    g = _by_name(G.run_gates(_task(repo), repo, base, sha, Unsandboxed(repo), C.load(repo), skip=SKIP))
    assert not g["e2e_written"].ok and not g["session_log"].ok


def test_failing_verification_fails(repo):
    base, sha = _commit(repo, {**GOOD, "src/greet.txt": "bye\n"})
    g = _by_name(G.run_gates(_task(repo), repo, base, sha, Unsandboxed(repo), C.load(repo), skip=SKIP))
    assert g["verification"].ok is False and "grep -q hello" in g["verification"].detail


def test_dirty_or_moved_head_fails_clean_gate(repo):
    base, sha = _commit(repo, GOOD)
    (repo / "src/stray.txt").write_text("x")
    assert not _by_name(G.run_gates(_task(repo), repo, base, sha, Unsandboxed(repo), C.load(repo), skip=SKIP))["clean"].ok


def test_new_e2e_parser_finds_async_tests():
    patch = ("+++ b/crates/e2e/tests/net.rs\n+#[tokio::test]\n+async fn joins_cluster() {}\n"
             "+++ b/crates/node/src/x.rs\n+#[test]\n+fn unit() {}\n")
    found = G.new_e2e_tests(patch, C.E2E(dir="crates/e2e/tests/"))
    assert [(t.target, t.name, t.path) for t in found] == [("net", "joins_cluster", "crates/e2e/tests/net.rs")]


class Recorder(Unsandboxed):
    """Runs nothing; records every command and reports one passing test."""
    def __init__(self, repo):
        super().__init__(repo)
        self.cmds = []

    def run(self, cmd, timeout=1800):
        from factory.sandbox import Result
        self.cmds.append(cmd)
        return Result(0, "test result: ok. 1 passed; 0 failed")


def test_without_a_config_only_the_universal_gates_run(repo):
    git(repo, "rm", "-q", ".factory/config.yaml")
    git(repo, "commit", "-q", "-m", "no config")
    base, sha = _commit(repo, {"src/greet.txt": "hello\n"})
    gs = G.run_gates(_task(repo), repo, base, sha, Unsandboxed(repo), C.load(repo))
    assert [g.name for g in gs] == ["clean", "diff", "conflict_markers", "plan_untouched", "verification"]
    assert G.passed(gs), G.table(gs)


def test_new_e2e_tests_run_by_name_and_chain_paths_run_the_suite(repo):
    cfg = C.load(repo)
    base, sha = _commit(repo, GOOD)
    sbx = Recorder(repo)
    G.run_gates(_task(repo), repo, base, sha, sbx, cfg)
    assert sbx.cmds[-2:] == ["cargo test --workspace --exclude demo-e2e",
                             "cargo test -p demo-e2e --test greet greeting_e2e -- --exact"]
    wide = C.parse({**_raw(repo), "e2e": {**_raw(repo)["e2e"], "run_all_when": ["^src/"]}})
    sbx = Recorder(repo)
    G.run_gates(_task(repo), repo, base, sha, sbx, wide)
    assert sbx.cmds[-1] == "cargo test -p demo-e2e"


def test_python_e2e_tests_are_detected_and_run(repo):
    cfg = C.parse({"session_log": "docs/sessions", "e2e": {
        "dir": "crates/e2e/tests", "language": "python", "run_new": "pytest {path}::{name}"}})
    files = {**GOOD, "crates/e2e/tests/test_greet.py": "import os\n\ndef test_greets():\n    assert True\n"}
    del files["crates/e2e/tests/greet.rs"]
    base, sha = _commit(repo, files)
    sbx = Recorder(repo)
    g = _by_name(G.run_gates(_task(repo), repo, base, sha, sbx, cfg))
    assert g["e2e_written"].ok and g["e2e_written"].detail == "test_greet::test_greets"
    assert sbx.cmds[-1] == "pytest crates/e2e/tests/test_greet.py::test_greets"


def _raw(repo):
    import yaml
    return yaml.safe_load((repo / ".factory/config.yaml").read_text())


def test_conflict_markers_fail_the_gate(repo):
    left = {**GOOD, "src/greet.txt": "<<<<<<< HEAD\nhi\n||||||| parent\n=======\nhello\n>>>>>>> abc (task change)\n"}
    base, sha = _commit(repo, left)
    gs = _by_name(G.run_gates(_task(repo), repo, base, sha, Unsandboxed(repo), C.load(repo), skip=SKIP))
    assert gs["conflict_markers"].ok is False
    assert gs["conflict_markers"].detail == "conflict markers left at src/greet.txt:1, src/greet.txt:3, src/greet.txt:6"
    assert G.conflict_markers("+++ b/a.md\n@@ -1 +1,2 @@\n context\n+<<<<<<<< eight is not a marker\n") == []
