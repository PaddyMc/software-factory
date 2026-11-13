import unittest

from textkit.slug import slugify


class SlugifyHiddenTests(unittest.TestCase):
    def test_accents_fold_to_ascii(self):
        self.assertEqual(slugify("Café au Beurre"), "cafe-au-beurre")

    def test_punctuation_runs_collapse_and_trim(self):
        self.assertEqual(slugify("Hello, World!!!"), "hello-world")
        self.assertEqual(slugify("--One___two   three--"), "one-two-three")

    def test_empty_and_all_symbol_titles_are_empty(self):
        for title in ("", "   ", "!!!", "☃︎ !!! ???"):
            with self.subTest(title=title):
                self.assertEqual(slugify(title), "")

    def test_length_cut_stops_at_a_word_boundary(self):
        self.assertEqual(slugify("The quick brown fox jumps", max_length=18), "the-quick-brown")
        self.assertEqual(slugify("hello world again", max_length=11), "hello-world")

    def test_a_long_first_word_is_hard_cut(self):
        self.assertEqual(slugify("ABCDEFGHIJ", max_length=5), "abcde")


if __name__ == "__main__":
    unittest.main()
