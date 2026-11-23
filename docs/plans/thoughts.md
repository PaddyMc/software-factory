# Plan: See what the models thought

**Status:** Planned (2026-11-15). Workstream scoped; awaiting kickoff.

---

## Execution Plan

### Locked Decisions

| Decision | Choice |
|---|---|
| Where thoughts show | **Transcript, trace and live log.** Each run's transcript keeps every step's full reasoning, and `factory transcript` prints it. `factory trace` counts each step's thinking tokens. The task log gets a short `thinks:` line per step, so `factory logs`, `factory top` and the web task page show what the model is thinking while it runs |
| Models that don't share | **Record what comes back.** No request changes: no reasoning, thinking or effort setting is sent, so model behaviour and cost stay as they are. A step that used thinking tokens but returned no text says so, with its token count |
| Web page | **Included, after `webui-t05`.** The transcript page shows each step's thoughts. The mockup and the stylesheet rules are committed with this plan; the task waits for `webui-t05`, which builds the page |
| Sequencing | **Start now, alongside `measure` and `pr-descriptions`.** They also change `factory/agents.py`, but not `_observe` or the transcript renderers; whichever PR merges second gets a small conflict the factory resolves |

### Milestones

| # | Deliverable | Exit criteria | Parallelizable with |
|---|---|---|---|
| **M1** | Thoughts recorded | The t01 tests in `tests/test_agent_loop.py` pass: each `ai` event carries `reasoning` and `usage.reasoning`, and the log gets `thinks:` lines | measure, pr-descriptions |
| **M2** | Thoughts in the terminal | The t02 tests in `tests/test_observe.py` and `tests/test_agent_loop.py` pass: `factory transcript` prints thoughts and `factory trace` counts thinking tokens; the reference and README say so | measure, pr-descriptions |
| **M3** | Thoughts on the web | The t03 tests in `tests/test_web.py` pass, and the transcript page looks like `docs/design/webui/transcript.html` | — |

**Sequence:** `M1 → M2 → [webui-t05 →] M3`.

### Task Contracts

| Milestone | Task IDs | Coverage |
|---|---|---|
| **M1** | `thoughts-t01` | Reading reasoning and thinking tokens in `LangChainRoles._observe` (`factory/agents.py`), the transcript event, the `thinks:` log line and the `done:` line; tests in `tests/test_agent_loop.py` |
| **M2** | `thoughts-t02` | `render_transcript`, `trace_rows` and `render_trace` in `factory/observe.py`; tests in `tests/test_observe.py` and `tests/test_agent_loop.py`; `docs/reference.md` and `README.md` |
| **M3** | `thoughts-t03` | The transcript page in `factory/web/views.py`; tests in `tests/test_web.py` |

```yaml
- id: thoughts-t01
  goal: "Every agent step's reasoning is saved: the step's `ai` event in the run's transcript carries the reasoning text the model returned and its thinking-token count, the task log gets a `thinks:` line for each step that shared its reasoning, and the step's `done:` line counts thinking tokens"
  spec_refs:
    - "docs/plans/thoughts.md#recording"
    - "factory/agents.py"
  depends_on: []
  non_goals:
    - "Changing what models are asked: no reasoning, thinking or effort setting is added to any model request or to .factory/config.yaml"
    - "Changing a step's `text`, its final answer, or anything the pipeline reads from it: plans, review verdicts, reports and PR bodies stay as they are"
    - "Changing token, cost or step accounting: thinking tokens are already part of each step's output tokens"
    - "Showing thoughts in `factory transcript`, `factory trace` or the web pages (thoughts-t02, thoughts-t03)"
    - "Decoding encrypted or redacted reasoning"
    - "Changing `LangChainRoles.step` beyond the `done:` line, or `_kit`"
  acceptance:
    - "Every `ai` event in a run's transcript has a `reasoning` key: the `reasoning` text of the message's `content_blocks` entries of type `reasoning`, joined by a blank line, or an empty string when there are none. It is cut at 200,000 characters, like tool results"
    - "Every `ai` event's `usage` has a `reasoning` key: the step's thinking tokens from `usage_metadata` `output_token_details.reasoning`, or null when the provider doesn't report it"
    - "Reasoning that arrives the OpenRouter way (`additional_kwargs` `reasoning_content`) and reasoning already in the message content as standard `reasoning` blocks are both recorded. Neither appears in the event's `text`, and the step's final answer (`Output.text`) is the reply text alone"
    - "For a step whose reasoning isn't empty, the task log gets `thinks: ` followed by the reasoning clipped to 240 characters with `factory.log.clip`, logged before that step's `says:` and `→` lines"
    - "A step without reasoning logs no `thinks:` line, and its event has `reasoning` set to an empty string and `usage.reasoning` set to null"
    - "`Output` gains `thinking: int = 0`, the sum of the steps' reported thinking tokens. When it is above 0, the `done:` line has ` (Z thinking)` right after `Y out`, as in `done: 31 steps, 1204113 tokens in / 14020 out (9812 thinking), $0.1102`; otherwise the line is unchanged"
    - "The existing tests in tests/test_agent_loop.py and tests/test_pipeline.py still pass"
  verification:
    - "uv run pytest -q tests/test_agent_loop.py::test_reasoning_is_recorded_with_each_step tests/test_agent_loop.py::test_reasoning_blocks_in_the_content_are_recorded_and_kept_out_of_the_answer tests/test_agent_loop.py::test_the_log_gets_a_thinks_line_before_the_step_says_and_calls tests/test_agent_loop.py::test_a_step_without_reasoning_records_none"
    - "uv run pytest -q tests/test_agent_loop.py tests/test_pipeline.py"
  risk: low

- id: thoughts-t02
  goal: "`factory transcript` prints each step's thoughts above what the step said and did, `factory trace` counts each step's thinking tokens, and docs/reference.md and README.md say both"
  spec_refs:
    - "docs/plans/thoughts.md#in-the-terminal"
    - "factory/observe.py"
  depends_on: [thoughts-t01]
  non_goals:
    - "New flags on `factory transcript` or `factory trace`"
    - "Changing what agents record (thoughts-t01)"
    - "The web transcript page (thoughts-t03)"
    - "Changing `factory show`, `factory status`, `factory top` or `factory logs`"
  acceptance:
    - "`factory transcript` prints, under each `[agent step N]` header and before the step's text and tool calls, `thinks: ` followed by the step's reasoning, cut at the same 2,000-character limit as the other text unless `--full`"
    - "The `[agent step N]` header reads `IN in / OUT out (K thinking)` when the event's `usage.reasoning` is a number above 0, and `IN in / OUT out` as before otherwise"
    - "A step whose `usage.reasoning` is above 0 and whose `reasoning` is empty prints `thinks: (K tokens; the model didn't share its reasoning)`"
    - "`observe.trace_rows` gives each row a `thinking` value: the event's `usage.reasoning`, or None when it is missing or null"
    - "`factory trace` has a `think` column right after `out`, showing the row's `thinking`, or `-` for None. The summary's tokens line ends `output X (Y thinking)` when any row has a thinking count, and `output X` as before otherwise"
    - "A transcript recorded before thoughts-t01, with no `reasoning` keys, prints in `factory transcript` exactly as it does today, and in `factory trace` as today apart from `-` in the think column"
    - "In docs/reference.md, the `factory transcript` row says it shows each step's thoughts, and the `factory trace` row lists thinking tokens. README.md's transcripts row lists the reasoning each model returned"
    - "The existing tests in tests/test_observe.py and tests/test_agent_loop.py still pass"
  verification:
    - "uv run pytest -q tests/test_observe.py::test_transcript_shows_each_steps_thoughts_first tests/test_observe.py::test_a_model_that_did_not_share_its_thoughts_is_said_so tests/test_observe.py::test_trace_counts_thinking_tokens tests/test_observe.py::test_transcripts_without_thoughts_print_as_before tests/test_agent_loop.py::test_a_recorded_runs_thoughts_show_in_its_transcript_and_trace"
    - "uv run pytest -q tests/test_observe.py tests/test_agent_loop.py"
    - "grep -q 'thoughts' docs/reference.md"
    - "grep -q 'thinking tokens' docs/reference.md"
  risk: low

- id: thoughts-t03
  goal: "The web transcript page shows each step's thoughts above what the step said, quieter than the step's own words and with long thoughts folded after their opening, and labels the model's time as time in the model rather than thinking. It looks like docs/design/webui/transcript.html"
  spec_refs:
    - "docs/plans/thoughts.md#on-the-web"
    - "docs/design/webui/transcript.html"
    - "docs/plans/webui.md#transcript-page"
  depends_on: [thoughts-t02, webui-t05]
  non_goals:
    - "Changing factory/web/static/app.css: its `.thinks` rules are committed with this plan"
    - "Thinking tokens on the task page, the board, the activity page or in the runs table"
    - "Rendering Markdown in thoughts: they are plain text, kept with their line breaks"
    - "Searching or filtering thoughts, or a control that opens every fold at once"
    - "Changing what agents record, or `factory transcript` and `factory trace`"
  acceptance:
    - "Each step whose `reasoning` isn't empty renders, before the step's `says` paragraph and calls, a `div` with class `thinks` holding a `div` with class `thinks-head` and the reasoning in a `p`. The head reads `Thought, K tokens` when `usage.reasoning` is a number above 0, and `Thought` otherwise"
    - "A thought of 800 characters or fewer is shown whole. A longer one shows its first 600 characters, cut at the last whitespace before the 600th and followed by `…`, then a `details` element with class `fold` and id `t-STEP-thought`, whose summary reads `The rest of the thought, M characters` and whose `p` holds the remainder with its leading whitespace removed, M being that remainder's length"
    - "A step whose `usage.reasoning` is above 0 and whose `reasoning` is empty renders the `thinks` block with the head `Thought, K tokens` and a `p` with class `thinks-none` reading `The model didn't share its reasoning.`"
    - "Reasoning is HTML-escaped: a thought containing `<script>` and `&` shows them as text"
    - "Each step's facts read `Xs in the model`, with `, Ys in tools` when tools took a second or more, where they read `Xs thinking` before. A step with a thinking count above 0 has a `K thinking` line after its tokens line"
    - "The page's `time` fact reads `… in the model, … in tools`, and its `tokens` fact ends `(N thinking)` when any step has a thinking count, N being their sum with thousands separators"
    - "A transcript without `reasoning` keys renders as before apart from the new time labels"
    - "The transcript tests webui-t05 added still pass, with their assertions on the old `thinking` time label updated to `in the model`"
  verification:
    - "uv run pytest -q tests/test_web.py::test_transcript_page_shows_thoughts_above_what_the_step_said tests/test_web.py::test_long_thoughts_fold_after_their_opening tests/test_web.py::test_a_step_that_thought_without_sharing_says_so tests/test_web.py::test_transcript_page_labels_model_time_and_thinking_tokens"
    - "uv run pytest -q tests/test_web.py"
  risk: low
```

Planned test additions. Each verification filter must select its tests; zero matching tests is a failure.

| Task | File | Tests |
|---|---|---|
| t01 | `tests/test_agent_loop.py` | `test_reasoning_is_recorded_with_each_step`, `test_reasoning_blocks_in_the_content_are_recorded_and_kept_out_of_the_answer`, `test_the_log_gets_a_thinks_line_before_the_step_says_and_calls`, `test_a_step_without_reasoning_records_none` |
| t02 | `tests/test_observe.py` | `test_transcript_shows_each_steps_thoughts_first`, `test_a_model_that_did_not_share_its_thoughts_is_said_so`, `test_trace_counts_thinking_tokens`, `test_transcripts_without_thoughts_print_as_before` |
| t02 | `tests/test_agent_loop.py` | `test_a_recorded_runs_thoughts_show_in_its_transcript_and_trace` |
| t03 | `tests/test_web.py` | `test_transcript_page_shows_thoughts_above_what_the_step_said`, `test_long_thoughts_fold_after_their_opening`, `test_a_step_that_thought_without_sharing_says_so`, `test_transcript_page_labels_model_time_and_thinking_tokens` |

Prerequisite for `thoughts-t03`: `webui-t05` merged or with an open PR. It is `failed` today: every gate passed, then opening its PR failed with `OSError: [Errno 7] Argument list too long: 'gh'`, because its PR body was too large. It runs again after `pr-descriptions-t01`, which keeps PR bodies under the limit (see [pr-descriptions](pr-descriptions.md)).

### Risks

1. **A model may share nothing.** OpenRouter returns reasoning for the reasoning models in use, but a provider route can return it encrypted or not at all, and direct Anthropic and OpenAI models only share it when the request asks. No live call was made while planning to confirm what each model in use returns. **Action:** the thinking-token count is recorded whenever the provider reports it, and every view says "the model didn't share its reasoning" for a step that thought without sharing, so a missing thought shows up rather than going quiet. A reasoning setting per role is listed under Out of Scope for when it's needed.
2. **Transcripts grow.** Reasoning can run to several times the visible reply. **Action:** each step's reasoning is capped at 200,000 characters, like tool results. `factory transcript` cuts it at 2,000 characters unless `--full`, and the web page folds it after 600.
3. **Noisier logs.** Every step that shares its reasoning adds a log line. **Action:** one line per step, clipped to 240 characters, and only when there is reasoning to show.
4. **A thought isn't proof of why.** The reasoning text is what the model wrote, and some providers return a summary, not the full chain. **Action:** the views call it the reasoning the model returned. Nothing feeds it to the reviewer, the gates or the PR.
5. **Conflicts with plans that change `factory/agents.py`.** `measure-t01` adds `prompt_version` to `Output` and `LangChainRoles.step`, `pr-descriptions-t02` changes the verify message in `_kit`, and strict-flow changes the agent loop later. **Action:** t01 changes only `_observe`, one `Output` field and the `done:` line. Whichever PR merges second gets a small conflict the factory resolves, as `measure` and `pr-descriptions` already do with each other.
6. **`webui-t05` is stuck.** The web task can't start until it lands. **Action:** t03 is last and nothing waits for it. t01 and t02 deliver the thoughts in the terminal and the live log, including the web task page's log, regardless.
7. **The label change breaks `webui-t05`'s tests.** Its page calls the model's time "thinking", which now means something else. **Action:** t03's acceptance lets it update those assertions to `in the model`, and the mockup already uses the new labels.

---

## Problem

The factory keeps three records of every agent step, and the model's reasoning is in none of them:

- **The transcript** (`$FACTORY_HOME/transcripts/TASK/NNNNN-ROLE-ATTEMPT.jsonl`). `LangChainRoles._observe` records each reply as `{"type": "ai", "step", "text": m.text, "usage", "cost_usd", "tool_calls"}` (`factory/agents.py:329`). `AIMessage.text` is the reply text alone; the reasoning is dropped.
- **The live log.** The same method logs `says:` with the reply text and `→` per tool call (`factory/agents.py:333`–`338`). Nothing says what the model weighed before acting.
- **The trace.** `observe.trace_rows` counts input, output and cached tokens per step (`factory/observe.py:228`), but not how many of the output tokens were thinking.

Every run on this board uses OpenRouter models that reason before they answer: GLM-5.3, DeepSeek V4 Pro and Flash, and Kimi K3 and K3.1. The OpenRouter integration already hands their reasoning to the factory. It puts the text in `additional_kwargs["reasoning_content"]` (`langchain_openrouter/chat_models.py:1368`) and the token count in `usage_metadata["output_token_details"]["reasoning"]` (`:1566`). So when a build goes wrong, the transcript shows what the builder did but not why. Its thinking tokens are paid for, and then thrown away.

## Goal

Every agent step's reasoning is kept in its transcript and visible wherever its actions are: in `factory transcript`, in the live log, as thinking tokens in `factory trace`, and on the web transcript page. Model requests and costs don't change.

## Design

### Where reasoning comes from

LangChain's standard content blocks give every provider's reasoning the same shape. `AIMessage.content_blocks` (langchain-core 1.6.9) returns `{"type": "reasoning", "reasoning": TEXT}` for each piece, whichever way the provider sent it:

| Provider | How the reply carries reasoning | Shared without asking |
|---|---|---|
| OpenRouter, every model in use | A `reasoning` field, kept as `additional_kwargs["reasoning_content"]`. Thinking tokens in `completion_tokens_details.reasoning_tokens`, kept as `usage_metadata["output_token_details"]["reasoning"]` | Yes, for models that reason, unless the route hides it |
| Anthropic | `thinking` content blocks | Only when the request enables thinking, which `build_model` doesn't |
| OpenAI | Reasoning summary blocks (Responses API) | Only when the request asks for summaries |

When the content already holds standard `reasoning` blocks, `content_blocks` doesn't also add `reasoning_content`, so nothing is counted twice. Thinking tokens are already part of each step's output tokens, so cost and step accounting don't change.

### Recording

In `LangChainRoles._observe` (`factory/agents.py:318`), for each `AIMessage`:

```python
reasoning = "\n\n".join(b["reasoning"] for b in m.content_blocks
                        if b.get("type") == "reasoning" and b.get("reasoning"))
thinking = ((usage.get("output_token_details") or {}).get("reasoning"))   # int, or None when not reported
```

The transcript event gains two keys; everything else stays the same:

```json
{"type": "ai", "step": 2, "text": "…", "reasoning": "report.py keeps each run's steps…",
 "usage": {"in": 24112, "out": 412, "cache_read": 0, "reasoning": 318}, "cost_usd": 0.005, "tool_calls": […]}
```

- `reasoning` is the empty string when the step has none, and is cut at 200,000 characters.
- `usage.reasoning` is null when the provider doesn't report a count.
- Transcripts written before this change have neither key, and every reader treats them as `""` and null.

The live log gets one line before the step's `says:` and `→` lines, only when there is reasoning:

```
21:31:07 [build#3] thinks: report.py keeps each run's steps as a list of dicts with name, model and prompt_sha, and compare_header only looks at the first one. That explains the missing line: when only the build prompt…
21:31:07 [build#3] says: The compare header is missing the per-step prompt_sha line. I'll read the report module first.
21:31:07 [build#3] → read_file(path=factory/bench/report.py)
```

`Output.thinking` sums the steps' thinking tokens, and the step's last line counts them: `done: 31 steps, 1204113 tokens in / 14020 out (9812 thinking), $0.1102`. The task's `activity`, which `factory top` shows, is still the last line logged, so it stays the step's last tool call.

The reasoning is logged after the reply arrives, at the same moment as the step's actions. The agent loop receives each reply whole (`stream_mode="updates"`), so thoughts don't stream as they're generated.

### In the terminal

`factory transcript` prints the thought first in each step, because the model thought before it spoke and acted:

```
21:31:04 [agent step 1] 18204 in / 210 out (152 thinking) $0.0040
thinks: The test that fails compares two runs, and the assertion wants a line saying the build prompt changed. So the header has to compare prompt_sha per step, not per run. report.py builds the header, so start there.
The compare header is missing the per-step prompt_sha line. I'll read the report module first.
  → read_file {"path": "factory/bench/report.py"}
```

A thought longer than 2,000 characters is cut like any other text, with `… (N more chars; --full)`.

A step that used thinking tokens but returned no text prints `thinks: (121 tokens; the model didn't share its reasoning)`. A step with neither prints no `thinks:` line.

`factory trace` adds a `think` column after `out`, and the summary's tokens line ends `output 14,020 (9,812 thinking)`:

```
step   model   tools   ctx in  cached    out  think     cost  result  calls
   1    4.1s    0.4s    18204       0    210    152  $0.0040  21904  read_file(path=factory/bench/report.py)
   2    6.8s   41.0s    24112       0    412    318  $0.0050    188  run(command=uv run pytest -q tests/te…), run(command=git commit -am wip) ⚠1 refused
```

`-` marks a step whose provider reported no count. A transcript from before this change shows `-` in every row and no thinking in the summary.

### On the web

[`docs/design/webui/transcript.html`](../design/webui/transcript.html) is the reference, and the `.thinks` rules in [`factory/web/static/app.css`](../../factory/web/static/app.css) are committed with this plan. A thought sits above what the step said: smaller, in the secondary grey, behind a dashed rule, so it reads as the model's aside and not its answer.

```html
<div class="thinks">
  <div class="thinks-head">Thought, 318 tokens</div>
  <p>report.py keeps each run's steps … If the test…</p>
  <details class="fold" id="t-2-thought"><summary>The rest of the thought, 246 characters</summary><p>run confirms both, …</p></details>
</div>
<p class="says">…</p>
```

- **Short thoughts are shown whole.** A thought of 800 characters or fewer appears in full. A longer one shows its first 600 characters, cut at a space and followed by `…`, and folds the rest. The fold's id is `t-STEP-thought`, so it stays open across the page's live refresh like the other folds.
- **A step that thought without sharing** shows the head and `The model didn't share its reasoning.` (class `thinks-none`).
- **Plain text.** Thoughts are HTML-escaped and keep their line breaks (`white-space: pre-wrap`); Markdown isn't rendered.
- **Labels.** `webui-t05`'s page calls the model's time "thinking" (`4.1s thinking`, `2m 40s thinking, 58s in tools`). Now that the page shows real thinking, the time becomes `4.1s in the model` and `2m 40s in the model, 58s in tools`. A step with a thinking count gets a `152 thinking` line after its tokens, and the page's `tokens` fact ends `(9,812 thinking)`.

The task page needs no change: its log shows the `thinks:` lines t01 adds.

## Files Changed

| File | Change |
|---|---|
| `factory/agents.py` | `_observe` records `reasoning` and `usage.reasoning` and logs `thinks:`; `Output.thinking`; the `done:` line (t01) |
| `factory/observe.py` | `render_transcript` prints thoughts; `trace_rows` and `render_trace` count thinking tokens (t02) |
| `factory/web/views.py` | The transcript page's thoughts and labels (t03) |
| `factory/web/static/app.css` | `.thinks` rules (this plan) |
| `docs/design/webui/transcript.html` | Thoughts in steps 1–3, a folded long thought, a step that didn't share, the new labels (this plan) |
| `tests/test_agent_loop.py` | t01 and t02 tests |
| `tests/test_observe.py` | t02 tests |
| `tests/test_web.py` | t03 tests, and `webui-t05`'s assertions on the old label |
| `docs/reference.md`, `README.md` | The `factory transcript` and `factory trace` rows, and the transcripts row (t02) |
| `NEXT.md` | Item 12 (this plan) |
| `docs/plans/webui.md` | Cross-link to `thoughts-t03` (this plan) |
| `docs/sessions/<date>-thoughts-tNN.md` | One per task |

## Test Plan

### Unit tests

`tests/fake_model.py`'s `ScriptedModel` returns whatever `AIMessage` the test scripts, so tests give a message `additional_kwargs={"reasoning_content": …}` and `usage_metadata` with `output_token_details`. That is what the OpenRouter integration produces, and it runs through the real agent loop.

- **t01, `tests/test_agent_loop.py`**
  - `test_reasoning_is_recorded_with_each_step`: a planner whose first step carries OpenRouter-style reasoning, 30 output tokens and 25 thinking tokens. The `ai` event has that `reasoning` and `usage.reasoning == 25`, its `text` is the reply alone, and the `done:` line contains `30 out (25 thinking)`.
  - `test_reasoning_blocks_in_the_content_are_recorded_and_kept_out_of_the_answer`: a reply whose content holds two standard `reasoning` blocks and a text block. The event's `reasoning` is both, joined by a blank line, and `Output.text` is the text alone.
  - `test_the_log_gets_a_thinks_line_before_the_step_says_and_calls`: the log's order for the step is `thinks:`, `says:`, `→`. A 1,000-character thought is clipped to 240.
  - `test_a_step_without_reasoning_records_none`: no `thinks:` line, `reasoning == ""`, `usage.reasoning is None`, and the `done:` line has no thinking count.
- **t02, `tests/test_observe.py`**
  - `test_transcript_shows_each_steps_thoughts_first`: hand-written events; `thinks:` comes after the step header and before its text and calls, the header carries `(318 thinking)`, and a long thought is cut without `--full` and whole with it.
  - `test_a_model_that_did_not_share_its_thoughts_is_said_so`: `usage.reasoning` 121 with empty `reasoning` prints `thinks: (121 tokens; the model didn't share its reasoning)`.
  - `test_trace_counts_thinking_tokens`: `trace_rows` gives `thinking` per row (None when missing), the `think` column shows it or `-`, and the summary ends `output X (Y thinking)`.
  - `test_transcripts_without_thoughts_print_as_before`: an old-format transcript renders exactly as a fixed expected string.
- **t02, `tests/test_agent_loop.py`**
  - `test_a_recorded_runs_thoughts_show_in_its_transcript_and_trace`: a scripted run records to a JSONL file, and `observe.render_transcript` and `observe.render_trace` on that file show its thoughts and thinking tokens.
- **t03, `tests/test_web.py`**
  - `test_transcript_page_shows_thoughts_above_what_the_step_said`: the `thinks` block comes before `says`, with the token head, and `<script>` and `&` are escaped.
  - `test_long_thoughts_fold_after_their_opening`: an 846-character thought shows 600 characters or fewer and `…`, then the fold `t-2-thought` with the right count; an 800-character thought is shown whole.
  - `test_a_step_that_thought_without_sharing_says_so`: the `thinks-none` paragraph.
  - `test_transcript_page_labels_model_time_and_thinking_tokens`: `in the model` labels, the per-step `K thinking` line, and the page's `(N thinking)` fact; a transcript without thoughts has neither.

### End-to-end tests

The project configures no e2e directory. `test_a_recorded_runs_thoughts_show_in_its_transcript_and_trace` runs the real agent loop, transcript recording and renderers together.

## Verification

1. `uv run pytest -q` passes after each task.
2. After t01, run any task (`factory run thoughts-t02` does) and follow it with `factory logs thoughts-t02 -f`: `thinks:` lines appear before the builder's actions.
3. After t02: `factory transcript TASK --role build` shows a `thinks:` block in each step, and `factory trace TASK --role build` has a filled `think` column. On an older task, both read as before.
4. After t03, open a build's transcript in `factory web` beside `docs/design/webui/transcript.html`. Thoughts sit above what each step said, and long thoughts fold after their opening.

## Cross-Workstream Coordination

- **Depends on:** [webui](webui.md). `thoughts-t03` waits for `webui-t05`, the transcript page it changes. `webui-t05` runs again after [pr-descriptions](pr-descriptions.md)' `pr-descriptions-t01` (see the prerequisite above).
- **Required by:** [flow-tuning](flow-tuning.md). `flow-tuning-t01` stacks on `thoughts-t01`: its re-ask continues a review's conversation through the same `_observe`, so the re-asked turns keep their thoughts.
- **Required by** [thought-timeline](thought-timeline.md). Its CLI builds on `thoughts-t02` and its web page on `thoughts-t03` to follow one task across roles and retries.
- **Overlaps:** [measure](measure.md), [pr-descriptions](pr-descriptions.md) and [strict-flow](strict-flow.md) also change `factory/agents.py`. This plan runs alongside the first two by decision; see Risk 5. strict-flow builds on whatever is on main when it starts, and its loop records each step through the same `_observe`, so its runs keep their thoughts.
- **Related:** [measure](measure.md)'s `factory stats` could later report thinking tokens per role from the transcripts. This plan doesn't add a column for them to the `runs` table.

## Notes / Out of Scope

- **A reasoning setting per role**, such as `reasoning: {build: high}` in `.factory/config.yaml`. It would turn on Anthropic's `thinking`, ask OpenAI for reasoning summaries, and set OpenRouter's effort (`ChatOpenRouter.reasoning`). It changes model behaviour and cost, so it gets its own plan when a model in use stops sharing its reasoning.
- **Streaming thoughts** while the model is still generating. The agent loop gets each reply whole.
- **Using thoughts elsewhere.** They aren't given to the reviewer or the verifier, put in PR bodies, or judged by any gate.
- **Thoughts of past runs.** Runs before t01 never saved them; nothing can recover them.
- **Thinking tokens outside transcripts.** The `runs` table, `factory show`, `factory status`, `factory top`, the board and the task page's run list don't get a thinking count.
- **Thoughts already go back to the model.** The OpenRouter integration sends each earlier reply's reasoning back with later steps (`langchain_openrouter/chat_models.py:1322`). Whether that costs input tokens is for `measure` to show, and this plan leaves it as it is.
