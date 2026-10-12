import pytest

from factory import verification
from factory.verification import FAIL, INCONCLUSIVE, PASS, classify

CARGO_ZERO = """running 0 tests

test result: ok. 0 passed; 0 failed; 0 ignored; 0 measured; 12 filtered out; finished in 0.00s
"""
CARGO_SOME = CARGO_ZERO + "test result: ok. 3 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out\n"


def test_zero_filtered_test_is_not_pass():
    assert classify("cargo test -p x nothing_matches", 0, CARGO_ZERO) == INCONCLUSIVE
    assert classify("uv run pytest -q -k nope", 5, "3 deselected in 0.01s\n") == INCONCLUSIVE
    assert classify("uv run pytest -q -k nope", 0, "no tests ran in 0.01s\n") == INCONCLUSIVE


def test_tests_that_ran_pass():
    assert verification.tests_run(CARGO_SOME) == 3
    assert classify("cargo test -p x", 0, CARGO_SOME) == PASS
    assert classify("uv run pytest -q", 0, "4 passed, 2 deselected in 0.1s\n") == PASS


@pytest.mark.parametrize("cmd,code", [("cargo test", 101), ("git diff --check", 2), ("uv run pytest", 1)])
def test_nonzero_exit_fails(cmd, code):
    assert classify(cmd, code, "") == FAIL


def test_non_test_command_passes_on_zero_exit():
    assert classify("git diff --check", 0, "") == PASS
