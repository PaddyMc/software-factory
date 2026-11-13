import io
import unittest
from contextlib import redirect_stdout

from reporttool.cli import main


class CliTests(unittest.TestCase):
    def test_readme_example_renders_exactly(self):
        output = io.StringIO()
        with redirect_stdout(output):
            status = main(["Q3 Expenses", "rent=1200", "food=340.50"])
        self.assertEqual(status, 0)
        self.assertEqual(output.getvalue(), "Q3 Expenses\n-----------\nrent 1200\nfood 340.50\n")

    def test_keys_left_align_to_the_longest_key(self):
        output = io.StringIO()
        with redirect_stdout(output):
            main(["T", "a=1", "bbb=2"])
        self.assertEqual(output.getvalue(), "T\n-\na   1\nbbb 2\n")

    def test_no_items_prints_only_the_header(self):
        output = io.StringIO()
        with redirect_stdout(output):
            main(["Empty"])
        self.assertEqual(output.getvalue(), "Empty\n-----\n")


if __name__ == "__main__":
    unittest.main()
