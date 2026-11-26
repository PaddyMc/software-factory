"""factory/web/markdown.py renders the Markdown subset the plans are written in.

The tests follow the sections of docs/plans/plan-pages.md that the plan-pages-t01
contract names: "The Markdown subset" (the block and inline tables), "Heading ids",
"Hooks" (fence, link and term) and "Security". Every assertion is tied to a row of
one of those tables or to a line of the task's acceptance criteria.
"""

import html
import re
import time
from html.parser import HTMLParser
from pathlib import Path

from factory import contracts
from factory.web import markdown

ROOT = Path(__file__).resolve().parents[1]
PLANS = ROOT / "docs" / "plans"


def _tight(markup):
    """`markup` with the whitespace between tags removed: block structure can then be
    asserted without pinning the line breaks the renderer puts between elements."""
    return re.sub(r">\s+<", "><", markup)


class _Tags(HTMLParser):
    """Every start tag with its attributes, for the structure and security checks."""

    def __init__(self):
        super().__init__()
        self.starts = []

    def handle_starttag(self, tag, attrs):
        self.starts.append((tag, dict(attrs)))


def _scan(markup):
    parser = _Tags()
    parser.feed(markup)
    return parser.starts


class _HeadingIds(HTMLParser):
    """The id attribute of every h1 to h6 in a document."""

    def __init__(self):
        super().__init__()
        self.ids = set()

    def handle_starttag(self, tag, attrs):
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self.ids.update(value for name, value in attrs if name == "id")


HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}


def test_the_first_h1_is_the_title_and_headings_get_github_ids():
    doc = markdown.render(
        "# Plan: Read plans in the web page\n"
        "\n"
        "Intro paragraph.\n"
        "\n"
        "## Execution Plan\n"
        "\n"
        "### The Markdown subset\n"
        "\n"
        "## `factory web`\n"
        "\n"
        "## Notes / Out of Scope\n"
        "\n"
        "## Same\n"
        "\n"
        "## Same\n"
        "\n"
        "## same\n"
        "\n"
        "## Section 3.2 and worker.json\n"
        "\n"
        "## Closing hashes ##\n"
        "\n"
        "## What's new?\n"
        "\n"
        "## C++ & beyond\n"
        "\n"
        "#### Deep heading\n"
        "\n"
        "# Second level one\n"
    )
    assert doc.title == "Plan: Read plans in the web page"
    # the first level-1 heading is the title and is left out of the html
    assert "Plan: Read plans in the web page" not in doc.html
    assert doc.html.count("<h1") == 1  # a later level-1 heading stays in the html
    assert '<h1 id="second-level-one">Second level one</h1>' in _tight(doc.html)

    # levels 2 and 3, in document order; the text is the heading without its markup
    assert [(h.level, h.id, h.text) for h in doc.headings] == [
        (2, "execution-plan", "Execution Plan"),
        (3, "the-markdown-subset", "The Markdown subset"),
        (2, "factory-web", "factory web"),                       # a code span's content
        (2, "notes--out-of-scope", "Notes / Out of Scope"),       # a removed character leaves its spaces
        (2, "same", "Same"),
        (2, "same-1", "Same"),                                    # repeats get -1, -2, ... in order
        (2, "same-2", "same"),
        (2, "section-32-and-workerjson", "Section 3.2 and worker.json"),
        (2, "closing-hashes", "Closing hashes"),                  # closing hashes are dropped
        (2, "whats-new", "What's new?"),
        (2, "c--beyond", "C++ & beyond"),
    ]

    # every h1 to h6 in the html carries an id made by the plan's rule
    assert all("id" in attrs for tag, attrs in _scan(doc.html) if tag in HEADING_TAGS)
    assert '<h2 id="factory-web"><code>factory web</code></h2>' in _tight(doc.html)
    assert '<h4 id="deep-heading">Deep heading</h4>' in _tight(doc.html)
    assert "deep-heading" not in [h.id for h in doc.headings]  # only levels 2 and 3 are listed

    # a link inside a heading: the id keeps the label, the markup still renders
    doc = markdown.render("## See [the goal](https://example.com)\n")
    assert [(h.level, h.id, h.text) for h in doc.headings] == [(2, "see-the-goal", "See the goal")]
    assert '<h2 id="see-the-goal">See <a href="https://example.com">the goal</a></h2>' in _tight(doc.html)

    # only a level-1 heading can be the title, wherever it falls
    assert markdown.render("## Just a two\n").title is None
    assert markdown.render("Prose only.\n").title is None
    assert markdown.render("").title is None
    doc = markdown.render("## Before\n\n# Late\n")
    assert doc.title == "Late"
    assert [(h.level, h.id, h.text) for h in doc.headings] == [(2, "before", "Before")]

    # the heading shape is 1 to 6 hashes and a space
    doc = markdown.render("####### seven hashes\n\n#nospace\n")
    assert "<h7" not in doc.html and "<h1" not in doc.html
    assert "<p>####### seven hashes</p>" in _tight(doc.html)
    assert "<p>#nospace</p>" in _tight(doc.html)


def test_every_plan_anchor_in_this_repository_is_a_heading_id():
    plans = sorted(PLANS.rglob("*.md"))
    assert plans, "docs/plans has no plan docs to render"

    rendered = {}  # every plan renders without an exception
    for path in plans:
        doc = markdown.render(path.read_text(encoding="utf-8"))
        assert isinstance(doc.html, str) and isinstance(doc.headings, list)
        rendered[str(path.relative_to(ROOT))] = doc

    refs = {
        (str(path.relative_to(ROOT)), ref)
        for path in plans
        for task in contracts.parse_plan(path, ROOT)
        for ref in task.spec_refs
        if ref.startswith("docs/plans/") and "#" in ref
    }
    assert refs, "this repository's plans use no docs/plans/...#fragment spec refs"

    ids = {}
    for name, doc in rendered.items():
        parser = _HeadingIds()
        parser.feed(doc.html)
        ids[name] = parser.ids | {h.id for h in doc.headings}

    # devbox.md names one anchor the plan's id rule doesn't make: `### Stopping and
    # worker.json` gets the id `stopping-and-workerjson` (the rule drops the `.`),
    # but devbox-t02's spec ref says `#stopping-and-worker-json`. The plan doc landed
    # on 2026-11-22, after this plan's 2026-11-18 anchor survey, and editing it is
    # outside this task's scope, so the ref is skipped here rather than bending the
    # rule for it. The assertion at the end pins that the renderer does follow the
    # rule for that heading.
    known_broken = {"docs/plans/devbox.md#stopping-and-worker-json"}

    unresolved = []
    for source, ref in sorted(refs):
        target, _, fragment = ref.partition("#")
        if fragment in ids.get(target, set()) or ref in known_broken:
            continue
        unresolved.append(f"{source} names {ref}")
    assert not unresolved, "plan anchors that no rendered heading has: " + "; ".join(unresolved)

    assert "stopping-and-workerjson" in ids["docs/plans/devbox.md"]


def test_paragraphs_and_nested_lists():
    # consecutive lines make one paragraph, joined with a newline
    doc = markdown.render("one\ntwo\n")
    assert "<p>one\ntwo</p>" in doc.html

    for marker in ("-", "*", "+"):
        doc = markdown.render(f"{marker} bullet\n")
        assert "<ul><li>bullet</li></ul>" in _tight(doc.html)

    # blank lines between items keep one list
    doc = markdown.render("- a\n\n- b\n")
    assert "<ul><li>a</li><li>b</li></ul>" in _tight(doc.html)

    # ordered lists, with start when the first number isn't 1
    assert "<ol><li>one</li></ol>" in _tight(markdown.render("1. one\n").html)
    assert '<ol start="3"><li>three</li></ol>' in _tight(markdown.render("3. three\n").html)
    assert '<ol start="2"><li>two</li></ol>' in _tight(markdown.render("2) two\n").html)

    # a marker indented at least to the item's text starts a nested list inside the li
    doc = markdown.render("- a\n  - b\n    - c\n- d\n")
    assert "<ul><li>a<ul><li>b<ul><li>c</li></ul></li></ul></li><li>d</li></ul>" in _tight(doc.html)
    # the nested list can be an ordered one
    doc = markdown.render("- a\n  1. b\n")
    assert "<ul><li>a<ol><li>b</li></ol></li></ul>" in _tight(doc.html)
    # a plain line indented to the item's text belongs to the item
    doc = markdown.render("- item\n  continued\n")
    assert re.search(r"<li>item\s+continued</li>", _tight(doc.html))

    # nesting deeper than 16 levels is not nested further
    deep = "\n".join(" " * (2 * i) + f"- item {i}" for i in range(20)) + "\n"
    doc = markdown.render(deep)
    assert doc.html.count("<ul>") == 16
    assert doc.html.count("<li>") == 20


def test_pipe_tables_split_on_unescaped_pipes():
    doc = markdown.render(
        "| A | B |\n"
        "|---|---:|\n"
        "| 1 | 2 |\n"
        "| 3 |\n"
        "| a | b | c |\n"
        "| x \\| y | z |\n"
        "| a `code` span | *em* |\n"
        "\n"
        "After the blank line.\n"
    )
    assert (
        '<div class="table-wrap"><table><thead><tr><th>A</th><th>B</th></tr></thead>'
        "<tbody>"
        "<tr><td>1</td><td>2</td></tr>"
        "<tr><td>3</td><td></td></tr>"            # short rows are padded to the header
        "<tr><td>a</td><td>b</td></tr>"           # long rows are cut to the header
        "<tr><td>x | y</td><td>z</td></tr>"       # a backslash before a pipe is a literal pipe
        "<tr><td>a <code>code</code> span</td><td><em>em</em></td></tr>"
        "</tbody></table></div>"
    ) in _tight(doc.html)
    assert "<p>After the blank line.</p>" in _tight(doc.html)

    # a body row ends at a line without a pipe
    doc = markdown.render("| A | B |\n|---|---|\n| 1 | 2 |\nno pipes here\n")
    assert "<tr><td>1</td><td>2</td></tr>" in _tight(doc.html)
    assert "<p>no pipes here</p>" in _tight(doc.html)

    # outer pipes are optional, and a delimiter cell may carry colons
    doc = markdown.render("A | B\n:-- | --:\n1 | 2\n")
    assert "<thead><tr><th>A</th><th>B</th></tr></thead>" in _tight(doc.html)
    assert "<tr><td>1</td><td>2</td></tr>" in _tight(doc.html)

    # a line with a pipe but no delimiter row after it is not a table
    doc = markdown.render("a | b\nstill no delimiter\n")
    assert "<table>" not in doc.html
    assert "<p>a | b\nstill no delimiter</p>" in doc.html


def test_fences_quotes_and_rules():
    # three or more backticks, an optional info string, and the body escaped
    doc = markdown.render("```python\na < b & c\n```\n")
    body = html.escape("a < b & c")
    assert (f'<pre class="code"><code>{body}</code></pre>' in doc.html
            or f'<pre class="code"><code>{body}\n</code></pre>' in doc.html)
    # tildes fence the same way
    doc = markdown.render("~~~\nplain\n~~~\n")
    assert re.search(r"<pre class=\"code\"><code>plain\n?</code></pre>", doc.html)
    # a longer opening fence is not closed by a shorter run of the same character
    doc = markdown.render("````\ninner\n```\nstill body\n````\n")
    assert re.search(r"<pre class=\"code\"><code>inner\n```\nstill body\n?</code></pre>", doc.html)
    # an unclosed fence runs to the end of the text
    doc = markdown.render("```\nto the end")
    assert re.search(r"<pre class=\"code\"><code>to the end\n?</code></pre>", doc.html)

    # a block quote wraps its rendered content
    doc = markdown.render("> quoted **words**\n")
    assert "<blockquote><p>quoted <strong>words</strong></p></blockquote>" in _tight(doc.html)
    doc = markdown.render("> one line\n> and another\n")
    assert "<blockquote><p>one line\nand another</p></blockquote>" in _tight(doc.html)

    # a rule is 3 or more -, * or _, spaces allowed, and nothing else
    for rule in ("---", "***", "___", "- - -", "* * *"):
        assert re.search(r"<hr\s*/?>", markdown.render(f"{rule}\n").html)
    assert "<hr" not in markdown.render("--\n").html
    doc = markdown.render("Before.\n\n---\n\nAfter.\n")
    assert "<p>Before.</p><hr><p>After.</p>" in _tight(doc.html)


def test_inline_code_emphasis_links_and_escapes():
    doc = markdown.render(
        "A `code span`, ``a `nested` one`` and ` padded `.\n"
        "\n"
        "**bold** and *em*; snake_case_names and __dunder__ never emphasise.\n"
        "\n"
        "[label](https://example.com/page), [frag](#anchor), "
        "[titled](https://example.com/ \"a title\") and [docs](docs/plans/webui.md).\n"
        "\n"
        "Autolinks <https://example.com/auto> and <http://example.com/plain>.\n"
        "\n"
        "![alt words](image.png) is its alt text alone.\n"
        "\n"
        "Escapes \\* \\_ \\[ \\! and \\\\ stay literal.\n"
    )
    # a code span runs to the next run of backticks of the same length
    assert "<code>code span</code>" in doc.html
    assert "<code>a `nested` one</code>" in doc.html
    # one leading and one trailing space are stripped when both are present
    assert "<code>padded</code>" in doc.html
    assert "<strong>bold</strong>" in doc.html
    assert "<em>em</em>" in doc.html
    # underscores never make emphasis
    assert "snake_case_names" in doc.html and "<em>case_names</em>" not in doc.html
    assert "__dunder__" in doc.html and "<strong>dunder</strong>" not in doc.html

    assert '<a href="https://example.com/page">label</a>' in doc.html
    assert '<a href="#anchor">frag</a>' in doc.html
    # the quoted title is part of the link source, not the target
    assert '<a href="https://example.com/">titled</a>' in doc.html
    assert '<span class="ref" title="docs/plans/webui.md">docs</span>' in doc.html
    # autolinks go through the same rendering
    assert '<a href="https://example.com/auto">https://example.com/auto</a>' in doc.html
    assert '<a href="http://example.com/plain">http://example.com/plain</a>' in doc.html

    # an image renders as its alt text alone
    assert "alt words" in doc.html
    assert "<img" not in doc.html

    # a backslash before ASCII punctuation gives that character
    assert "Escapes * _ [ ! and \\ stay literal." in doc.html

    # unmatched markers are text, never dropped
    doc = markdown.render("An `unclosed span and a *loose star.\n")
    assert "<code>" not in doc.html and "<em>" not in doc.html
    assert "An `unclosed span and a *loose star." in doc.html


def test_the_link_hook_decides_each_href():
    doc = markdown.render(
        "[a](https://x.test/1) [b](http://x.test/2) [c](#anchor) [d](/abs) "
        "[e](relative.md) [f](mailto:a@b.test) [g](javascript:alert(1))\n"
    )
    # the default hook keeps https://, http:// and # targets
    assert '<a href="https://x.test/1">a</a>' in doc.html
    assert '<a href="http://x.test/2">b</a>' in doc.html
    assert '<a href="#anchor">c</a>' in doc.html
    # every other target loses its link, and keeps its target in the title
    for label, target in (("d", "/abs"), ("e", "relative.md"),
                          ("f", "mailto:a@b.test"), ("g", "javascript:alert(1)")):
        assert f'<span class="ref" title="{target}">{label}</span>' in doc.html
    assert 'href="javascript:' not in doc.html

    # a returned href is escaped, and so is the target of a span that keeps no link
    doc = markdown.render("[q](https://x.test/?a=1&b=2)\n")
    assert f'<a href="{html.escape("https://x.test/?a=1&b=2")}">q</a>' in doc.html
    doc = markdown.render("[r](a&b)\n")
    assert f'<span class="ref" title="{html.escape("a&b")}">r</span>' in doc.html

    # a custom hook decides every href, replacing the default allowlist entirely
    seen = []

    def link(target):
        seen.append(target)
        if target == "docs/plans/webui.md#security":
            return "/plans/webui#security"
        if target == "https://x.test/auto":
            return "/hooked/auto"
        return None

    doc = markdown.render(
        "[webui](docs/plans/webui.md#security) [plain](https://x.test/) "
        "<https://x.test/auto>\n",
        link=link,
    )
    assert '<a href="/plans/webui#security">webui</a>' in doc.html
    assert '<span class="ref" title="https://x.test/">plain</span>' in doc.html
    # autolinks go through the hook too, with the url as their label
    assert '<a href="/hooked/auto">https://x.test/auto</a>' in doc.html
    assert set(seen) == {"docs/plans/webui.md#security", "https://x.test/", "https://x.test/auto"}


def test_the_fence_hook_can_replace_a_block():
    calls = []

    def fence(info, body):
        calls.append((info, body))
        if info == "rows":
            return '<ul class="rows"><li>a & b</li></ul>'
        return None

    doc = markdown.render(
        "```python extra words\n"
        "first\n"
        "  second indented\n"
        "```\n"
        "\n"
        "```\n"
        "plain body\n"
        "```\n"
        "\n"
        "~~~rows\n"
        "the yaml\n"
        "~~~\n",
        fence=fence,
    )
    # the first word of the info string, empty when there is none; the body verbatim
    assert [info for info, _ in calls] == ["python", "", "rows"]
    first = "first\n  second indented"
    assert calls[0][1] in (first, first + "\n")
    assert calls[1][1] in ("plain body", "plain body\n")
    assert calls[2][1] in ("the yaml", "the yaml\n")

    # a returned string replaces the whole block, as it is
    assert '<ul class="rows"><li>a & b</li></ul>' in doc.html
    # None falls back to <pre class="code"><code> with the body escaped
    assert re.search(r"<pre class=\"code\"><code>first\n  second indented\n?</code></pre>", doc.html)
    assert re.search(r"<pre class=\"code\"><code>plain body\n?</code></pre>", doc.html)
    assert doc.html.count("<pre") == 2

    # an unclosed fence is a fenced block too, and reaches the hook
    calls.clear()
    markdown.render("````\nnever closed", fence=fence)
    assert [info for info, _ in calls] == [""]
    assert calls[0][1] in ("never closed", "never closed\n")


def test_the_term_hook_sees_words_and_code_spans():
    text = (
        "plan-pages-t01 with snake_case and a `whole code span` here.\n"
        "\n"
        "## A heading says qqhead\n"
        "\n"
        "- a list item says qqitem\n"
        "\n"
        "[qqlabel](https://x.test/) and <http://qqauto.test/> alone.\n"
        "\n"
        "```\n"
        "qqfenced\n"
        "```\n"
    )
    calls = []

    def term(word, code):
        calls.append((word, code))
        return None

    markdown.render(text, term=term)

    # words are maximal runs of letters, digits, _ and -; code spans are whole
    assert ("plan-pages-t01", False) in calls
    assert ("snake_case", False) in calls
    assert ("whole code span", True) in calls
    assert ("whole", False) not in calls      # a code span's content is not also a word
    for word in ("plan", "pages", "t01", "whole", "span"):
        assert (word, False) not in calls
    # headings and list text are text
    assert ("qqhead", False) in calls
    assert ("qqitem", False) in calls
    # never inside link labels, autolinks or fenced blocks
    for word in ("qqlabel", "qqauto", "qqfenced"):
        assert (word, False) not in calls
        assert (word, True) not in calls

    # a returned string replaces the word or the whole code span, as it is
    def term(word, code):
        if word == "plan-pages-t01" and not code:
            return '<a class="task-ref" href="/tasks/plan-pages-t01">plan-pages-t01</a>'
        if word == "mono" and code:
            return "<b>mono</b>"
        return None

    doc = markdown.render("See plan-pages-t01 and `mono`.\n", term=term)
    assert '<a class="task-ref" href="/tasks/plan-pages-t01">plan-pages-t01</a>' in doc.html
    assert "<b>mono</b>" in doc.html
    assert "<code>" not in doc.html

    # None keeps the default rendering
    prose = "Words like plan-pages-t01 and `code` in a paragraph.\n"
    assert markdown.render(prose, term=lambda word, code: None).html == markdown.render(prose).html


def test_raw_html_is_escaped_and_no_markup_is_injected():
    doc = markdown.render(
        "<script>alert(1)</script>\n"
        "\n"
        "<details>\n"
        "\n"
        "<img onerror=x>\n"
        "\n"
        "Inline <b>bold</b>, \"quotes\", 'single', & ampersand, < and >.\n"
        "\n"
        "`code with <tags> & more`\n"
    )
    # raw html comes out as text, escaped with html.escape(quote=True)
    assert html.escape("<script>alert(1)</script>") in doc.html
    assert html.escape("<details>") in doc.html
    assert html.escape("<img onerror=x>") in doc.html
    assert html.escape("Inline <b>bold</b>, \"quotes\", 'single', & ampersand, < and >.") in doc.html
    assert f"<code>{html.escape('code with <tags> & more')}</code>" in doc.html

    # the same holds in every block, and nothing injects an attribute or an element
    doc = markdown.render(
        "## Heading with <script>\n"
        "\n"
        "- item with <details open>\n"
        "\n"
        "| a <th> | b |\n"
        "|---|---|\n"
        "| <td> | style=x |\n"
        "\n"
        "> quote with <img onerror=x>\n"
        "\n"
        "<div style=\"color:red\" onclick=\"x()\">raw</div>\n"
        "\n"
        "[x](javascript:alert(1))\n"
    )
    assert html.escape("<script>") in doc.html
    assert html.escape("<details open>") in doc.html
    assert html.escape("<img onerror=x>") in doc.html
    assert html.escape('<div style="color:red" onclick="x()">raw</div>') in doc.html
    assert 'href="javascript:' not in doc.html

    starts = _scan(doc.html)
    tags = {tag for tag, _ in starts}
    assert not tags & {"script", "style", "img", "details", "iframe"}
    bad = [name for _, attrs in starts for name in attrs
           if name == "style" or name.startswith("on")]
    assert bad == []
    assert all("id" in attrs for tag, attrs in starts if tag in HEADING_TAGS)


def test_pathological_input_renders_quickly():
    # 1 MB of unclosed backticks, asterisks, brackets and parentheses
    hostile = "`" * 125_000 + "*" * 125_000 + "[" * 125_000 + "(" * 125_000 + "`*" * 250_000
    assert len(hostile) == 1_000_000
    started = time.monotonic()
    doc = markdown.render(hostile)
    assert isinstance(doc.html, str)
    assert time.monotonic() - started < 2.0

    # 5,000 list lines, each indented two spaces more than the one before
    deep = "\n".join(" " * (2 * i) + f"- item {i}" for i in range(5_000)) + "\n"
    started = time.monotonic()
    doc = markdown.render(deep)
    elapsed = time.monotonic() - started
    assert doc.html.count("<ul>") == 16     # nesting stops at 16 levels
    assert doc.html.count("<li>") == 5_000  # and no line is dropped
    assert elapsed < 2.0


def test_the_term_hook_never_sees_internal_placeholders():
    calls = []

    def term(word, code):
        calls.append((word, code))
        if not code and word.isdigit():
            return f"<b>{word}</b>"
        return None

    doc = markdown.render("Run `ticks` for 12 seconds.", term=term)
    assert doc.html == "<p>Run <code>ticks</code> for <b>12</b> seconds.</p>"
    assert "\x00" not in doc.html
    assert ("ticks", True) in calls
    assert ("0", False) not in calls
