# factory-spec-t06 — 2026-11-24

## What changed

- Added `docs/spec/00-spec.txt` as the implementer's entry point: audience and
  edition authority, requirement words, exact chapter index, separate task-run
  and failure-diagnosis reading paths, shared terminology, and a two-task
  lifecycle from contract discovery through stacked PRs, refresh/restack, and
  two human merges. Each lifecycle decision names its behavioral evidence and
  the actor with authority to change state.
- Corrected the chapter 01 example's nonexistent documentation anchor.
- Normalized the chapter 03 and 04 opening lines to the series' number-and-title
  convention; corrected chapter 04's module-level `parse` citation.
- Corrected chapter 06's stale CLI, pipeline, review, and CI symbols, including
  `Pipeline.rework`, `Pipeline.resolve`, `reviews.requests`, `ci.red`, and
  `ci.FAILED`.
- Corrected chapter 07's command-to-owner chapter map, including configuration,
  synchronization, scheduling/flows, gates, and benchmarks.
- Chapter 08 already cited the module-level `factory/db.py:open_db` correctly,
  so it required no edit. No runtime code, tests, configuration, historical
  plans, commands, or product behavior changed.

## Series-wide reference-check results

Final audit passed with no unresolved references:

- Exactly ten nonempty UTF-8 chapters, `00-spec.txt` through `09-spec.txt`;
  each topic basename appears exactly once in the overview index and its title
  matches the chapter's opening title.
- Both explicit filename/section references resolve: chapter 01 to chapter 02
  sections 2 and 4, and chapter 02 to chapter 01 section 5. The audit also
  checked 16 internal section references and 32 overview chapter/section
  references, including subsections and ranges.
- All 59 unique cited `factory/`/`tests/` Python paths, 200 unique pytest node
  IDs, and 252 cited source symbols (including shorthand lists and class
  members) exist. All five cited documentation anchors exist.
- The audit found and the integration pass fixed the stale symbols listed
  above. No remaining missing numbered filename, section, source path, source
  symbol, test node, or documentation anchor was found.

Baseline boundaries were left intact. Chapter 03's baseline flow-kind and
reserved-name lists do not incorporate the post-baseline `test` kind or
`tester` reserved name visible at the current checkout; those are content
changes for a later edition, not reference corrections permitted by this task.

## Files

- `docs/spec/00-spec.txt` (new)
- `docs/spec/01-spec.txt`
- `docs/spec/03-spec.txt`
- `docs/spec/04-spec.txt`
- `docs/spec/06-spec.txt`
- `docs/spec/07-spec.txt`
- `docs/sessions/2026-11-24-factory-spec-t06.md` (new)

## Final verification commands

- Contract structure command — exit 0:

  ```sh
  python3 -c "from pathlib import Path; import re; d=Path('docs/spec'); names={f'{i:02}-spec.txt' for i in range(10)}; assert {p.name for p in d.glob('*.txt')} == names; book={n:(d/n).read_text(encoding='utf-8') for n in names}; assert all(s.strip() for s in book.values()); refs=lambda s:set(re.findall(r'\b[0-9]{2}-spec\.txt\b', s)); assert names-{'00-spec.txt'} <= refs(book['00-spec.txt']); assert all(refs(s) <= names for s in book.values())"
  ```

- `uv run --offline pytest -q tests/test_scheduler.py::test_one_run_gives_a_pr_per_task_with_dependents_stacked`
  — exit 0; 1 passed.
- `uv run --offline pytest -q tests/test_spec_chapters_01_02.py tests/test_spec_chapters_05_06.py tests/test_spec_t04.py`
  — exit 0; 57 passed.
- Python heredoc series-reference audit (filenames/titles, explicit and
  internal sections, Python paths, AST-resolved source symbols, pytest nodes,
  and documentation anchors) — exit 0; counts and results above.
- `uv run pytest -q` — exit 0; 552 passed.
- `git diff --check` — exit 0.
