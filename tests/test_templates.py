"""`factory init` scaffolds a project; the shipped role prompts match the factory."""

import re

import pytest

from factory import config as C
from factory.agents import ROLE_FILES, load_role, missing_keys, parse_verdict, role_models
from factory.cli import main


@pytest.fixture
def initialised(repo, monkeypatch, capsys):
    (repo / ".factory/config.yaml").unlink()
    monkeypatch.chdir(repo)
    assert main(["init"]) == 0
    capsys.readouterr()
    return repo


def test_init_writes_config_and_role_prompts(initialised):
    cfg = C.load(initialised)
    assert cfg.name == "repo" and cfg.e2e is None and cfg.session_log is None
    for name in ("planner", "builder", "reviewer", "verifier"):
        assert (initialised / f".factory/agents/{name}.md").is_file()


def test_init_keeps_existing_files_unless_forced(initialised, capsys):
    path = initialised / ".factory/agents/builder.md"
    path.write_text("mine")
    assert main(["init"]) == 0
    assert path.read_text() == "mine" and "keep   .factory/agents/builder.md" in capsys.readouterr().out
    assert main(["init", "--force"]) == 0
    assert path.read_text() != "mine"


@pytest.mark.parametrize("role", list(ROLE_FILES))
def test_role_prompts_load_with_models(initialised, role):
    cfg, body = load_role(initialised, role)
    assert re.match(r"^openrouter:[\w.-]+/[\w.:-]+$", cfg["model"]) and int(cfg["max_steps"]) > 0
    assert f"You are the {ROLE_FILES[role].upper()}" in body
    assert "Cleartree" not in body and "crates/" not in body        # project-specific rules come from config


def test_reviewer_prompt_matches_verdict_parser(initialised):
    _, body = load_role(initialised, "review")
    assert "VERDICT: APPROVE" in body and "VERDICT: CHANGES" in body
    assert parse_verdict("text\nVERDICT: APPROVE\n") == "APPROVE"
    assert parse_verdict("looks fine to me") == "CHANGES"          # missing verdict fails safe
    assert parse_verdict("VERDICT: APPROVE\n...\nVERDICT: CHANGES") == "CHANGES"


def test_missing_provider_key_is_reported_before_work(initialised):
    models = role_models(initialised)
    assert missing_keys(models, {}) == ["OPENROUTER_API_KEY"]
    assert missing_keys(models, {"OPENROUTER_API_KEY": "x"}) == []
    assert missing_keys(role_models(initialised, "anthropic:claude-opus-5-5"), {"OPENROUTER_API_KEY": "x"}) == ["ANTHROPIC_API_KEY"]


def test_config_command_prints_effective_settings(initialised, capsys):
    assert main(["config"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("# .factory/config.yaml;") and "name: repo" in out and "plans:" in out
