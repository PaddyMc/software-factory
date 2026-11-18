"""Named agent flows: the ordered list of steps a task goes through.

A repository defines flows under `flows:` in `.factory/config.yaml` and picks one with `flow:`;
without either, the built-in `default` flow runs, which is today's plan -> build -> review ->
gates -> verify pipeline. Each step has a kind, which fixes the agent's tools and how its output
is used, plus an optional name, model, step limit and loop behaviours. An optional test step writes
acceptance tests directly before the builds. A flow without a `gates` step gets one
inserted after its last review step (or its last build step), so gates always decide the PR.
This module only parses and validates the config; running a flow lives in the pipeline.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .config import ConfigError

KINDS = ("plan", "test", "build", "review", "verify", "gates")
LOOP = ("trim", "map", "nudge", "resume")
NAME_RE = re.compile(r"^[a-z][a-z0-9-]*$")
RESERVED = ("resolve", "ci", "pr", "human_review", "planner", "tester", "builder", "reviewer", "verifier")


@dataclass(frozen=True)
class Step:
    """One step of a flow. The kind fixes its tools and output; the rest may stay unset."""
    name: str
    kind: str                             # plan | test | build | review | verify | gates
    model: str | None = None              # `provider:model`; None = the kind's model
    max_steps: int | None = None          # model calls allowed; None = the kind's limit
    loop: tuple[str, ...] = ()            # loop behaviours, e.g. ("trim",)
    prove: bool = False                   # review only: CHANGES needs a reproduced failure or scope finding
    candidates: int = 1                   # build only: first-attempt candidates, built and gated in turn


@dataclass(frozen=True)
class Flow:
    name: str
    steps: tuple[Step, ...]


# Today's pipeline: plan, build, review, gates, verify, each step named after its kind.
DEFAULT = Flow("default", (Step("plan", "plan"), Step("build", "build"), Step("review", "review"),
                           Step("gates", "gates"), Step("verify", "verify")))

# Every stricter behaviour together: independently written tests, bounded and resumed builds,
# gates before a proving review, and the verifier's report. No planner: the builder plans.
STRICT = Flow("strict", (
    Step("test", "test", loop=("map", "trim", "nudge")),
    Step("build", "build", loop=("map", "trim", "nudge", "resume")),
    Step("gates", "gates"),
    Step("review", "review", prove=True, loop=("trim",)),
    Step("verify", "verify"),
))


def parse_step(flow: str, raw) -> Step:
    """One step: a bare kind, or a mapping with `kind`, its optional settings and `loop` behaviours."""
    if isinstance(raw, str):
        if raw not in KINDS:
            raise ConfigError(f"flows.{flow}.{raw}: a string step must be a kind ({', '.join(KINDS)})")
        return Step(raw, raw)
    if not isinstance(raw, dict):
        raise ConfigError(f"flows.{flow}: a step must be a kind string or a mapping, got {raw!r}")
    where = f"flows.{flow}.{raw['name']}" if isinstance(raw.get("name"), str) else f"flows.{flow}"
    kind = raw.get("kind")
    if kind not in KINDS:
        raise ConfigError(f"{where}: a step mapping needs `kind`, one of {', '.join(KINDS)}")
    name = raw.get("name") or kind
    if not isinstance(name, str):
        raise ConfigError(f"flows.{flow}: a step's `name` must be a string")
    where = f"flows.{flow}.{name}"
    extra = sorted(str(k) for k in set(raw) - {"kind", "name", "model", "max_steps", "loop", "prove", "candidates"})
    if extra:
        raise ConfigError(f"{where}: unknown key(s) {', '.join(extra)}")
    if kind == "gates":
        raise ConfigError(f"{where}: a gates step is the bare string `gates`, it takes no keys")
    model = raw.get("model")
    if model is not None and not isinstance(model, str):
        raise ConfigError(f"{where}: model must be a string (`provider:model`)")
    max_steps = raw.get("max_steps")
    if max_steps is not None and (not isinstance(max_steps, int) or isinstance(max_steps, bool) or max_steps <= 0):
        raise ConfigError(f"{where}: max_steps must be a positive integer")
    loop = raw.get("loop", [])
    if not isinstance(loop, list):
        raise ConfigError(f"{where}: loop must be a list of behaviour names ({', '.join(LOOP)})")
    seen_loop = set()
    for behaviour in loop:
        if behaviour not in LOOP:
            raise ConfigError(f"{where}: unknown loop behaviour {behaviour!r} (loop: {', '.join(LOOP)})")
        if behaviour in seen_loop:
            raise ConfigError(f"{where}: loop behaviour {behaviour!r} appears more than once")
        seen_loop.add(behaviour)
    if "resume" in seen_loop and kind != "build":
        raise ConfigError(f"{where}: loop behaviour 'resume' is only valid on build steps")
    prove = raw.get("prove", False)
    if not isinstance(prove, bool):
        raise ConfigError(f"{where}: prove must be a boolean")
    if prove and kind != "review":
        raise ConfigError(f"{where}: 'prove' is only valid on review steps")
    candidates = raw.get("candidates", 1)
    if "candidates" in raw and (not isinstance(candidates, int) or isinstance(candidates, bool)
                                or not 2 <= candidates <= 5):
        raise ConfigError(f"{where}: candidates must be an integer from 2 to 5")
    if "candidates" in raw and kind != "build":
        raise ConfigError(f"{where}: 'candidates' is only valid on build steps")
    return Step(name, kind, model, max_steps, tuple(loop or ()), prove, candidates)


def validate(flow: str, steps: tuple[Step, ...]) -> None:
    """The rules a flow's steps must satisfy; every error names the flow and the offending step."""
    if not NAME_RE.match(flow):
        raise ConfigError(f"flows.{flow}: flow names must match {NAME_RE.pattern}")
    if flow in ("default", "strict"):
        raise ConfigError(f"flows.{flow}: the built-in `{flow}` flow cannot be redefined")
    seen: set[str] = set()
    for s in steps:
        where = f"flows.{flow}.{s.name}"
        if not NAME_RE.match(s.name):
            raise ConfigError(f"{where}: step names must match {NAME_RE.pattern}")
        if s.name in seen:
            raise ConfigError(f"{where}: duplicate step name")
        seen.add(s.name)
        if s.name in RESERVED:
            raise ConfigError(f"{where}: reserved step name ({', '.join(RESERVED)} are taken)")
        if s.name in KINDS and s.name != s.kind:
            raise ConfigError(f"{where}: a step named `{s.name}` must have kind `{s.name}`, not `{s.kind}`")
        if s.kind not in KINDS:
            raise ConfigError(f"{where}: unknown kind {s.kind!r} (kinds: {', '.join(KINDS)})")
    _order(flow, steps)


def _order(flow: str, steps: tuple[Step, ...]) -> None:
    """[plan]? [test]? build+ (review | gates)* [verify]? — with at most one gates step."""
    kinds = [s.kind for s in steps]
    plans = [s for s in steps if s.kind == "plan"]
    if len(plans) > 1:
        raise ConfigError(f"flows.{flow}.{plans[1].name}: at most one plan step")
    if plans and kinds[0] != "plan":
        raise ConfigError(f"flows.{flow}.{plans[0].name}: the plan step must be first")
    tests = [s for s in steps if s.kind == "test"]
    if len(tests) > 1:
        raise ConfigError(f"flows.{flow}.{tests[1].name}: at most one test step")
    verifies = [s for s in steps if s.kind == "verify"]
    if len(verifies) > 1:
        raise ConfigError(f"flows.{flow}.{verifies[1].name}: at most one verify step")
    if verifies and kinds[-1] != "verify":
        raise ConfigError(f"flows.{flow}.{verifies[0].name}: the verify step must be last")
    gates = [s for s in steps if s.kind == "gates"]
    if len(gates) > 1:
        raise ConfigError(f"flows.{flow}.{gates[1].name}: at most one gates step")
    builds = [i for i, s in enumerate(steps) if s.kind == "build"]
    if not builds:
        bad = steps[1] if plans and len(steps) > 1 else steps[0]
        raise ConfigError(f"flows.{flow}.{bad.name}: at least one build step is required")
    start = 1 if plans else 0
    if tests and (kinds[start] != "test" or start + 1 >= len(steps) or kinds[start + 1] != "build"):
        raise ConfigError(f"flows.{flow}.{tests[0].name}: the test step must be directly before the first build step")
    start += 1 if tests else 0
    if builds != list(range(start, start + len(builds))):
        bad = steps[next(i for i in builds if i not in set(range(start, start + len(builds))))]
        raise ConfigError(f"flows.{flow}.{bad.name}: build steps come first (after any plan or test step) and are contiguous")


def _candidates(flow: str, steps: tuple[Step, ...]) -> None:
    """Candidates are gated before any other post-build step, so their flow has one fixed shape."""
    builds = [s for s in steps if s.kind == "build"]
    for i, step in enumerate(steps):
        if step.candidates > 1 and (len(builds) != 1 or i + 1 >= len(steps) or steps[i + 1].kind != "gates"):
            raise ConfigError(f"flows.{flow}.{step.name}: 'candidates' needs one build step followed by the gates")


def parse_flow(name: str, raw) -> Flow:
    """A named flow: a list of steps, validated, with a gates step inserted when omitted."""
    if not isinstance(raw, list) or not raw:
        raise ConfigError(f"flows.{name}: a flow is a non-empty list of steps")
    steps = tuple(parse_step(name, s) for s in raw)
    validate(name, steps)
    if all(s.kind != "gates" for s in steps):
        # Validated order puts reviews after builds, so the last build-or-review is the last
        # review when there is one, else the last build. There is always at least one build.
        after = max(i for i, s in enumerate(steps) if s.kind in ("build", "review"))
        steps = steps[:after + 1] + (Step("gates", "gates"),) + steps[after + 1:]
    _candidates(name, steps)
    return Flow(name, steps)


def parse_flows(raw) -> dict[str, Flow]:
    """The `flows:` mapping: name -> Flow."""
    if not isinstance(raw, dict):
        raise ConfigError("flows must be a mapping of flow names to lists of steps")
    return {str(name): parse_flow(str(name), steps) for name, steps in raw.items()}
