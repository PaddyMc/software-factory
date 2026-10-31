import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

TASK = """\
- id: demo-t01
  goal: "Add the greeting module"
  spec_refs: ["docs/spec/greeting.md#hello"]
  depends_on: []
  non_goals: ["Anything else"]
  acceptance: ["src/greet.txt says hello"]
  verification: ["grep -q hello src/greet.txt"]
  risk: low
- id: demo-t02
  goal: "Do the second thing"
  spec_refs: []
  depends_on: [demo-t01]
  non_goals: []
  acceptance: ["Second thing done"]
  verification: ["true"]
  risk: high
"""

# The demo project's settings: a Rust-style e2e requirement and a session log, so the gates under
# test are the full set. Tests that need a different project write their own config.
DEMO_CONFIG = """\
name: demo
exclude: ["docs/user/**"]
session_log: docs/sessions
e2e:
  dir: crates/e2e/tests/
  language: rust
  run_new: "cargo test -p demo-e2e --test {target} {name} -- --exact"
  run_all: "cargo test -p demo-e2e"
unit_tests: ["cargo test --workspace --exclude demo-e2e"]
"""

GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}


def plan_text(yaml_body: str = TASK) -> str:
    return f"# Plan: Demo\n\nProse.\n\n```yaml\n{yaml_body}```\n\nMore prose.\n"


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True,
                          env={**os.environ, **GIT_ENV}).stdout.strip()


@pytest.fixture(autouse=True)
def git_identity(monkeypatch):
    for k, v in GIT_ENV.items():
        monkeypatch.setenv(k, v)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A throwaway repo (branch main) with one contracted plan, pushed to a bare `origin`."""
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    r = tmp_path / "repo"
    (r / "docs/plans/demo").mkdir(parents=True)
    (r / "docs/plans/demo/demo.md").write_text(plan_text())
    (r / "AGENTS.md").write_text("# Demo repo\n")
    (r / ".factory").mkdir()
    (r / ".factory/config.yaml").write_text(DEMO_CONFIG)
    (r / ".gitignore").write_text("__pycache__/\n")
    git(r, "init", "-q", "-b", "main")
    git(r, "add", "-A")
    git(r, "commit", "-q", "-m", "init")
    git(r, "remote", "add", "origin", str(origin))
    git(r, "push", "-q", "-u", "origin", "main")
    return r


@pytest.fixture
def home(tmp_path: Path, monkeypatch) -> Path:
    h = tmp_path / "factory-home"
    h.mkdir()
    monkeypatch.setenv("FACTORY_HOME", str(h))
    return h


FAKE_GH = textwrap.dedent(f"""\
    #!{sys.executable}
    # Test double for the gh calls the factory makes. State lives next to this script.
    import json, os, sys
    state = os.path.join(os.path.dirname(__file__), "gh-state.json")
    s = json.load(open(state)) if os.path.exists(state) else {{"prs": {{}}, "calls": []}}
    a = sys.argv[1:]
    s["calls"].append(a)
    def save(): json.dump(s, open(state, "w"))
    if a[:2] == ["pr", "create"]:
        head = a[a.index("--head") + 1]
        url = f"https://github.test/pr/{{len(s['prs']) + 1}}"
        s["prs"][head] = {{"url": url, "state": "OPEN", "base": a[a.index("--base") + 1],
                          "title": a[a.index("--title") + 1], "body": a[a.index("--body") + 1]}}
        save(); print(url); sys.exit(0)
    if a[:2] == ["pr", "view"]:
        key = a[2]
        pr = s["prs"].get(key) or next((p for p in s["prs"].values() if p["url"] == key), None)
        save()
        if not pr: sys.exit(1)
        fields = a[a.index("--json") + 1].split(",")
        if "-q" in a: print(pr["state"] if "state" in fields else pr["url"]); sys.exit(0)
        print(json.dumps({{f: pr.get(f, "MERGEABLE" if f == "mergeable" else None) for f in fields}})); sys.exit(0)
    if a[:2] == ["pr", "list"] and "--head" not in a:
        save()
        print(json.dumps([{{"headRefName": h, "url": p["url"], "state": p["state"], "baseRefName": p["base"]}}
                          for h, p in s["prs"].items()]))
        sys.exit(0)
    if a[:2] == ["pr", "list"]:
        pr = s["prs"].get(a[a.index("--head") + 1])
        save()
        if pr and pr["state"] == "OPEN": print(pr["url"])
        sys.exit(0)
    if a[:2] == ["pr", "edit"]:
        save(); sys.exit(0)
    if a[:1] == ["api"]:
        if "PATCH" in a:   # edit: api -X PATCH repos/{{owner}}/{{repo}}/pulls/N -f base=B -f body=…
            num = a[3].rsplit("/", 1)[1]
            for pr in s["prs"].values():
                if pr["url"].endswith("/" + num):
                    pr.update(a[i + 1].split("=", 1) for i, x in enumerate(a) if x == "-f")
        save(); sys.exit(0)
    save(); sys.exit(2)
    """)


@pytest.fixture
def fake_gh(tmp_path: Path, monkeypatch) -> Path:
    b = tmp_path / "bin"
    b.mkdir()
    exe = b / "gh"
    exe.write_text(FAKE_GH)
    exe.chmod(0o755)
    monkeypatch.setenv("PATH", f"{b}{os.pathsep}{os.environ['PATH']}")
    return b / "gh-state.json"
