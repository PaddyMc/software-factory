"""Scratch (deleted after use): prove the flow-tuning-t05 acceptance tests pass on a faithful
rendering of the plan's design, by building a fake repo tree and running the tests against it."""
import importlib.util
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("tt", REPO / "tests" / "test_templates.py")
tt = importlib.util.module_from_spec(spec)
sys.modules["tt"] = tt
spec.loader.exec_module(tt)

tmp = Path(tempfile.mkdtemp())
(tmp / "docs").mkdir()
(tmp / "factory" / "templates" / "skills" / "factory-ops").mkdir(parents=True)

# ------------------------------------------------------------------ architecture.md
arch = (REPO / "docs" / "architecture.md").read_text()
roles_row = ("| selector | openrouter:z-ai/glm-5.3 | 30 | read, on the start commit "
             "| Which passing candidate carries on (fallback: the smallest diff) |\n")
arch = arch.replace("| verifier | openrouter:z-ai/glm-5.3 | 30 |", roles_row
                    + "| verifier | openrouter:z-ai/glm-5.3 | 30 |", 1)
subsection = """
### Build candidates

A build step can set `candidates: N` (2 to 5), opt-in: the first attempt of a fresh build builds N
candidates one after another, each in its own worktree from the same start commit, and the gates
judge each before anything else sees it. One first attempt with three candidates looks like:

```text
attempt 1:  build#1.1 (task worktree) ─▶ gates#1.1 ─┐
            build#1.2 (TASK.c2)       ─▶ gates#1.2 ─┼─▶ choose ─▶ reset branch ─▶ review ─▶ verify ─▶ PR
            build#1.3 (TASK.c3)       ─▶ gates#1.3 ─┘
                                                     none pass ─▶ closest candidate carries on
attempt 2+: one build on the chosen (or carried) candidate, as without candidates
```

How the choice is made: only candidates that pass every gate can carry on. One passing candidate is
chosen directly; with two or more, the selector compares their diffs against the contract and names
one, falling back to the smallest passing diff when its choice is missing or invalid. When none
pass, the candidate with the fewest failing gates carries on, with its failures as the feedback.

Later attempts, and resolve, ci and human_review reworks, build one change, as a flow without the
option does. What candidates cost: three candidates are three first builds and three gates runs, and
`--max-cost` counts every candidate, so a candidates task spends more of its budget up front.

---
"""
arch = arch.replace("\n---\n\n## Measuring the factory", subsection + "\n## Measuring the factory", 1)
assert "### Build candidates" in arch
(tmp / "docs" / "architecture.md").write_text(arch)

# ------------------------------------------------------------------ reference.md
ref = (REPO / "docs" / "reference.md").read_text()
ref = ref.replace("optional `name`, `model`, `max_steps`, `loop` and `prove`",
                  "optional `name`, `model`, `max_steps`, `loop`, `prove` and `candidates`", 1)
ref = ref.replace("(`plan`, `test`, `build`, `review`, `verify`)",
                  "(`plan`, `test`, `build`, `review`, `verify`, `select`)")
flows_doc = """**Build candidates:** a build step mapping can set `candidates` (an integer from 2 to 5): the first
attempt of a fresh build builds that many candidates, each in its own worktree, and the gates judge
each. A flow with `candidates` needs one build step followed by the gates, so a candidate is judged
before anything else sees it; later attempts and reworks build one change.

```yaml
flows:
  gates-first-x3:                        # the gates stay directly after the candidates build
    - plan
    - {kind: build, candidates: 3}
    - gates
    - review
    - verify
```
"""
marker = "**`strict`** is the second built-in"
assert marker in ref, "reference marker moved"
ref = ref.replace(marker, flows_doc + marker, 1)
ref = ref.replace("| Status `conflict` |",
                  "| `flows.<name>.<step>: 'candidates' needs one build step followed by the gates`"
                  " | The flow's candidates build must be its only build step, with the gates step"
                  " directly after it. Reorder the steps |\n"
                  "| A selector run is recorded as `fallback` | The selector's report had no valid"
                  " `CHOICE:` line naming a passing candidate, so the smallest passing diff was chosen"
                  " instead. The run and its report stay; read them with `factory show TASK` |\n"
                  "| Status `conflict` |", 1)
assert "'candidates' needs" in ref
(tmp / "docs" / "reference.md").write_text(ref)

# ------------------------------------------------------------------ NEXT.md
nxt = (REPO / "NEXT.md").read_text()
old14 = ("| 14 | A review without a verdict costs a rebuild, a task gets one build per attempt, and "
         "nothing picks the default flow from data. Planned: [flow-tuning](docs/plans/flow-tuning.md) "
         "| medium | 8, 9 |")
new14 = ("| ✓ | A review without a verdict costs a rebuild, a task gets one build per attempt, and "
         "nothing picks the default flow from data. Done: [Build candidates]"
         "(docs/architecture.md#build-candidates) | — | — |")
assert old14 in nxt, "NEXT item 14 row moved"
(tmp / "NEXT.md").write_text(nxt.replace(old14, new14, 1))

# ------------------------------------------------------------------ config template
cfg = (REPO / "factory" / "templates" / "config.yaml").read_text()
cfg = cfg.replace(
    "flow: gates-first\nflows:\n",
    "# A build step can build several candidates (2 to 5): the first attempt builds them one after\n"
    "# another, the gates judge each, and a selector keeps the one that fits the contract.\n"
    "# flow: gates-first-x3\n"
    "# flows:\n"
    "#   gates-first-x3:\n"
    "#     - plan\n"
    "#     - {kind: build, candidates: 3}\n"
    "#     - gates\n"
    "#     - review\n"
    "#     - verify\n"
    "flow: gates-first\nflows:\n", 1)
assert "candidates: 3" in cfg, "config template marker moved"
(tmp / "factory" / "templates" / "config.yaml").write_text(cfg)

# ------------------------------------------------------------------ factory-ops skill
skill = (REPO / "factory" / "templates" / "skills" / "factory-ops" / "SKILL.md").read_text()
skill = skill.replace(
    "- **`factory run PLAN`**",
    "- **Choosing a flow with candidates:** a build step can set `candidates: N` (2 to 5); pick such a "
    "flow as any other, with `factory run TASK --flow NAME` or `flow:` in `.factory/config.yaml`. The "
    "first attempt builds N candidates, the gates judge each, and a selector keeps the one that fits.\n"
    "- **Reading a task's candidate runs:** `factory show TASK` labels each candidate's runs "
    "`candidate K of N` and marks the chosen one; a selector run recorded as `fallback` chose by the "
    "smallest diff.\n"
    "- **`factory run PLAN`**", 1)
assert "candidates" in skill, "skill marker moved"
(tmp / "factory" / "templates" / "skills" / "factory-ops" / "SKILL.md").write_text(skill)

# ------------------------------------------------------------------ run the tests against the tree
tt.PACKAGE = tmp / "factory"
for name in ("test_the_agent_flows_document_build_candidates", "test_the_roles_table_has_the_selector",
             "test_the_reference_documents_candidates_and_the_select_role",
             "test_the_reference_troubleshooting_covers_candidates_and_the_selector",
             "test_next_marks_item_14_done", "test_the_config_template_documents_candidates",
             "test_the_factory_ops_skill_covers_candidates"):
    getattr(tt, name)()
    print("PASS on simulated docs:", name)
