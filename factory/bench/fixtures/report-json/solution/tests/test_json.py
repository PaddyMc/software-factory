import io
import json
import unittest
from contextlib import redirect_stdout

from reporttool.cli import main


class JsonTests(unittest.TestCase):
    def test_json_format_emits_title_and_rows(self):
        output = io.StringIO()
        with redirect_stdout(output):
            status = main(["--format", "json", "Q3 Expenses", "rent=1200", "food=340.50"])
        self.assertEqual(status, 0)
        self.assertEqual(
            json.loads(output.getvalue()),
            {"title": "Q3 Expenses", "rows": [["rent", "1200"], ["food", "340.50"]]},
        )

    def test_default_table_output_is_unchanged(self):
        output = io.StringIO()
        with redirect_stdout(output):
            main(["Q3 Expenses", "rent=1200", "food=340.50"])
        self.assertEqual(output.getvalue(), "Q3 Expenses\n-----------\nrent 1200\nfood 340.50\n")


if __name__ == "__main__":
    unittest.main()
