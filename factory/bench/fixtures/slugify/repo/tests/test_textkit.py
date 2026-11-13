import unittest

from textkit.slug import normalize


class NormalizeTests(unittest.TestCase):
    def test_whitespace_runs_collapse(self):
        self.assertEqual(normalize("  A\t title\n with spaces  "), "A title with spaces")

    def test_already_normalized_text_is_unchanged(self):
        self.assertEqual(normalize("A title"), "A title")


if __name__ == "__main__":
    unittest.main()
