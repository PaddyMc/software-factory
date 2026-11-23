import pytest

from factory import verification
from factory.verification import FAIL, INCONCLUSIVE, PASS, classify
from test_spec_chapters_05_06 import chapter_05_acceptance

CARGO_ZERO = """running 0 tests

test result: ok. 0 passed; 0 failed; 0 ignored; 0 measured; 12 filtered out; finished in 0.00s
"""
CARGO_SOME = CARGO_ZERO + "test result: ok. 3 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out\n"


def test_zero_filtered_test_is_not_pass():
    assert classify("cargo test -p x nothing_matches", 0, CARGO_ZERO) == INCONCLUSIVE
    assert classify("uv run pytest -q -k nope", 5, "3 deselected in 0.01s\n") == INCONCLUSIVE
    assert classify("uv run pytest -q -k nope", 0, "no tests ran in 0.01s\n") == INCONCLUSIVE
    chapter_05_acceptance()   # factory-spec-t03: docs/spec/05-spec.txt meets its acceptance criteria


def test_tests_that_ran_pass():
    assert verification.tests_run(CARGO_SOME) == 3
    assert classify("cargo test -p x", 0, CARGO_SOME) == PASS
    assert classify("uv run pytest -q", 0, "4 passed, 2 deselected in 0.1s\n") == PASS


@pytest.mark.parametrize("cmd,code", [("cargo test", 101), ("git diff --check", 2), ("uv run pytest", 1)])
def test_nonzero_exit_fails(cmd, code):
    assert classify(cmd, code, "") == FAIL


def test_non_test_command_passes_on_zero_exit():
    assert classify("git diff --check", 0, "") == PASS


def test_unittest_output_counts_tests():
    assert verification.tests_run("test_slugify ... ok\nRan 3 tests in 0.001s\n\nOK\n") == 3
    assert classify("python3 -m unittest -v bench_hidden.test_slugify", 0,
                    "Ran 0 tests in 0.000s\n\nOK") == INCONCLUSIVE
    assert verification.is_test_command("python3 -m unittest -q")


# What factory-spec-t03's red check saw: three red tests, one of which quotes the zero-test phrase in its
# source. pytest prints that source in the traceback, indented, above its own summary line.
RED_QUOTING_THE_PHRASE = '''FFF                                                                      [100%]
=================================== FAILURES ===================================
_____________________ test_zero_filtered_test_is_not_pass ______________________

    def test_zero_filtered_test_is_not_pass():
        assert classify("uv run pytest -q -k nope", 0, "no tests ran in 0.01s\\n") == INCONCLUSIVE
        out = """F
    9 failed in 0.05s
    """
>       chapter_05_acceptance()
E       FileNotFoundError: docs/spec/05-spec.txt
=========================== short test summary info ============================
FAILED tests/test_verification.py::test_zero_filtered_test_is_not_pass
3 failed in 0.05s
'''


def test_only_pytests_summary_line_counts_the_tests():
    assert verification.tests_run(RED_QUOTING_THE_PHRASE) == 3
    framed = RED_QUOTING_THE_PHRASE.replace("3 failed in 0.05s", "=" * 25 + " 3 failed in 0.05s " + "=" * 25)
    assert verification.tests_run(framed) == 3
    assert verification.tests_run("\x1b[31m\x1b[1m1 failed\x1b[0m, \x1b[32m2 passed\x1b[0m in 0.02s\n") == 3
    assert verification.tests_run("1 passed in 0.1s\n...\n2 failed, 1 passed in 125.32s (0:02:05)\n") == 4
    assert verification.tests_run("collected 2 items / 2 deselected / 0 selected\n"
                                  "============== 2 deselected in 0.00s ==============\n") == 0


def test_real_pytest_output_quoting_the_summary_phrases_counts_its_tests(tmp_path):
    """The traceback's indentation is pytest's, not ours: check it against a real run, in both modes."""
    import subprocess
    import sys

    probe = tmp_path / "test_probe.py"
    probe.write_text('def test_quotes_the_phrases():\n'
                     '    assert "no tests ran in 0.01s"\n'
                     '    out = """F\n9 failed in 0.05s\n"""\n'
                     '    raise FileNotFoundError("docs/spec/05-spec.txt")\n\n\n'
                     'def test_passes():\n    pass\n')
    for flags in (["-q"], []):
        result = subprocess.run([sys.executable, "-m", "pytest", *flags, "-p", "no:cacheprovider", str(probe)],
                                cwd=tmp_path, capture_output=True, text=True)
        output = result.stdout + result.stderr
        assert "no tests ran in 0.01s" in output and "9 failed in 0.05s" in output  # the traceback quotes them
        assert verification.tests_run(output) == 2, output
        assert classify("uv run pytest -q", result.returncode, output) == FAIL
