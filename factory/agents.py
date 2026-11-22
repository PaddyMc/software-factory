"""The agent steps of a flow (LangChain `create_agent`), each of one of the five kinds. Prompts ship in
factory/prompts/<role>.md; a repository may override one with .factory/agents/<role>.md, give a custom step
its own .factory/agents/<step>.md, and set models and step limits in .factory/config.yaml."""

from __future__ import annotations

import datetime as dt
import hashlib
from importlib import resources
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol

import yaml
from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware, ModelCallLimitMiddleware, ModelRetryMiddleware, ToolErrorMiddleware
from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.messages.utils import count_tokens_approximately
from langgraph.errors import GraphRecursionError

from . import prices, verification
from .config import Config
from .contracts import Task
from .flows import Flow, Step
from .log import NullLog, clip
from .tools import DENIED_COMMANDS, READ_CAP, PathGuard, ToolLog, diff_tool, read_tools, run_tool, write_tools

OVERRIDE_DIR = ".factory/agents"                 # per-repository prompt overrides, in the main checkout
ROLE_FILES = {"plan": "planner", "test": "tester", "build": "builder", "review": "reviewer", "verify": "verifier"}
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
    reviews: dict[str, str] = field(default_factory=dict)  # verify only: cleaned, capped reports by step name
    resolution: str = ""                    # resolve only: the conflict brief (see pipeline.replay_worktree)
    review_brief: str = ""                  # review only: the review-rework brief, whose requests are in scope
    earlier: tuple[str, ...] = ()           # build steps after the first: the earlier build steps' final messages
    test_files: tuple[str, ...] = ()         # build only: acceptance-test files locked at the test commit
    red_commands: tuple[str, ...] = ()       # build only: commands red before the change, green at the candidate
    passing_before: tuple[str, ...] = ()     # test only: the test commands, when every one already passes at base
    log: Callable[[str, str], None] = field(default_factory=NullLog)          # (tag, message)
    # (steps, max_steps, tokens_in, tokens_out, cost_usd | None, refused_tool_calls)
    progress: Callable[..., None] = lambda *a: None
    record: Callable[[dict], None] = lambda event: None                        # full transcript event


@dataclass
class Output:
    text: str
    model: str = ""
    prompt_version: str = ""
    verdict: str | None = None              # review only: APPROVE | CHANGES
    log: ToolLog = field(default_factory=ToolLog)
    steps: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    thinking: int = 0                          # sum of the steps' thinking tokens (output_token_details.reasoning)
    cost_usd: float | None = None
    refused: int = 0                         # tool calls refused (paths, denied commands)
    stopped: str | None = None               # why the loop ended early, e.g. "step limit"
    wants_tools: bool = False                # last model call asked for tools (so it was not finished)


class Roles(Protocol):
    def step(self, step: Step, ctx: Ctx, tag: str | None = None, message: str | None = None) -> Output: ...
    def plan(self, ctx: Ctx) -> Output: ...
    def build(self, ctx: Ctx) -> Output: ...
    def resolve(self, ctx: Ctx, step: Step = Step("build", "build")) -> Output: ...
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


def prompt_version(parts) -> str:
    """First 12 hex characters of the SHA-256 of a step's system prompt without its per-task
    parts (the contract block and the `Today: …` line). Everything else counts — the prompt
    file as loaded, the project rules, the repository guidance, and any part added to the
    system prompt later — so runs under the same instructions share a version."""
    return hashlib.sha256("\n\n".join(p for p in parts if p).encode()).hexdigest()[:12]


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


def proof_rules() -> str:
    """The extra review contract when a step opts into independently reproduced findings."""
    return """# Proof rules (enforced by the factory)

- A blocker or major finding about what the code does when it runs must carry a line `REPRO:` followed by one shell command that fails on the candidate. Run the command with `run` before reporting it.
- A finding about scope — a non-goal done, an acceptance criterion with no change behind it, an unrelated edit, or documentation made untrue — must be tagged `[scope]` and cite `path:line`.
- `VERDICT: CHANGES` counts only with a REPRO that fails again on the candidate or a blocker or major finding tagged `[scope]`. Otherwise the factory records `APPROVE (unproven)` and keeps the findings in its report."""


_REPRO = re.compile(r"^[ \t]*REPRO:[ \t]*(.+?)[ \t]*$", re.M)
_FINDING = re.compile(r"^\s*\d+\.\s*(?:\[(blocker|major|minor)\])?")


def parse_repros(text: str) -> list[str]:
    """The first PROVE_MAX distinct REPRO commands, in their report order."""
    return list(dict.fromkeys(_REPRO.findall(text)))[:PROVE_MAX]


def has_scope_finding(text: str) -> bool:
    """Whether a numbered blocker or major finding carries the scope tag, including on a continuation line."""
    in_finding = False
    for line in text.splitlines():
        finding = _FINDING.match(line)
        if finding:
            in_finding = finding.group(1) in ("blocker", "major")
        elif re.match(r"^(?:#{1,6}\s|VERDICT:)", line):
            in_finding = False
        if in_finding and "[scope]" in line:
            return True
    return False


def run_repros(commands: list[str], sandbox, denied: tuple[str, ...] = ()) -> list[tuple[str, str, str]]:
    """Run each REPRO independently, returning (command, result, output tail) for the Proof section."""
    patterns = DENIED_COMMANDS + tuple(denied)
    results = []
    for command in commands[:PROVE_MAX]:
        pattern = next((pat for pat in patterns if re.search(pat, command)), None)
        if pattern is not None:
            results.append((command, "denied", f"command matches denied pattern {pattern!r}"))
            continue
        result = sandbox.run(command, timeout=PROVE_TIMEOUT)
        output = "\n".join(result.output.splitlines()[-PROOF_OUTPUT_LINES:])
        if result.code == -1 and "timeout" in result.output:
            word = "timed out"
        elif result.code != 0:
            word = "reproduced"
        else:
            word = "passed"
        results.append((command, word, output))
    return results


def proof_section(results: list[tuple[str, str, str]]) -> str:
    """The report's reproducibility evidence, including output even when a command did not reproduce."""
    if not results:
        return ""
    entries = []
    for number, (command, result, output) in enumerate(results, 1):
        entries.append(f"### {number}. `{command}`\n\nResult: **{result}**\n\n"
                       f"```text\n{output or '(no output)'}\n```")
    return "## Proof\n\n" + "\n\n".join(entries)


def apply_proof(text: str, verdict: str, sandbox, denied: tuple[str, ...] = ()) -> tuple[str, str, str]:
    """Re-run a proving review's REPROs and return its augmented report, effective verdict and run outcome."""
    results = run_repros(parse_repros(text), sandbox, denied)
    proof = proof_section(results)
    report = f"{text.rstrip()}\n\n{proof}" if proof else text
    if not _VERDICT.search(text):
        return report, "CHANGES", "CHANGES"
    if verdict == "APPROVE":
        return report, "APPROVE", "APPROVE"
    if any(result == "reproduced" for _, result, _ in results) or has_scope_finding(text):
        return report, "CHANGES", "CHANGES"
    return report, "APPROVE", "APPROVE (unproven)"


def role_model(root: Path, role: str, cfg: Config, override: str | None = None) -> str:
    """`--model` > the config's `models` > the prompt's frontmatter > the default."""
    return override or cfg.models.get(role) or load_role(root, role)[0].get("model", DEFAULT_MODEL)


def role_models(root: Path, override: str | None = None, cfg: Config | None = None) -> dict[str, str]:
    """The original four roles, for callers not running a flow; optional steps use `flow_models`."""
    cfg = cfg or Config()
    return {role: role_model(root, role, cfg, override) for role in ROLE_FILES if role != "test"}


def step_model(root: Path, step: Step, cfg: Config, override: str | None = None) -> str:
    """`--model` > the step's `model` > the config's `models[kind]` > the prompt's frontmatter > the default."""
    return override or step.model or cfg.models.get(step.kind) or load_step(root, step)[0].get("model", DEFAULT_MODEL)


def step_limit(step: Step, cfg: Config, meta: dict) -> int:
    """The step's `max_steps` > the config's `max_steps[kind]` > the prompt's frontmatter > 60."""
    return int(step.max_steps or cfg.max_steps.get(step.kind) or meta.get("max_steps", 60))


def flow_models(root: Path, flow: Flow, cfg: Config, override: str | None = None) -> dict[str, str]:
    """The model each agent step of a flow resolves to, by step name (a gates step has no model)."""
    return {s.name: step_model(root, s, cfg, override) for s in flow.steps if s.kind != "gates"}


def same_model_warning(flow: Flow, models: dict[str, str]) -> str | None:
    """Warn when independently written tests would share a build step's model and blind spots."""
    tests = [s for s in flow.steps if s.kind == "test"]
    builds = [s for s in flow.steps if s.kind == "build"]
    for test in tests:
        for build in builds:
            model = models.get(test.name)
            if model is not None and model == models.get(build.name):
                return (f"⚠ flow {flow.name}: the test step `{test.name}` and the build step `{build.name}` "
                        f"both run on {model}; the tests share the builder's blind spots")
    return None


def missing_keys(models: dict[str, str], env: dict) -> list[str]:
    """Env vars the configured providers need but that are unset (checked before any work starts)."""
    need = {PROVIDER_KEYS.get(spec.split(":", 1)[0]) for spec in models.values()}
    return sorted(k for k in need if k and not env.get(k))


CALL_LIMIT_MARKER = "Model call limits exceeded"
# Provider errors (rate limits, credits held by in-flight requests, DNS blips) are retried with backoff
# (2, 4, 8, 16 s); then the exception ends the run with the real error. The middleware's default
# ("continue") returns the error text as an AIMessage, which the pipeline took for the agent's answer.
MODEL_RETRY = {"max_retries": 4, "initial_delay": 2.0}
TRIM_AT = 60_000      # approximate conversation tokens that trigger a clearing batch
TRIM_KEEP = 8         # most recent tool results kept in full
MAP_LINES = 120       # repository-map lines, including its heading and any truncation line
NUDGE_EDITS = 6       # combined successful writes to one path before an edits nudge
NUDGE_FAILS = 3       # consecutive non-zero exits of one command before a failing nudge
PROVE_MAX = 5         # distinct REPRO commands the factory runs again after a proving review
PROVE_TIMEOUT = 300   # seconds allowed for each REPRO command
PROOF_OUTPUT_LINES = 20
# The closing message of a review that ran out of model calls before its VERDICT line.
VERDICT_CALL = ("You have used every model call this review is allowed, so no tool will run any more. Write "
                "your complete final review now from what you have already checked, in the format your "
                "instructions give, and end it with the VERDICT line. Say what you could not check rather "
                "than guessing.")


def repository_map(worktree: Path, spec_refs: tuple[str, ...]) -> str:
    """A compact map of tracked files and the contract's tracked spec references, or "" outside git."""
    try:
        result = subprocess.run(["git", "ls-files"], cwd=worktree, capture_output=True, text=True)
    except FileNotFoundError:
        return ""
    if result.returncode:
        return ""
    tracked = result.stdout.splitlines()
    files = set(tracked)
    top = [path for path in tracked if "/" not in path]
    counts: dict[str, int] = {}
    for path in tracked:
        parts = path.split("/")
        for depth in range(1, min(2, len(parts) - 1) + 1):
            directory = "/".join(parts[:depth])
            counts[directory] = counts.get(directory, 0) + 1
    directories = sorted(counts)
    lines = ["# Repository map"]
    if top:
        lines.append("  ".join(top))
    lines.extend(f"{directory}/ {counts[directory]} files" for directory in directories)
    if len(lines) > MAP_LINES:
        kept = lines[:max(0, MAP_LINES - 1)]
        kept_directories = max(0, len(kept) - 1 - bool(top))
        lines = kept + [f"… ({len(directories) - kept_directories} more directories)"]
    references = ["# Spec references"]
    for ref in spec_refs:
        path = ref.split("#", 1)[0]
        if path not in files:
            references.append(f"- {ref} (not a file)")
            continue
        line_count = len((worktree / path).read_text(errors="replace").splitlines())
        detail = f"{path}, {line_count} lines" if "#" in ref else f"{line_count} lines"
        references.append(f"- {ref} ({detail})")
    return "\n".join(lines + [""] + references)


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


CLEARED_MARK = "[cleared: "


def _cleared(name, args) -> str:
    details = ", ".join(f"{k}={clip(v, 60)!s}" for k, v in args.items() if k != "content")
    return f"{CLEARED_MARK}{name}({details}): call it again if you need it]"


def _tool_details(messages) -> dict[int, tuple[str, dict]]:
    """Tool result position -> (name, args), paired with its nearest preceding issuing AI message."""
    calls = {}
    details = {}
    for i, m in enumerate(messages):
        if isinstance(m, AIMessage):
            # Ids can be reused: a result belongs to its nearest preceding issuer.
            calls.update({call.get("id"): call for call in m.tool_calls})
        elif isinstance(m, ToolMessage):
            call = calls.get(m.tool_call_id, {})
            details[i] = (m.name or call.get("name") or "tool", call.get("args") or {})
    return details


def _answered(messages) -> list:
    """The conversation without the call-limit marker, ending after a tool result or a plain message:
    a trailing tool call that never ran has no result, and providers reject a request that holds one."""
    kept = [m for m in messages
            if not (isinstance(m, AIMessage) and str(m.content).startswith(CALL_LIMIT_MARKER))]
    while kept and isinstance(kept[-1], AIMessage) and kept[-1].tool_calls:
        kept.pop()
    return kept


class TrimMiddleware(AgentMiddleware):
    """Clear old tool results in the model request, leaving the transcript and graph untouched."""
    def __init__(self, tag: str, ctx: Ctx):
        super().__init__()
        self.tag = tag
        self.ctx = ctx
        self.cleared: set[int] = set()       # message positions: the conversation only appends

    def view(self, messages):
        """The non-system messages with every result cleared so far replaced by its placeholder."""
        messages = [m for m in messages if not isinstance(m, SystemMessage)]
        details = _tool_details(messages)
        return [m.model_copy(update={"content": _cleared(*details[i])})
                if isinstance(m, ToolMessage) and i in self.cleared else m
                for i, m in enumerate(messages)]

    def wrap_model_call(self, request, handler):
        messages = [m for m in request.messages if not isinstance(m, SystemMessage)]
        trimmed = self.view(messages)
        before = count_tokens_approximately(trimmed)
        if before > TRIM_AT:
            results = [i for i, m in enumerate(messages) if isinstance(m, ToolMessage)]
            candidates = results[:max(0, len(results) - TRIM_KEEP)]
            newly = [i for i in candidates if i not in self.cleared]
            if newly:
                self.cleared.update(newly)
                trimmed = self.view(messages)
                after = count_tokens_approximately(trimmed)
                self.ctx.record({"type": "trim", "cleared": len(newly),
                                 "tokens_before": before, "tokens_after": after})
                self.ctx.log(self.tag, f"trim: cleared {len(newly)} tool results ({before} → {after} tokens)")
        if not self.cleared:
            return handler(request)
        return handler(request.override(messages=trimmed))


class NudgeMiddleware(AgentMiddleware):
    """Warn once per budget, repeatedly edited path or repeatedly failing command."""
    def __init__(self, tag: str, ctx: Ctx, max_steps: int, carried_calls: int = 0):
        super().__init__()
        self.tag = tag
        self.ctx = ctx
        self.max_steps = max_steps
        self.carried_calls = carried_calls
        self.budget_nudged = False
        self.nudged_paths: set[str] = set()
        self.nudged_commands: set[str] = set()

    def wrap_model_call(self, request, handler):
        # Trim clears only the outgoing request; the state retains the run's full tool history.
        state = getattr(request, "state", None) or {}
        history = state.get("messages") or request.messages
        messages = [m for m in history if not isinstance(m, SystemMessage)]
        nudges: list[tuple[str, str]] = []
        used = max(0, sum(isinstance(m, AIMessage) and not str(m.content).startswith(CALL_LIMIT_MARKER)
                          for m in messages) - self.carried_calls)
        threshold = (3 * self.max_steps + 3) // 4
        if used >= threshold and not self.budget_nudged:
            self.budget_nudged = True
            nudges.append(("budget", f"You have used {used} of {self.max_steps} allowed model calls. "
                                     "Finish your changes, run your checks and write your final report."))

        edits: dict[str, int] = {}
        failures: dict[str, int] = {}
        for i, (name, args) in _tool_details(messages).items():
            content = str(messages[i].content)
            if name in ("write_file", "edit_file"):
                prefix = "wrote " if name == "write_file" else "edited "
                if not content.startswith(prefix):
                    continue
                path = content[len(prefix):]
                edits[path] = edits.get(path, 0) + 1
                if edits[path] >= NUDGE_EDITS and path not in self.nudged_paths:
                    self.nudged_paths.add(path)
                    nudges.append(("edits", f"{path} has been written {edits[path]} times in this run. "
                                            "Re-read the failing output and the contract before editing it again."))
            elif name == "run" and isinstance(args.get("command"), str):
                command = args["command"]
                match = re.match(r"exit (-?\d+)(?:\n|$)", content)
                if not match:
                    continue
                if int(match.group(1)) == 0:
                    failures[command] = 0
                    continue
                failures[command] = failures.get(command, 0) + 1
                if failures[command] >= NUDGE_FAILS and command not in self.nudged_commands:
                    self.nudged_commands.add(command)
                    nudges.append(("failing", f"The command `{command}` has exited non-zero "
                                              f"{failures[command]} times in a row. This approach isn't working; "
                                              "re-read its output and the contract before trying again."))

        if not nudges:
            return handler(request)
        for kind, text in nudges:
            self.ctx.record({"type": "nudge", "kind": kind, "text": text})
            self.ctx.log(self.tag, f"nudge: {kind}: {clip(text, 240)}")
        return handler(request.override(messages=[*request.messages, *(HumanMessage(text) for _, text in nudges)]))


@dataclass
class _Carried:
    """One build step's resumable conversation, or an error that forbids resuming it."""
    messages: tuple = ()
    error: bool = False


class LangChainRoles:
    def __init__(self, root: Path, model_override: str | None = None, model_factory=None, cfg: Config | None = None):
        self.root = root
        self.model_override = model_override
        self.model_factory = model_factory
        self.cfg = cfg or Config()
        self.resumes: dict[str, _Carried] = {}

    def step(self, step: Step, ctx: Ctx, tag: str | None = None, message: str | None = None) -> Output:
        """Run one flow step: its kind's tools and task message, its own prompt, model and step limit.
        `tag`/`message` override the defaults (resolve runs a build step under its own tag and message)."""
        meta, instructions = load_step(self.root, step)
        spec = step_model(self.root, step, self.cfg, self.model_override)
        steps = step_limit(step, self.cfg, meta)
        parts = [                                    # (text, per_task): per-task parts stay out of the version
            (instructions.strip(), False),
            (contract_block(ctx.task), True),
            (project_rules(self.cfg), False),
            (f"Today: {dt.date.today().isoformat()}. Worktree root is the tools' working directory.", True),
            (_repo_guidance(ctx.worktree, self.cfg.guidance), False),
        ]
        if step.kind == "review" and step.prove:
            parts.insert(3, (proof_rules(), False))
        system = "\n\n".join(text for text, _ in parts if text)
        version = prompt_version(text for text, per_task in parts if text and not per_task)
        tools, default_message, log = self._kit(step, ctx)
        message = message if message is not None else default_message
        tag = tag or (f"{step.name}#{ctx.attempt}" if step.kind in ("build", "review") else step.name)

        resume = step.kind == "build" and "resume" in step.loop
        remember = resume and not ctx.resolution
        carried = ()
        resumed = False
        if resume:
            previous = self.resumes.get(step.name)
            if ctx.resolution:
                # A resolve neither continues nor seeds a conversation; its next build attempt starts fresh too.
                self.resumes.pop(step.name, None)
                ctx.log(tag, "resume: starting fresh — a conflict resolution does not resume or seed a conversation")
            elif ctx.attempt <= 1:
                # A new run's first attempt never uses memory left by an earlier run on the same object.
                self.resumes.pop(step.name, None)
                ctx.log(tag, "resume: starting fresh — first attempt of the step in this run")
            elif previous is not None and previous.error:
                ctx.log(tag, "resume: starting fresh — an earlier attempt ended in an error")
            elif previous is not None and previous.messages:
                carried = previous.messages
                resumed = True
                message = f"# Attempt {ctx.attempt}"
                if ctx.feedback:
                    message += f"\n\n# Feedback to address first\n\n{ctx.feedback}"
                if ctx.earlier:
                    seen = "\n\n".join(f"{i}. {m}" for i, m in enumerate(ctx.earlier, 1))
                    message += f"\n\n# Earlier build steps in this attempt\n\n{seen}"
                ctx.log(tag, f"resume: carrying {len(carried)} messages into attempt {ctx.attempt}")
            else:
                ctx.log(tag, "resume: starting fresh — nothing to resume after a conflict resolution")
        if "map" in step.loop and not resumed:
            block = repository_map(ctx.worktree, ctx.task.spec_refs)
            if block:
                message = f"{message}\n\n{block}"

        middleware = [ModelCallLimitMiddleware(run_limit=steps, exit_behavior="end"),
                      ModelRetryMiddleware(**MODEL_RETRY, on_failure="error"), tool_errors(ctx.worktree)]
        trimmer = None
        if "trim" in step.loop:
            trimmer = TrimMiddleware(tag, ctx)
            middleware.append(trimmer)
        if "nudge" in step.loop:
            carried_calls = sum(isinstance(m, AIMessage) and not str(m.content).startswith(CALL_LIMIT_MARKER)
                                for m in carried)
            middleware.append(NudgeMiddleware(tag, ctx, steps, carried_calls))
        model = (self.model_factory or build_model)(spec)
        agent = create_agent(model, tools, system_prompt=system, middleware=middleware)
        ctx.log(tag, f"start ({spec}, max {steps} steps)")
        if step.kind == "review" and "VERDICT:" not in instructions:
            ctx.log(tag, f"⚠ {step.name}'s prompt has no VERDICT: line; every review will count as CHANGES")
        if resumed:
            ctx.record({"type": "resumed", "messages": len(carried)})
        ctx.record({"type": "system", "model": spec, "max_steps": steps, "content": system})
        ctx.record({"type": "human", "content": message})
        out = Output(text="", model=spec, prompt_version=version)
        human = HumanMessage(message)
        history = [human]
        # Each agent step runs 4 graph nodes (call-limit before_model, model, call-limit after_model,
        # tools). ModelCallLimitMiddleware enforces max_steps; the recursion limit is only a backstop
        # and must sit above 4 * steps or a run that finishes on its last step is killed.
        try:
            for update in agent.stream({"messages": [*carried, human]},
                                       config={"recursion_limit": recursion_limit(steps)}, stream_mode="updates"):
                for payload in update.values():
                    for m in (payload or {}).get("messages", []) if isinstance(payload, dict) else []:
                        history.append(m)
                        self._observe(m, out, tag, ctx)
                ctx.progress(out.steps, steps, out.tokens_in, out.tokens_out, out.cost_usd, out.refused)
        except GraphRecursionError:
            out.stopped = "graph recursion limit"
        except Exception:
            if remember:
                # Even a good earlier conversation is unusable once any attempt in its chain errors.
                self.resumes[step.name] = _Carried(error=True)
            raise
        if out.stopped is None and out.steps >= steps and out.wants_tools:
            out.stopped = "step limit"
        if remember:
            messages = [*carried, *history]
            self.resumes[step.name] = _Carried(tuple(trimmer.view(messages) if trimmer else messages))
        if out.stopped:
            ctx.log(tag, f"⚠ stopped: {out.stopped} after {out.steps} steps (raise max_steps for this role in .factory/config.yaml)")
            ctx.record({"type": "stopped", "reason": out.stopped, "steps": out.steps})
        if step.kind == "review" and out.stopped == "step limit" and not _VERDICT.search(out.text):
            conversation = [*carried, *history]
            self._verdict_call(model, tools, system, trimmer.view(conversation) if trimmer else conversation,
                               out, tag, ctx)
            ctx.progress(out.steps, steps, out.tokens_in, out.tokens_out, out.cost_usd, out.refused)
        cost = f", ${out.cost_usd:.4f}" if out.cost_usd is not None else ""
        refused = f", {out.refused} tool calls refused" if out.refused else ""
        thinking_note = f" ({out.thinking} thinking)" if out.thinking else ""
        ctx.log(tag, f"done: {out.steps} steps, {out.tokens_in} tokens in / {out.tokens_out} out{thinking_note}{cost}{refused}")
        if log is not None:
            out.log = log
        if step.kind == "review":
            out.verdict = parse_verdict(out.text)
        return out

    def _verdict_call(self, model, tools, system: str, messages: list, out: Output, tag: str, ctx: Ctx) -> None:
        """One more model call, with tools disabled, for a review that ran out of calls before its VERDICT
        line. Without it the missing verdict counts as CHANGES, which skips a proving review's proof and
        costs the task another build, gates and review. If the call fails, the review stays as it was."""
        ctx.record({"type": "nudge", "kind": "verdict", "text": VERDICT_CALL})
        ctx.log(tag, "nudge: verdict: out of model calls with no VERDICT line; one more call, without tools")
        try:
            try:
                bound = model.bind_tools(tools, tool_choice="none")
            except (TypeError, ValueError):
                bound = model.bind_tools(tools)
            reply = bound.invoke([SystemMessage(system), *_answered(messages), HumanMessage(VERDICT_CALL)])
        except Exception as e:
            ctx.log(tag, f"⚠ verdict call failed: {clip(f'{type(e).__name__}: {e}', 240)}")
            return
        self._observe(reply, out, tag, ctx)

    def _kit(self, step: Step, ctx: Ctx) -> tuple[list, str, ToolLog | None]:
        """A step kind's tools and task message (exactly what its role method builds today), plus the
        build kind's ToolLog, attached to the Output after the run."""
        guard = self._guard(ctx)
        cap = READ_CAP if "trim" in step.loop else None
        if step.kind == "plan":
            return read_tools(ctx.worktree, guard, cap), f"Plan task {ctx.task.id}.", None
        if step.kind == "test":
            log = ToolLog()
            tools = (read_tools(ctx.worktree, guard, cap)
                     + write_tools(ctx.worktree, guard, log, allowed=self.cfg.test_paths)
                     + run_tool(ctx.sandbox, log, self.cfg.denied_commands))
            commands = [c for c in ctx.task.verification if verification.is_test_command(c)]
            msg = (f"Write the acceptance tests for task {ctx.task.id}.\n\n# Test paths\n\n"
                   + _bullets(f"`{p}`" for p in self.cfg.test_paths) + "\n\n# Test commands\n\n"
                   + _bullets(f"`{c}`" for c in commands))
            if ctx.passing_before:
                msg += ("\n\n# These commands already pass\n\nEvery test command above selects existing tests and "
                        "passes before the change. If the task changes only documentation or specs and needs no new "
                        "test, write no tests and say why in your report: the step then passes, and the build starts "
                        "without locked tests. Never make an existing test or a shared fixture (such as conftest.py) "
                        "check this task's deliverable just to turn a command red.")
            if ctx.feedback:
                msg += f"\n\n# Feedback to address first\n\n{ctx.feedback}"
            return tools, msg, None
        if step.kind == "build":
            log = ToolLog()
            tools = (read_tools(ctx.worktree, guard, cap) + write_tools(ctx.worktree, guard, log)
                     + run_tool(ctx.sandbox, log, self.cfg.denied_commands))
            msg = f"Implement task {ctx.task.id} (attempt {ctx.attempt}).\n\n# Plan\n\n{ctx.plan}"
            if ctx.test_files:
                msg += (
                    "\n\n# Acceptance tests (locked)\n\nThe test step wrote these files:\n"
                    + _bullets(f"`{path}`" for path in ctx.test_files)
                    + "\n\nThese commands fail until the change is built and must pass at the candidate:\n"
                    + _bullets(f"`{command}`" for command in ctx.red_commands)
                    + "\n\nThose files may gain lines, but no line the test step wrote may change or be removed. "
                      "The `acceptance_untouched` gate fails a candidate that changes or removes one.\n\n"
                      "If a test contradicts the contract, do not edit it. Report the contradiction in your final "
                      "message with `RESULT: BLOCKED` and the reason."
                )
            if ctx.feedback:
                msg += f"\n\n# Feedback to address first\n\n{ctx.feedback}"
            if ctx.earlier:
                seen = "\n\n".join(f"{i}. {m}" for i, m in enumerate(ctx.earlier, 1))
                msg += f"\n\n# Earlier build steps in this attempt\n\n{seen}"
            return tools, msg, log
        if step.kind == "review":
            tools = read_tools(ctx.worktree, guard, cap) + diff_tool(ctx.worktree, ctx.base_sha)
            if step.prove:
                tools += run_tool(ctx.sandbox, ToolLog(), self.cfg.denied_commands)
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
            tools = (read_tools(ctx.worktree, guard, cap) + diff_tool(ctx.worktree, ctx.base_sha)
                     + run_tool(ctx.sandbox, ToolLog(), self.cfg.denied_commands))
            msg = f"All gates passed for task {ctx.task.id}. Write the PR report.\n\n# Gates\n\n{ctx.gates}"
            if ctx.reviews:
                msg += "\n\n# Reviewer reports\n\n" + "\n\n".join(
                    f"## {name}\n\n{report}" for name, report in ctx.reviews.items())
            return tools, msg, None
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
            reasoning = "\n\n".join(b["reasoning"] for b in m.content_blocks
                                    if b.get("type") == "reasoning" and b.get("reasoning"))[:200_000]
            thinking = (usage.get("output_token_details") or {}).get("reasoning")
            out.tokens_in += tin
            out.tokens_out += tout
            if thinking is not None:
                out.thinking += thinking
            out.wants_tools = bool(m.tool_calls)
            step_cost = prices.cost(out.model, tin, tout, cached)
            if step_cost is not None:
                out.cost_usd = (out.cost_usd or 0.0) + step_cost
            ctx.record({"type": "ai", "step": out.steps, "text": m.text, "reasoning": reasoning,
                        "usage": {"in": tin, "out": tout, "cache_read": cached, "reasoning": thinking},
                        "cost_usd": step_cost,
                        "tool_calls": [{"name": tc["name"], "args": tc["args"]} for tc in m.tool_calls]})
            if reasoning:
                ctx.log(tag, "thinks: " + clip(reasoning, 240))
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

    def resolve(self, ctx: Ctx, step: Step = Step("build", "build")) -> Output:
        """The builder, resolving a replayed change's conflicts, on the flow's first build step."""
        msg = f"Resolve the merge conflicts of task {ctx.task.id}.\n\n{ctx.resolution}\n\n# The task's plan\n\n{ctx.plan}"
        return self.step(step, ctx, tag="resolve", message=msg)

    def review(self, ctx: Ctx) -> Output:
        return self.step(Step("review", "review"), ctx)

    def verify(self, ctx: Ctx) -> Output:
        return self.step(Step("verify", "verify"), ctx)
