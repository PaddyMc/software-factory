import unittest

from textkit.slug import slugify


class SlugifyTests(unittest.TestCase):
    def test_title_becomes_an_ascii_slug(self):
        self.assertEqual(slugify("  Café,   au Beurre! "), "cafe-au-beurre")

    def test_symbols_only_produce_an_empty_slug(self):
        self.assertEqual(slugify("!!!"), "")

    def test_length_cut_does_not_leave_a_partial_word(self):
        self.assertEqual(slugify("The quick brown fox jumps", max_length=18), "the-quick-brown")
        self.assertEqual(slugify("Extraordinary", max_length=5), "extra")


if __name__ == "__main__":
    unittest.main()
