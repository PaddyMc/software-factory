"""Observability: the `factory top` dashboard, merged logs, and transcript rendering."""

from __future__ import annotations

import json
import shutil
import time
from collections import Counter
from pathlib import Path

from .contracts import ContractError, plan_name, plan_order
from .db import ACTIVE, DB, pid_alive, seconds_since
from .log import clip

DONE = ("merged", "abandoned")
GLYPHS = {"merged": "✓", "pr_open": "◆", "conflict": "≠", "failed": "✗", "abandoned": "⊘", "queued": "·"}   # running: ▶


def fit(line: str, width: int) -> str:
    """Truncate to the terminal width without collapsing column padding."""
    return line if len(line) <= width else line[: max(1, width - 1)] + "…"


def human_secs(secs: float | None) -> str:
    if secs is None:
        return "-"
    secs = int(secs)
    if secs < 60:
        return f"{secs}s"
    if secs < 3600:
        return f"{secs // 60}m{secs % 60:02d}s"
    return f"{secs // 3600}h{secs % 3600 // 60:02d}m"


def liveness(row) -> str:
    """For a task in an active state: is its `factory run` process still there?"""
    if row["status"] not in ACTIVE + ("queued",) or not row["pid"]:
        return ""
    return "" if pid_alive(row["pid"]) else "DEAD"


def failing_summary(note: str | None) -> str:
    return (note or "").splitlines()[0] if note else ""


def detail(db: DB, row) -> str:
    """One-line description of where a task is (shared by `status` and `top`)."""
    st = row["status"]
    if st in ACTIVE:
        dead = liveness(row)
        idle = seconds_since(row["heartbeat_at"])
        parts = [row["progress"] or ""]
        if dead:
            parts.append(f"DEAD: process {row['pid']} is gone (run `factory clean {row['id']}`)")
        elif idle is not None and idle >= 120:
            parts.append(f"quiet {human_secs(idle)}")
        return " · ".join(p for p in parts if p)
    if st in ("queued", "failed"):
        ready = db.readiness(row["id"])
        return ready + (f" · last run: {failing_summary(row['note'])}" if st == "failed" and row["note"] else "")
    if st == "pr_open":
        return (row["pr_url"] or "") + (f" · stacked on {row['stacked_on']}" if row["stacked_on"] else "")
    if st == "conflict":
        return f"{row['pr_url'] or ''} · {failing_summary(row['note'])}"
    return failing_summary(row["note"])


def strip(db: DB, rows) -> str:
    """One glyph per task, in plan order: ✓ merged ◆ PR open ≠ PR conflicts ▶ running ✗ failed · queued ⊘ held."""
    return "".join("▶" if r["status"] in ACTIVE else GLYPHS.get(r["status"], "?") for r in rows)


def counts(db: DB, rows) -> str:
    """Task counter for one plan: '2/5 merged · 1 PR open · 1 running · 1 waiting'."""
    c = Counter()
    for r in rows:
        st = r["status"]
        c["running" if st in ACTIVE else "PR open" if st == "pr_open" else "held" if st == "abandoned"
          else ("ready" if db.ready(r["id"]) else "waiting") if st == "queued" else st] += 1
    rest = [f"{c[k]} {k}" for k in ("PR open", "conflict", "running", "failed", "ready", "waiting", "held") if c[k]]
    return " · ".join([f"{c['merged']}/{len(rows)} merged"] + rest)


def plan_groups(db: DB, rows) -> list[tuple[str, list]]:
    """[(plan name, its tasks in dependency order)], plans sorted by name."""
    by: dict[str, list] = {}
    for r in rows:
        by.setdefault(r["plan"], []).append(r)
    out = []
    for plan, rs in sorted(by.items(), key=lambda kv: plan_name(kv[0])):
        try:
            order = {t.id: i for i, t in enumerate(plan_order([db.contract(r["id"]) for r in rs]))}
        except ContractError:
            order = {}
        out.append((plan_name(plan), sorted(rs, key=lambda r: (order.get(r["id"], 0), r["id"]))))
    return out


def in_plan(rows, plan: str | None) -> list:
    """Rows of one plan (by name or path), or all rows."""
    return [r for r in rows if plan in (None, r["plan"], plan_name(r["plan"]))]


def _cost(row) -> str:
    return f"${row['cost_usd']:.2f}" if row["cost_usd"] is not None else "-"


def recent_events(home: Path, task_ids: list[str], limit: int) -> list[str]:
    """Last `limit` log lines across the given tasks, prefixed with the task and ordered by time."""
    lines: list[tuple[str, int, str]] = []
    for tid in task_ids:
        path = home / "logs" / f"{tid}.log"
        if not path.is_file():
            continue
        tail = path.read_text(errors="replace").splitlines()[-limit:]
        lines += [(l[:8], i, f"{tid:<30} {l}") for i, l in enumerate(tail)]
    lines.sort(key=lambda x: (x[0], x[1]))
    return [l for _, _, l in lines[-limit:]]


def render_top(db: DB, home: Path, width: int | None = None, events: int = 12, plan: str | None = None) -> str:
    """Plans that are running, have open PRs or failures, each with its task counter and every task;
    the other plans one line each; then the latest events."""
    width = width or shutil.get_terminal_size((160, 40)).columns
    rows = in_plan(db.tasks(), plan)
    by = lambda *sts: [r for r in rows if r["status"] in sts]
    active, prs, failed = by(*ACTIVE), by("pr_open", "conflict"), by("failed")
    queued = by("queued")
    ready = [r for r in queued if db.ready(r["id"])]
    total_cost = sum(r["cost_usd"] or 0 for r in rows)
    out = [f"factory · {len(active)} running · {len(prs)} PR open · {len(failed)} failed · "
           f"{len(ready)} ready · {len(queued) - len(ready)} waiting · {len(by(*DONE))} done · "
           f"spent ${total_cost:.2f}", ""]
    groups = plan_groups(db, rows)
    live = lambda rs: any(r["status"] in ACTIVE + ("pr_open", "conflict", "failed") for r in rs)
    shown = [(n, rs) for n, rs in groups if plan or live(rs)]
    idle = [(n, rs) for n, rs in groups if not (plan or live(rs))]
    head = f"  {'TASK':<32} {'STATUS':<10} {'ELAPSED':>8} {'QUIET':>7} {'COST':>7}  PROGRESS / NOW"
    if shown:
        out += [head, "-" * min(width, len(head) + 40)]
    for name, rs in shown:
        cost = sum(r["cost_usd"] or 0 for r in rs)
        out.append(fit(f"{name}  {strip(db, rs)}  {counts(db, rs)} · ${cost:.2f}", width))
        for r in rs:
            running = r["status"] in ACTIVE
            elapsed = human_secs(seconds_since(r["started_at"])) if running else ""
            quiet = human_secs(seconds_since(r["heartbeat_at"])) if running else ""
            status = "DEAD" if liveness(r) else r["status"]
            out.append(fit(f"  {r['id']:<32} {status:<10} {elapsed:>8} {quiet:>7} {_cost(r):>7}  {detail(db, r)}", width))
            if running and r["activity"]:
                out.append(fit(f"  {'':<32} {'':<10} {'':>8} {'':>7} {'':>7}  ↳ " + clip(r["activity"], 400), width))
    if not shown:
        out.append("(no plan is running or has an open PR or a failure — `factory run <plan>`)")
    if idle:
        out += ["", "other plans"]
        out += [fit(f"  {n:<32} {strip(db, rs):<10} {counts(db, rs)}", width) for n, rs in idle]
    recent_ids = [r["id"] for r in active + failed + prs]
    if recent_ids and events:
        out += ["", "recent events"]
        out += [fit(l, width) for l in recent_events(home, recent_ids, events)]
    return "\n".join(out)


def follow_all(home: Path, lines: int, follow: bool, poll: float = 0.5, stop=None) -> None:
    """Print every task log merged (prefixed with the task id); keep following new lines."""
    logs = home / "logs"
    offsets: dict[Path, int] = {}
    for line in recent_events(home, sorted(p.stem for p in logs.glob("*.log")), lines or 10_000):
        print(line, flush=True)
    for p in logs.glob("*.log"):
        offsets[p] = p.stat().st_size
    while follow and not (stop and stop()):
        for p in sorted(logs.glob("*.log")):
            size = p.stat().st_size
            start = offsets.get(p, 0)
            if size > start:
                with p.open(errors="replace") as f:
                    f.seek(start)
                    for l in f.read().splitlines():
                        print(f"{p.stem:<30} {l}", flush=True)
                offsets[p] = size
        time.sleep(poll)


def render_transcript(path: Path, full: bool = False, limit: int = 2000) -> str:
    def cut(text: str) -> str:
        text = str(text)
        return text if full or len(text) <= limit else text[:limit] + f"\n… ({len(text) - limit} more chars; --full)"

    out = []
    for raw in path.read_text().splitlines():
        e = json.loads(raw)
        t, at = e.get("type"), e.get("at", "")[11:19]
        if t == "system":
            out.append(f"{at} [system] model={e.get('model')} max_steps={e.get('max_steps')}"
                       + (f"\n{e['content']}" if full else f" ({len(e.get('content', ''))} chars; --full to show)"))
        elif t == "human":
            out.append(f"{at} [task message]\n{cut(e['content'])}")
        elif t == "ai":
            cost = f" ${e['cost_usd']:.4f}" if e.get("cost_usd") is not None else ""
            u = e.get("usage", {})
            out.append(f"{at} [agent step {e['step']}] {u.get('in', 0)} in / {u.get('out', 0)} out{cost}")
            if e.get("text"):
                out.append(cut(e["text"]))
            for tc in e.get("tool_calls", []):
                args = json.dumps(tc["args"], indent=None, ensure_ascii=False)
                out.append(f"  → {tc['name']} {cut(args)}")
        elif t == "tool":
            flag = "⚠ " if str(e.get("content", "")).startswith("refused") else ""
            out.append(f"{at} [{flag}tool {e.get('name')}]\n{cut(e.get('content', ''))}")
    return "\n".join(out)


def _brief_args(args: dict) -> str:
    for key in ("path", "command", "pattern"):
        if key in args:
            return f"{key}={clip(args[key], 48)}"
    return ",".join(sorted(args))[:48]


def trace_rows(events: list[dict]) -> list[dict]:
    """One row per model call: how long the model took, how long its tools took, context size, cost."""
    import datetime as dt

    def at(e):
        return dt.datetime.fromisoformat(e["at"]) if e.get("at") else None

    rows: list[dict] = []
    mark = at(events[0]) if events else None          # when the model was last handed the conversation
    for i, e in enumerate(events):
        if e["type"] != "ai":
            continue
        t_ai = at(e)
        results = []
        for nxt in events[i + 1:]:
            if nxt["type"] != "tool":
                break
            results.append(nxt)
        t_done = at(results[-1]) if results else t_ai
        u = e.get("usage", {})
        rows.append({
            "step": e["step"],
            "model_s": (t_ai - mark).total_seconds() if t_ai and mark else None,
            "tools_s": (t_done - t_ai).total_seconds() if results and t_ai and t_done else 0.0,
            "ctx_in": u.get("in", 0), "out": u.get("out", 0), "cached": u.get("cache_read", 0) or 0,
            "cost": e.get("cost_usd"),
            "calls": [f"{tc['name']}({_brief_args(tc['args'])})" for tc in e.get("tool_calls", [])] or ["(final answer)"],
            "result_chars": sum(len(str(r.get("content", ""))) for r in results),
            "refused": sum(1 for r in results if str(r.get("content", "")).startswith("refused")),
        })
        mark = t_done
    return rows


def render_trace(path: Path, width: int | None = None) -> str:
    from collections import Counter

    width = width or shutil.get_terminal_size((160, 40)).columns
    events = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    system = next((e for e in events if e["type"] == "system"), {})
    human = next((e for e in events if e["type"] == "human"), {})
    stopped = next((e for e in events if e["type"] == "stopped"), None)
    rows = trace_rows(events)
    out = [f"model {system.get('model', '?')} · max_steps {system.get('max_steps', '?')} · system prompt "
           f"{len(system.get('content', ''))} chars · task message {len(human.get('content', ''))} chars", ""]
    head = f"{'step':>4} {'model':>7} {'tools':>7} {'ctx in':>8} {'cached':>7} {'out':>6} {'cost':>8} {'result':>7}  calls"
    out += [head, "-" * min(width, 120)]
    for r in rows:
        secs = lambda v: "-" if v is None else f"{v:.1f}s"
        cost = "-" if r["cost"] is None else f"${r['cost']:.4f}"
        flag = f" ⚠{r['refused']} refused" if r["refused"] else ""
        out.append(fit(f"{r['step']:>4} {secs(r['model_s']):>7} {secs(r['tools_s']):>7} {r['ctx_in']:>8} "
                       f"{r['cached']:>7} {r['out']:>6} {cost:>8} {r['result_chars']:>7}  "
                       f"{', '.join(r['calls'])}{flag}", width))
    if not rows:
        return "\n".join(out + ["(no model calls recorded)"])
    tin = sum(r["ctx_in"] for r in rows)
    tout = sum(r["out"] for r in rows)
    cached = sum(r["cached"] for r in rows)
    model_s = sum(r["model_s"] or 0 for r in rows)
    tools_s = sum(r["tools_s"] for r in rows)
    costs = [r["cost"] for r in rows if r["cost"] is not None]
    mix = Counter((c.split("(")[0] or "final answer") for r in rows for c in r["calls"])
    heavy = sorted(rows, key=lambda r: r["result_chars"], reverse=True)[:3]
    slow = sorted(rows, key=lambda r: r["tools_s"], reverse=True)[:3]
    out += ["", "summary",
            f"  steps {len(rows)}" + (f" — stopped: {stopped['reason']}" if stopped else ""),
            f"  time  model {human_secs(model_s)} · tools {human_secs(tools_s)}",
            f"  tokens  input {tin:,} (context re-sent every step: {rows[0]['ctx_in']:,} → {rows[-1]['ctx_in']:,}"
            f"; {cached:,} served from cache) · output {tout:,}",
            f"  cost  {'$%.4f' % sum(costs) if costs else 'unknown'}"
            + (f" · input share {100 * tin / max(1, tin + tout):.0f}% of tokens" if rows else ""),
            "  tool mix  " + ", ".join(f"{k} ×{v}" for k, v in mix.most_common()),
            "  largest results (they stay in context for every later step)  "
            + "; ".join(f"step {r['step']}: {r['result_chars']:,} chars {r['calls'][0]}" for r in heavy if r["result_chars"]),
            "  slowest tools  " + "; ".join(f"step {r['step']}: {human_secs(r['tools_s'])} {r['calls'][0]}"
                                           for r in slow if r["tools_s"])]
    return "\n".join(fit(l, width) if l.startswith("  ") else l for l in out)
