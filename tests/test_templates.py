"""`factory init` sets a repository up; the role prompts and skills ship with the factory and stay generic."""

import re
import subprocess
from pathlib import Path

import pytest
import yaml

from factory import config as C
from factory import contracts
from factory.agents import ROLE_FILES, load_role, missing_keys, parse_verdict, prompt_source, role_models
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
