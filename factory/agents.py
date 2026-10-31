"""The four role agents (LangChain `create_agent`), configured from .factory/agents/<role>.md."""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol

import yaml
from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware, ModelRetryMiddleware, ToolErrorMiddleware
from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.errors import GraphRecursionError

from . import prices
from .config import Config
from .contracts import Task
from .log import NullLog, clip
from .tools import PathGuard, ToolLog, diff_tool, read_tools, run_tool, write_tools

AGENTS_DIR = ".factory/agents"
ROLE_FILES = {"plan": "planner", "build": "builder", "review": "reviewer", "verify": "verifier"}
_FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.S)
_VERDICT = re.compile(r"^VERDICT:\s*(APPROVE|CHANGES)\s*$", re.M)
DEFAULT_MODEL = "openrouter:z-ai/glm-5.3"
PROVIDER_KEYS = {"openrouter": "OPENROUTER_API_KEY", "anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}


@dataclass
class Ctx:
    task: Task
    worktree: Path
    base_sha: str
    attempt: int
    sandbox: object
    plan: str = ""
    feedback: str = ""
    gates: str = ""
    resolution: str = ""                    # resolve only: the conflict brief (see pipeline.replay_worktree)
    log: Callable[[str, str], None] = field(default_factory=NullLog)          # (tag, message)
    # (steps, max_steps, tokens_in, tokens_out, cost_usd | None, refused_tool_calls)
    progress: Callable[..., None] = lambda *a: None
    record: Callable[[dict], None] = lambda event: None                        # full transcript event


@dataclass
class Output:
    text: str
    model: str = ""
    verdict: str | None = None              # review only: APPROVE | CHANGES
    log: ToolLog = field(default_factory=ToolLog)
    steps: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float | None = None
    refused: int = 0                         # tool calls refused (paths, denied commands)
    stopped: str | None = None               # why the loop ended early, e.g. "step limit"
    wants_tools: bool = False                # last model call asked for tools (so it was not finished)


class Roles(Protocol):
    def plan(self, ctx: Ctx) -> Output: ...
    def build(self, ctx: Ctx) -> Output: ...
    def resolve(self, ctx: Ctx) -> Output: ...
    def review(self, ctx: Ctx) -> Output: ...
    def verify(self, ctx: Ctx) -> Output: ...


def parse_verdict(text: str) -> str:
    """Last VERDICT line; anything else (missing, malformed) fails safe to CHANGES."""
    found = _VERDICT.findall(text)
    return found[-1] if found else "CHANGES"


def load_role(root: Path, role: str) -> tuple[dict, str]:
    text = (root / AGENTS_DIR / f"{ROLE_FILES[role]}.md").read_text()
    m = _FRONTMATTER.match(text)
    return (yaml.safe_load(m.group(1)) or {}, text[m.end():]) if m else ({}, text)


def build_model(spec: str):
    """`provider:model`, e.g. openrouter:z-ai/glm-5.3, anthropic:claude-opus-5-5, openai:<model>.
    Credentials come from the provider's env var (PROVIDER_KEYS)."""
    kwargs = {"max_tokens": 16000} if spec.startswith("anthropic:") else {}
    return init_chat_model(spec, **kwargs)


def _bullets(items) -> str:
    return "\n".join(f"- {i}" for i in items) or "- (none)"


def contract_block(task: Task) -> str:
    return "\n\n".join([
        f"# Task `{task.id}` (from `{task.plan}`)",
        f"**Goal:** {task.goal}",
        f"**Spec references:**\n{_bullets(task.spec_refs)}",
        f"**Non-goals:**\n{_bullets(task.non_goals)}",
        f"**Acceptance criteria:**\n{_bullets(task.acceptance)}",
        f"**Verification commands:**\n{_bullets(f'`{c}`' for c in task.verification)}",
        f"**Risk:** {task.risk}",
    ])


def _repo_guidance(worktree: Path, files: tuple[str, ...]) -> str:
    """The repository's own agent guidance: the first of `files` (AGENTS.md, CLAUDE.md, …) that exists."""
    for name in files:
        p = worktree / name
        if p.is_file():
            return f"# Repository guidance ({name})\n\n{p.read_text()}"
    return ""


def project_rules(cfg: Config) -> str:
    """What the gates will check beyond the contract, generated from .factory/config.yaml."""
    rules = []
    if cfg.session_log:
        rules.append(f"Add a session log entry to `{cfg.session_log.rstrip('/')}/<today>.md` (what changed, files, "
                     "commands run). The session_log gate fails without it.")
    if cfg.e2e:
        kind = "a `#[test]` (or `#[tokio::test]`) function" if cfg.e2e.language == "rust" else "a `def test_*` function"
        rules.append(f"Every task adds at least one NEW end-to-end test: {kind} in a file directly under "
                     f"`{cfg.e2e.dir}`. The e2e_written gate fails without one, and the e2e_tests gate runs it by name.")
    if cfg.unit_tests:
        rules.append("The unit_tests gate runs: " + "; ".join(f"`{c}`" for c in cfg.unit_tests) + ".")
    rules.append("The contract's verification commands must pass. A test command that selects zero tests fails.")
    return "# Project rules (enforced by the factory's gates)\n\n" + _bullets(rules)


def role_models(root: Path, override: str | None = None) -> dict[str, str]:
    return {role: override or load_role(root, role)[0].get("model", DEFAULT_MODEL) for role in ROLE_FILES}


def missing_keys(models: dict[str, str], env: dict) -> list[str]:
    """Env vars the configured providers need but that are unset (checked before any work starts)."""
    need = {PROVIDER_KEYS.get(spec.split(":", 1)[0]) for spec in models.values()}
    return sorted(k for k in need if k and not env.get(k))


CALL_LIMIT_MARKER = "Model call limits exceeded"
# Provider errors (rate limits, credits held by in-flight requests, DNS blips) are retried with backoff
# (2, 4, 8, 16 s); then the exception ends the run with the real error. The middleware's default
# ("continue") returns the error text as an AIMessage, which the pipeline took for the agent's answer.
MODEL_RETRY = {"max_retries": 4, "initial_delay": 2.0}


def recursion_limit(max_steps: int) -> int:
    """Graph-step backstop for an agent allowed `max_steps` model calls (4 nodes per step + slack)."""
    return 4 * max_steps + 25


def tool_errors(worktree: Path) -> ToolErrorMiddleware:
    """An exception from a tool call (a path that does not exist yet, reading a directory, a timeout…) goes
    back to the model as an `error:` result it can recover from, instead of ending the whole run."""
    roots = {f"{worktree}/", f"{worktree.resolve()}/"}

    def on_error(exc: Exception, request) -> str:
        text = f"error: {type(exc).__name__}: {exc}"
        for r in roots:
            text = text.replace(r, "")
        return text

    return ToolErrorMiddleware(on_error)


class LangChainRoles:
    def __init__(self, root: Path, model_override: str | None = None, model_factory=None, cfg: Config | None = None):
        self.root = root
        self.model_override = model_override
        self.model_factory = model_factory
        self.cfg = cfg or Config()

    def _run(self, role: str, ctx: Ctx, tools: list, message: str, tag: str | None = None) -> Output:
        cfg, instructions = load_role(self.root, role)
        spec = self.model_override or cfg.get("model", DEFAULT_MODEL)
        steps = int(cfg.get("max_steps", 60))
        system = "\n\n".join(x for x in [
            instructions.strip(), contract_block(ctx.task), project_rules(self.cfg),
            f"Today: {dt.date.today().isoformat()}. Worktree root is the tools' working directory.",
            _repo_guidance(ctx.worktree, self.cfg.guidance)] if x)
        agent = create_agent(
            (self.model_factory or build_model)(spec), tools, system_prompt=system,
            middleware=[ModelCallLimitMiddleware(run_limit=steps, exit_behavior="end"),
                        ModelRetryMiddleware(**MODEL_RETRY, on_failure="error"), tool_errors(ctx.worktree)],
        )
        tag = tag or (f"{role}#{ctx.attempt}" if role in ("build", "review") else role)
        ctx.log(tag, f"start ({spec}, max {steps} steps)")
        ctx.record({"type": "system", "model": spec, "max_steps": steps, "content": system})
        ctx.record({"type": "human", "content": message})
        out = Output(text="", model=spec)
        # Each agent step runs 4 graph nodes (call-limit before_model, model, call-limit after_model,
        # tools). ModelCallLimitMiddleware enforces max_steps; the recursion limit is only a backstop
        # and must sit above 4 * steps or a run that finishes on its last step is killed.
        try:
            for update in agent.stream({"messages": [HumanMessage(message)]},
                                       config={"recursion_limit": recursion_limit(steps)}, stream_mode="updates"):
                for payload in update.values():
                    for m in (payload or {}).get("messages", []) if isinstance(payload, dict) else []:
                        self._observe(m, out, tag, ctx)
                ctx.progress(out.steps, steps, out.tokens_in, out.tokens_out, out.cost_usd, out.refused)
        except GraphRecursionError:
            out.stopped = "graph recursion limit"
        if out.stopped is None and out.steps >= steps and out.wants_tools:
            out.stopped = "step limit"
        if out.stopped:
            ctx.log(tag, f"⚠ stopped: {out.stopped} after {out.steps} steps (raise max_steps in .factory/agents/)")
            ctx.record({"type": "stopped", "reason": out.stopped, "steps": out.steps})
        cost = f", ${out.cost_usd:.4f}" if out.cost_usd is not None else ""
        refused = f", {out.refused} tool calls refused" if out.refused else ""
        ctx.log(tag, f"done: {out.steps} steps, {out.tokens_in} tokens in / {out.tokens_out} out{cost}{refused}")
        return out

    @staticmethod
    def _observe(m, out: Output, tag: str, ctx: Ctx) -> None:
        if isinstance(m, AIMessage) and str(m.content).startswith(CALL_LIMIT_MARKER):
            # Injected by ModelCallLimitMiddleware(exit_behavior="end") when max_steps is reached:
            # not a model call and not the agent's answer.
            out.stopped = "step limit"
            return
        if isinstance(m, AIMessage):
            out.steps += 1
            usage = m.usage_metadata or {}
            tin, tout = usage.get("input_tokens", 0), usage.get("output_tokens", 0)
            cached = (usage.get("input_token_details") or {}).get("cache_read", 0) or 0
            out.tokens_in += tin
            out.tokens_out += tout
            out.wants_tools = bool(m.tool_calls)
            step_cost = prices.cost(out.model, tin, tout, cached)
            if step_cost is not None:
                out.cost_usd = (out.cost_usd or 0.0) + step_cost
            ctx.record({"type": "ai", "step": out.steps, "text": m.text,
                        "usage": {"in": tin, "out": tout, "cache_read": cached},
                        "cost_usd": step_cost,
                        "tool_calls": [{"name": tc["name"], "args": tc["args"]} for tc in m.tool_calls]})
            if m.text:
                out.text = m.text.strip()
                ctx.log(tag, "says: " + clip(m.text, 240))
            for tc in m.tool_calls:
                args = ", ".join(f"{k}={clip(v, 60)!s}" for k, v in tc["args"].items() if k != "content")
                ctx.log(tag, f"→ {tc['name']}({args})")
        elif isinstance(m, ToolMessage):
            content = str(m.content)
            if content.startswith("refused"):
                out.refused += 1
            ctx.record({"type": "tool", "name": m.name, "content": content[:200_000]})
            flag = "⚠ " if content.startswith(("refused", "error")) else ""
            ctx.log(tag, f"← {flag}{m.name}: {clip(content, 160) or '(empty)'}")

    def _guard(self, ctx: Ctx) -> PathGuard:
        return PathGuard(ctx.worktree, self.cfg.dependency_dirs())

    def plan(self, ctx: Ctx) -> Output:
        tools = read_tools(ctx.worktree, self._guard(ctx))
        return self._run("plan", ctx, tools, f"Plan task {ctx.task.id}.")

    def build(self, ctx: Ctx) -> Output:
        log = ToolLog()
        guard = self._guard(ctx)
        tools = (read_tools(ctx.worktree, guard) + write_tools(ctx.worktree, guard, log)
                 + run_tool(ctx.sandbox, log, self.cfg.denied_commands))
        msg = f"Implement task {ctx.task.id} (attempt {ctx.attempt}).\n\n# Plan\n\n{ctx.plan}"
        if ctx.feedback:
            msg += f"\n\n# Feedback to address first\n\n{ctx.feedback}"
        out = self._run("build", ctx, tools, msg)
        out.log = log
        return out

    def resolve(self, ctx: Ctx) -> Output:
        """The builder, resolving a replayed change's conflicts."""
        log = ToolLog()
        guard = self._guard(ctx)
        tools = (read_tools(ctx.worktree, guard) + write_tools(ctx.worktree, guard, log)
                 + run_tool(ctx.sandbox, log, self.cfg.denied_commands))
        msg = f"Resolve the merge conflicts of task {ctx.task.id}.\n\n{ctx.resolution}\n\n# The task's plan\n\n{ctx.plan}"
        out = self._run("build", ctx, tools, msg, tag="resolve")
        out.log = log
        return out

    def review(self, ctx: Ctx) -> Output:
        tools = read_tools(ctx.worktree, self._guard(ctx)) + diff_tool(ctx.worktree, ctx.base_sha)
        out = self._run("review", ctx, tools, f"Review the change for task {ctx.task.id}. Start with git_diff(stat=True).")
        out.verdict = parse_verdict(out.text)
        return out

    def verify(self, ctx: Ctx) -> Output:
        tools = (read_tools(ctx.worktree, self._guard(ctx)) + diff_tool(ctx.worktree, ctx.base_sha)
                 + run_tool(ctx.sandbox, ToolLog(), self.cfg.denied_commands))
        return self._run("verify", ctx, tools,
                         f"All gates passed for task {ctx.task.id}. Write the PR report.\n\n# Gates\n\n{ctx.gates}")
