"""Throwaway reference renderer: only here to validate tests/test_web_markdown.py's
expectations before the real factory/web/markdown.py exists. NOT a deliverable.
"""

import html as _html
import re
from dataclasses import dataclass

MAX_DEPTH = 16
PUNCT = set("!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~")
ITEM = re.compile(r"^(?P<indent> *)(?P<marker>-|\*|\+|\d{1,9}[.)]) (?P<text>.*)$")
FENCE = re.compile(r"^(`{3,}|~{3,})(.*)$")
HR = re.compile(r"^ *(?:([-*_]) *){3,}$")
DELIM_CELL = re.compile(r"^:?-+:?$")
RUN_RE = re.compile(r"`+")
IMG_RE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
AUTO_RE = re.compile(r"<(https?://[^>]*)>")
LINK_RE = re.compile(r"\[([^\]]*)\]\(([^()\s]*(?:\([^()]*\)[^()\s]*)*)(?:\s+\"[^\"]*\")?\)")


@dataclass
class Heading:
    level: int
    id: str
    text: str


@dataclass
class Doc:
    title: object
    html: str
    headings: list


def esc(text):
    return _html.escape(text, quote=True)


def plain(text):
    """The heading text without its inline markup."""
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"<(https?://[^>]*)>", r"\1", text)
    text = re.sub(r"`+([^`]*)`+", r"\1", text)
    text = re.sub(r"\\([" + re.escape("!\"#$%&'()*+,-./:;<=>?@[]^_`{|}~") + r"])", r"\1", text)
    return text.replace("**", "").replace("*", "")


def heading_id(text):
    t = plain(text).lower()
    t = re.sub(r"[^a-z0-9 _-]", "", t)
    return t.replace(" ", "-")


class Ctx:
    def __init__(self, fence, link, term):
        self.fence = fence
        self.link = link
        self.term = term
        self.title = None
        self.headings = []
        self.ids = {}


def _inline(text, ctx, term_text=True):
    # 1. code spans, links, autolinks, images and escapes; placeholders protect their
    # rendered form from the word and emphasis passes below
    placeholders = []

    def keep(rendered):
        placeholders.append(rendered)
        return f"\x00{len(placeholders) - 1}\x00"

    out = []
    i, n = 0, len(text)
    while i < n:
        if text[i] == "\\" and i + 1 < n and text[i + 1] in PUNCT:
            out.append(keep(esc(text[i + 1])))
            i += 2
            continue
        if text[i] == "`":
            run = RUN_RE.match(text, i).group(0)
            closer = re.compile(r"(?<!`)(`{%d})(?!`)" % len(run))
            m = closer.search(text, i + len(run))
            if m:
                content = text[i + len(run):m.start()]
                if content[:1] == " " and content[-1:] == " ":
                    content = content[1:-1]
                hook = ctx.term(content, True) if ctx.term else None
                out.append(keep(hook if hook is not None else f"<code>{esc(content)}</code>"))
                i = m.end()
                continue
            out.append(keep(run))
            i += len(run)
            continue
        if text.startswith("![", i):
            m = IMG_RE.match(text, i)
            if m:
                out.append(keep(esc(m.group(1))))
                i = m.end()
                continue
        if text[i] == "<":
            m = AUTO_RE.match(text, i)
            if m:
                out.append(keep(_link(m.group(1), m.group(1), ctx)))
                i = m.end()
                continue
        if text[i] == "[":
            m = LINK_RE.match(text, i)
            if m:
                out.append(keep(_link(m.group(1), m.group(2), ctx)))
                i = m.end()
                continue
        out.append(text[i])
        i += 1
    joined = "".join(out)

    # 2. words -> the term hook (code spans, links and autolinks are placeholders)
    if term_text and ctx.term:
        def word(match):
            hook = ctx.term(match.group(0), False)
            return keep(hook) if hook is not None else match.group(0)
        joined = re.sub(r"[A-Za-z0-9_-]+", word, joined)

    # 3. escape the remaining text, then strong and emphasis (asterisks only)
    joined = esc(joined)
    joined = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", joined)
    joined = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", joined)

    # 4. put the placeholders back
    def back(match):
        return placeholders[int(match.group(1))]
    return re.sub(r"\x00(\d+)\x00", back, joined)


def _link(label, target, ctx):
    href = ctx.link(target) if ctx.link else _default_link(target)
    if href is None:
        return f'<span class="ref" title="{esc(target)}">{esc(label)}</span>'
    return f'<a href="{esc(href)}">{esc(label)}</a>'


def _default_link(target):
    return target if target.startswith(("https://", "http://", "#")) else None


def _split_cells(line):
    cells, current, i = [], [], 0
    while i < len(line):
        if line[i] == "\\" and i + 1 < len(line) and line[i + 1] == "|":
            current.append("|")
            i += 2
            continue
        if line[i] == "|":
            cells.append("".join(current))
            current = []
            i += 1
            continue
        current.append(line[i])
        i += 1
    cells.append("".join(current))
    if cells and cells[0].strip() == "":
        cells = cells[1:]
    if cells and cells[-1].strip() == "":
        cells = cells[:-1]
    return cells


def _blocks(lines, i, end, ctx, depth=0):
    out = []
    while i < end:
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        m = FENCE.match(line)
        if m:
            char, length = m.group(1)[0], len(m.group(1))
            info = m.group(2).strip()
            body, j = [], i + 1
            while j < end:
                close = FENCE.match(lines[j])
                if close and close.group(1)[0] == char and len(close.group(1)) >= length and not close.group(2).strip():
                    break
                body.append(lines[j])
                j += 1
            blob = "\n".join(body) + ("\n" if body else "")
            word = info.split()[0] if info else ""
            block = ctx.fence(word, blob) if ctx.fence else None
            out.append(block if block is not None else f'<pre class="code"><code>{esc(blob)}</code></pre>')
            i = j + 1 if j < end else end
            continue
        m = re.match(r"^(#{1,6}) +(.*)$", line)
        if m and len(line) > len(m.group(1)):
            level = len(m.group(1))
            text = re.sub(r"\s+#+\s*$", "", m.group(2))
            ident = heading_id(text)
            seen = ctx.ids.get(ident, 0)
            ctx.ids[ident] = seen + 1
            ident = ident if seen == 0 else f"{ident}-{seen}"
            if level == 1 and ctx.title is None:
                ctx.title = plain(text)
            else:
                if level in (2, 3):
                    ctx.headings.append(Heading(level, ident, plain(text)))
                out.append(f'<h{level} id="{ident}">{_inline(text, ctx)}</h{level}>')
            i += 1
            continue
        if HR.match(line):
            out.append("<hr>")
            i += 1
            continue
        if "|" in line and i + 1 < end and _delimiter(lines[i + 1]):
            header = [c.strip() for c in _split_cells(line)]
            rows, j = [], i + 2
            while j < end and lines[j].strip() and "|" in lines[j]:
                rows.append([c.strip() for c in _split_cells(lines[j])])
                j += 1
            cells = "".join(f"<th>{_inline(c, ctx)}</th>" for c in header)
            body = "".join(
                "<tr>"
                + "".join(f"<td>{_inline((r[k] if k < len(r) else ''), ctx)}</td>" for k in range(len(header)))
                + "</tr>"
                for r in rows
            )
            out.append(
                '<div class="table-wrap"><table>'
                f"<thead><tr>{cells}</tr></thead><tbody>{body}</tbody>"
                "</table></div>"
            )
            i = j
            continue
        if line.lstrip().startswith(">"):
            quote, j = [], i
            while j < end and lines[j].lstrip().startswith(">"):
                quote.append(re.sub(r"^ *> ?", "", lines[j]))
                j += 1
            out.append(f"<blockquote>{_blocks(quote, 0, len(quote), ctx)}</blockquote>")
            i = j
            continue
        if ITEM.match(line):
            chunk, i = _list(lines, i, end, ctx, depth)
            out.append(chunk)
            continue
        para, j = [], i
        while j < end and lines[j].strip() and not _starts_block(lines[j], lines, j, end):
            para.append(lines[j])
            j += 1
        if not para:
            para, j = [line], i + 1
        out.append(f"<p>{_inline(chr(10).join(para), ctx)}</p>")
        i = j
    return "".join(out)


def _delimiter(line):
    if "|" not in line:
        return False
    return all(DELIM_CELL.match(c.strip()) for c in _split_cells(line) if True) and len(_split_cells(line)) >= 1


def _starts_block(line, lines, i, end):
    if FENCE.match(line) or re.match(r"^#{1,6} ", line) or line.lstrip().startswith(">"):
        return True
    if HR.match(line):
        return True
    if ITEM.match(line):
        return True
    if "|" in line and i + 1 < end and _delimiter(lines[i + 1]):
        return True
    return False


def _list(lines, i, end, ctx, depth):
    first = ITEM.match(lines[i])
    base = len(first.group("indent"))
    ordered = first.group("marker")[0].isdigit()
    tag = "ol" if ordered else "ul"
    attrs = ""
    if ordered and first.group("marker")[:-1] != "1":
        attrs = f' start="{first.group("marker")[:-1]}"'
    out = [f"<{tag}{attrs}>"]
    while i < end:
        line = lines[i]
        if not line.strip():
            k = i
            while k < end and not lines[k].strip():
                k += 1
            if k < end and ITEM.match(lines[k]) and len(ITEM.match(lines[k]).group("indent")) == base:
                i = k
                continue
            break
        m = ITEM.match(line)
        if not m or len(m.group("indent")) != base:
            break
        text_col = len(m.group("indent")) + len(m.group("marker")) + 1
        content, nested, j = [m.group("text")], [], i + 1
        while j < end and lines[j].strip() and len(lines[j]) - len(lines[j].lstrip()) >= text_col:
            (nested if ITEM.match(lines[j]) else content).append(lines[j])
            j += 1
        out.append(f"<li>{_inline(chr(10).join(content), ctx)}</li>")
        if nested and depth + 1 < MAX_DEPTH:
            inner_html, _ = _list(nested, 0, len(nested), ctx, depth + 1)
            out[-1] = f"<li>{_inline(chr(10).join(content), ctx)}{inner_html}</li>"
        elif nested:
            # deeper than 16 levels is not nested further: items of the deepest list
            for extra in nested:
                out.append(f"<li>{_inline(ITEM.match(extra).group('text'), ctx)}</li>")
        i = j
    out.append(f"</{tag}>")
    return "".join(out), i


def render(text, fence=None, link=None, term=None):
    ctx = Ctx(fence, link, term)
    lines = text.split("\n")
    body = _blocks(lines, 0, len(lines), ctx)
    return Doc(ctx.title, body, ctx.headings)
