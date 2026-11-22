# Plan: Read plans in the web page

**Status:** Planned (2026-11-18). Workstream scoped; awaiting kickoff: `plan-pages-t01` can run once this plan is merged and synced. Roadmap: [NEXT.md item 17](../../NEXT.md#17-read-plans-in-the-web-page).

---

## Execution Plan

### Locked Decisions

| Decision | Choice |
|---|---|
| Rendering | **A built-in Markdown subset.** New `factory/web/markdown.py` renders what plans are written in (headings, paragraphs, nested lists, pipe tables, fenced code, quotes, rules, inline code, emphasis, links) with the standard library. It keeps the [webui](webui.md) decision of no new dependencies. Raw HTML in a plan is shown as text, never passed through |
| Contracts | **Live task rows.** Each fenced contract block becomes the plan's tasks, as the board shows them. A row has the status, the id linking to the task page, the goal, what it waits for, its PR, risk, builds and cost. The YAML stays under a fold below the rows. A task id in the prose links to its task page, with its status mark |
| Source | **The checkout, with a drift note.** The page reads the plan file in the repository `factory web` was started in, which is what `factory sync` loads, so drafts show too. When the file's contracts differ from the board's, the page says how and offers Load plans |
| Look | **Fixed by mockups committed with this plan.** [`docs/design/webui/plans.html`](../design/webui/plans.html) and [`plan.html`](../design/webui/plan.html) are new. The new rules in [`app.css`](../../factory/web/static/app.css) are added and no existing rule changed. The other mockups gain the Plans navigation item and the new links |

### Milestones

| # | Deliverable | Exit criteria | Parallelizable with |
|---|---|---|---|
| **M1** | The Markdown renderer | The t01 tests in `tests/test_web_markdown.py` pass, including rendering every plan in this repository and resolving all of its plan anchors | — |
| **M2** | The Plans page and plan pages | The t02 tests in `tests/test_web.py` pass, and `/plans` and `/plans/NAME` look like `plans.html` and `plan.html` | — |
| **M3** | Plans and tasks link to each other | The t03 tests in `tests/test_web.py` pass: board cards, task breadcrumbs and Reads link into plan pages | — |
| **M4** | Docs | `tests/test_templates.py::test_the_docs_describe_the_plan_pages` passes, and `tests/test_templates.py` passes | — |

**Sequence:** `M1 → M2 → M3 → M4`. t02 and t03 both change `factory/web/server.py`, `factory/web/views.py` and `tests/test_web.py`, so they run one after the other. t04 describes what t02 and t03 built.

### Task Contracts

| Milestone | Task IDs | Coverage |
|---|---|---|
| **M1** | `plan-pages-t01` | New `factory/web/markdown.py` (the subset, heading ids, the fence, link and term hooks, escaping); new `tests/test_web_markdown.py` |
| **M2** | `plan-pages-t02` | `/plans` and `/plans/NAME` in `factory/web/server.py`; the two pages, the plan cache, the task rows, links, task ids, the drift notice and the Plans navigation item in `factory/web/views.py`; tests in `tests/test_web.py` |
| **M3** | `plan-pages-t03` | Read the plan on the board's plan cards; the task page's breadcrumb and Reads links in `factory/web/views.py`; tests in `tests/test_web.py` |
| **M4** | `plan-pages-t04` | `docs/reference.md`, `docs/architecture.md`, the factory-ops skill (template and installed copy) and `NEXT.md`; a new test in `tests/test_templates.py` |

```yaml
- id: plan-pages-t01
  goal: "New factory/web/markdown.py renders the Markdown that plans are written in to safe HTML with the standard library alone: headings with GitHub-style ids, paragraphs, nested lists, pipe tables, fenced code, block quotes, rules, inline code, emphasis and links. Three hooks let a caller replace a fenced block, choose each link's href, and turn a word or a code span into its own HTML"
  spec_refs:
    - "docs/plans/plan-pages.md#the-markdown-subset"
    - "docs/plans/plan-pages.md#heading-ids"
    - "docs/plans/plan-pages.md#hooks"
    - "docs/plans/plan-pages.md#security"
    - "factory/web/views.py"
  depends_on: []
  non_goals:
    - "Any page, route or change to factory/web/server.py or factory/web/views.py (plan-pages-t02)"
    - "Full CommonMark: setext headings, reference-style links, footnotes, HTML blocks, hard line breaks, strikethrough and task-list checkboxes"
    - "Passing raw HTML through, or adding a dependency"
    - "Changes outside factory/web/markdown.py, tests/test_web_markdown.py and this task's session log"
  acceptance:
    - "`markdown.render(text, fence=None, link=None, term=None)` returns a `Doc` with `title`, `html` and `headings`. `title` is the text of the first level-1 heading, or None when there is none, and that heading is left out of `html`. `headings` lists every level-2 and level-3 heading in document order as `Heading(level, id, text)`, where `text` is the heading without its inline markup"
    - "Every construct in the plan's Markdown subset table renders to the elements and classes the table gives, from the source shapes it gives. Lists nest by indentation, and nesting deeper than 16 levels is not nested further. A table's rows are cut or padded to the header's cell count, and a backslash before a pipe is a literal pipe inside a cell"
    - "Every h1 to h6 has an id made by the rule in the plan's Heading ids section, and a repeated id gets `-1`, `-2`… in document order. For every spec ref of the form `docs/plans/PATH.md#FRAGMENT` in this repository's plans, FRAGMENT is the id of a heading in that plan rendered with `render`"
    - "Inline: a code span is a run of backticks up to the next run of the same length. `**text**` is strong and `*text*` is emphasis, while underscores never make emphasis. Also supported: `[label](target)`, `[label](target \"title\")`, `<https://…>` and `<http://…>` autolinks, `![alt](src)` rendered as its alt text alone, and a backslash before ASCII punctuation, which gives that character"
    - "`link(target)` returns the href to use, or None. The default keeps targets starting with `https://`, `http://` or `#`, and returns None for every other target. A link the hook returns None for renders as `<span class=\"ref\" title=\"TARGET\">label</span>`, and a returned href is escaped. With the default hook, `[x](javascript:alert(1))` has no href"
    - "`fence(info, body)` is called for every fenced block with the first word of its info string (empty when there is none) and its body verbatim. A returned string replaces the whole block as it is. None gives `<pre class=\"code\"><code>BODY</code></pre>` with BODY escaped"
    - "`term(text, code)` is called with the whole content of each code span (code=True), and with each maximal run of letters, digits, `_` and `-` in other text (code=False). It is never called inside link labels, autolinks or fenced blocks. A returned string replaces that span or run as it is, and None keeps the default rendering"
    - "Every character of text from the source reaches `html` escaped with html.escape(quote=True). Source such as `<script>alert(1)</script>`, `<details>` or `<img onerror=x>` comes out as text, and no element in `html` has a `style` or `on…` attribute, except in what a hook returned"
    - "Each of these inputs renders in under 2 seconds: 1 MB of unclosed backticks, asterisks, brackets and parentheses; and 5,000 list lines, each indented two spaces more than the one before"
    - "Every Markdown file under docs/plans/ renders without an exception"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_web_markdown.py::test_the_first_h1_is_the_title_and_headings_get_github_ids tests/test_web_markdown.py::test_every_plan_anchor_in_this_repository_is_a_heading_id tests/test_web_markdown.py::test_paragraphs_and_nested_lists tests/test_web_markdown.py::test_pipe_tables_split_on_unescaped_pipes tests/test_web_markdown.py::test_fences_quotes_and_rules tests/test_web_markdown.py::test_inline_code_emphasis_links_and_escapes tests/test_web_markdown.py::test_the_link_hook_decides_each_href tests/test_web_markdown.py::test_the_fence_hook_can_replace_a_block tests/test_web_markdown.py::test_the_term_hook_sees_words_and_code_spans tests/test_web_markdown.py::test_raw_html_is_escaped_and_no_markup_is_injected tests/test_web_markdown.py::test_pathological_input_renders_quickly"
    - "uv run pytest -q tests/test_web_markdown.py"
  risk: medium

- id: plan-pages-t02
  goal: "`factory web` has a Plans page at /plans that lists every plan doc the config's `plans` globs find, and a page per plan at /plans/NAME. The plan page renders the plan from the checkout with its contents, and shows each contract as a task row with its status on the board. It links task ids and other plans, and says when the plan and the board disagree. Plans is in every page's navigation, and the pages look like docs/design/webui/plans.html and plan.html"
  spec_refs:
    - "docs/plans/plan-pages.md#plans-page"
    - "docs/plans/plan-pages.md#plan-page"
    - "docs/plans/plan-pages.md#the-plan-and-the-board"
    - "docs/plans/plan-pages.md#links-and-task-ids"
    - "docs/plans/plan-pages.md#reading-plans"
    - "docs/plans/plan-pages.md#security"
    - "docs/design/webui/plans.html"
    - "docs/design/webui/plan.html"
    - "factory/contracts.py"
  depends_on:
    - plan-pages-t01
  non_goals:
    - "Links into plan pages from the board's plan cards or the task page (plan-pages-t03)"
    - "Editing plans from the page, or the server writing the board: Load plans runs `factory sync` as a job, as it does on the board"
    - "Serving any repository file other than the plan docs the `plans` globs find, or reading a path taken from the URL"
    - "Reading plans from a git ref instead of the checkout"
    - "Changing existing rules in factory/web/static/app.css, app.js, or the mockups"
  acceptance:
    - "GET /plans/NAME finds NAME among the stems of contracts.discover_plans(root, config), and never treats it as a path. An unknown NAME gets a 404 page that says `NAME isn't a plan in this repository` and links to /plans. A NAME that several plan docs share gets a 404 page naming their repo-relative paths. The file is read as UTF-8, with invalid bytes replaced"
    - "The plan page has the classes and structure of docs/design/webui/plan.html. Its title is NAME. The breadcrumbs are Board, Plans and NAME. The lede is the plan's title without a leading `Plan: `, or NAME when it has none. The facts are `tasks` (the strip), `status` (the counts text of the board's plan card), `spent` and `file` (the repo-relative path). Run plan, shown when the board's card would show it, and `Show on the board`, a link to /#plan-NAME, appear only when the plan has tasks on the board. The contents nav lists the level-2 headings with their level-3 headings nested, and is left out when there are none. The rendered plan is in <div class=\"prose\">. The page's <main> has no data-refresh"
    - "Each fenced yaml block that contracts.parse_text loads tasks from becomes <ul class=\"rows task-cards\">, with one <li class=\"row\" id=\"task-ID\"> per contract in file order. A task on the board shows its status word, class and mark as the board does, and its id links to /tasks/ID. A task not on the board shows `Not loaded` with class s-new, and its id is a plain <span class=\"id\">. Then come the goal from the file, and a .why line. That line holds `waits for` and links to what the task waits for (the board's readiness for a waiting task, the file's depends_on for a task not loaded), and `pull request #N` linking to the task's PR when it has one. The end shows risk, builds and cost. A <details class=\"fold\" id=\"contracts-K\"> with the summary `The contracts as written, N tasks` and the block's YAML, escaped, follows the rows. Any other fenced block stays code. When contracts.parse_text raises ContractError for the file, every block stays code"
    - "In the prose, a task id on the board renders as <a class=\"task-ref\" href=\"/tasks/ID\"><i class=\"CLASS\"></i>ID</a>, with the task's status class. A code span that is only a task id keeps its <code> inside the link. A link to a relative target that resolves, against the plan file's directory, to a plan doc the globs find goes to /plans/STEM, keeping any #fragment. `https://`, `http://` and `#` targets are kept. Every other target is rendered without a link, with its target in the title"
    - "The page compares the file's contracts with the board. New tasks are in the file and not on the board. Changed tasks are on the board with a stored contract that differs from the file's (`task.to_json()`, as `db.sync` counts updates). Removed tasks are board rows whose plan is this file's repo-relative path and which the file no longer has. When any of these exist, a <div class=\"notice notice-you\"> says `This plan has changed since the board loaded it: ` and then the non-zero parts of `N new task(s), M changed, K removed`, followed by `. Load plans to bring the board up to date.`. It holds the Load plans form (`factory sync`, with next set to /plans/NAME). When contracts.parse_text raises ContractError, a <div class=\"notice notice-bad\"> says `The board can't load this plan's contracts: ` and the error. Otherwise there is no notice"
    - "GET /plans has the classes and structure of docs/design/webui/plans.html. The lede is `N plan(s), M with work left.`, followed by `K isn't on the board yet.` or `K aren't on the board yet.` when K is above 0. M counts plans with a task on the board that is neither merged nor on hold, and K counts plans with contracts but no task on the board. With no plan docs the lede is `No plans yet.`, followed by a line naming the config's `plans` globs. Each plan doc is one <li id=\"plan-NAME\"> in <ul class=\"plan-list\">, sorted by name. A row has the name linking to /plans/NAME, the strip of its board tasks in the board's order, the title and repo-relative path, and the board's counts text and cost. When the plan has no task on the board, the counts text is `Not on the board yet`, or `No task contracts` when the file has none. The page's <main> has data-refresh=\"2\", and its top bar has Load plans with next set to /plans"
    - "App keeps each plan doc's title and contracts keyed by its path, size and modification time. A request parses a plan doc, through contracts.parse_text called as an attribute of the factory.contracts module, only when one of those three changed since the last parse. Two requests for /plans with no file changed parse each plan once"
    - "The navigation on every page reads Board, Plans, Activity, linking to /, /plans and /activity, with aria-current=\"page\" on Plans for /plans and /plans/NAME. The navigation assertion in tests/test_web.py::test_activity_lists_jobs_newest_first_with_their_output is updated to include Plans"
    - "Text from a plan file reaches the page only escaped or as the markdown renderer's output. A plan holding `<script>`, raw HTML, a `javascript:` link, and a contract whose goal has `<script>` produces no markup from any of them"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_web.py::test_plan_page_renders_the_plan_from_the_checkout_with_its_contents tests/test_web.py::test_plan_page_shows_each_contract_as_a_task_row_with_its_board_status tests/test_web.py::test_plan_page_links_task_ids_and_other_plans tests/test_web.py::test_plan_page_says_when_the_plan_and_the_board_disagree tests/test_web.py::test_plan_page_with_contracts_the_board_cant_load tests/test_web.py::test_unknown_and_ambiguous_plan_names_are_404s tests/test_web.py::test_plan_pages_escape_the_plan_text tests/test_web.py::test_plans_page_lists_every_plan_doc_with_its_status tests/test_web.py::test_plan_docs_are_parsed_again_only_when_they_change tests/test_web.py::test_every_page_has_plans_in_its_navigation"
    - "uv run pytest -q tests/test_web.py tests/test_web_markdown.py"
  risk: medium

- id: plan-pages-t03
  goal: "Plans and tasks link to each other. Every plan card on the board has a Read the plan link, a task page's breadcrumb goes to the task's row on its plan page, and a task's Reads list links each plan section it names"
  spec_refs:
    - "docs/plans/plan-pages.md#links-between-plans-and-tasks"
    - "docs/design/webui/board.html"
    - "docs/design/webui/task.html"
  depends_on:
    - plan-pages-t02
  non_goals:
    - "Changing the plan pages themselves (plan-pages-t02)"
    - "Links into plan pages from the transcript, run form or activity pages beyond their breadcrumbs"
    - "Turning spec refs that aren't plan docs into links: the page serves no other repository file"
  acceptance:
    - "On the board, the .plan-end of each plan card whose plan file is among the plan docs the `plans` globs find starts with <a class=\"btn btn-quiet\" href=\"/plans/NAME\">Read the plan</a>. A card whose plan file no longer exists has no such link"
    - "The plan crumb links to /plans/NAME#task-ID on the task page, the transcript page and a task's run form, and to /plans/NAME on a plan's run form. Each falls back to /#plan-NAME, as before, when the plan file no longer exists. The `Back to PLAN` links on error pages are unchanged. The breadcrumb assertions of `/#plan-demo` and `/#plan-form` in tests/test_web.py::test_task_page_shows_the_contract_with_what_it_waits_for_and_what_needs_it, test_transcript_page_shows_each_step_with_its_calls_and_results and test_run_form_lists_what_will_run_and_previews_the_command are updated to the new links"
    - "In a task page's Reads list, a spec ref `PATH` or `PATH#FRAGMENT` whose PATH is a plan doc the globs find becomes <a href=\"/plans/STEM#FRAGMENT\">REF</a> inside its <li class=\"mono\">, without the fragment when there is none. Every other spec ref stays text"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_web.py::test_board_plan_cards_link_to_their_plan_pages tests/test_web.py::test_breadcrumbs_go_to_the_tasks_row_on_its_plan_page tests/test_web.py::test_task_page_links_spec_refs_into_plan_pages"
    - "uv run pytest -q tests/test_web.py"
  risk: low

- id: plan-pages-t04
  goal: "The docs describe the plan pages. The reference's web page section lists /plans and /plans/NAME, and the architecture's web page section says how plan pages read and render plans safely. The factory-ops skill points to the pages, and NEXT.md marks item 17 done"
  spec_refs:
    - "docs/plans/plan-pages.md#design"
    - "docs/reference.md#the-web-page"
    - "docs/architecture.md#the-web-page"
  depends_on:
    - plan-pages-t03
  non_goals:
    - "Code changes"
    - "Screenshots or other images"
    - "Rewriting the parts of the web page docs that plan pages don't change"
  acceptance:
    - "docs/reference.md's `### The web page` page table has rows for `/plans` (every plan doc with its tasks' statuses) and `/plans/NAME` (the plan rendered, its contracts as task rows with their statuses, task ids and other plans linked, and a notice when the plan and the board disagree)"
    - "docs/architecture.md's `## The web page` section lists both pages. It says that plan docs are found by the `plans` globs in the checkout, never by a path in the URL, and are rendered by factory/web/markdown.py, a Markdown subset with raw HTML shown as text. It also says that a plan page doesn't refresh itself and that Load plans brings the board up to date with a changed plan"
    - "factory/templates/skills/factory-ops/SKILL.md says that `factory web` shows every plan at /plans, with each plan's page linking its tasks. .claude/skills/factory-ops/SKILL.md is the same file, as tests/test_templates.py::test_this_repository_uses_the_factory_it_ships requires"
    - "NEXT.md marks item 17 done in its table, with a link to docs/architecture.md#the-web-page"
    - "A new test, tests/test_templates.py::test_the_docs_describe_the_plan_pages, checks the four statements above by the strings `/plans/NAME` in docs/reference.md and docs/architecture.md, `markdown.py` in docs/architecture.md, `/plans` in the factory-ops template, and `architecture.md#the-web-page` on NEXT.md's item 17 row"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_templates.py::test_the_docs_describe_the_plan_pages"
    - "uv run pytest -q tests/test_templates.py"
  risk: low
```

Planned test additions:

| Task | File | Tests |
|---|---|---|
| t01 | new `tests/test_web_markdown.py` | `test_the_first_h1_is_the_title_and_headings_get_github_ids`, `test_every_plan_anchor_in_this_repository_is_a_heading_id`, `test_paragraphs_and_nested_lists`, `test_pipe_tables_split_on_unescaped_pipes`, `test_fences_quotes_and_rules`, `test_inline_code_emphasis_links_and_escapes`, `test_the_link_hook_decides_each_href`, `test_the_fence_hook_can_replace_a_block`, `test_the_term_hook_sees_words_and_code_spans`, `test_raw_html_is_escaped_and_no_markup_is_injected`, `test_pathological_input_renders_quickly` |
| t02 | `tests/test_web.py` | `test_plan_page_renders_the_plan_from_the_checkout_with_its_contents`, `test_plan_page_shows_each_contract_as_a_task_row_with_its_board_status`, `test_plan_page_links_task_ids_and_other_plans`, `test_plan_page_says_when_the_plan_and_the_board_disagree`, `test_plan_page_with_contracts_the_board_cant_load`, `test_unknown_and_ambiguous_plan_names_are_404s`, `test_plan_pages_escape_the_plan_text`, `test_plans_page_lists_every_plan_doc_with_its_status`, `test_plan_docs_are_parsed_again_only_when_they_change`, `test_every_page_has_plans_in_its_navigation` |
| t03 | `tests/test_web.py` | `test_board_plan_cards_link_to_their_plan_pages`, `test_breadcrumbs_go_to_the_tasks_row_on_its_plan_page`, `test_task_page_links_spec_refs_into_plan_pages` |
| t04 | `tests/test_templates.py` | `test_the_docs_describe_the_plan_pages` |

Each verification command names its tests, so a missing test fails the gate rather than passing with zero selected. Every task has at least one new test that fails before its change, which the strict flow's test step needs: this repository runs `flow: strict`. That includes the docs task, t04.

The project sets no `e2e`, so no task adds an e2e test. `session_log` is set, so each task adds its own `docs/sessions/<date>-<task id>.md`.

Every task changes the factory itself, and runs through `factory run` like the webui tasks did. The tests use the `home` and `repo` fixtures, whose plan is `docs/plans/demo/demo.md` (`demo`). A test that needs a second plan, an ambiguous name or a changed contract writes it into the `repo` checkout. No test needs the network or a browser.

### Risks

1. **A hand-written Markdown parser is a new place for markup to slip through.** Plan text is written by people and agents, and the page serves it next to buttons that run commands. **Action:** text has one way out, through html.escape. Raw HTML is never passed through, and links default to an allowlist of `https://`, `http://` and `#`. The CSP from webui stays as it is, with no inline scripts or styles. t01 and t02 test `<script>`, raw HTML, `on…` attributes and `javascript:` links.
2. **A parser can hang or recurse too deep on hostile input.** **Action:** t01 renders 1 MB of unclosed inline markers, and 5,000 ever-deeper list lines, each in under 2 seconds. Nesting stops at 16 levels.
3. **The page renders differently from GitHub.** Plans are reviewed on GitHub, and the subset isn't CommonMark. **Action:** a survey on 2026-11-18 found no images, block quotes, setext headings or indented fences in `docs/plans/`. The subset covers every construct in use. t01 renders every plan in the repository and checks that all 123 plan anchors used in `spec_refs`, this plan's included, are heading ids. A construct outside the subset degrades to text and never raises.
4. **The anchor test makes every future plan keep its anchors working.** **Action:** that is intended. A broken anchor is a dead link on the plan page and a wrong `spec_refs` entry for the agents. The plan PR's CI catches it before the plan merges.
5. **Parsing every plan is slow.** PyYAML took about 600 ms for this repository's 13 plans, measured on 2026-11-18, and the Plans page refreshes every 2 seconds. **Action:** t02 caches each plan doc's title and contracts by path, size and modification time, and tests that unchanged files aren't parsed again. The plan page doesn't refresh itself, since it is read rather than watched, and a refresh would take the reader's place and selection.
6. **The checkout can be on another branch than the board's plans came from.** Several sessions share this checkout. **Action:** the page reads what `factory sync` reads and shows the file's path. The drift notice says when the file and the board disagree, so a branch switch shows up as a difference rather than passing silently.
7. **Existing tests assert the old breadcrumb and navigation.** **Action:** t02 and t03 name each test and assertion to update. The strict flow's tester makes those edits, so they are locked like its new lines.
8. **No browser runs in the sandbox, so the look isn't gated.** **Action:** the mockups and rules are committed with this plan, and the contracts name them, so the reviewer compares markup and classes. You compare `/plans` and a plan page, wide and below 45rem, with the mockups before merging t02.
9. **Merge conflicts with flow-tuning and security-review.** `flow-tuning-t05` and `security-review-t07` also edit `docs/reference.md`, `docs/architecture.md`, `NEXT.md` and the factory-ops skill, and `security-review-t05` adds a role's display name to `factory/web/views.py`. **Action:** t04 only adds lines to the web page sections, item 17 and the skill's `factory web` bullet. A conflicting PR goes through the factory's conflict resolution (`factory run TASK`).

---

## Problem

The board and the plans live apart.

- **The web page shows tasks without their plans.** A plan card (`factory/web/views.py:269`, `_plan`) shows status squares and task rows, but nothing of the plan behind them: its locked decisions, milestones, design, risks or what's out of scope. The page has no route for a plan (`factory/web/server.py:301`, `App.handle`).
- **The plan doc shows contracts without their status.** Read in an editor or on GitHub, a plan's contracts are YAML. Whether `webui-t05` is merged, failed or waiting takes `factory status`.
- **Links stop at the plan.** A task page's breadcrumb goes to the plan's card on the board (`views.task`), not to the plan. Its Reads list prints `docs/plans/webui.md#the-board-lock` as text (`views._contract_block`, `factory/web/views.py:708`), so the section the agent was told to read is a copy-paste away.
- **A changed plan is silent.** When someone edits a plan and forgets `factory sync`, the board runs the old contracts, and nothing shows that the file and the board disagree.

## Goal

From the web page, you can open any plan as a readable page and see each of its tasks' status in place, then click through to the tasks. From a task, you can get back to the plan section that explains it. When a plan and the board disagree, the plan page says so and offers Load plans. Nothing new is installed, and the look matches the rest of the page.

## Design

```
 GET /plans            ─► discover_plans(root, config) ─► title + contracts of each ─┐   (cached by path,
 GET /plans/NAME       ─► the one plan doc whose stem is NAME                         │    size, mtime)
                           │ read from the checkout, UTF-8, errors replaced           │
                           ▼                                                          │
                 markdown.render(text, fence=…, link=…, term=…)  factory/web/markdown.py
                           │ fence: a contract block → task rows with board statuses  │
                           │ link:  a plan doc → /plans/STEM#frag; http(s), # kept    ├─► views.py ─► HTML
                           │ term:  a task id on the board → /tasks/ID, status mark   │
                           ▼                                                          │
                 file contracts vs board rows → drift notice + Load plans (factory sync job)
```

**Principles.**
- **Read, never write.** The server reads plan files found by the config's globs and the board through its read-only connection. Load plans is the existing `factory sync` job.
- **One renderer, no hooks into the page from Markdown.** `markdown.py` knows nothing about tasks or plans. The plan page supplies the three hooks, so all of the factory's knowledge stays in `views.py`.
- **The board's words.** Task rows on a plan page use the board's status words, classes, marks, counts text and readiness, through the same helpers (`views.status`, `views._counts`, `db.readiness`), so a plan page and the board never disagree.

### The Markdown subset

Blocks:

| Construct | Source | Output |
|---|---|---|
| Heading | 1 to 6 `#`, a space, the text; closing `#`s dropped | `<hN id="ID">`; the first level-1 heading is the title and isn't in `html` |
| Paragraph | consecutive non-blank lines that don't start another block | `<p>`, lines joined with a newline |
| Bullet list | `-`, `*` or `+`, then a space | `<ul><li>` |
| Ordered list | digits, then `.` or `)`, then a space | `<ol>`, with `start="N"` when the first number isn't 1 |
| Nesting | a later line indented at least to the item's text belongs to the item; a list marker there starts a nested list; blank lines between items keep one list | the nested `<ul>` or `<ol>` inside its `<li>`; deeper than 16 levels isn't nested further |
| Table | a line with a `\|`, then a delimiter row of `-` cells with optional `:`; body rows until a blank line or a line without `\|` | `<div class="table-wrap"><table><thead><tr><th>`…`</th></tr></thead><tbody><tr><td>`…`</td></tr></tbody></table></div>`; outer pipes optional; a backslash before a pipe is a literal pipe |
| Fenced code | 3 or more backticks or tildes, optional info string; closed by a fence of the same character at least as long, or the end of the text | the fence hook's HTML, else `<pre class="code"><code>`…`</code></pre>` |
| Block quote | lines starting with `>` | `<blockquote>` around the rendered content |
| Rule | a line of 3 or more `-`, `*` or `_`, spaces allowed, and nothing else | `<hr>` |
| Raw HTML | anywhere | escaped text |

Inline:

| Construct | Source | Output |
|---|---|---|
| Code span | a run of N backticks up to the next run of exactly N | `<code>`; one leading and one trailing space stripped when both are present; the term hook (code=True) |
| Strong | `**text**` | `<strong>` |
| Emphasis | `*text*` | `<em>`; underscores never make emphasis, so `snake_case_names` stay as they are |
| Link | `[label](target)` or `[label](target "title")` | the link hook: `<a href="HREF">label</a>`, else `<span class="ref" title="TARGET">label</span>` |
| Autolink | `<https://…>` or `<http://…>` | `<a href>` through the link hook |
| Image | `![alt](src)` | the alt text alone: the page serves no repository images |
| Escape | a backslash before ASCII punctuation | that character |
| Word | a maximal run of letters, digits, `_` and `-` in other text | the term hook (code=False) |

#### Heading ids

The id is GitHub's. Take the heading's text without markup, keeping code span contents and link labels. Lowercase it, remove every character that isn't a letter, a digit, a space, `-` or `_`, and replace each space with `-`. The second heading with the same id gets `-1`, the third `-2`, and so on in document order. A heading of `factory web` in a code span gets the id `factory-web`, and `## Notes / Out of Scope` gets `notes--out-of-scope`. Every `spec_refs` anchor into a plan already uses this rule: all 123 resolved when checked on 2026-11-18, this plan's included.

#### Hooks

```python
doc = markdown.render(
    text,
    fence=lambda info, body: ...,   # -> str | None: HTML for the whole fenced block
    link=lambda target: ...,        # -> str | None: the href, or None for no link
    term=lambda text, code: ...,    # -> str | None: HTML for a code span or a word
)
doc.title      # str | None
doc.html       # str
doc.headings   # [Heading(level=2, id="execution-plan", text="Execution Plan"), ...]
```

A hook's returned string goes into the page as it is, so a hook escapes what it builds, as `views.esc` does.

### Reading plans

- The plan docs are `contracts.discover_plans(root, config)`, the same files `factory sync` loads, read from the checkout `factory web` serves. A plan's name is its file stem (`contracts.plan_name`), as on the board.
- App caches each plan doc's title and contracts, keyed by its path, size and modification time. A parse error is cached the same way.
- The title is the first level-1 heading without a leading `Plan: `, else the name.

### Plans page

The structure is `docs/design/webui/plans.html`.

- **Sentence.** `13 plans, 3 with work left.`, followed by `1 isn't on the board yet.` when a plan has contracts but none of its tasks is on the board. With no plan docs: `No plans yet.`, followed by a line naming the `plans` globs.
- **Rows**, by name: the name, as a link to the plan page; the strip of its board tasks in the board's order; the title over the repo-relative path; and the board's counts text and cost. A plan with no task on the board shows `Not on the board yet`, or `No task contracts` when its file has none.
- **Top bar:** Load plans, returning to `/plans`.
- The page refreshes every 2 seconds, like the board.

### Plan page

The structure is `docs/design/webui/plan.html`.

- **Head:** breadcrumbs (Board, Plans, the name), the title, then the facts: the strip, the counts text, the cost and the file. Run plan follows, under the same rule as on the board, and then `Show on the board`.
- **Notice:** see [The plan and the board](#the-plan-and-the-board).
- **Contents:** the level-2 headings, each with its level-3 headings nested, linking to their ids. The contents are sticky beside the text on a wide screen, and above it below 60rem.
- **Prose:** the rendered plan in `<div class="prose">`.
- **Task rows.** Each contract block becomes `<ul class="rows task-cards">`, one row per contract, followed by the YAML under a fold:

  | Part | Task on the board | Task not on the board |
  |---|---|---|
  | Status | the board's word, class and mark | `Not loaded`, `s-new` (dotted square, grey) |
  | Id | link to `/tasks/ID` | plain text |
  | Goal | from the file | from the file |
  | `.why` | `waits for …` (from `db.readiness`) when waiting; `pull request #N` when it has a PR | `waits for …` from the file's `depends_on`, when it has any |
  | End | risk, builds, cost | risk |

  Each row's id is `task-ID`, so `/plans/NAME#task-ID` scrolls to it.
- **No refresh.** A plan is read, not watched. Statuses are as of the page's load, and reloading updates them.

### The plan and the board

The page compares the file's contracts with the board's, as `db.sync` would:

| Count | Meaning |
|---|---|
| new | in the file, not on the board |
| changed | on the board, with a stored contract that isn't the file's `task.to_json()` |
| removed | on the board with this file as its plan, and no longer in the file |

When any count is above zero, the page shows a `notice-you` notice, for example `This plan has changed since the board loaded it: 1 new task, 1 changed. Load plans to bring the board up to date.`, with the Load plans button. When the file's contracts don't load (`ContractError`), it shows a `notice-bad` notice with the error, and every contract block stays code.

### Links and task ids

| In the plan | On the page |
|---|---|
| A task id on the board, as a word or a whole code span | `<a class="task-ref" href="/tasks/ID"><i class="CLASS"></i>ID</a>`, with the code span's `<code>` inside the link |
| A relative link to a plan doc, such as `[webui](webui.md#security)` | `/plans/webui#security` |
| `https://…`, `http://…`, `#fragment` | unchanged |
| Any other link, such as `../../NEXT.md#3-…` or `factory/db.py` | the label without a link, its target in `title` (`.ref`) |

### Links between plans and tasks

- **Board:** each plan card gets `Read the plan` (`btn-quiet`) at the start of `.plan-end`, as in `board.html`.
- **Breadcrumbs:** the plan crumb on the task page, the transcript page and a task's run form goes to `/plans/NAME#task-ID`, and on a plan's run form to `/plans/NAME`. It falls back to the board card when the plan file is gone.
- **Reads:** a spec ref into a plan doc becomes a link to that section of its plan page, as in `task.html`.

### Security

The webui plan's [Security](webui.md#security) measures stay as they are: loopback only, the Host check, the CSP, the response headers and POST checks. Plan pages add:

| Measure | Detail |
|---|---|
| Files | Only plan docs that `contracts.discover_plans` finds. The URL carries a stem that is looked up among them, never a path |
| Text | Every character from a plan goes through `html.escape(…, quote=True)`, in the renderer or in `views.esc`. Raw HTML is text |
| Links | `https://`, `http://`, `#` and `/plans/…` only. Every other target loses its link |
| Hooks | `views.py` builds hook output with `views.esc` and the board's status classes only |

### Look

The mockups [`plans.html`](../design/webui/plans.html) and [`plan.html`](../design/webui/plan.html) are the reference, alongside the [webui mockups](../design/webui/README.md). The new rules in `app.css` are in its `plans` section:
- `.plan-list` and `.plan-about` lay out the Plans page as the board lays out a plan card's summary.
- `.doc`, `.toc` and `.prose` handle the plan text. `.prose` styles headings, lists, tables, code, quotes and rules in the site's type: Instrument Serif for level-2 headings, Hanken Grotesk for text and DM Mono for code.
- `.task-cards` gives the board's rows a goal on its own line, and `.task-ref` gives an inline task id its status mark.
- `.ref` marks a link the page can't follow, `.notice-you` is the amber drift notice, and `.page-acts` holds the head's buttons.
- `.s-new` is `Not loaded`, a dotted grey square.

No existing rule changes. Below 60rem the contents go above the text, and below 45rem each task row stacks.

## Files Changed

| File | Change |
|---|---|
| `factory/web/markdown.py` | New: the Markdown subset, heading ids, hooks (t01) |
| `factory/web/server.py` | `/plans` and `/plans/NAME`, the plan cache (t02) |
| `factory/web/views.py` | The Plans page and plan page, task rows, links, task ids, the drift notice and the Plans navigation item (t02). Read the plan on the board's cards, breadcrumbs and Reads links (t03) |
| `factory/web/static/app.css` | New rules for the plan pages (with this plan) |
| `docs/design/webui/plans.html`, `plan.html` | New mockups (with this plan) |
| `docs/design/webui/board.html`, `task.html`, `transcript.html`, `run.html`, `activity.html`, `README.md` | The Plans navigation item, Read the plan, the breadcrumb and Reads links (with this plan) |
| `tests/test_web_markdown.py` | New (t01) |
| `tests/test_web.py` | Plan page and Plans page tests (t02); link tests (t03); the updated navigation and breadcrumb assertions |
| `docs/reference.md`, `docs/architecture.md`, `NEXT.md` | The plan pages (t04) |
| `factory/templates/skills/factory-ops/SKILL.md`, `.claude/skills/factory-ops/SKILL.md` | The plan pages (t04) |
| `tests/test_templates.py` | `test_the_docs_describe_the_plan_pages` (t04) |

## Test Plan

### Unit tests

- **t01, `tests/test_web_markdown.py`:**
  - `test_the_first_h1_is_the_title_and_headings_get_github_ids`: title, `headings`, id rules, repeats.
  - `test_every_plan_anchor_in_this_repository_is_a_heading_id`: every plan anchor in `spec_refs` resolves.
  - `test_paragraphs_and_nested_lists`: paragraphs, bullet and ordered lists, `start`, nesting, the 16-level cap.
  - `test_pipe_tables_split_on_unescaped_pipes`: header and body, outer pipes, escaped pipes, short and long rows.
  - `test_fences_quotes_and_rules`: both fence characters, unclosed fences, quotes, rules.
  - `test_inline_code_emphasis_links_and_escapes`: backtick runs, strong and em, underscores, links with titles, autolinks, images, backslash escapes.
  - `test_the_link_hook_decides_each_href`: the default allowlist, `javascript:`, a custom hook, `.ref` spans.
  - `test_the_fence_hook_can_replace_a_block`: the arguments, replacement and fallback.
  - `test_the_term_hook_sees_words_and_code_spans`: words and code spans, never link labels or fences.
  - `test_raw_html_is_escaped_and_no_markup_is_injected`: `<script>`, `<details>`, `onerror`, attributes.
  - `test_pathological_input_renders_quickly`: 1 MB of unclosed markers and 5,000 nested lines, each under 2 seconds.
- **t02, `tests/test_web.py`:** the ten tests in its contract, through `App.handle` on the `repo` checkout and a synced board.
- **t03, `tests/test_web.py`:** the three link tests.
- **t04, `tests/test_templates.py`:** `test_the_docs_describe_the_plan_pages`.

### End-to-end tests

The project configures no `e2e` gate. The `App.handle` tests are the end-to-end path: a request goes through the routing, the read-only board and the files in the checkout, and comes back as the page.

## Verification

- `uv run pytest -q` passes after each task.
- After t02, run `factory web`, open `/plans`, then a plan with tasks in several statuses. Compare both pages with `plans.html` and `plan.html` at full width and below 45rem. Edit a contract's goal in the checkout and check that the plan page shows the drift notice and that Load plans clears it.
- After t03, click from a board card to its plan, from a task row on the plan page to the task, and from the task's breadcrumb and Reads back to the plan.

## Cross-Workstream Coordination

- **Depends on:** [webui](webui.md), merged. These pages extend `factory web`, its stylesheet, its status words and its Load plans job.
- **Required by:** nothing yet.
- **Overlaps:** [flow-tuning](flow-tuning.md) and [security-review](security-review.md). `flow-tuning-t05` and `security-review-t07` also edit `docs/reference.md`, `docs/architecture.md`, `NEXT.md` and the factory-ops skill, and `security-review-t05` touches `factory/web/views.py` (see Risk 9). Neither waits on this plan, nor this plan on them.
- **Related:** [factory-spec](factory-spec.md) describes the factory shipped at `8bd7012`. Its operator-interfaces chapter (`factory-spec-t04`) therefore leaves out these pages, and a later edition covers them.

## Notes / Out of Scope

- **Editing plans or contracts from the page.** Plans are written with `/plan-workstream`, reviewed as PRs and live in git.
- **Plans from a git ref.** The page shows the checkout, as `factory sync` reads it. Showing the trunk's version beside a draft is deferred.
- **Rendering agents' reports and PR bodies as Markdown.** `markdown.py` could render the reports on the task page too. It is deferred, to keep this workstream to plans.
- **A drawn dependency graph** of a plan's tasks. The rows are in file order and say what each task waits for.
- **Search across plans**, and a plan's history or diff.
- **A live plan page.** A plan page doesn't refresh itself. Refreshing only the task rows would need `app.js` to swap part of a page, which is deferred.
