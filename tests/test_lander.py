"""The lander: a read-only agent role that reviews one factory PR at its head against the trunk.

Everything here is real (LangChain agents and tools, git, SQLite) except the LLM — a scripted
model that plays the lander — and GitHub: land-t04 passes the PR, the gate table, the checks,
the PR's comments and the lander's earlier findings in, so this suite fetches nothing."""

import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from factory import agents, config as C, flows, lander, prices
from factory.agents import load_role, parse_land_verdict, prompt_source, role_model, step_limit
from factory.cli import main
from factory.contracts import parse_text
from factory.db import ROLES, open_db

from conftest import DEMO_CONFIG, git, plan_text
from fake_model import call

PACKAGE = Path(__file__).resolve().parents[1] / "factory"


class ScriptedLander(BaseChatModel):
    """Plays the lander: one reply per model call, repeating the last when the script runs out,
    and recording every request it is sent and every tool binding it gets. The `plays` sinks are
    shared across instances, as ScriptedModel's are, so a reask's fresh model keeps the state."""

    plays: dict

    def __init__(self, **data):
        plays = data.get("plays")
        super().__init__(**data)
        if isinstance(plays, dict):
            object.__setattr__(self, "plays", plays)

    @property
    def _llm_type(self) -> str:
        return "scripted-lander"

    def bind_tools(self, tools, **kwargs):
        self.plays.setdefault("_tools", []).append([getattr(t, "name", str(t)) for t in tools])
        self.plays.setdefault("_binds", []).append(dict(kwargs))
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        self.plays.setdefault("_seen", []).append(list(messages))
        script = self.plays.get("LANDER") or [AIMessage("VERDICT: MERGE")]
        at = self.plays.get("_at", 0)
        self.plays["_at"] = at + 1
        return ChatResult(generations=[ChatGeneration(message=script[min(at, len(script) - 1)])])


@pytest.fixture
def pr(repo):
    """A repo whose checkout sits at the PR head: one commit past the fork point, while the trunk
    moved on after it, so a diff against the merge base is not a diff against the trunk tip."""
    git(repo, "checkout", "-q", "-b", "factory/demo-t01")
    (repo / "src").mkdir()
    (repo / "src" / "greet.txt").write_text("hello\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "Add the greeting")
    head = git(repo, "rev-parse", "HEAD")
    git(repo, "checkout", "-q", "main")
    (repo / "trunk-only.txt").write_text("the trunk moved on after the PR branched\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "The trunk moves on")
    base = git(repo, "merge-base", "main", "factory/demo-t01")
    git(repo, "checkout", "-q", "factory/demo-t01")
    return SimpleNamespace(root=repo, head=head, trunk="main", base=base)


def _board(home, attempts=3):
    """The task under review, on the board with its open PR at its head."""
    db = open_db(home)
    task = parse_text(plan_text(), "docs/plans/demo/demo.md")[0]
    db.upsert_task(task)
    db.update(task.id, attempts=attempts, status="pr_open")
    return db, task


def _pr_inputs(**over):
    """The lander's inputs as land-t04 passes them: the PR's URL, title and body, the trunk and
    head, the gate table at the head, the checks with their conclusions, the build reviewer's last
    report, the PR's conversation and inline comments (each with its author), earlier findings."""
    inputs = dict(
        url="https://github.test/demo/repo/pull/7",
        title="Add the greeting module",
        body="## What changed\n- src/greet.txt says hello\n\n"
             "## What to check\n- the greeting is the one the contract asks for",
        trunk="main",
        head="a9" * 20,
        gates="| Gate | Result | Detail |\n|---|---|---|\n| verification | pass | exit=0 tests=1 |",
        checks=[("unit tests", "SUCCESS"), ("e2e (rust)", "FAILURE")],
        review_report="## Findings\n1. [minor] fine as far as the diff shows\n\nVERDICT: APPROVE",
        conversation=[("alice", "Please also cover the empty greeting."), ("pat", "And the sad path.")],
        inline_comments=[("bob", "src/greet.txt:1 — this should say hello")],
        earlier_findings="1. [major] tests/test_greet.py:3 asserts the wrong greeting",
    )
    return {**inputs, **over}


def _review(pr, monkeypatch, db, task, script, cfg, record):
    """Run the lander over the PR with a scripted model; returns its Review and the plays."""
    plays = {"LANDER": list(script), "_tools": [], "_binds": [], "_seen": [], "_at": 0}
    monkeypatch.setattr(agents, "build_model", lambda spec: ScriptedLander(plays=plays))
    out = lander.review(root=pr.root, db=db, task=task, worktree=pr.root, cfg=cfg,
                        merge_base=pr.base, record=record, log=lambda *a: None,
                        **_pr_inputs(head=pr.head))
    return out, plays


def test_lander_prompt_matches_land_verdict_parser(repo):
    """The land prompt ships with its model and step limit, asks for the MERGE/HOLD verdict the
    land verdict parser reads, and tells the lander what to judge: whether this PR, at this head,
    can go into the trunk without a human — the acceptance criteria and non-goals at this head,
    the PR's What to check items, comments answered, no unrelated edits or weakened tests."""
    meta, body = load_role(repo, "land")
    assert meta == {"model": "openrouter:z-ai/glm-5.3", "max_steps": 40}
    assert "You are the LANDER" in body
    for phrase in ("trunk", "human", "acceptance criteri", "non-goal", "What to check",
                   "comment", "unrelated", "weaken", "exactly one line"):
        assert phrase.lower() in body.lower(), phrase
    assert "VERDICT: MERGE" in body and "VERDICT: HOLD" in body
    # ... and the parser reads what the prompt asks for: the last VERDICT line decides
    assert parse_land_verdict("## Findings\n1. [minor] fine\n\nVERDICT: MERGE") == "MERGE"
    assert parse_land_verdict("## Findings\n1. [major] the greeting is wrong\n\nVERDICT: HOLD") == "HOLD"
    assert parse_land_verdict("VERDICT: MERGE\n\nOn reflection.\n\nVERDICT: HOLD") == "HOLD"
    assert parse_land_verdict("VERDICT: HOLD\n\nOn reflection.\n\nVERDICT: MERGE") == "MERGE"
    assert parse_land_verdict("Still checking the trunk; no verdict yet.") is None   # no verdict
    assert parse_land_verdict("VERDICT: SHIP") is None                              # not a verdict it can give


def test_the_land_role_can_be_configured_overridden_and_printed(repo, monkeypatch, capsys):
    """`land` maps to lander.md, a repository's .factory/agents/lander.md overrides it, and
    `factory prompt land` prints the prompt in effect. The model resolves as `--model` >
    `models.land` > the prompt's frontmatter > the default, `max_steps.land` likewise.
    `land` and `lander` are reserved step names, and db.ROLES records `land` runs."""
    assert agents.ROLE_FILES["land"] == "lander"
    assert prompt_source(repo, "land") == PACKAGE / "prompts" / "lander.md"
    assert "land" in flows.RESERVED and "lander" in flows.RESERVED
    assert "land" in ROLES

    meta, _ = load_role(repo, "land")
    cfg = C.parse({"models": {"land": "anthropic:claude-opus-5-5"}, "max_steps": {"land": 7}})
    assert role_model(repo, "land", cfg) == "anthropic:claude-opus-5-5"          # models.land
    assert role_model(repo, "land", cfg, "openai:gpt-x") == "openai:gpt-x"       # --model beats it all
    assert role_model(repo, "land", C.parse({})) == "openrouter:z-ai/glm-5.3"     # else the prompt's frontmatter
    assert step_limit(flows.Step("land", "land"), cfg, meta) == 7                # max_steps.land
    assert step_limit(flows.Step("land", "land"), C.parse({}), meta) == 40       # else the frontmatter
    for name in ("land", "lander"):          # neither can name a flow step: the lander is not a flow
        with pytest.raises(C.ConfigError, match="reserved"):
            C.parse({"flows": {"myflow": ["build", {"name": name, "kind": "review"}, "verify"]}})

    d = repo / ".factory" / "agents"          # a repository's override wins
    d.mkdir()
    (d / "lander.md").write_text("---\nmodel: openrouter:a/override\nmax_steps: 3\n---\nYou are our LANDER.\n")
    assert load_role(repo, "land") == ({"model": "openrouter:a/override", "max_steps": 3},
                                       "You are our LANDER.\n")
    monkeypatch.chdir(repo)
    assert main(["prompt", "land"]) == 0
    out = capsys.readouterr().out
    assert "lander.md" in out and "You are our LANDER." in out and "model openrouter:a/override" in out

    (d / "lander.md").write_text("You are our LANDER, briefly.\n")    # no frontmatter model: the default
    assert load_role(repo, "land") == ({}, "You are our LANDER, briefly.\n")
    assert role_model(repo, "land", C.parse({})) == agents.DEFAULT_MODEL
    assert step_limit(flows.Step("land", "land"), C.parse({}), {}) == 60


def test_the_message_holds_the_pr_gates_checks_comments_and_earlier_findings():
    """The lander's task message is built from what it is given, and a section with nothing in it
    is marked `(none)`."""
    inputs = _pr_inputs()
    msg = lander.message(**inputs)
    for text in (inputs["url"], inputs["title"],
                 "src/greet.txt says hello", "the greeting is the one the contract asks for",
                 inputs["trunk"], inputs["head"], "| verification | pass | exit=0 tests=1 |",
                 "unit tests", "SUCCESS", "e2e (rust)", "FAILURE",
                 "## Findings\n1. [minor] fine as far as the diff shows",
                 "alice", "Please also cover the empty greeting.", "pat", "And the sad path.",
                 "bob", "src/greet.txt:1 — this should say hello",
                 "1. [major] tests/test_greet.py:3 asserts the wrong greeting"):
        assert text in msg, text
    assert "(none)" not in msg                                  # every section holds something
    for section, empty in (("body", ""), ("gates", ""), ("checks", []), ("review_report", ""),
                           ("conversation", []), ("inline_comments", []), ("earlier_findings", "")):
        assert "(none)" in lander.message(**{**inputs, section: empty}), section


def test_the_lander_gets_read_tools_and_the_diff_against_the_trunk_only(pr, home, monkeypatch):
    """The lander runs in the given worktree at the PR head with the read tools and `git_diff`
    against the merge base with the trunk — no write or run tools — under its configured model and
    step limit, on the task message `message(...)` builds."""
    db, task = _board(home)
    toolsets, real = [], agents.create_agent
    monkeypatch.setattr(agents, "create_agent",
                        lambda model, tools, **kw: (toolsets.append([t.name for t in tools])
                                                    or real(model, tools, **kw)))
    events = []
    out, _ = _review(pr, monkeypatch, db, task,
                     [call("git_diff", stat=True),
                      AIMessage("## Findings\n1. [minor] fine\n\nVERDICT: MERGE")],
                     cfg=C.load(pr.root), record=events.append)
    assert out.decision == "MERGE"
    assert toolsets[0] == ["read_file", "list_dir", "grep", "git_diff"]      # the read tools and the diff
    assert all("write_file" not in ts and "edit_file" not in ts and "run" not in ts for ts in toolsets)
    diff = next(e for e in events if e["type"] == "tool" and e["name"] == "git_diff")
    assert "src/greet.txt" in diff["content"]            # the PR's change at its head…
    assert "trunk-only.txt" not in diff["content"]        # …diffed against the merge base, not the trunk tip
    system = next(e for e in events if e["type"] == "system")
    assert system["model"] == "openrouter:z-ai/glm-5.3" and system["max_steps"] == 40
    human = next(e for e in events if e["type"] == "human")["content"]
    assert lander.message(**_pr_inputs(head=pr.head)).strip() in human    # the lander's task message


def test_the_last_verdict_decides_and_a_missing_one_is_asked_for_once(pr, home, monkeypatch):
    """The last VERDICT line decides. A review that stops at its step limit without a verdict
    gets one more call without tools, and a verdict still missing is asked for once more in the
    same conversation, as for the reviewer; still missing, the decision is no verdict."""
    db, task = _board(home)
    (pr.root / ".factory/config.yaml").write_text(DEMO_CONFIG + "max_steps:\n  land: 2\n")
    cfg = C.load(pr.root)

    def run(script):
        events = []
        out, plays = _review(pr, monkeypatch, db, task, script, cfg=cfg, record=events.append)
        return out, plays, events

    no_verdict = AIMessage("## Findings\n1. [major] still checking the trunk")

    out, _, _ = run([AIMessage("VERDICT: MERGE\n\nOn reflection.\n\nVERDICT: HOLD")])
    assert out.decision == "HOLD"                        # the last VERDICT line decides
    out, _, _ = run([AIMessage("## Findings\n1. [minor] fine\n\nVERDICT: HOLD\n\nOn reflection: VERDICT: MERGE")])
    assert out.decision == "MERGE"

    out, plays, events = run([call("read_file", path="AGENTS.md"),
                               AIMessage("## Findings\n\nnone\n\nVERDICT: MERGE")])
    assert out.decision == "MERGE" and len(plays["_seen"]) == 2     # a verdict needs no extra call
    assert not any(e["type"] == "reask" for e in events)

    out, plays, events = run([call("read_file", path="AGENTS.md"),
                              call("grep", pattern="greet", path="src"),
                              no_verdict,
                              AIMessage("## Findings\n1. [minor] fine now\n\nVERDICT: MERGE")])
    assert out.decision == "MERGE"
    assert len(plays["_seen"]) == 4                    # 2 in the run + one closing call + the one ask
    assert any(e["type"] == "stopped" and e["reason"] == "step limit" for e in events)
    assert any(e["type"] == "nudge" and e.get("kind") == "verdict" for e in events)
    assert sum(e["type"] == "reask" for e in events) == 1
    assert any(b.get("tool_choice") == "none" for b in plays["_binds"])    # the closing call runs no tool
    first, closing, ask = plays["_seen"][0], plays["_seen"][2], plays["_seen"][3]
    assert closing[0] == first[0] and closing[1] == first[1]                # …in the same conversation,
    assert ask[0] == first[0] and ask[1] == first[1]                        # as the ask is too
    assert isinstance(closing[-1], HumanMessage) and closing[-1] != first[-1]
    assert isinstance(ask[-1], HumanMessage) and ask[-1] != first[-1]
    assert any(isinstance(m, AIMessage) and "still checking" in m.text for m in ask)

    out, _, events = run([call("read_file", path="AGENTS.md"),
                          call("grep", pattern="greet", path="src"),
                          no_verdict, no_verdict, no_verdict, no_verdict])
    assert out.decision is None                       # still missing: the decision is no verdict
    assert sum(e["type"] == "reask" for e in events) == 1              # asked once, never twice


def test_each_review_is_recorded_as_a_land_run_on_its_head(pr, home, monkeypatch):
    """Every review is a run with role `land`, step `review`, outcome merge, hold or no_verdict,
    the sha of the head it judged, and its report, model, prompt version, tokens and cost —
    and a review changes no status (land-t04 and land-t05 do that)."""
    db, task = _board(home, attempts=3)
    monkeypatch.setattr(prices, "cost", lambda *a, **k: 0.5)

    def review(script):
        return _review(pr, monkeypatch, db, task, script, cfg=C.load(pr.root),
                       record=lambda event: None)[0]

    report = "## Findings\n1. [minor] the greeting holds\n\nVERDICT: MERGE"
    out = review([call("git_diff", stat=True),
                  AIMessage(report, usage_metadata={"input_tokens": 100, "output_tokens": 40,
                                                    "total_tokens": 140})])
    assert (out.decision, out.report) == ("MERGE", report)
    row = next(r for r in db.runs(task.id) if r["role"] == "land")
    assert (row["step"], row["outcome"], row["sha"]) == ("review", "merge", pr.head)
    assert row["report"] == report
    assert row["model"] == "openrouter:z-ai/glm-5.3"
    assert re.fullmatch(r"[0-9a-f]{12}", row["prompt_version"])
    assert row["attempt"] == 3                        # the attempt under review, as other roles' runs
    assert (row["tokens_in"], row["tokens_out"]) == (100, 40)
    assert row["cost_usd"] == 1.0                     # 0.5 per model call, two calls
    assert db.task(task.id)["status"] == "pr_open"    # a review changes no status

    out = review([AIMessage("## Findings\n1. [major] src/greet.txt:1 needs the other greeting\n\n"
                            "VERDICT: HOLD")])
    assert out.decision == "HOLD"
    row = [r for r in db.runs(task.id) if r["role"] == "land"][-1]
    assert (row["step"], row["outcome"], row["sha"]) == ("review", "hold", pr.head)

    (pr.root / ".factory/config.yaml").write_text(DEMO_CONFIG + "max_steps:\n  land: 1\n")
    out = review([call("read_file", path="AGENTS.md")] + [AIMessage("still checking the trunk")] * 4)
    assert out.decision is None
    row = [r for r in db.runs(task.id) if r["role"] == "land"][-1]
    assert (row["step"], row["outcome"], row["sha"]) == ("review", "no_verdict", pr.head)
    assert db.task(task.id)["status"] == "pr_open"    # still no status change