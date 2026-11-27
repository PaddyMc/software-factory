"""`factory land --dry-run`: what each open factory PR waits for before it can land on the trunk.

`land.readiness` judges one task from its board row, its contract and the PR as `gh pr view`
reports it (state, mergeability, head, checks, base, changed files), with no model call: ready,
`waits` with a reason (the factory will act later) or `human` with a reason (only a person can
move it). The dry run prints one line per open factory PR of the selected plans, in plan order,
and changes nothing: no refresh, no comment, no merge, no model, the board untouched.
"""

import json
import re

import pytest

from factory import config as C
from factory import land
from factory.cli import main
from factory.contracts import parse_text
from factory.db import open_db
from conftest import git, plan_text

TRUNK = "dev"                      # the configured trunk; land.release is main
HEAD = "c" * 40                    # the candidate the factory built and pushed
PUSHED = "f" * 40                  # a commit someone else pushed to the PR's branch
URL = "https://github.test/pr/1"
# The demo plan's two tasks: demo-t01 (risk low) and demo-t02 (risk high, depends on demo-t01).
TASKS = {t.id: t for t in parse_text(plan_text(), "docs/plans/demo/demo.md")}


def _cfg(require_checks=True, guidance=("AGENTS.md", "CLAUDE.md")):
    return C.parse({"trunk": TRUNK, "guidance": list(guidance),
                    "land": {"release": "main", "require_checks": require_checks}})


def _check(name, conclusion="SUCCESS", status="COMPLETED"):
    return {"__typename": "CheckRun", "workflowName": "factory", "name": name,
            "status": status, "conclusion": conclusion, "detailsUrl": ""}


def _status(context, state):
    return {"__typename": "StatusContext", "context": context, "state": state, "targetUrl": ""}


GREEN = [_check("tests"), _check("fmt")]


def _pr(base=TRUNK, head=HEAD, mergeable="MERGEABLE", rollup=GREEN, files=("src/greet.txt",),
        state="OPEN"):
    """The PR as `gh pr view` reports it: state, mergeability, head, checks, base, changed files."""
    return {"state": state, "mergeable": mergeable, "headRefOid": head, "statusCheckRollup": list(rollup),
            "baseRefName": base, "files": [{"path": p} for p in files]}


def _row(home, tid="demo-t01", **fields):
    """The task's board row as `readiness` sees it: an open PR on the trunk at the candidate."""
    db = open_db(home)
    for t in TASKS.values():
        db.upsert_task(t)
    db.update(tid, **{"status": "pr_open", "candidate_sha": HEAD, "pr_url": URL,
                      "base_ref": TRUNK, "trunk": TRUNK, **fields})
    return db.task(tid)


# -------------------------------------------------------------------------- readiness, one task

def test_a_pr_on_the_trunk_with_green_checks_is_ready(tmp_path):
    row, task = _row(tmp_path / "a"), TASKS["demo-t01"]
    assert land.readiness(row, task, _pr(), _cfg()) == ("ready", None)

    # a finished check that says nothing about the change (cancelled) is not a failure
    assert land.readiness(row, task, _pr(rollup=[_check("tests"), _check("fmt", "CANCELLED")]), _cfg()) == \
        ("ready", None)

    # with land.require_checks: false, a head with no checks at all counts as checked
    assert land.readiness(row, task, _pr(rollup=[]), _cfg(require_checks=False)) == ("ready", None)

    # anything but pr_open waits on the board's note, whatever GitHub says about the PR
    for status in ("conflict", "ci_failed", "changes_requested"):
        note = f"{status}: fixed by a run"
        assert land.readiness(_row(tmp_path / status, status=status, note=note), task, _pr(), _cfg()) == \
            ("waits", f"{status}: {note}")


def test_stacked_prs_wait_for_their_dependency(tmp_path):
    task = TASKS["demo-t02"]                # depends on demo-t01; the board says the PR is stacked on it
    stacked = {"stacked_on": "demo-t01", "base_ref": "factory/demo-t01"}
    row = _row(tmp_path / "a", "demo-t02", **stacked)
    assert land.readiness(row, task, _pr(base="factory/demo-t01"), _cfg()) == \
        ("waits", "stacked on demo-t01")

    # the stack is what it waits for, whatever else the PR looks like
    worse = _pr(base="factory/demo-t01", mergeable="CONFLICTING", rollup=[_check("fmt", "FAILURE")])
    assert land.readiness(row, task, worse, _cfg()) == ("waits", "stacked on demo-t01")
    # ... and only its status comes first
    moved = _row(tmp_path / "b", "demo-t02", status="ci_failed", note="CI fails on its head", **stacked)
    assert land.readiness(moved, task, _pr(base="factory/demo-t01"), _cfg()) == \
        ("waits", "ci_failed: CI fails on its head")


def test_pending_failed_or_missing_checks_and_unknown_mergeability_wait(tmp_path):
    row, task = _row(tmp_path / "a"), TASKS["demo-t01"]

    # GitHub hasn't computed mergeability yet: wait, whatever the checks say
    for rollup in (GREEN, [_check("fmt", "FAILURE")]):
        assert land.readiness(row, task, _pr(mergeable="UNKNOWN", rollup=rollup), _cfg()) == \
            ("waits", "GitHub hasn't computed mergeability yet")

    # a conflict with the trunk waits too, before anything the checks say
    running = [_check("tests"), _check("fmt", None, status="IN_PROGRESS")]
    assert land.readiness(row, task, _pr(mergeable="CONFLICTING", rollup=running), _cfg()) == \
        ("waits", f"conflicts with {TRUNK}")

    # checks still running: how many of the head's checks are pending
    assert land.readiness(row, task, _pr(rollup=running + [_check("e2e", None, status="QUEUED")]), _cfg()) == \
        ("waits", "CI running (2 of 3 checks pending)")
    # a pending check outranks one that failed
    assert land.readiness(row, task, _pr(rollup=running + [_check("e2e", "FAILURE")]), _cfg()) == \
        ("waits", "CI running (1 of 3 checks pending)")

    # failed checks, none pending
    assert land.readiness(row, task, _pr(rollup=[_check("tests"), _check("fmt", "FAILURE"),
                                                _check("e2e", "TIMED_OUT")]), _cfg()) == \
        ("waits", "CI failed (factory / fmt, factory / e2e)")
    # ... including a failed status context
    assert land.readiness(row, task, _pr(rollup=[_status("ci/external", "FAILURE")]), _cfg()) == \
        ("waits", "CI failed (ci/external)")

    # no checks on the head at all, while the config requires at least one
    assert land.readiness(row, task, _pr(rollup=[]), _cfg()) == ("waits", "no CI checks on its head yet")


def test_a_pushed_head_or_a_pr_on_another_base_waits_for_a_human(tmp_path):
    row, task = _row(tmp_path / "a"), TASKS["demo-t01"]

    # someone else pushed to the PR's branch: the head isn't the factory's candidate
    assert land.readiness(row, task, _pr(head=PUSHED), _cfg()) == ("human", "someone else pushed to it")
    # ... before GitHub's mergeability is even read
    assert land.readiness(row, task, _pr(head=PUSHED, mergeable="UNKNOWN"), _cfg()) == \
        ("human", "someone else pushed to it")

    # a PR on another branch targets somewhere else — even when the trunk the task was built on
    # is not the configured one
    elsewhere = _row(tmp_path / "b", trunk="main", base_ref="main")
    for pr in (_pr(base="main"), _pr(base="main", head=PUSHED), _pr(base="main", mergeable="UNKNOWN")):
        assert land.readiness(elsewhere, task, pr, _cfg()) == \
            ("human", f"targets main, not the trunk {TRUNK}")


def test_risk_high_and_steering_paths_wait_for_a_human(tmp_path):
    low, high = TASKS["demo-t01"], TASKS["demo-t02"]
    row = _row(tmp_path / "a")

    # a high-risk contract is a human's call, once everything else is ready
    assert land.readiness(_row(tmp_path / "b", "demo-t02"), high, _pr(), _cfg()) == ("human", "risk: high")

    # so is a change under .factory/ or .github/, or to a guidance file
    assert land.readiness(row, low, _pr(files=("docs/x.md", ".factory/agents/lander.md")), _cfg()) == \
        ("human", "changes .factory/agents/lander.md")
    assert land.readiness(row, low, _pr(files=(".github/workflows/ci.yml", ".factory/config.yaml")), _cfg()) == \
        ("human", "changes .github/workflows/ci.yml")
    # the first such path in the PR's files is the one named
    assert land.readiness(row, low, _pr(files=("src/ok.txt", "AGENTS.md", ".github/x.yml")), _cfg()) == \
        ("human", "changes AGENTS.md")
    # only paths under those directories count, and only the config's guidance files do
    assert land.readiness(row, low, _pr(files=(".factoryrc", "src/x.py")), _cfg()) == ("ready", None)
    assert land.readiness(row, low, _pr(files=("CLAUDE.md",)), _cfg(guidance=("AGENTS.md",))) == ("ready", None)

    # the contract's risk comes before the files it changes, and neither outranks an unready PR
    assert land.readiness(_row(tmp_path / "c", "demo-t02"), high,
                          _pr(files=(".factory/config.yaml",)), _cfg()) == ("human", "risk: high")
    assert land.readiness(_row(tmp_path / "d", "demo-t02"), high,
                          _pr(rollup=[_check("fmt", "FAILURE")]), _cfg()) == \
        ("waits", "CI failed (factory / fmt)")


# ------------------------------------------------------------------------ factory land --dry-run

LAND_CONFIG = f"trunk: {TRUNK}\nland:\n  release: main\n"
BASE = "d" * 40                       # where the trunk was when each task branched off
H1, H2, H3, H4, H5, H6 = ("a" * 40, "b" * 40, "e" * 40, "3" * 40, "4" * 40, "5" * 40)
OPEN = ("alpha-t02", "alpha-t01", "alpha-t03", "zoo-t01")   # the open factory PRs, in plan order
ZOO_NOTE = "a review requests changes (@alice): `factory run zoo-t01` addresses them"


def _contract(tid, goal, depends=()):
    return (f"- id: {tid}\n"
            f"  goal: \"{goal}\"\n"
            f"  spec_refs: []\n"
            f"  depends_on: [{', '.join(depends)}]\n"
            f"  non_goals: []\n"
            f"  acceptance: [\"{goal} done\"]\n"
            f"  verification: [\"true\"]\n"
            f"  risk: low\n")


ALPHA = (_contract("alpha-t02", "Second thing first") +
         _contract("alpha-t01", "First thing, second in its plan") +
         _contract("alpha-t03", "Stacked on its dependency", ("alpha-t02",)))
ZOO = (_contract("zoo-t01", "A review still requests changes") +
       _contract("zoo-t02", "Merged already") +
       _contract("zoo-t03", "Still queued"))
SOLO = _contract("solo-t01", "Merged, nothing open")


@pytest.fixture
def land_repo(repo, home, fake_gh, monkeypatch):
    """A repo on the dev trunk with land configured, three plans (alpha, solo, zoo — discovered in
    that order), a board row per task and each PR on GitHub. The dry run reads exactly these."""
    monkeypatch.chdir(repo)
    (repo / ".factory/config.yaml").write_text(LAND_CONFIG)
    (repo / "docs/plans/demo/demo.md").unlink()          # this repo has only the plans below
    tasks = []
    for name, body in (("alpha", ALPHA), ("solo", SOLO), ("zoo", ZOO)):
        (repo / f"docs/plans/{name}").mkdir()
        (repo / f"docs/plans/{name}/{name}.md").write_text(plan_text(body))
        tasks += parse_text(plan_text(body), f"docs/plans/{name}/{name}.md")
    db = open_db(home)
    for t in tasks:
        db.upsert_task(t)
    db.update("alpha-t02", status="pr_open", candidate_sha=H1, base_ref=TRUNK, base_sha=BASE,
              trunk=TRUNK, pr_url="https://github.test/pr/1")
    db.update("alpha-t01", status="pr_open", candidate_sha=H2, base_ref=TRUNK, base_sha=BASE,
              trunk=TRUNK, pr_url="https://github.test/pr/2")
    db.update("alpha-t03", status="pr_open", candidate_sha=H3, base_ref="factory/alpha-t02",
              base_sha=H1, trunk=TRUNK, stacked_on="alpha-t02", pr_url="https://github.test/pr/3")
    db.update("zoo-t01", status="changes_requested", candidate_sha=H4, base_ref=TRUNK, base_sha=BASE,
              trunk=TRUNK, pr_url="https://github.test/pr/4", note=ZOO_NOTE)
    db.update("zoo-t02", status="merged", candidate_sha=H5, base_ref=TRUNK, trunk=TRUNK,
              pr_url="https://github.test/pr/5")
    db.update("solo-t01", status="merged", candidate_sha=H6, base_ref=TRUNK, trunk=TRUNK,
              pr_url="https://github.test/pr/6")

    def gh_pr(number, base, head, state="OPEN", files=("src/a.txt",)):
        return {"url": f"https://github.test/pr/{number}", "state": state, "base": base,
                "baseRefName": base, "mergeable": "MERGEABLE", "headRefOid": head,
                "commits": [{"oid": head}], "statusCheckRollup": GREEN,
                "files": [{"path": p} for p in files]}

    fake_gh.write_text(json.dumps({"calls": [], "prs": {
        "factory/alpha-t02": gh_pr(1, TRUNK, H1),
        "factory/alpha-t01": gh_pr(2, TRUNK, H2, files=("src/b.txt", ".factory/config.yaml")),
        "factory/alpha-t03": gh_pr(3, "factory/alpha-t02", H3),
        "factory/zoo-t01": gh_pr(4, TRUNK, H4),
        "factory/zoo-t02": gh_pr(5, TRUNK, H5, state="MERGED"),
        "factory/solo-t01": gh_pr(6, TRUNK, H6, state="MERGED"),
    }}))
    git(repo, "push", "-q", "origin", f"main:refs/heads/{TRUNK}")   # the trunk exists on origin
    git(repo, "branch", "-q", TRUNK)
    return repo


def _pr_lines(text, ids=OPEN):
    """The dry run's PR lines, in the order they printed."""
    return [l for l in text.splitlines() if l.split()[:1] and l.split()[0] in ids]


def _shape(line, tid, verdict, url):
    """One dry-run line: the task id, `ready` or the reason, then the PR URL, in that order."""
    assert re.fullmatch(rf"{re.escape(tid)}\s+{re.escape(verdict)}\s+{re.escape(url)}", line.rstrip()), \
        f"expected `{tid} … {verdict} … {url}`, got {line!r}"


def test_dry_run_prints_each_open_pr_and_changes_nothing(land_repo, home, fake_gh, capsys):
    db = open_db(home)
    board = [dict(r) for r in db.tasks()]
    github = json.loads(fake_gh.read_text())

    assert main(["land", "--dry-run"]) == 0
    out = capsys.readouterr()
    text = out.out + out.err
    # one line per open factory PR, in plan order (not task id order): alpha's tasks in the plan's
    # order, then zoo's
    lines = _pr_lines(text)
    assert [l.split()[0] for l in lines] == list(OPEN)
    _shape(lines[0], "alpha-t02", "ready", "https://github.test/pr/1")
    _shape(lines[1], "alpha-t01", "waits for a human: changes .factory/config.yaml",
           "https://github.test/pr/2")
    _shape(lines[2], "alpha-t03", "waits: stacked on alpha-t02", "https://github.test/pr/3")
    _shape(lines[3], "zoo-t01", f"waits: changes_requested: {ZOO_NOTE}", "https://github.test/pr/4")
    # merged, queued and PR-less tasks have no open factory PR
    assert not _pr_lines(text, ("zoo-t02", "zoo-t03", "solo-t01"))

    # it changes nothing: the board and its runs are untouched, and GitHub saw reads only —
    # no refresh, no comment, no merge, no model call
    assert [dict(r) for r in db.tasks()] == board
    assert list(db.conn.execute("SELECT * FROM runs")) == []
    calls = json.loads(fake_gh.read_text())["calls"]
    assert calls and all(c[:2] in (["pr", "view"], ["pr", "list"]) for c in calls)
    assert json.loads(fake_gh.read_text())["prs"] == github["prs"]

    # --plan selects plans, repeats, and --no-sandbox is accepted
    assert main(["land", "--dry-run", "--plan", "alpha"]) == 0
    out = capsys.readouterr()
    assert [l.split()[0] for l in _pr_lines(out.out + out.err)] == \
        ["alpha-t02", "alpha-t01", "alpha-t03"]
    assert main(["land", "--dry-run", "--plan", "alpha", "--plan", "zoo", "--no-sandbox"]) == 0
    out = capsys.readouterr()
    assert [l.split()[0] for l in _pr_lines(out.out + out.err)] == list(OPEN)

    # a plan whose tasks are all merged has no open factory PR
    assert main(["land", "--dry-run", "--plan", "solo"]) == 0
    out = capsys.readouterr()
    assert "no open factory PRs" in out.out + out.err
    assert not _pr_lines(out.out + out.err)

    # and so does a board where nothing is open any more, on GitHub as on the board
    for tid in OPEN:
        db.update(tid, status="merged")
    state = json.loads(fake_gh.read_text())
    state["prs"] = {head: {**pr, "state": "MERGED"} for head, pr in state["prs"].items()}
    fake_gh.write_text(json.dumps(state))
    assert main(["land", "--dry-run"]) == 0
    out = capsys.readouterr()
    assert "no open factory PRs" in out.out + out.err
    assert not _pr_lines(out.out + out.err)


def test_land_refuses_without_land_config(repo, home, fake_gh, monkeypatch, capsys):
    monkeypatch.chdir(repo)      # the fixture's config has no land: block

    assert main(["land", "--dry-run"]) == 1
    text = capsys.readouterr()
    assert "land: is not configured in .factory/config.yaml: factory land merges only into a " \
           "configured trunk" in text.out + text.err
    assert main(["land"]) == 1
    text = capsys.readouterr()
    assert "land: is not configured in .factory/config.yaml" in text.out + text.err

    # with land: configured, --plan must name a plan file
    (repo / ".factory/config.yaml").write_text(LAND_CONFIG)
    assert main(["land", "--dry-run", "--plan", "nope"]) == 1
    text = capsys.readouterr()
    assert "nope is not a plan (a plan's file name without .md)" in text.out + text.err

    # ... and an existing plan with an empty board is a dry run with nothing to land
    assert main(["land", "--dry-run", "--plan", "demo"]) == 0
    text = capsys.readouterr()
    assert "no open factory PRs" in text.out + text.err
