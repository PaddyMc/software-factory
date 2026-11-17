"""A scripted chat model standing in for the LLM: it plays each role by reading the
system prompt, so the real LangChain agents, tools, and graph run unchanged."""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult


def call(name: str, **args) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"c-{name}-{len(args)}", "type": "tool_call"}])


E2E = "#[test]\nfn greeting_e2e() {\n    assert!(true);\n}\n"
TEST = "def test_greeting():\n    assert True\n"


def scripts(review_verdicts: list[str], greeting: str = "hello") -> dict[str, list]:
    return {
        "PLANNER": [call("list_dir", path="."), AIMessage("**Files**: src/greet.txt, crates/e2e/tests/greet.rs\n**Steps**: write them")],
        "TESTER": [call("write_file", path="tests/test_greet.py", content=TEST), AIMessage(
            "## Acceptance tests\n- tests/test_greet.py covers the greeting\n\nWrote the tests under tests/**.")],
        "BUILDER": [
            call("write_file", path="src/greet.txt", content=f"{greeting}\n"),
            call("write_file", path="crates/e2e/tests/greet.rs", content=E2E),
            call("write_file", path="docs/sessions/2026-10-09.md", content="## [12:00] demo-t01\n"),
            call("write_file", path=".git/config", content="clobbered"),   # refused by the guard
            call("run", command="grep -q hello src/greet.txt"),
            AIMessage("Wrote the greeting and e2e test.\nRESULT: DONE"),
        ],
        "REVIEWER": [call("git_diff", stat=True), "VERDICT"],
        "VERIFIER": [call("read_file", path="src/greet.txt"), AIMessage(
            "TITLE: Adds the greeting\n\n## What changed\n- src/greet.txt says hello\n\n"
            "## What to check\n- the greeting is the one the contract asks for\n")],
        "_verdicts": list(review_verdicts),
        "_calls": [],
    }


class ScriptedModel(BaseChatModel):
    plays: dict

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        system = next(m.content for m in messages if isinstance(m, SystemMessage))
        role = next(r for r in ("PLANNER", "TESTER", "BUILDER", "REVIEWER", "VERIFIER") if f"You are the {r}" in system)
        step = sum(isinstance(m, AIMessage) for m in messages)
        script = self.plays[role]
        msg = script[min(step, len(script) - 1)]
        if msg == "VERDICT":
            v = self.plays["_verdicts"].pop(0) if self.plays["_verdicts"] else "APPROVE"
            msg = AIMessage(f"## Findings\n1. [minor] ok\n\nVERDICT: {v}")
        self.plays["_calls"].append((role, step))
        return ChatResult(generations=[ChatGeneration(message=msg)])
