import json
import subprocess
import sys
import unittest


def run_report(*args):
    return subprocess.run(
        [sys.executable, "-m", "reporttool", *args],
        capture_output=True,
        text=True,
    )


class ReportJsonHiddenTests(unittest.TestCase):
    def test_json_output_has_the_documented_shape(self):
        result = run_report(
            "--format", "json", "Q3 Expenses", "rent=1200", "food=340.50"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            {"title": "Q3 Expenses", "rows": [["rent", "1200"], ["food", "340.50"]]},
        )

    def test_json_output_with_no_items_has_empty_rows(self):
        result = run_report("--format", "json", "Empty")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"title": "Empty", "rows": []})

    def test_default_table_output_is_byte_for_byte_unchanged(self):
        result = run_report("Q3 Expenses", "rent=1200", "food=340.50")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "Q3 Expenses\n-----------\nrent 1200\nfood 340.50\n")

    def test_explicit_table_format_matches_the_default(self):
        default = run_report("T", "a=1")
        explicit = run_report("--format", "table", "T", "a=1")
        self.assertEqual(default.returncode, 0, default.stderr)
        self.assertEqual(explicit.returncode, 0, explicit.stderr)
        self.assertEqual(explicit.stdout, default.stdout)


if __name__ == "__main__":
    unittest.main()
