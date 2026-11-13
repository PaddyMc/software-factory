import unittest

import iniapp.app
import iniapp.db
from iniapp.app import load_settings
from iniapp.db import load_db_config
from iniapp.ini import parse_pairs


SAMPLE = "  name = demo app  \n# c\n\nretries = 3\nretries = 5\nhost = localhost\n"
EXPECTED = {"name": "demo app", "retries": "5", "host": "localhost"}


class IniRefactorHiddenTests(unittest.TestCase):
    def test_shared_parser_preserves_the_settings_semantics(self):
        self.assertEqual(parse_pairs(SAMPLE), EXPECTED)

    def test_shared_parser_rejects_a_line_without_a_separator(self):
        with self.assertRaises(ValueError):
            parse_pairs("just text\n")

    def test_public_functions_keep_their_behavior(self):
        for loader in (load_settings, load_db_config):
            with self.subTest(loader=loader.__name__):
                self.assertEqual(loader(SAMPLE), EXPECTED)
                with self.assertRaises(ValueError):
                    loader("just text\n")

    def test_public_functions_keep_their_names(self):
        self.assertTrue(callable(iniapp.app.load_settings))
        self.assertTrue(callable(iniapp.db.load_db_config))


if __name__ == "__main__":
    unittest.main()
