"""`factory init` sets a repository up; the role prompts and skills ship with the factory and stay generic.

The factory's own docs describe what it ships: the tests at the end pin build candidates and the selector
in docs/architecture.md, docs/reference.md, NEXT.md, the config template and the factory-ops skill."""

import re
import subprocess
from pathlib import Path

import pytest
import yaml

from factory import config as C
from factory import contracts
from factory import flows
from factory import prbody
from factory.agents import (ROLE_FILES, load_role, missing_keys, parse_verdict, prompt_source,
                            role_model, role_models, step_limit)
from factory.cli import main
from factory.scaffold import BEGIN, END, SKILLS

PACKAGE = Path(__file__).resolve().parents[1] / "factory"
SPECIFIC = ("Cleartree", "did-spec", "did:tree", "tools/factory", "NEXT.md")   # the project this was extracted from


@pytest.fixture
def initialised(repo, monkeypatch, capsys):
    (repo / ".factory/config.yaml").unlink()
    monkeypatch.chdir(repo)
    assert main(["init"]) == 0
    capsys.readouterr()
    return repo


@pytest.fixture
def fresh(tmp_path, monkeypatch):
    """An empty git repository: no plans, no guidance, no config."""
    r = tmp_path / "fresh"
    r.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(r)], check=True)
    monkeypatch.chdir(r)
    return r


def test_init_writes_config_skills_session_log_and_guidance(initialised):
    cfg = C.load(initialised)
    assert cfg.name == "repo" and cfg.e2e is None and cfg.session_log == "docs/sessions" and cfg.unit_tests == ()
    for skill in SKILLS:
        source = initialised / f".claude/skills/{skill}"
        codex = initialised / f".agents/skills/{skill}"
        assert (source / "SKILL.md").is_file()
        assert codex.is_symlink() and not codex.readlink().is_absolute()
        assert codex.samefile(source)
    assert (initialised / ".agents/skills/factory-ops/references/troubleshooting.md").is_file()
    for skill in ("plan-workstream", "review-task"):
        policy = initialised / f".agents/skills/{skill}/agents/openai.yaml"
        assert yaml.safe_load(policy.read_text())["policy"]["allow_implicit_invocation"] is False
    assert (initialised / "docs/sessions/README.md").is_file()
    assert not (initialised / ".factory/agents").exists()                  # prompts ship with the factory
    assert not (initialised / "docs/plans/example.md").exists()            # the repo already has plans
    guidance = (initialised / "AGENTS.md").read_text()
    assert guidance.startswith("# Demo repo\n") and guidance.count(BEGIN) == 1 and "factory status --refresh" in guidance


def test_init_in_an_empty_repo_gets_a_valid_starter_plan(fresh, capsys):
    (fresh / "pyproject.toml").write_text("[project]\nname = 'x'\n")
    assert main(["init", "--no-session-log"]) == 0
    cfg = C.load(fresh)
    assert cfg.name == "fresh" and cfg.session_log is None and cfg.unit_tests == ("uv run pytest -q",)
    assert not (fresh / "docs/sessions").exists()
    assert (fresh / "AGENTS.md").read_text().startswith(BEGIN)
    plan = fresh / "docs/plans/example.md"
    tasks, errs = contracts.validate_plan(plan, fresh)
    assert errs == [] and [t.id for t in tasks] == ["example-t01"]
    capsys.readouterr()
    assert main(["validate-plan"]) == 0
    out = capsys.readouterr().out
    assert "ok   docs/plans/example.md (1 tasks)" in out and "warn" not in out     # runnable by the factory


def test_rust_repos_get_cargo_unit_tests_and_a_custom_session_log(fresh):
    (fresh / "Cargo.toml").write_text("[workspace]\n")
    assert main(["init", "--session-log", "notes/log"]) == 0
    cfg = C.load(fresh)
    assert cfg.unit_tests == ("cargo test --workspace",) and cfg.session_log == "notes/log"
    assert (fresh / "notes/log/README.md").is_file()


def test_the_section_goes_to_the_guidance_file_agents_read(fresh):
    (fresh / "CLAUDE.md").write_text("# Mine\n")
    assert main(["init", "--no-skills"]) == 0
    assert not (fresh / "AGENTS.md").exists()                            # agents read the first that exists
    assert (fresh / "CLAUDE.md").read_text().startswith("# Mine\n\n" + BEGIN)
    assert not (fresh / ".claude").exists()
    assert not (fresh / ".agents").exists()


def test_rerun_keeps_files_and_replaces_only_the_section(initialised, capsys):
    skill = initialised / ".claude/skills/review-task/SKILL.md"
    skill.write_text("mine")
    agents = initialised / "AGENTS.md"
    text = agents.read_text()
    inside = text[text.index(BEGIN):text.index(END) + len(END)]
    agents.write_text(text.replace(inside, BEGIN + "\nstale\n" + END) + "\n## Later notes\n")
    assert main(["init"]) == 0
    out = capsys.readouterr().out
    assert skill.read_text() == "mine" and "keep   .claude/skills/review-task (exists; --force overwrites)" in out
    assert "update AGENTS.md (factory section replaced)" in out
    assert agents.read_text() == text + "\n## Later notes\n"
    assert main(["init"]) == 0 and "keep   AGENTS.md (factory section up to date)" in capsys.readouterr().out
    assert main(["init", "--force"]) == 0
    assert skill.read_text() != "mine" and agents.read_text().count(BEGIN) == 1
    codex = initialised / ".agents/skills/review-task"
    assert codex.is_symlink() and (codex / "SKILL.md").read_text() == skill.read_text()


def test_init_adds_codex_links_to_an_existing_installation(fresh):
    skill = fresh / ".claude/skills/plan-workstream/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("custom planning instructions")

    assert main(["init"]) == 0
    codex = fresh / ".agents/skills/plan-workstream"
    assert codex.is_symlink() and (codex / "SKILL.md").read_text() == "custom planning instructions"
    assert main(["init"]) == 0
    assert skill.read_text() == "custom planning instructions"


@pytest.mark.parametrize("kind", ["file", "directory"])
def test_init_preserves_existing_codex_skills_even_with_force(fresh, kind):
    codex = fresh / ".agents/skills/review-task"
    codex.parent.mkdir(parents=True)
    if kind == "directory":
        codex.mkdir()
        custom = codex / "SKILL.md"
    else:
        custom = codex
    custom.write_text("custom review instructions")

    for args in (["init"], ["init", "--force"]):
        assert main(args) == 0
        assert not codex.is_symlink() and custom.read_text() == "custom review instructions"
        assert (fresh / ".agents/skills/plan-workstream/SKILL.md").is_file()


@pytest.mark.parametrize("dangling", [False, True])
def test_force_replaces_a_different_codex_symlink_without_modifying_its_target(fresh, dangling):
    target = fresh / "custom-review"
    if not dangling:
        target.mkdir()
        (target / "SKILL.md").write_text("custom review instructions")
    codex = fresh / ".agents/skills/review-task"
    codex.parent.mkdir(parents=True)
    codex.symlink_to(target, target_is_directory=True)

    assert main(["init"]) == 0
    assert codex.readlink() == target
    assert main(["init", "--force"]) == 0
    assert codex.samefile(fresh / ".claude/skills/review-task")
    if dangling:
        assert not target.exists()
    else:
        assert (target / "SKILL.md").read_text() == "custom review instructions"


@pytest.mark.parametrize("force", [False, True])
def test_no_skills_leaves_existing_skills_and_links_untouched(initialised, force):
    source = initialised / ".claude/skills/review-task/SKILL.md"
    source.write_text("custom review instructions")
    codex = initialised / ".agents/skills/review-task"
    codex.unlink()
    codex.symlink_to("custom-review", target_is_directory=True)

    assert main(["init", "--no-skills", *(["--force"] if force else [])]) == 0
    assert source.read_text() == "custom review instructions" and codex.readlink() == Path("custom-review")


@pytest.mark.parametrize("skill", SKILLS)
def test_skills_are_valid_and_generic(skill):
    root = PACKAGE / "templates/skills" / skill
    text = (root / "SKILL.md").read_text()
    front = yaml.safe_load(re.match(r"\A---\n(.*?)\n---\n", text, re.S).group(1))
    assert front["name"] == skill and len(front["description"]) <= 1024
    assert ("Explicit-invocation only" in front["description"]) == (skill != "factory-ops")
    assert "factory " in text
    for f in root.rglob("*.md"):
        for specific in (*SPECIFIC, "crates/"):
            assert specific not in f.read_text(), (f, specific)


def test_this_repository_uses_the_factory_it_ships():
    """The factory's own repository has the skills, guidance and config comments `factory init` ships:
    a change to a template is copied here too (.claude/skills/<skill>/, AGENTS.md, .factory/config.yaml)."""
    repo = PACKAGE.parent
    for skill in SKILLS:
        shipped, installed = PACKAGE / "templates/skills" / skill, repo / ".claude/skills" / skill
        files = sorted(p.relative_to(shipped) for p in shipped.rglob("*") if p.is_file())
        assert files == sorted(p.relative_to(installed) for p in installed.rglob("*") if p.is_file()), installed
        for rel in files:
            assert (installed / rel).read_text() == (shipped / rel).read_text(), f"copy {shipped / rel} to {installed / rel}"
        assert (repo / ".agents/skills" / skill).readlink() == Path(f"../../.claude/skills/{skill}")
    guidance = (repo / "AGENTS.md").read_text()
    assert guidance[guidance.index(BEGIN) + len(BEGIN):guidance.index(END)].strip() == \
        (PACKAGE / "templates/agents-section.md").read_text().strip()
    lines = iter((repo / C.CONFIG_PATH).read_text().splitlines())
    for prose in (line for line in (PACKAGE / "templates/config.yaml").read_text().splitlines() if re.match(r"# [A-Z]", line)):
        assert prose in lines, f"{C.CONFIG_PATH} lacks (or reorders) the template's comment {prose!r}"
    C.load(repo)                                                  # and it is valid, flows included


def test_nothing_in_the_package_names_the_original_project():
    for f in PACKAGE.rglob("*"):
        if f.is_file() and f.suffix in (".py", ".md", ".yaml"):
            for specific in SPECIFIC:
                assert specific not in f.read_text(), (f, specific)


@pytest.mark.parametrize("role", list(ROLE_FILES))
def test_role_prompts_ship_with_the_factory(repo, role):
    assert prompt_source(repo, role) == PACKAGE / "prompts" / f"{ROLE_FILES[role]}.md"
    meta, body = load_role(repo, role)
    assert re.match(r"^openrouter:[\w.-]+/[\w.:-]+$", meta["model"]) and int(meta["max_steps"]) > 0
    assert f"You are the {ROLE_FILES[role].upper()}" in body
    assert "crates/" not in body                                  # project-specific rules come from config


def test_prompt_command_shows_the_prompt_in_effect(repo, monkeypatch, capsys):
    monkeypatch.chdir(repo)
    assert main(["prompt", "reviewer"]) == 0
    out = capsys.readouterr().out
    assert out.startswith(f"# {PACKAGE / 'prompts/reviewer.md'} · model openrouter:") and "VERDICT: APPROVE" in out
    assert main(["prompt", "judge"]) == 2


def test_a_repository_can_override_a_prompt_and_set_models(repo):
    override = repo / ".factory/agents/reviewer.md"
    override.parent.mkdir(parents=True)
    override.write_text("---\nmodel: openrouter:a/override\nmax_steps: 5\n---\nYou are our REVIEWER.\n")
    assert load_role(repo, "review") == ({"model": "openrouter:a/override", "max_steps": 5}, "You are our REVIEWER.\n")
    shipped = load_role(repo, "plan")[0]["model"]
    cfg = C.parse({"models": {"plan": "anthropic:claude-x"}, "max_steps": {"build": 7}})
    assert role_models(repo, cfg=cfg) == {"plan": "anthropic:claude-x", "build": load_role(repo, "build")[0]["model"],
                                          "review": "openrouter:a/override", "verify": load_role(repo, "verify")[0]["model"]}
    assert set(role_models(repo, "openai:gpt-x", cfg).values()) == {"openai:gpt-x"}      # --model wins
    assert shipped.startswith("openrouter:") and cfg.max_steps == {"build": 7}


@pytest.mark.parametrize("data, error", [
    ({"models": {"planner": "x"}}, "unknown role"),
    ({"max_steps": {"build": "lots"}}, "positive integers"),
    ({"max_steps": {"build": 0}}, "positive integers"),
])
def test_bad_role_settings_are_rejected(data, error):
    with pytest.raises(C.ConfigError, match=error):
        C.parse(data)


def test_verifier_prompt_asks_for_the_fixed_shape(repo):
    meta, body = load_role(repo, "verify")
    assert meta == {"model": "openrouter:deepseek/deepseek-v4-flash-0731", "max_steps": 30}
    assert body.startswith("You are the VERIFIER")
    for text in ("TITLE: ", "## What changed", "## What to check", "1 to 5 bullets", "0 to 6 bullets"):
        assert text in body
    examples = re.findall(r"```markdown\n(.*?)\n```", body, re.S)
    assert len(examples) == 1
    summary = prbody.parse_summary(examples[0])
    assert summary is not None and summary.title and summary.changed and summary.check


def test_reviewer_prompt_matches_verdict_parser(repo):
    _, body = load_role(repo, "review")
    assert "VERDICT: APPROVE" in body and "VERDICT: CHANGES" in body
    assert parse_verdict("text\nVERDICT: APPROVE\n") == "APPROVE"
    assert parse_verdict("looks fine to me") == "CHANGES"          # missing verdict fails safe
    assert parse_verdict("VERDICT: APPROVE\n...\nVERDICT: CHANGES") == "CHANGES"


def test_missing_provider_key_is_reported_before_work(repo):
    models = role_models(repo)
    assert missing_keys(models, {}) == ["OPENROUTER_API_KEY"]
    assert missing_keys(models, {"OPENROUTER_API_KEY": "x"}) == []
    assert missing_keys(role_models(repo, "anthropic:claude-opus-5-5"), {"OPENROUTER_API_KEY": "x"}) == ["ANTHROPIC_API_KEY"]


def test_config_command_prints_effective_settings(initialised, capsys):
    assert main(["config"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("# .factory/config.yaml;") and "name: repo" in out and "plans:" in out and "models: {}" in out


def test_selector_prompt_matches_choice_parser(repo):
    """The select prompt asks for the CHOICE line the choice parser reads."""
    from factory.agents import parse_choice
    meta, body = load_role(repo, "select")
    assert meta == {"model": "openrouter:z-ai/glm-5.3", "max_steps": 30}
    assert body.startswith("You are the SELECTOR") and "CHOICE:" in body
    assert parse_choice("## Choice\n\nCandidate 2 fits the contract best.\n\nCHOICE: 2") == 2
    assert parse_choice("CHOICE: 1\n\nOn reflection.\n\nCHOICE: 3") == 3      # the last matching line wins
    assert parse_choice("I could not decide between the candidates.") is None  # a missing line is no choice


def test_the_select_role_can_be_configured_overridden_and_printed(repo, monkeypatch, capsys):
    monkeypatch.chdir(repo)
    meta, _ = load_role(repo, "select")
    cfg = C.parse({"models": {"select": "openrouter:z-ai/glm-5.2"}, "max_steps": {"select": 9}})
    step = flows.Step("select", "select")
    assert role_model(repo, "select", cfg) == "openrouter:z-ai/glm-5.2"       # models.select
    assert step_limit(step, cfg, meta) == 9 and step_limit(step, C.parse({}), meta) == 30

    assert main(["prompt", "select"]) == 0                                   # factory prompt select prints it
    out = capsys.readouterr().out
    assert out.startswith(f"# {PACKAGE / 'prompts/selector.md'} · model openrouter:z-ai/glm-5.3") and "CHOICE:" in out

    override = repo / ".factory/agents/selector.md"          # a repository can replace the shipped prompt
    override.parent.mkdir(parents=True)
    override.write_text("---\nmodel: fake:select\nmax_steps: 5\n---\nYou are our SELECTOR.\n")
    assert prompt_source(repo, "select") == override
    assert load_role(repo, "select") == ({"model": "fake:select", "max_steps": 5}, "You are our SELECTOR.\n")


# What the factory ships, it documents (flow-tuning-t05): build candidates and the selector, in its own
# docs, in the config template it scaffolds, and in the factory-ops skill.


def _doc(name: str) -> str:
    """One of the factory's own docs: they describe what the factory does."""
    return (PACKAGE.parent / "docs" / name).read_text()


def _section(text: str, heading: str) -> str:
    """A markdown section: the text under `heading`, up to the next heading of the same or higher level."""
    level = len(heading) - len(heading.lstrip("#"))
    _, found, rest = text.partition("\n" + heading + "\n")
    assert found, f"no {heading!r} heading"
    lines = []
    for line in rest.splitlines():
        if line.strip() == "---" or re.match(rf"^#{{1,{level}}} ", line):
            break
        lines.append(line)
    return "\n".join(lines)


def _table(text: str) -> list[str]:
    """The first markdown table in `text`, its header row included."""
    rows = []
    for line in text.splitlines():
        if line.startswith("|"):
            rows.append(line)
        elif rows:
            break
    assert rows, "no markdown table"
    return rows


def _row(table: list[str], key: str) -> str:
    """The table row of the config key `key` (its first cell)."""
    (row,) = [r for r in table if r.startswith(f"| `{key}` |")]
    return row


def test_the_agent_flows_document_build_candidates():
    """`### Build candidates` shows one first attempt with three candidates and says how the choice is
    made, what carries on when none pass, that later attempts and reworks build one change, and the cost."""
    agent_flows = _section(_doc("architecture.md"), "## Agent flows")
    assert "\n### Build candidates\n" in agent_flows, \
        "the Agent flows section has no `### Build candidates` subsection"
    body = _section(agent_flows, "### Build candidates")
    diagram = next((d for _, d in re.findall(r"```(\w*)\n(.*?)```", body, re.S) if "build#1.1" in d), None)
    assert diagram is not None, "no diagram of one first attempt with three candidates"
    for tag in ("build#1.1", "build#1.2", "build#1.3", "gates#1.1", "gates#1.2", "gates#1.3"):
        assert tag in diagram, f"the diagram shows no {tag}: three candidates, each judged by the gates"
    assert any(word in diagram for word in ("choose", "choice")), "the diagram shows no choice"
    assert "review" in diagram and "verify" in diagram, "the diagram doesn't show the flow's later steps"
    assert "selector" in body, "the section doesn't say the selector picks among the candidates that pass"
    assert "smallest" in body, "the section doesn't say the fallback: the smallest passing diff"
    assert "fewest failing gates" in body and "carries on" in body, \
        "the section doesn't say what carries on when no candidate passes"
    assert "rework" in body and re.search(r"(later attempts?|attempt 2)", body, re.I) \
           and re.search(r"one (change|build)", body), \
        "the section doesn't say that later attempts and reworks build one change"
    assert "--max-cost" in body and re.search(r"three (first )?builds", body), \
        "the section doesn't say what candidates cost"


def test_the_roles_table_has_the_selector():
    """The Roles table lists every role the factory runs: the selector has its row."""
    rows = _table(_section(_doc("architecture.md"), "### Roles"))
    assert any(re.match(r"\| (selector|select) \|", row) for row in rows), \
        "the Roles table has no row for the selector"


def test_the_reference_documents_candidates_and_the_select_role():
    """The flows documentation covers the `candidates` build step key with its rules and an example flow
    that parses; the configuration table lists the `select` role under models and max_steps."""
    config = _section(_doc("reference.md"), "## Configure a project")
    assert "candidates" in config, "the flows documentation doesn't cover the `candidates` build step key"
    assert "2 to 5" in config, "the flows documentation doesn't give the candidates range, 2 to 5"
    assert re.search(r"(followed by the gates|directly (after|followed))", config), \
        "the flows documentation doesn't give the placement rule: the gates step directly after the build"
    rows = _table(config)
    assert "candidates" in _row(rows, "flows"), "the `flows` row doesn't list the `candidates` step key"
    assert "select" in _row(rows, "models"), "the `models` row doesn't list the `select` role"
    assert "select" in _row(rows, "max_steps"), "the `max_steps` row doesn't list the `select` role"
    examples = []
    for block in re.findall(r"```yaml\n(.*?)```", config, re.S):
        parsed = yaml.safe_load(block)
        for name, steps in (parsed.get("flows", {}) if isinstance(parsed, dict) else {}).items():
            if isinstance(steps, list):                     # a documented example must be a valid flow
                flow = flows.parse_flow(str(name), steps)
                if any(s.candidates > 1 for s in flow.steps):
                    examples.append(flow)
    assert examples, "no example flow in the flows documentation uses a build step with `candidates`"


def test_the_reference_troubleshooting_covers_candidates_and_the_selector():
    """Troubleshooting has a row for the candidates flow-shape error and one for a selector run recorded
    as `fallback`."""
    rows = _table(_section(_doc("reference.md"), "## Troubleshooting"))
    assert any(re.search(r"candidates'? needs one build step followed by the gates", row) for row in rows), \
        "no row for `candidates needs one build step followed by the gates`"
    assert any("selector" in row and "fallback" in row for row in rows), \
        "no row for a selector run recorded as `fallback`"


def test_next_marks_item_14_done():
    """NEXT.md's table marks the one-build-per-attempt item done, linking the Build candidates section."""
    rows = [line for line in (PACKAGE.parent / "NEXT.md").read_text().splitlines()
            if line.startswith("|") and "one build per attempt" in line]
    assert rows, "NEXT.md's table has no item 14 row (the one-build-per-attempt gap)"
    assert rows[0].startswith("| ✓ |"), "item 14 isn't marked done in its table"
    assert "architecture.md#build-candidates" in rows[0], \
        "the done item doesn't link docs/architecture.md#build-candidates"


def test_the_config_template_documents_candidates():
    """The shipped config template carries a commented example of a build step with candidates, with a
    one-line explanation."""
    template = (PACKAGE / "templates/config.yaml").read_text()
    mentions = [line for line in template.splitlines() if "candidates" in line]
    assert mentions, "the config template doesn't mention `candidates`"
    assert all(line.lstrip().startswith("#") for line in mentions), \
        "the `candidates` example must be commented out, not active, in the shipped template"
    assert any("candidates" in line and "build" in line for line in mentions), \
        "no commented example of a build step with candidates"
    assert any(re.match(r"# [A-Z].*candidate", line) for line in template.splitlines()), \
        "no one-line comment explaining the `candidates` example"


def test_the_factory_ops_skill_covers_candidates():
    """The factory-ops skill covers choosing a flow with candidates and reading a task's candidate runs."""
    skill = (PACKAGE / "templates/skills/factory-ops/SKILL.md").read_text()
    assert "candidates" in skill, "the factory-ops skill doesn't mention `candidates`"
    assert any("candidates" in line and ("--flow" in line or "flow:" in line or "flows:" in line)
               for line in skill.splitlines()), \
        "the skill doesn't cover choosing a flow with candidates"
    assert any("candidate" in line and "factory show" in line for line in skill.splitlines()), \
        "the skill doesn't cover reading a task's candidate runs"


# The plan pages are in the factory's own docs too (plan-pages-t04): the web page sections of the
# reference and the architecture, the factory-ops skill's `factory web` bullet, and NEXT.md's item 17.


def test_the_docs_describe_the_plan_pages():
    """The docs describe the plan pages: the reference's web page table has a row for each page, the
    architecture's web page section lists both pages and names the Markdown renderer, the factory-ops
    skill says `factory web` shows the plans at /plans, and NEXT.md marks item 17 done."""
    pages = _table(_section(_doc("reference.md"), "### The web page"))
    assert any(re.match(r"\| `?/plans`? \|", row) for row in pages), \
        "the page table in docs/reference.md's web page section has no `/plans` row"
    assert any(re.match(r"\| `?/plans/NAME`? \|", row) for row in pages), \
        "the page table in docs/reference.md's web page section has no `/plans/NAME` row"

    web = _section(_doc("architecture.md"), "## The web page")
    assert re.search(r"/plans(?!/NAME)", web), \
        "the web page section in docs/architecture.md lists no `/plans` page"
    assert "/plans/NAME" in web, \
        "the web page section in docs/architecture.md lists no `/plans/NAME` page"
    assert "markdown.py" in web, \
        "the web page section in docs/architecture.md doesn't say plans are rendered by factory/web/markdown.py"

    skill = (PACKAGE / "templates/skills/factory-ops/SKILL.md").read_text()
    assert any("factory web" in line and "/plans" in line for line in skill.splitlines()), \
        "the factory-ops skill doesn't say `factory web` shows the plans at /plans"

    rows = [line for line in (PACKAGE.parent / "NEXT.md").read_text().splitlines()
            if line.startswith("|") and "Plans can't be read on the web page" in line]
    assert rows, "NEXT.md's table has no item 17 row (plans can't be read on the web page)"
    assert rows[0].startswith("| ✓ |"), "item 17 isn't marked done in NEXT.md's table"
    assert "architecture.md#the-web-page" in rows[0], \
        "the done item doesn't link docs/architecture.md#the-web-page"
