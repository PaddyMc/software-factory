"""The read-only lander role: judge one PR head against the trunk and record its verdict.

GitHub supplies the PR evidence and the caller supplies a worktree already checked out at the head. This
module fetches nothing, runs no gates, and changes no task status; it only builds the review brief, runs the
agent, and records the resulting `land` run.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from . import agents
from .config import Config
from .contracts import Task
from .db import DB
from .flows import Step


@dataclass(frozen=True)
class Review:
    """A land decision and its report; None means the agent never supplied a usable verdict."""
    decision: str | None
    report: str
    output: agents.Output


def _section(title: str, text: str) -> str:
    return f"## {title}\n\n{text.strip() if text and text.strip() else '(none)'}"


def _numbered(items: Iterable[tuple[str, str]], label: bool = False) -> str:
    lines = []
    for first, second in items:
        lines.append(f"- @{first}: {second}" if label else f"- {first}: {second}")
    return "\n".join(lines)


def message(url: str, title: str, body: str = "", trunk: str = "", head: str = "", gates: str = "",
            checks: Iterable[tuple[str, str]] = (), review_report: str = "",
            conversation: Iterable[tuple[str, str]] = (), inline_comments: Iterable[tuple[str, str]] = (),
            earlier_findings: str = "") -> str:
    """Build the lander's brief solely from the PR and review evidence supplied by the caller."""
    return "\n\n".join([
        f"PR: {url} | {title}",
        body.strip() if body and body.strip() else "(none)",
        _section("Trunk", trunk),
        _section("Head", head),
        _section("Gates at this head", gates),
        _section("CI checks at this head", _numbered(checks)),
        _section("Build reviewer's last report", review_report),
        _section("PR conversation", _numbered(conversation, label=True)),
        _section("Inline comments", _numbered(inline_comments, label=True)),
        _section("Lander's earlier findings on this task", earlier_findings),
    ])


def review(*, root: Path, db: DB, task: Task, worktree: Path, cfg: Config, merge_base: str,
           url: str, title: str, trunk: str, head: str, body: str = "", gates: str = "",
           checks: Iterable[tuple[str, str]] = (), review_report: str = "",
           conversation: Iterable[tuple[str, str]] = (), inline_comments: Iterable[tuple[str, str]] = (),
           earlier_findings: str = "", record: Callable[[dict], None] | None = None,
           log: Callable[[str, str], None] | None = None, model: str | None = None) -> Review:
    """Run the lander in `worktree`, diffing from `merge_base`, and record the decision on `head`."""
    attempt = db.task(task.id)["attempts"]
    spec = agents.role_model(root, "land", cfg, model)
    run_id = db.start_run(task.id, "land", attempt, model=spec, step="review")

    def progress(steps: int, max_steps: int, tokens_in: int, tokens_out: int,
                 cost_usd: float | None, refused: int) -> None:
        db.progress(task.id, run_id, f"land#{attempt} step {steps}/{max_steps}", steps, tokens_in, tokens_out,
                    cost_usd, refused)

    ctx = agents.Ctx(task=task, worktree=worktree, base_sha=merge_base, attempt=attempt, sandbox=None,
                     progress=progress, record=record or (lambda event: None), log=log or (lambda *args: None))
    brief = message(url=url, title=title, body=body, trunk=trunk, head=head, gates=gates, checks=checks,
                    review_report=review_report, conversation=conversation, inline_comments=inline_comments,
                    earlier_findings=earlier_findings)
    roles = agents.LangChainRoles(root, model_override=model, cfg=cfg)
    try:
        out = roles.step(Step("land", "land"), ctx, message=brief)
    except Exception as e:
        db.finish_run(run_id, "error", f"{type(e).__name__}: {e}", sha=head)
        raise

    decision = out.verdict
    outcome = decision.lower() if decision else "no_verdict"
    db.conn.execute("UPDATE runs SET model=?, prompt_version=? WHERE id=?", (out.model, out.prompt_version, run_id))
    db.progress(task.id, run_id, f"land#{attempt} {outcome}", out.steps, out.tokens_in, out.tokens_out,
                out.cost_usd, out.refused)
    db.finish_run(run_id, outcome, out.text, sha=head)
    return Review(decision=decision, report=out.text, output=out)
