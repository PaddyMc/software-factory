"""Plan documents discovered in the checkout, rendered against the local board."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

import yaml

from .. import contracts, observe
from . import markdown, views


@dataclass(frozen=True)
class PlanDoc:
    path: Path
    rel: str
    title: str
    text: str
    tasks: tuple[contracts.Task, ...]
    error: contracts.ContractError | None

    @property
    def name(self) -> str:
        return self.path.stem


def load_docs(root: Path, config, cache: dict) -> list[PlanDoc]:
    """Read and parse a doc only when its path, size or modification time changes."""
    docs = []
    for path in contracts.discover_plans(root, config):
        stat = path.stat()
        key = (stat.st_size, stat.st_mtime_ns)
        cached = cache.get(path)
        if cached is not None and cached[0] == key:
            docs.append(cached[1])
            continue
        rel = path.relative_to(root).as_posix()
        text = path.read_bytes().decode("utf-8", errors="replace")
        error = None
        try:
            tasks = tuple(contracts.parse_text(text, plan=rel))
        except contracts.ContractError as exc:
            tasks, error = (), exc
        title = markdown.render(text).title
        if title:
            title = re.sub(r"^Plan:\s*", "", title)
        doc = PlanDoc(path, rel, title or path.stem, text, tasks, error)
        cache[path] = (key, doc)
        docs.append(doc)
    return docs


def _url(doc: PlanDoc) -> str:
    return "/plans/" + quote(doc.name, safe="")


def _sync_form(token: str, next_: str) -> str:
    return views.action_form("sync", token, next_, "Load plans", "factory sync")


def _board_rows(db, doc: PlanDoc, rows):
    return next((tasks for _, tasks in observe.plan_groups(db, rows)
                 if tasks and tasks[0]["plan"] == doc.rel), [])


def _strip(db, rows, empty_label: str = "", queued_waiting: bool = False) -> str:
    infos = [views.WAITING if queued_waiting and row["status"] == "queued"
             else views.status(db, row) for row in rows]
    _, aria = views._counts(rows, infos)
    squares = "".join(f'<i class="{info.css}"></i>' for info in infos)
    return (f'<span class="strip" role="img" aria-label="{views.esc(aria or empty_label)}">'
            f'{squares}</span>')


def _page_head(db, doc: PlanDoc, rows) -> str:
    counts, _ = views._counts(rows, [views.status(db, row) for row in rows])
    spent = f"${sum(row['cost_usd'] or 0 for row in rows):.2f}"
    facts = (
        '<dl class="facts">'
        f'<div><dt>tasks</dt><dd>{_strip(db, rows)}</dd></div>'
        f'<div><dt>status</dt><dd>{views.esc(counts)}</dd></div>'
        f'<div><dt>spent</dt><dd>{spent}</dd></div>'
        f'<div><dt>file</dt><dd>{views.esc(doc.rel)}</dd></div></dl>'
    )
    crumbs = ('<ol class="crumbs"><li><a href="/">Board</a></li>'
              '<li><a href="/plans">Plans</a></li>'
              f'<li>{views.esc(doc.name)}</li></ol>')
    return (f'<div class="page-head">{crumbs}<h1 class="lede">{views.esc(doc.title)}</h1>'
            f'{facts}</div>')


def _page_actions(db, doc: PlanDoc, rows, config) -> str:
    if not rows:
        return ""
    from ..scheduler import startable

    plan = views.board_plan(db, config, doc.name, rows)
    run = ""
    if any(startable(db, plan, row["id"], set()) for row in rows):
        run = f'<a class="btn" href="/run?plan={quote(doc.name, safe="")}">Run plan</a>'
    board = f'<a class="btn btn-quiet" href="/#plan-{quote(doc.name, safe="")}">Show on the board</a>'
    return f'<div class="page-acts">{run}{board}</div>'


def _drift(doc: PlanDoc, rows) -> tuple[list[str], list[str], list[str]]:
    by_id = {row["id"]: row for row in rows}
    ids = {task.id for task in doc.tasks}
    new = [task.id for task in doc.tasks if task.id not in by_id]
    changed = [task.id for task in doc.tasks
               if task.id in by_id and by_id[task.id]["contract"] != task.to_json()]
    removed = [row["id"] for row in rows if row["plan"] == doc.rel and row["id"] not in ids]
    return new, changed, removed


def _notice(doc: PlanDoc, rows, token: str) -> str:
    if doc.error is not None:
        text = "The board can't load this plan's contracts: " + str(doc.error)
        return f'<div class="notice notice-bad" role="status"><span>{views.esc(text)}</span></div>'
    new, changed, removed = _drift(doc, rows)
    if not (new or changed or removed):
        return ""
    parts = []
    if new:
        parts.append(f"{len(new)} new task" + ("s" if len(new) != 1 else ""))
    if changed:
        parts.append(f"{len(changed)} changed")
    if removed:
        parts.append(f"{len(removed)} removed")
    text = ("This plan has changed since the board loaded it: " + ", ".join(parts)
            + ". Load plans to bring the board up to date.")
    return ('<div class="notice notice-you" role="status">'
            f'<span>{views.esc(text)}</span>{_sync_form(token, _url(doc))}</div>')


def _task_href(tid: str, by_id) -> str:
    return (f"/tasks/{quote(tid, safe='')}" if tid in by_id
            else f"#task-{quote(tid, safe='')}")


def _link_task_id(tid: str, by_id) -> str:
    return f'<a href="{views.esc(_task_href(tid, by_id))}">{views.esc(tid)}</a>'


def _link_ids(text: str, by_id) -> str:
    out, at = [], 0
    for match in re.finditer(r"[a-z0-9]+(?:-[a-z0-9]+)*-t\d{2}[a-z]?", text):
        out.append(views.esc(text[at:match.start()]))
        out.append(_link_task_id(match.group(0), by_id))
        at = match.end()
    out.append(views.esc(text[at:]))
    return "".join(out)


def _goal(task: contracts.Task) -> str:
    rendered = markdown.render(task.goal).html
    match = re.fullmatch(r"<p>(.*)</p>", rendered, re.S)
    if match:
        return match.group(1)
    return rendered or views.esc(task.goal)


def _task_row(db, task: contracts.Task, by_id, link, term) -> str:
    row = by_id.get(task.id)
    if row is None:
        state = '<span class="status s-new"><i class="mark"></i>Not loaded</span>'
        ident = f'<span class="id">{views.esc(task.id)}</span>'
        why = ""
        if task.depends_on:
            why = "waits for " + ", ".join(_link_task_id(dep, by_id) for dep in task.depends_on)
        attempts, cost = 0, None
    else:
        info = views.status(db, row)
        state = views.status_html(info)
        ident = (f'<a class="id" href="/tasks/{quote(task.id, safe="")}">'
                 f'{views.esc(task.id)}</a>')
        why = _link_ids(db.readiness(task.id), by_id) if info.kind == "waiting" else ""
        url = views.safe_url(row["pr_url"])
        number = views._pr_number(url)
        if url and number:
            pr = f'<a href="{views.esc(url)}">pull request #{number}</a>'
            why = (why + " · " if why else "") + pr
        attempts, cost = row["attempts"], row["cost_usd"]
    what = f'<div class="goal">{_goal(task)}</div>'
    if why:
        what += f'<div class="why">{why}</div>'
    builds = f"{attempts} build" + ("s" if attempts != 1 else "") if attempts else ""
    cost_text = f"${cost:.2f}" if cost is not None else ""
    end = (f'<div class="end"><span class="num quiet">{views.esc(task.risk)}</span>'
           f'<span class="num quiet builds">{builds}</span>'
           f'<span class="num cost">{cost_text}</span></div>')
    return (f'<li class="row" id="task-{views.esc(task.id)}">{state}{ident}'
            f'<div class="what">{what}</div>{end}</li>')


class _Renderer:
    def __init__(self, db, doc: PlanDoc, docs: list[PlanDoc], rows):
        self.db = db
        self.doc = doc
        self.by_id = {row["id"]: row for row in rows}
        self.by_path = {item.path.resolve(): item for item in docs}
        self.task_at = 0
        self.contract_block = 0
        self.yaml_bodies = {}
        for match in re.finditer(r"^```yaml\n(.*?)^```", doc.text, re.S | re.M):
            body = match.group(1)
            self.yaml_bodies[body] = self.yaml_bodies.get(body, 0) + 1

    def link(self, target: str):
        if target.startswith(("https://", "http://", "#")):
            return target
        try:
            split = urlsplit(target)
        except ValueError:
            return None
        if split.scheme or split.netloc or split.query or not split.path or target.startswith("/"):
            return None
        candidate = (self.doc.path.parent / unquote(split.path)).resolve()
        found = self.by_path.get(candidate)
        if found is None:
            return None
        return _url(found) + (f"#{split.fragment}" if split.fragment else "")

    def term(self, word: str, code: bool):
        row = self.by_id.get(word)
        if row is None:
            return None
        info = views.status(self.db, row)
        label = f"<code>{views.esc(word)}</code>" if code else views.esc(word)
        return (f'<a class="task-ref" href="/tasks/{quote(word, safe="")}">'
                f'<i class="{info.css}"></i>{label}</a>')

    @staticmethod
    def _code(body: str) -> str:
        return f'<pre class="code"><code>{views.esc(body.removesuffix(chr(10)))}</code></pre>'

    def fence(self, lang: str, body: str):
        code = self._code(body)
        if self.doc.error is not None or lang != "yaml" or not self.yaml_bodies.get(body):
            return code
        try:
            items = yaml.safe_load(body)
        except yaml.YAMLError:
            return code
        if not isinstance(items, list) or not items or not all(
                isinstance(item, dict) and "id" in item for item in items):
            return code
        tasks = self.doc.tasks[self.task_at:self.task_at + len(items)]
        if len(tasks) != len(items) or [task.id for task in tasks] != [item["id"] for item in items]:
            return code
        self.task_at += len(items)
        self.contract_block += 1
        self.yaml_bodies[body] -= 1
        rows = "".join(_task_row(self.db, task, self.by_id, self.link, self.term) for task in tasks)
        count = len(tasks)
        summary = f"The contracts as written, {count} task" + ("s" if count != 1 else "")
        return (f'<ul class="rows task-cards">{rows}</ul>'
                f'<details class="fold" id="contracts-{self.contract_block}">'
                f'<summary>{summary}</summary><pre class="code"><code>{views.esc(body)}</code></pre></details>')


def _contents(headings: list[markdown.Heading]) -> str:
    entries = []
    for heading in headings:
        item = f'<a href="#{views.esc(heading.id)}">{views.esc(heading.text)}</a>'
        if heading.level == 2:
            entries.append([item, []])
        elif entries:
            entries[-1][1].append(item)
    if not entries:
        return ""
    items = []
    for item, children in entries:
        nested = f'<ol>{"".join(f"<li>{child}</li>" for child in children)}</ol>' if children else ""
        items.append(f"<li>{item}{nested}</li>")
    return ('<nav class="toc" aria-labelledby="h-toc"><h2 id="h-toc">Contents</h2>'
            f'<ol>{"".join(items)}</ol></nav>')


def plan_page(db, doc: PlanDoc, docs: list[PlanDoc], config, home, port, token: str) -> str:
    rows = db.tasks()
    board = _board_rows(db, doc, rows)
    renderer = _Renderer(db, doc, docs, rows)
    rendered = markdown.render(doc.text, fence=renderer.fence, link=renderer.link, term=renderer.term)
    body = (_page_head(db, doc, board) + _page_actions(db, doc, board, config)
            + _notice(doc, rows, token)
            + f'<div class="doc">{_contents(rendered.headings)}<div class="prose">{rendered.html}</div></div>')
    return views._page(doc.name, config.name, home, port, body, current="plans")


def _awaiting_board(doc: PlanDoc) -> bool:
    # A Plan: heading marks a workstream even before its first contract block is added.
    return (bool(doc.tasks) or doc.error is not None
            or re.search(r"^# +Plan:\s*", doc.text, re.M) is not None)


def plans_page(db, docs: list[PlanDoc], config, home, port, token: str) -> str:
    rows = db.tasks()
    ordered = sorted(docs, key=lambda doc: (doc.name, doc.rel))
    board_by_path = {doc.rel: _board_rows(db, doc, rows) for doc in ordered}
    working = sum(bool(board_by_path[doc.rel]) and any(
        row["status"] not in ("merged", "abandoned", "on_hold")
        for row in board_by_path[doc.rel]) for doc in ordered)
    unloaded = sum(_awaiting_board(doc) and not board_by_path[doc.rel] for doc in ordered)
    if ordered:
        lede = f"{len(ordered)} plan" + ("s" if len(ordered) != 1 else "") + f", {working} with work left."
        if unloaded:
            lede += f" {unloaded} " + ("isn't" if unloaded == 1 else "aren't") + " on the board yet."
    else:
        lede = "No plans yet."
    items = []
    for doc in ordered:
        board = board_by_path[doc.rel]
        if board:
            infos = [views.WAITING if row["status"] == "queued" else views.status(db, row)
                     for row in board]
            counts, _ = views._counts(board, infos)
            empty_label = ""
        else:
            awaiting = _awaiting_board(doc)
            counts = "Not on the board yet" if awaiting else "No task contracts"
            empty_label = "not on the board" if awaiting else "no task contracts"
        items.append(
            f'<li id="plan-{views.esc(doc.name)}">'
            f'<a class="plan-name" href="{_url(doc)}">{views.esc(doc.name)}</a>'
            f'{_strip(db, board, empty_label, queued_waiting=True)}'
            f'<span class="plan-about"><span class="plan-title">{views.esc(doc.title)}</span>'
            f'<span class="plan-path">{views.esc(doc.rel)}</span></span>'
            f'<span class="plan-end"><span class="plan-counts">{views.esc(counts)}</span>'
            f'<span class="num">{views._plan_cost(board)}</span></span></li>')
    empty = ""
    if not ordered:
        empty = ('<p class="fine">The config\'s <code>plans</code> globs are '
                 f'<code>{views.esc(", ".join(config.plans))}</code>.</p>')
    heading = (f'<h2 id="h-plans">Plans <span class="count">{len(ordered)}</span> '
               f'<span class="fine">{views.esc(", ".join(config.plans))}</span></h2>')
    section = f'<section class="board"><div class="board-head">{heading}</div><ul class="plan-list">{"".join(items)}</ul></section>'
    body = f'<div class="page-head"><h1 class="lede">{views.esc(lede)}</h1>{empty}</div>{section}'
    top_end = (f'<span class="live-dot" title="Refreshing every 2 seconds"></span>'
               f'{_sync_form(token, "/plans")}')
    return views._page("Plans", config.name, home, port, body, refresh=2, current="plans", top_end=top_end)


def plan_error(name: str, matches: list[PlanDoc], config, home, port) -> str:
    if matches:
        paths = ", ".join(doc.rel for doc in sorted(matches, key=lambda doc: doc.rel))
        lede = f"{name} names more than one plan doc: {paths}"
    else:
        lede = f"{name} isn't a plan in this repository"
    body = (f'<div class="page-head"><h1 class="lede">{views.esc(lede)}</h1>'
            '<p class="fine"><a href="/plans">Back to all plans</a></p></div>')
    return views._page("Plans", config.name, home, port, body, current="plans")
