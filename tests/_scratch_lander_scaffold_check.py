"""SCRATCH - delete after running: checks tests/test_lander.py's scaffolding against the real
reviewer machinery, which the lander is specified to mirror ('as for the reviewer')."""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "tests")

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from conftest import git, plan_text
from fake_model import call
from factory import agents
from factory.contracts import parse_text
from factory.flows import Step


class ScriptedLander(BaseChatModel):
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


r = Path(tempfile.mkdtemp()) / "repo"
(r / "docs/plans/demo").mkdir(parents=True)
(r / "docs/plans/demo/demo.md").write_text(plan_text())
(r / "AGENTS.md").write_text("# Demo repo\n")
(r / ".factory/agents").mkdir(parents=True)
(r / ".factory/agents/reviewer.md").write_text(
    "---\nmodel: fake:x\nmax_steps: 2\n---\nYou are the REVIEWER.\n\n"
    "End with exactly one line, VERDICT: APPROVE or VERDICT: CHANGES.\n")
git(r, "init", "-q", "-b", "main")
git(r, "add", "-A")
git(r, "commit", "-q", "-m", "init")
git(r, "checkout", "-q", "-b", "factory/demo-t01")
(r / "src").mkdir()
(r / "src/greet.txt").write_text("hello\n")
git(r, "add", "-A")
git(r, "commit", "-q", "-m", "Add the greeting")
base = git(r, "rev-parse", "main")

task = parse_text(plan_text(), "docs/plans/demo/demo.md")[0]
events = []
plays = {"LANDER": [call("git_diff", stat=True), call("read_file", path="AGENTS.md"),
                    AIMessage("## Findings\n1. [major] still checking"),
                    AIMessage("## Findings\n1. [minor] fine now\n\nVERDICT: APPROVE")],
         "_tools": [], "_binds": [], "_seen": [], "_at": 0}
agents.build_model = lambda spec: ScriptedLander(plays=plays)
roles = agents.LangChainRoles(r)
ctx = agents.Ctx(task=task, worktree=r, base_sha=base, attempt=1, sandbox=None,
                 record=events.append,
                 log=lambda tag, msg: events.append({"type": "log", "tag": tag, "msg": msg}))
out = roles.step(Step("review", "review"), ctx)

print("verdict", out.verdict, "| steps", out.steps, "| stopped", out.stopped, "| reasked", out.reasked)
print("model", out.model, "| prompt_version", out.prompt_version)
print("seen requests:", len(plays["_seen"]))
for i, b in enumerate(plays["_binds"]):
    print("  bind", i, "tool_choice=", b.get("tool_choice"), "tools=", plays["_tools"][i])
kinds = [(e["type"], e.get("kind") or e.get("reason")) for e in events
         if e["type"] in ("stopped", "nudge", "reask")]
print("events:", kinds)
first, closing, ask = plays["_seen"][0], plays["_seen"][2], plays["_seen"][3]
print("closing same conv:", closing[0] == first[0], closing[1] == first[1],
      "| human ask:", isinstance(closing[-1], HumanMessage), closing[-1] != first[-1])
print("ask same conv:", ask[0] == first[0], ask[1] == first[1],
      "| human ask:", isinstance(ask[-1], HumanMessage), ask[-1] != first[-1])
print("ask holds the no-verdict reply:",
      any(isinstance(m, AIMessage) and "still checking" in m.text for m in ask))
tools_events = [(e["name"], e["content"][:60]) for e in events if e["type"] == "tool"]
print("tool results:", tools_events)