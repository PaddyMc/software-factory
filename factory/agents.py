"""The agent steps of a flow (LangChain `create_agent`), each of one of the four kinds. Prompts ship in
factory/prompts/<role>.md; a repository may override one with .factory/agents/<role>.md, give a custom step
its own .factory/agents/<step>.md, and set models and step limits in .factory/config.yaml."""

from __future__ import annotations

import datetime as dt
from importlib import resources
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
from .flows import Flow, Step
from .log import NullLog, clip
from .tools import PathGuard, ToolLog, diff_tool, read_tools, run_tool, write_tools

OVERRIDE_DIR = ".factory/agents"                 # per-repository prompt overrides, in the main checkout
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
    review_brief: str = ""                  # review only: the review-rework brief, whose requests are in scope
    earlier: tuple[str, ...] = ()           # build steps after the first: the earlier build steps' final messages
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
    def step(self, step: Step, ctx: Ctx, tag: str | None = None, message: str | None = None) -> Output: ...
    def plan(self, ctx: Ctx) -> Output: ...
    def build(self, ctx: Ctx) -> Output: ...
    def resolve(self, ctx: Ctx) -> Output: ...
    def review(self, ctx: Ctx) -> Output: ...
    def verify(self, ctx: Ctx) -> Output: ...


def parse_verdict(text: str) -> str:
    """Last VERDICT line; anything else (missing, malformed) fails safe to CHANGES."""
    found = _VERDICT.findall(text)
    return found[-1] if found else "CHANGES"


def prompt_source(root: Path, role: str):
    """The repository's override if it has one, else the prompt shipped with the factory."""
    override = root / OVERRIDE_DIR / f"{ROLE_FILES[role]}.md"
    return override if override.is_file() else resources.files("factory") / "prompts" / f"{ROLE_FILES[role]}.md"


def step_prompt_source(root: Path, step: Step):
    """A custom step's own prompt (.factory/agents/<name>.md) when it exists, else its kind's prompt."""
    if step.name != step.kind:
        own = root / OVERRIDE_DIR / f"{step.name}.md"
        if own.is_file():
            return own
    return prompt_source(root, step.kind)


def _load_prompt(path) -> tuple[dict, str]:
    text = path.read_text()
    m = _FRONTMATTER.match(text)
    return (yaml.safe_load(m.group(1)) or {}, text[m.end():]) if m else ({}, text)


def load_role(root: Path, role: str) -> tuple[dict, str]:
    return _load_prompt(prompt_source(root, role))


def load_step(root: Path, step: Step) -> tuple[dict, str]:
    return _load_prompt(step_prompt_source(root, step))


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
        rules.append(f"Add a session log entry as a NEW file `{cfg.session_log.rstrip('/')}/<today>-<task id>.md` "
                     "(what changed, files, commands run). Don't edit other log files: one file per task keeps "
                     "parallel tasks from conflicting. The session_log gate fails without it.")
    if cfg.e2e:
        kind = "a `#[test]` (or `#[tokio::test]`) function" if cfg.e2e.language == "rust" else "a `def test_*` function"
        rules.append(f"Every task adds at least one NEW end-to-end test: {kind} in a file directly under "
                     f"`{cfg.e2e.dir}`. The e2e_written gate fails without one, and the e2e_tests gate runs it by name.")
    if cfg.unit_tests:
        rules.append("The unit_tests gate runs: " + "; ".join(f"`{c}`" for c in cfg.unit_tests) + ".")
    rules.append("The contract's verification commands must pass. A test command that selects zero tests fails.")
    return "# Project rules (enforced by the factory's gates)\n\n" + _bullets(rules)


def role_model(root: Path, role: str, cfg: Config, override: str | None = None) -> str:
    """`--model` > the config's `models` > the prompt's frontmatter > the default."""
    return override or cfg.models.get(role) or load_role(root, role)[0].get("model", DEFAULT_MODEL)


def role_models(root: Path, override: str | None = None, cfg: Config | None = None) -> dict[str, str]:
    cfg = cfg or Config()
    return {role: role_model(root, role, cfg, override) for role in ROLE_FILES}


def step_model(root: Path, step: Step, cfg: Config, override: str | None = None) -> str:
    """`--model` > the step's `model` > the config's `models[kind]` > the prompt's frontmatter > the default."""
    return override or step.model or cfg.models.get(step.kind) or load_step(root, step)[0].get("model", DEFAULT_MODEL)


def step_limit(step: Step, cfg: Config, meta: dict) -> int:
    """The step's `max_steps` > the config's `max_steps[kind]` > the prompt's frontmatter > 60."""
    return int(step.max_steps or cfg.max_steps.get(step.kind) or meta.get("max_steps", 60))


def flow_models(root: Path, flow: Flow, cfg: Config, override: str | None = None) -> dict[str, str]:
    """The model each agent step of a flow resolves to, by step name (a gates step has no model)."""
    return {s.name: step_model(root, s, cfg, override) for s in flow.steps if s.kind != "gates"}


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

    def step(self, step: Step, ctx: Ctx, tag: str | None = None, message: str | None = None) -> Output:
        """Run one flow step: its kind's tools and task message, its own prompt, model and step limit.
        `tag`/`message` override the defaults (resolve runs a build step under its own tag and message)."""
        meta, instructions = load_step(self.root, step)
        spec = step_model(self.root, step, self.cfg, self.model_override)
        steps = step_limit(step, self.cfg, meta)
        system = "\n\n".join(x for x in [
            instructions.strip(), contract_block(ctx.task), project_rules(self.cfg),
            f"Today: {dt.date.today().isoformat()}. Worktree root is the tools' working directory.",
            _repo_guidance(ctx.worktree, self.cfg.guidance)] if x)
        tools, default_message, log = self._kit(step, ctx)
        message = message if message is not None else default_message
        agent = create_agent(
            (self.model_factory or build_model)(spec), tools, system_prompt=system,
            middleware=[ModelCallLimitMiddleware(run_limit=steps, exit_behavior="end"),
                        ModelRetryMiddleware(**MODEL_RETRY, on_failure="error"), tool_errors(ctx.worktree)],
        )
        tag = tag or (f"{step.name}#{ctx.attempt}" if step.kind in ("build", "review") else step.name)
        ctx.log(tag, f"start ({spec}, max {steps} steps)")
        if step.kind == "review" and "VERDICT:" not in instructions:
            ctx.log(tag, f"⚠ {step.name}'s prompt has no VERDICT: line; every review will count as CHANGES")
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
            ctx.log(tag, f"⚠ stopped: {out.stopped} after {out.steps} steps (raise max_steps for this role in .factory/config.yaml)")
            ctx.record({"type": "stopped", "reason": out.stopped, "steps": out.steps})
        cost = f", ${out.cost_usd:.4f}" if out.cost_usd is not None else ""
        refused = f", {out.refused} tool calls refused" if out.refused else ""
        ctx.log(tag, f"done: {out.steps} steps, {out.tokens_in} tokens in / {out.tokens_out} out{cost}{refused}")
        if log is not None:
            out.log = log
        if step.kind == "review":
            out.verdict = parse_verdict(out.text)
        return out

    def _kit(self, step: Step, ctx: Ctx) -> tuple[list, str, ToolLog | None]:
        """A step kind's tools and task message (exactly what its role method builds today), plus the
        build kind's ToolLog, attached to the Output after the run."""
        guard = self._guard(ctx)
        if step.kind == "plan":
            return read_tools(ctx.worktree, guard), f"Plan task {ctx.task.id}.", None
        if step.kind == "build":
            log = ToolLog()
            tools = (read_tools(ctx.worktree, guard) + write_tools(ctx.worktree, guard, log)
                     + run_tool(ctx.sandbox, log, self.cfg.denied_commands))
            msg = f"Implement task {ctx.task.id} (attempt {ctx.attempt}).\n\n# Plan\n\n{ctx.plan}"
            if ctx.feedback:
                msg += f"\n\n# Feedback to address first\n\n{ctx.feedback}"
            if ctx.earlier:
                seen = "\n\n".join(f"{i}. {m}" for i, m in enumerate(ctx.earlier, 1))
                msg += f"\n\n# Earlier build steps in this attempt\n\n{seen}"
            return tools, msg, log
        if step.kind == "review":
            tools = read_tools(ctx.worktree, guard) + diff_tool(ctx.worktree, ctx.base_sha)
            msg = f"Review the change for task {ctx.task.id}. Start with git_diff(stat=True)."
            if ctx.review_brief:
                msg += (
                    f"\n\n# Human review to address\n\nThe task's PR was reviewed, and those requests are in scope for "
                    f"this change even where they go beyond the plan, the goal or the non-goals. Judge whether each "
                    f"request was addressed; any request left unaddressed is a reason for VERDICT: CHANGES.\n\n"
                    f"{ctx.review_brief}"
                )
            return tools, msg, None
        if step.kind == "verify":
            tools = (read_tools(ctx.worktree, guard) + diff_tool(ctx.worktree, ctx.base_sha)
                     + run_tool(ctx.sandbox, ToolLog(), self.cfg.denied_commands))
            return tools, f"All gates passed for task {ctx.task.id}. Write the PR report.\n\n# Gates\n\n{ctx.gates}", None
        raise ValueError(f"step {step.name}: kind {step.kind!r} has no agent (gates run outside the agents)")

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
        return self.step(Step("plan", "plan"), ctx)

    def build(self, ctx: Ctx) -> Output:
        return self.step(Step("build", "build"), ctx)

    def resolve(self, ctx: Ctx) -> Output:
        """The builder, resolving a replayed change's conflicts."""
        msg = f"Resolve the merge conflicts of task {ctx.task.id}.\n\n{ctx.resolution}\n\n# The task's plan\n\n{ctx.plan}"
        return self.step(Step("build", "build"), ctx, tag="resolve", message=msg)

    def review(self, ctx: Ctx) -> Output:
        return self.step(Step("review", "review"), ctx)

    def verify(self, ctx: Ctx) -> Output:
        return self.step(Step("verify", "verify"), ctx)
