"""Reading a factory PR's reviews, and deciding which request changes and what brief the builder gets."""

import json

from factory import ci, reviews


def _review(id, login, state, body="", commit="a" * 40):
    return {"id": id, "user": {"login": login}, "state": state, "body": body, "commit_id": commit}


def _comment(id, review_id, path, body, *, line=None, original=None, reply_to=None):
    c = {"id": id, "pull_request_review_id": review_id, "path": path, "body": body, "user": {"login": "a"},
         "in_reply_to_id": reply_to}
    if line is None and original is not None:
        c["line"] = None
        c["original_line"] = original
    else:
        c["line"] = line
    return c


def _snap(author="you", revs=(), permissions=None):
    return reviews.Snapshot(author, tuple(revs), permissions or {})


def _state(fake_gh, *, author="you", reviews=(), comments=(), permissions=None):
    pr = {"url": "https://github.test/pr/1", "state": "OPEN", "author": author,
          "reviews": list(reviews), "comments": list(comments)}
    state = {"prs": {"branch": pr}, "calls": []}
    if permissions is not None:
        state["permissions"] = permissions
    fake_gh.write_text(json.dumps(state))
    return pr


def test_change_requests_count_only_from_reviewers_with_write_access():
    snap = _snap("you", [
        _review(1, "alice", "CHANGES_REQUESTED"),
        _review(2, "bob", "CHANGES_REQUESTED"),
        _review(3, "carol", "CHANGES_REQUESTED"),
        _review(4, "dave", "CHANGES_REQUESTED"),
        _review(5, "erin", "CHANGES_REQUESTED"),
        _review(6, "frank", "CHANGES_REQUESTED"),
    ], permissions={"alice": "write", "bob": "admin", "carol": "read", "dave": "triage", "erin": "none"})
    got = reviews.requests(snap)
    assert [r["id"] for r in got] == [1, 2]
    assert len(reviews.covered(snap)) == 2   # frank (absent) and read/triage/none never reach the brief either


def test_any_review_by_the_pr_author_requests_changes():
    snap = _snap("you", [
        _review(1, "you", "COMMENTED", body="a note"),
        _review(2, "you", "COMMENTED"),       # empty body: a single inline comment still counts
        _review(3, "you", "PENDING"),
        _review(4, "teammate", "COMMENTED"),
    ], permissions={"you": "none", "teammate": "write"})
    got = reviews.requests(snap)
    assert [r["id"] for r in got] == [1, 2]
    assert [r["id"] for r in reviews.covered(snap)] == [1, 2, 4]   # the teammate's COMMENTED isn't a request but reaches the brief


def test_each_reviewers_latest_decision_wins():
    # request then approve -> none; request then dismissed -> none
    assert reviews.requests(_snap("you", [_review(1, "a", "CHANGES_REQUESTED"), _review(2, "a", "APPROVED")],
                                  {"a": "write"})) == []
    assert reviews.requests(_snap("you", [_review(1, "a", "CHANGES_REQUESTED"), _review(2, "a", "DISMISSED")],
                                  {"a": "write"})) == []
    # approve then request -> one; request then COMMENTED -> still one (COMMENTED neither requests nor clears)
    snap = _snap("you", [_review(1, "a", "APPROVED"), _review(2, "a", "CHANGES_REQUESTED")], {"a": "write"})
    assert [r["id"] for r in reviews.requests(snap)] == [2]
    snap = _snap("you", [_review(1, "a", "CHANGES_REQUESTED"), _review(2, "a", "COMMENTED")], {"a": "write"})
    assert [r["id"] for r in reviews.requests(snap)] == [1]
    # two reviewers at once are judged independently
    snap = _snap("you", [
        _review(1, "alice", "CHANGES_REQUESTED"),
        _review(2, "alice", "APPROVED"),
        _review(3, "bob", "APPROVED"),
        _review(4, "bob", "CHANGES_REQUESTED"),
    ], permissions={"alice": "write", "bob": "write"})
    assert [r["id"] for r in reviews.requests(snap)] == [4]


def test_addressed_reviews_no_longer_count():
    snap = _snap("you", [
        _review(5, "you", "COMMENTED"),
        _review(10, "alice", "CHANGES_REQUESTED"),
        _review(12, "bob", "CHANGES_REQUESTED"),
    ], permissions={"alice": "write", "bob": "write"})
    assert [r["id"] for r in reviews.requests(snap, 10)] == [12]
    assert [r["id"] for r in reviews.requests(snap, 11)] == [12]
    assert [r["id"] for r in reviews.requests(snap, None)] == [5, 10, 12]   # NULL watermark counts as 0
    assert [r["id"] for r in reviews.requests(snap, 100)] == []


def test_fetch_reads_the_pr_reviews_and_permissions_through_gh_api(fake_gh):
    _state(fake_gh, author="you", reviews=[
        _review(1, "alice", "COMMENTED"),
        _review(2, "alice", "CHANGES_REQUESTED"),
        _review(3, "carol", "COMMENTED"),
        _review(4, "alice", "PENDING"),
        _review(5, "carol", "APPROVED"),
    ], permissions={"carol": "read"})

    snap = reviews.fetch(fake_gh.parent, "https://github.test/pr/1")
    assert snap is not None
    assert snap.author == "you"
    assert [r["id"] for r in snap.reviews] == [1, 2, 3, 5]     # submitted only, id order
    assert [(r["user"]["login"], r["state"]) for r in snap.reviews] == \
        [("alice", "COMMENTED"), ("alice", "CHANGES_REQUESTED"), ("carol", "COMMENTED"), ("carol", "APPROVED")]
    assert [r.get("commit_id") for r in snap.reviews] == ["a" * 40] * 4
    assert snap.permissions == {"alice": "write", "carol": "read"}   # once per reviewer, first-appearance order

    calls = json.loads(fake_gh.read_text())["calls"]
    expected = [
        ["api", "repos/{owner}/{repo}/pulls/1"],
        ["api", "--paginate", "repos/{owner}/{repo}/pulls/1/reviews?per_page=100"],
        ["api", "repos/{owner}/{repo}/collaborators/alice/permission"],
        ["api", "repos/{owner}/{repo}/collaborators/carol/permission"],
    ]
    assert calls == expected

    assert reviews.fetch(fake_gh.parent, "https://github.test/pr/404") is None

    _state(fake_gh, author="you", reviews=[_review(1, "alice", "COMMENTED")])
    state = json.loads(fake_gh.read_text())
    state["broken"] = ["pulls/1"]
    fake_gh.write_text(json.dumps(state))
    assert reviews.fetch(fake_gh.parent, "https://github.test/pr/1") is None


def test_brief_lists_review_bodies_and_inline_comments_by_path_and_line(fake_gh):
    comments = [
        _comment(1, 20, "factory/ci.py", "return the stderr instead of ''", line=61),
        _comment(2, 20, "factory/ci.py", "nit: name this `log_tail`", original=55),
        _comment(3, 20, "factory/ci.py", "yes, agreed", line=61, reply_to=1),
        _comment(4, 21, "factory/reviews.py", "also cover permissions", line=10),
        _comment(5, 9, "factory/x.py", "old request", line=2),
    ]
    _state(fake_gh, author="you", reviews=[
        _review(20, "alice", "CHANGES_REQUESTED", body="Please don't swallow the error here."),
        _review(21, "you", "COMMENTED"),
        _review(9, "bob", "CHANGES_REQUESTED"),
    ], comments=comments, permissions={"alice": "write", "bob": "write"})

    snap = reviews.fetch(fake_gh.parent, "https://github.test/pr/1")
    text = reviews.brief(fake_gh.parent, "https://github.test/pr/1", snap, 10)
    assert text.startswith("# Address review")
    assert "who approves the merge" in text
    assert "beyond the plan" in text
    assert "answer it in your final message" in text
    assert "## Review by @alice (CHANGES_REQUESTED, on aaaaaaaaaaaa)" in text
    assert "Please don't swallow the error here." in text
    assert "- factory/ci.py:61: return the stderr instead of ''" in text
    assert "- factory/ci.py:55 (outdated): nit: name this `log_tail`" in text
    assert "  - factory/ci.py:61: yes, agreed" in text
    assert "## Review by @you (COMMENTED, on aaaaaaaaaaaa)" in text
    assert "- factory/reviews.py:10: also cover permissions" in text
    assert "@bob" not in text and "old request" not in text
    assert ["api", "--paginate", "repos/{owner}/{repo}/pulls/1/comments?per_page=100"] in \
        json.loads(fake_gh.read_text())["calls"]

    # cap
    long_body = "x" * (ci.BRIEF_LIMIT + 100)
    _state(fake_gh, author="you", reviews=[_review(1, "alice", "CHANGES_REQUESTED", body=long_body)],
           permissions={"alice": "write"})
    snap = reviews.fetch(fake_gh.parent, "https://github.test/pr/1")
    text = reviews.brief(fake_gh.parent, "https://github.test/pr/1", snap, 0)
    assert len(text) == ci.BRIEF_LIMIT + len("\n… (truncated)")
    assert text.endswith("… (truncated)")