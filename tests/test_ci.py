"""Reading CI checks off a PR, and the brief the builder gets to fix them."""

import json

from factory import ci

JOB = "https://github.test/o/r/actions/runs/11/job/22"


def _run(name, conclusion, status="COMPLETED", url=JOB):
    return {"__typename": "CheckRun", "workflowName": "factory", "name": name, "status": status,
            "conclusion": conclusion, "detailsUrl": url}


def test_failing_reads_check_runs_and_commit_statuses():
    rollup = [_run("rust fmt", "FAILURE"), _run("rust e2e", "TIMED_OUT"), _run("factory tests", "SUCCESS"),
              _run("rust unit", "CANCELLED"), _run("rust check", "", status="IN_PROGRESS"),
              {"__typename": "StatusContext", "context": "ci/external", "state": "ERROR", "targetUrl": "https://ci.test/1"},
              {"__typename": "StatusContext", "context": "ci/pending", "state": "PENDING"}]
    got = ci.failing(rollup)
    assert [(c.name, c.conclusion) for c in got] == [("factory / rust fmt", "FAILURE"), ("factory / rust e2e", "TIMED_OUT"),
                                                     ("ci/external", "ERROR")]
    assert got[0].job_id == "22" and got[2].job_id is None
    assert ci.failing(None) == []


def test_red_only_judges_the_factorys_own_candidate():
    pr = {"headRefOid": "abc", "statusCheckRollup": [_run("rust fmt", "FAILURE")]}
    assert [c.name for c in ci.red(pr, "abc")] == ["factory / rust fmt"]
    assert ci.red(pr, "def") is None                  # someone pushed another commit: not ours to fix
    assert ci.red({}, "abc") is None                  # gh failed
    assert ci.red({"headRefOid": "abc", "statusCheckRollup": [_run("x", "SUCCESS")]}, "abc") == []


def test_brief_carries_each_failed_job_log_up_to_its_last_error(fake_gh):
    log = "\ufeff" + "\n".join(f"2026-10-31T10:00:{i % 60:02d}.0000000Z line {i}" for i in range(2000)) + (
        "\n2026-10-31T10:01:00.0Z \x1b[31mDiff in src/lib.rs\x1b[0m"
        "\n2026-10-31T10:01:01.0Z ##[error]Process completed with exit code 1."
        "\n2026-10-31T10:01:02.0Z Post job cleanup.\n2026-10-31T10:01:03.0Z Cleaning up orphan processes")
    fake_gh.write_text(json.dumps({"prs": {}, "calls": [], "logs": {"22": log}}))
    checks = ci.failing([_run("rust fmt", "FAILURE"),
                         {"__typename": "StatusContext", "context": "ci/external", "state": "FAILURE"}])
    text = ci.brief(fake_gh.parent, "https://github.test/pr/1", "a" * 40, checks)
    assert "# Fix failing CI" in text and "head commit aaaaaaaaaaaa" in text
    assert f"- factory / rust fmt: FAILURE ({JOB})" in text and "- ci/external: FAILURE" in text
    assert text.rstrip().endswith("(no log available: not a GitHub Actions job, or gh couldn't fetch it)")
    assert "\nDiff in src/lib.rs\n##[error]Process completed with exit code 1.\n```" in text   # timestamps, colours
    assert "Cleaning up" not in text and "\ufeff" not in text                 # and the job's cleanup dropped
    assert "line 1999" in text and "line 0\n" not in text and "earlier lines cut" in text
    assert ["api", "repos/{owner}/{repo}/actions/jobs/22/logs"] in json.loads(fake_gh.read_text())["calls"]
