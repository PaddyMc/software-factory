"""End to end: a fresh build makes sequential candidates, gates them, and carries one forward."""

import json
import random
import re
import shutil

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from factory import agents, pipeline, prices
from factory.cli import main
from factory.db import open_db
from conftest import DEMO_CONFIG, git, plan_text
from fake_model import E2E, ScriptedModel, call, scripts

SKIP = "unit_tests,e2e_tests"
SANDBOX = [] if shutil.which("bwrap") else ["--no-sandbox"]


@pytest.fixture
def factory_repo(repo, home, fake_gh, monkeypatch):
    agents_dir = repo / ".factory/agents"
    agents_dir.mkdir(parents=True)
    for role in ("planner", "builder", "reviewer", "verifier"):
        (agents_dir / f"{role}.md").write_text(
            f"---\nmodel: fake:{role}\nmax_steps: 20\n---\nYou are the {role.upper()} for one task.\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "agents")
    git(repo, "push", "-q", "origin", "main")
    monkeypatch.setenv("FAKE_API_KEY", "x")
    monkeypatch.setitem(agents.PROVIDER_KEYS, "fake", "FAKE_API_KEY")
    monkeypatch.setenv("OPENROUTER_API_KEY", "x")     # the shipped selector prompt's model
    monkeypatch.chdir(repo)
    return repo


def _use_model(monkeypatch, plays):
    monkeypatch.setattr(agents, "build_model", lambda spec: ScriptedModel(plays=plays))
    return plays["_calls"]


class CandidatesModel(ScriptedModel):
    """Give each fresh builder conversation the next candidate's script."""

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        system = next(m.content for m in messages if isinstance(m, SystemMessage))
        if "You are the BUILDER" in system:
            if "_seen" in self.plays:
                self.plays["_seen"].append(list(messages))
            if not any(isinstance(m, AIMessage) for m in messages) and self.plays.get("_builders"):
                counter = self.plays["_builder_counter"]
                number = counter[0]
                builders = self.plays["_builders"]
                self.plays["_current_builder"][0] = builders[min(number, len(builders) - 1)]
                counter[0] += 1
            if self.plays.get("_current_builder"):
                self.plays["BUILDER"] = self.plays["_current_builder"][0]
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


def _use_candidates(monkeypatch, plays):
    monkeypatch.setattr(agents, "build_model", lambda spec: CandidatesModel(plays=plays))
    return plays["_calls"]


def _flow_config(repo, yaml_tail):
    (repo / ".factory/config.yaml").write_text(DEMO_CONFIG + yaml_tail)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "config: candidates")
    git(repo, "push", "-q", "origin", "main")


def _candidate(number, greeting="hello", session=True, extra=()):
    """A complete candidate, with its sandbox's working directory committed as evidence."""
    script = [
        call("write_file", path="src/greet.txt", content=f"{greeting}\n"),
        call("write_file", path="crates/e2e/tests/greet.rs", content=E2E),
        call("write_file", path="docs/sessions/2026-10-09.md",
             content=f"## [12:00] demo-t01 candidate {number}\n") if session else
        call("read_file", path="src/greet.txt"),
        call("run", command="pwd > where.txt"),
        *extra,
        AIMessage(f"Candidate {number} finished with {greeting}.\nRESULT: DONE"),
    ]
    return script


def _candidate_plays(builders, verdicts=("APPROVE",)):
    plays = scripts(review_verdicts=list(verdicts))
    plays["_builders"] = builders
    plays["_builder_counter"] = [0]
    plays["_current_builder"] = [None]
    return plays


def _change(path, text="changed\n", message="Made the requested change."):
    return [call("write_file", path=path, content=text), AIMessage(message + "\nRESULT: DONE")]


def _no_candidate_worktrees(home):
    assert not list((home / "worktrees").glob("demo-t01.c*"))


def _tested_flow(repo):
    (repo / ".factory/agents/tester.md").write_text(
        "---\nmodel: fake:tester\nmax_steps: 20\n---\nYou are the TESTER for one task.\n")
    (repo / "tests").mkdir(exist_ok=True)
    (repo / "tests/__init__.py").write_text("")
    plan = repo / "docs/plans/demo/demo.md"
    plan.write_text(plan.read_text().replace(
        'verification: ["grep -q hello src/greet.txt"]',
        'verification: ["grep -q hello src/greet.txt", "python3 -m unittest tests.test_greet"]'))
    _flow_config(repo, "test_paths: ['tests/**']\nflow: tested-many\nflows:\n  tested-many:\n"
                       "    - plan\n    - test\n    - {kind: build, candidates: 2}\n"
                       "    - gates\n    - review\n    - verify\n")


def test_each_candidate_builds_in_its_own_worktree_from_the_same_start(factory_repo, home, fake_gh, monkeypatch):
    _tested_flow(factory_repo)
    plays = _candidate_plays([_candidate(1), _candidate(2)])
    _use_candidates(monkeypatch, plays)
    assert main(["run", "demo-t01", "--skip-gates", SKIP, *SANDBOX]) == 0

    db = open_db(home)
    assert db.task("demo-t01")["status"] == "pr_open"
    runs = db.runs("demo-t01")
    assert [(r["role"], r["step"], r["attempt"], r["candidate"]) for r in runs] == [
        ("plan", "plan", 0, None), ("test", "test", 1, None),
        ("build", "build", 1, 1), ("verify", "gates", 1, 1),
        ("build", "build", 1, 2), ("verify", "gates", 1, 2),
        ("select", "select", 1, None),                     # two passed: the selector picks between them
        ("review", "review", 1, None), ("verify", "verify", 1, None), ("pr", "pr", 1, None),
    ]
    assert [r["outcome"] for r in runs if r["candidate"] is not None] == ["committed", "pass"] * 2
    builds = [r for r in runs if r["role"] == "build"]
    test_sha = next(r["sha"] for r in runs if r["role"] == "test")
    for build in builds:
        assert git(factory_repo, "rev-parse", f"{build['sha']}^") == test_sha
    assert git(factory_repo, "show", f"{builds[0]['sha']}:where.txt") == str(home / "worktrees/demo-t01")
    assert git(factory_repo, "show", f"{builds[1]['sha']}:where.txt") == str(home / "worktrees/demo-t01.c2")

    messages = []
    for build in builds:
        events = [json.loads(line) for line in open(build["transcript"])]
        human = [event["content"] for event in events if event["type"] == "human"]
        assert len(human) == 1
        messages.append(human[0])
    assert messages[0] == messages[1]
    assert "# Plan" in messages[0] and "write them" in messages[0]
    log = (home / "logs/demo-t01.log").read_text()
    assert "build#1.2" in log and "gates#1.2" in log
    _no_candidate_worktrees(home)


def test_the_smallest_passing_candidate_is_chosen(factory_repo, home, fake_gh, monkeypatch):
    _flow_config(factory_repo, "flow: many\nflows:\n  many:\n    - plan\n"
                               "    - {kind: build, candidates: 4}\n    - gates\n    - review\n    - verify\n")
    big = [call("write_file", path="big.txt", content="".join(f"line {i}\n" for i in range(12)))]
    plays = _candidate_plays([_candidate(1, extra=big), _candidate(2), _candidate(3), _candidate(4, greeting="bye")])
    _use_candidates(monkeypatch, plays)
    assert main(["run", "demo-t01", "--skip-gates", SKIP, *SANDBOX]) == 0

    db = open_db(home)
    row = db.task("demo-t01")
    builds = [r for r in db.runs("demo-t01") if r["role"] == "build"]
    chosen = builds[1]["sha"]
    assert row["status"] == "pr_open" and row["candidate_sha"] == chosen
    assert "chose candidate 2 of 4 (3 passed the gates; smallest diff)" in \
        (home / "logs/demo-t01.log").read_text()
    assert all(git(factory_repo, "rev-parse", f"{r['sha']}^") == row["base_sha"] for r in builds)
    assert git(factory_repo, "show", f"{chosen}:src/greet.txt") == "hello"
    assert "big.txt" not in git(factory_repo, "diff", "--name-only", f"{row['base_sha']}..{chosen}")
    review = next(r for r in db.runs("demo-t01") if r["role"] == "review")
    assert review["sha"] == chosen and review["candidate"] is None
    assert git(factory_repo, "ls-remote", "origin", "refs/heads/factory/demo-t01").split()[0] == chosen
    _no_candidate_worktrees(home)


def test_when_none_pass_the_closest_candidate_carries_on(factory_repo, home, fake_gh, monkeypatch):
    _flow_config(factory_repo, "flow: many\nflows:\n  many:\n    - plan\n"
                               "    - {kind: build, candidates: 3, loop: [resume]}\n"
                               "    - gates\n    - review\n    - verify\n")
    first, second, third = (_candidate(1, greeting="bye"), _candidate(2, greeting="bye"),
                            _candidate(3, greeting="bye", session=False))
    # All three fresh conversations have five AI messages. The last script's continuation is used
    # when the carried conversation resumes, regardless of which candidate the factory carries.
    third += [call("write_file", path="src/greet.txt", content="hello\n"),
              AIMessage("Fixed the carried candidate.\nRESULT: DONE")]
    plays = _candidate_plays([first, second, third])
    plays["_seen"] = []
    _use_candidates(monkeypatch, plays)
    assert main(["run", "demo-t01", "--skip-gates", SKIP, "--max-attempts", "2", *SANDBOX]) == 0

    db = open_db(home)
    row = db.task("demo-t01")
    builds = [r for r in db.runs("demo-t01") if r["role"] == "build"]
    assert row["status"] == "pr_open" and row["attempts"] == 2
    assert [(r["attempt"], r["candidate"]) for r in builds] == [(1, 1), (1, 2), (1, 3), (2, None)]
    assert git(factory_repo, "rev-parse", f"{builds[-1]['sha']}^") == builds[0]["sha"]
    assert "no candidate passed the gates; candidate 1 of 3 carries on (fewest failing gates)" in \
        (home / "logs/demo-t01.log").read_text()

    events = [json.loads(line) for line in open(builds[-1]["transcript"])]
    assert [event["type"] for event in events[:3]] == ["resumed", "system", "human"]
    feedback = events[2]["content"]
    assert "Verification gates failed: verification" in feedback and "session_log" not in feedback
    resumed = plays["_seen"][-2]
    carried = resumed[1:-1]
    assert isinstance(resumed[0], SystemMessage) and isinstance(resumed[-1], HumanMessage)
    assert any(isinstance(m, AIMessage) and "Candidate 1 finished" in m.text for m in carried)
    assert not any(isinstance(m, AIMessage) and ("Candidate 2 finished" in m.text or
                                                  "Candidate 3 finished" in m.text) for m in carried)
    _no_candidate_worktrees(home)


FMT = {"__typename": "CheckRun", "workflowName": "factory", "name": "rust fmt", "status": "COMPLETED",
       "conclusion": "FAILURE", "detailsUrl": "https://github.test/o/r/actions/runs/11/job/22"}
FMT_LOG = "2026-10-31T10:00:00Z ##[error]the formatting check failed"


def _ci_says(fake_gh, head):
    state = json.loads(fake_gh.read_text())
    state["prs"]["factory/demo-t01"].update(
        commits=[{"oid": "0" * 40}, {"oid": head}], statusCheckRollup=[FMT])
    state.setdefault("logs", {})["22"] = FMT_LOG
    fake_gh.write_text(json.dumps(state))


def _reviews_say(fake_gh, head):
    state = json.loads(fake_gh.read_text())
    review = {"id": 1, "user": {"login": "alice"}, "state": "CHANGES_REQUESTED",
              "body": "Please add a note.", "commit_id": "a" * 40}
    state["prs"]["factory/demo-t01"].update(
        commits=[{"oid": "0" * 40}, {"oid": head}], statusCheckRollup=[], reviews=[review])
    fake_gh.write_text(json.dumps(state))


def _github_says(fake_gh, **fields):
    state = json.loads(fake_gh.read_text())
    state["prs"]["factory/demo-t01"].update(fields)
    fake_gh.write_text(json.dumps(state))


def _new_runs(home, before):
    return [r for r in open_db(home).runs("demo-t01") if r["id"] not in before]


def test_later_attempts_and_reworks_build_one_change(factory_repo, home, fake_gh, monkeypatch, capsys):
    _flow_config(factory_repo, "flow: many\nflows:\n  many:\n    - plan\n"
                               "    - {kind: build, candidates: 2}\n    - gates\n    - review\n    - verify\n")
    plays = _candidate_plays([_candidate(1), _candidate(2), _change("later-attempt.txt")],
                             verdicts=("CHANGES", "APPROVE"))
    _use_candidates(monkeypatch, plays)
    assert main(["run", "demo-t01", "--skip-gates", SKIP, "--max-attempts", "2", *SANDBOX]) == 0
    builds = [r for r in open_db(home).runs("demo-t01") if r["role"] == "build"]
    assert [(r["attempt"], r["candidate"]) for r in builds] == [(1, 1), (1, 2), (2, None)]

    # A CI rework builds once on the PR head, without reviving first-attempt candidates.
    head = open_db(home).task("demo-t01")["candidate_sha"]
    _ci_says(fake_gh, head)
    capsys.readouterr()
    assert main(["status", "--refresh"]) == 0
    assert open_db(home).task("demo-t01")["status"] == "ci_failed"
    plays = scripts(review_verdicts=["APPROVE"])
    plays["BUILDER"] = _change("ci-fix.txt")
    _use_model(monkeypatch, plays)
    before = {r["id"] for r in open_db(home).runs("demo-t01")}
    assert main(["run", "demo-t01", "--skip-gates", SKIP, *SANDBOX]) == 0
    runs = _new_runs(home, before)
    assert sum(r["role"] == "build" for r in runs) == 1
    assert all(r["candidate"] is None for r in runs)

    # The same is true of a human-review rework.
    head = open_db(home).task("demo-t01")["candidate_sha"]
    _reviews_say(fake_gh, head)
    capsys.readouterr()
    assert main(["status", "--refresh"]) == 0
    assert open_db(home).task("demo-t01")["status"] == "changes_requested"
    plays = scripts(review_verdicts=["APPROVE"])
    plays["BUILDER"] = _change("review-note.txt")
    _use_model(monkeypatch, plays)
    before = {r["id"] for r in open_db(home).runs("demo-t01")}
    assert main(["run", "demo-t01", "--skip-gates", SKIP, *SANDBOX]) == 0
    runs = _new_runs(home, before)
    assert sum(r["role"] == "build" for r in runs) == 1
    assert all(r["candidate"] is None for r in runs)

    # A conflict resolution uses the single resolve role, not a fresh set of candidates.
    (factory_repo / "src").mkdir(exist_ok=True)
    (factory_repo / "src/greet.txt").write_text("upstream\n")
    git(factory_repo, "add", "-A")
    git(factory_repo, "commit", "-q", "-m", "conflicting upstream greeting")
    git(factory_repo, "push", "-q", "origin", "main")
    _github_says(fake_gh, mergeable="CONFLICTING")
    capsys.readouterr()
    assert main(["status", "--refresh"]) == 0
    assert open_db(home).task("demo-t01")["status"] == "conflict"
    plays = scripts(review_verdicts=["APPROVE"])
    plays["BUILDER"] = [call("read_file", path="src/greet.txt"),
                        call("write_file", path="src/greet.txt", content="upstream\nhello\n"),
                        AIMessage("Resolved the greeting.\nRESULT: DONE")]
    _use_model(monkeypatch, plays)
    before = {r["id"] for r in open_db(home).runs("demo-t01")}
    assert main(["run", "demo-t01", "--skip-gates", SKIP, *SANDBOX]) == 0
    runs = _new_runs(home, before)
    assert [r["role"] for r in runs].count("resolve") == 1
    assert not any(r["role"] == "build" for r in runs)
    assert all(r["candidate"] is None for r in runs)
    _no_candidate_worktrees(home)


def test_candidate_worktrees_are_removed_however_the_run_ends(factory_repo, home, fake_gh, monkeypatch, capsys):
    _flow_config(factory_repo, "flow: many\nflows:\n  many:\n"
                               "    - {kind: build, candidates: 2}\n    - gates\n    - verify\n")

    _use_candidates(monkeypatch, _candidate_plays([_candidate(1), _candidate(2)]))
    assert main(["run", "demo-t01", "--skip-gates", SKIP, *SANDBOX]) == 0
    _no_candidate_worktrees(home)

    _use_candidates(monkeypatch, _candidate_plays([_candidate(1, greeting="bye"), _candidate(2, greeting="bye")]))
    assert main(["run", "demo-t01", "--force", "--skip-gates", SKIP,
                 "--max-attempts", "1", *SANDBOX]) == 1
    assert open_db(home).task("demo-t01")["status"] == "failed"
    _no_candidate_worktrees(home)

    real_cost = prices.cost
    monkeypatch.setattr(prices, "cost", lambda *args, **kwargs: 1.0)
    _use_candidates(monkeypatch, _candidate_plays([_candidate(1), _candidate(2)]))
    with pytest.raises(Exception, match="cost limit exceeded"):
        main(["run", "demo-t01", "--force", "--skip-gates", SKIP, "--max-cost", "7", *SANDBOX])
    assert "cost limit exceeded" in open_db(home).task("demo-t01")["note"]
    assert (open_db(home).task("demo-t01")["cost_usd"] or 0) > 7
    _no_candidate_worktrees(home)
    monkeypatch.setattr(prices, "cost", real_cost)

    class StopSecondCandidate(CandidatesModel):
        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            system = next(m.content for m in messages if isinstance(m, SystemMessage))
            fresh = not any(isinstance(m, AIMessage) for m in messages)
            if "You are the BUILDER" in system and fresh and self.plays["_builder_counter"][0] == 1:
                raise pipeline.Stopped("test stop")
            return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)

    plays = _candidate_plays([_candidate(1), _candidate(2)])
    monkeypatch.setattr(agents, "build_model", lambda spec: StopSecondCandidate(plays=plays))
    assert main(["run", "demo-t01", "--force", "--skip-gates", SKIP, *SANDBOX]) == 1
    assert "stopped by factory stop" in open_db(home).task("demo-t01")["note"]
    _no_candidate_worktrees(home)

    leftover = home / "worktrees/demo-t01.c2"
    leftover.parent.mkdir(parents=True, exist_ok=True)
    git(factory_repo, "worktree", "add", "-q", "--detach", str(leftover),
        open_db(home).task("demo-t01")["base_sha"])
    assert leftover.exists()
    capsys.readouterr()
    assert main(["clean", "demo-t01"]) == 0
    assert f"removed {leftover}" in capsys.readouterr().out
    _no_candidate_worktrees(home)


def test_show_labels_each_candidate_and_the_chosen_one(factory_repo, home, fake_gh, monkeypatch, capsys):
    _flow_config(factory_repo, "flow: many\nflows:\n  many:\n    - plan\n"
                               "    - {kind: build, candidates: 4}\n    - gates\n    - review\n    - verify\n")
    big = [call("write_file", path="big.txt", content="".join(f"line {i}\n" for i in range(12)))]
    _use_candidates(monkeypatch, _candidate_plays(
        [_candidate(1, extra=big), _candidate(2), _candidate(3), _candidate(4, greeting="bye")]))
    assert main(["run", "demo-t01", "--skip-gates", SKIP, *SANDBOX]) == 0
    capsys.readouterr()
    assert main(["show", "demo-t01"]) == 0
    out = capsys.readouterr().out
    headers = [line for line in out.splitlines() if line.startswith("## ")]
    for number in range(1, 5):
        labelled = [line for line in headers if f"candidate {number} of 4" in line]
        assert len(labelled) == 2
        assert any(line.startswith("## build #1") for line in labelled)
        assert any(line.startswith("## verify #1") and "step gates" in line for line in labelled)
    chosen = [line for line in headers if "chosen" in line]
    assert len(chosen) == 2 and all("candidate 2 of 4" in line for line in chosen)
    for role in ("plan", "review", "pr"):
        assert all("candidate " not in line for line in headers if line.startswith(f"## {role} "))
    verify_report = next(line for line in headers if line.startswith("## verify #1") and "step verify" in line)
    assert "candidate " not in verify_report and "chosen" not in verify_report


class _SelectorSpy(CandidatesModel):
    """Record what the selector is given: its bound tools, its task message and its tools' results."""

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        system = next(m.content for m in messages if isinstance(m, SystemMessage))
        if "You are the SELECTOR" in system:
            self.plays["_selector_tools"] = self.plays["_tools"][-1]
            self.plays.setdefault("_selector_seen", []).append([m.content for m in messages])
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


def _selector_flow(repo, candidates=3):
    _flow_config(repo, "flow: many\nflows:\n  many:\n    - plan\n"
                       f"    - {{kind: build, candidates: {candidates}}}\n    - gates\n    - review\n    - verify\n")


def test_the_selector_picks_among_passing_candidates(factory_repo, home, fake_gh, monkeypatch):
    _selector_flow(factory_repo)
    # Candidate 3 has by far the biggest diff: only the selector's choice can pick it.
    huge = [call("write_file", path="zz.txt",
                 content="".join(f"zz line {i:05d}\n" for i in range(2000)) + "END-OF-ZZ\n")]
    plays = _candidate_plays([_candidate(1, greeting="hello one"), _candidate(2, greeting="hello two"),
                              _candidate(3, greeting="hello three", extra=huge)])
    plays["_choices"] = ["3"]
    monkeypatch.setattr(agents, "build_model", lambda spec: _SelectorSpy(plays=plays))
    assert main(["run", "demo-t01", "--skip-gates", SKIP, *SANDBOX]) == 0

    db = open_db(home)
    row = db.task("demo-t01")
    builds = [r for r in db.runs("demo-t01") if r["role"] == "build"]
    chosen = builds[2]["sha"]
    assert row["status"] == "pr_open" and row["candidate_sha"] == chosen
    assert [(r["role"], r["step"], r["attempt"], r["candidate"]) for r in db.runs("demo-t01")] == [
        ("plan", "plan", 0, None),
        ("build", "build", 1, 1), ("verify", "gates", 1, 1),
        ("build", "build", 1, 2), ("verify", "gates", 1, 2),
        ("build", "build", 1, 3), ("verify", "gates", 1, 3),
        ("select", "select", 1, None),                    # the selector: once, on the attempt
        ("review", "review", 1, None), ("verify", "verify", 1, None), ("pr", "pr", 1, None),
    ]
    assert next(r for r in db.runs("demo-t01") if r["role"] == "review")["sha"] == chosen
    assert "chose candidate 3 of 3 (3 passed the gates; selector)" in (home / "logs/demo-t01.log").read_text()

    # The read tools on the task's worktree at the start commit, and no other tools.
    tools = plays["_selector_tools"]
    assert "read_file" in tools and "write_file" not in tools and "run" not in tools
    listing = plays["_selector_seen"][1][-1]               # the list_dir result the selector read
    assert "AGENTS.md" in listing and "src" not in listing and "zz.txt" not in listing

    # Its message holds every passing candidate: its number, diffstat, diff and gate table.
    message = plays["_selector_seen"][0][-1]
    for number, greeting in ((1, "hello one"), (2, "hello two"), (3, "hello three")):
        assert re.search(rf"(?i)\bcandidate {number}\b", message), number
        assert f"+{greeting}" in message
    assert "4 files changed" in message and "5 files changed" in message
    assert "| verification | PASS |" in message
    assert "zz line 00000" in message and "END-OF-ZZ" not in message   # the diff, capped at DIFF_LIMIT


def test_a_selector_without_a_valid_choice_falls_back_to_the_smallest_diff(factory_repo, home, fake_gh, monkeypatch):
    _selector_flow(factory_repo)
    big = [call("write_file", path="big.txt", content="".join(f"line {i}\n" for i in range(12)))]
    medium = [call("write_file", path="medium.txt", content="a\nb\n")]
    plays = _candidate_plays([_candidate(1, extra=big), _candidate(2), _candidate(3, extra=medium)])
    plays["_choices"] = ["9"]                              # names a candidate the gates never saw
    _use_candidates(monkeypatch, plays)
    assert main(["run", "demo-t01", "--skip-gates", SKIP, *SANDBOX]) == 0

    db = open_db(home)
    row = db.task("demo-t01")
    builds = [r for r in db.runs("demo-t01") if r["role"] == "build"]
    select_runs = [r for r in db.runs("demo-t01") if r["role"] == "select"]
    assert len(select_runs) == 1 and select_runs[0]["outcome"] == "fallback"
    assert row["status"] == "pr_open" and row["candidate_sha"] == builds[1]["sha"]   # the smallest passing diff
    log = (home / "logs/demo-t01.log").read_text()
    assert "selector gave no valid choice: smallest diff" in log
    assert "chose candidate 2 of 3 (3 passed the gates; smallest diff)" in log
    body = json.loads(fake_gh.read_text())["prs"]["factory/demo-t01"]["body"]
    assert "Chosen from 3 candidates (3 passed the gates; smallest diff)" in body


def test_one_passing_candidate_needs_no_selector(factory_repo, home, fake_gh, monkeypatch):
    _selector_flow(factory_repo)
    plays = _candidate_plays([_candidate(1, greeting="bye"), _candidate(2, greeting="bye"), _candidate(3)])
    _use_candidates(monkeypatch, plays)
    assert main(["run", "demo-t01", "--skip-gates", SKIP, *SANDBOX]) == 0

    db = open_db(home)
    row = db.task("demo-t01")
    builds = [r for r in db.runs("demo-t01") if r["role"] == "build"]
    assert row["status"] == "pr_open" and row["candidate_sha"] == builds[2]["sha"]
    assert not any(r["role"] == "select" for r in db.runs("demo-t01"))     # nothing to choose between
    assert all(role != "SELECTOR" for role, _ in plays["_calls"])
    assert "chose candidate 3 of 3 (1 passed the gates; smallest diff)" in (home / "logs/demo-t01.log").read_text()


def test_the_selector_sees_candidates_in_a_seeded_order(factory_repo, home, fake_gh, monkeypatch):
    _selector_flow(factory_repo)
    big = [call("write_file", path="big.txt", content="".join(f"line {i}\n" for i in range(12)))]
    medium = [call("write_file", path="medium.txt", content="a\nb\n")]
    # No `_choices`: the report ends without a CHOICE line, so the run falls back as well.
    plays = _candidate_plays([_candidate(1, extra=big), _candidate(2, extra=medium), _candidate(3)])
    monkeypatch.setattr(agents, "build_model", lambda spec: _SelectorSpy(plays=plays))
    assert main(["run", "demo-t01", "--skip-gates", SKIP, *SANDBOX]) == 0

    db = open_db(home)
    select_run = next(r for r in db.runs("demo-t01") if r["role"] == "select")
    message = plays["_selector_seen"][0][-1]
    order = list(dict.fromkeys(int(n) for n in re.findall(r"(?i)\bcandidate (\d+)\b", message)))
    expected = [1, 2, 3]
    random.Random("demo-t01").shuffle(expected)            # the task id is the shuffle's seed
    assert order == expected

    builds = [r for r in db.runs("demo-t01") if r["role"] == "build"]
    assert select_run["outcome"] == "fallback"             # a missing CHOICE line is no choice either
    assert db.task("demo-t01")["candidate_sha"] == builds[2]["sha"]
    assert "selector gave no valid choice: smallest diff" in (home / "logs/demo-t01.log").read_text()


def test_the_pr_says_how_its_change_was_chosen(factory_repo, home, fake_gh, monkeypatch):
    _selector_flow(factory_repo)
    plays = _candidate_plays([_candidate(1, greeting="hello one"), _candidate(2, greeting="hello two"),
                              _candidate(3, greeting="hello three")])
    plays["_choices"] = ["2"]
    _use_candidates(monkeypatch, plays)
    assert main(["run", "demo-t01", "--skip-gates", SKIP, *SANDBOX]) == 0

    db = open_db(home)
    row = db.task("demo-t01")
    builds = [r for r in db.runs("demo-t01") if r["role"] == "build"]
    assert row["status"] == "pr_open" and row["candidate_sha"] == builds[1]["sha"]
    body = json.loads(fake_gh.read_text())["prs"]["factory/demo-t01"]["body"]
    assert "Chosen from 3 candidates (3 passed the gates; selector)" in body
    assert body.index("## Checks") < body.index("Chosen from 3 candidates") < body.index("Gate table")
