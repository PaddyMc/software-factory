import unittest

from iniapp.app import load_settings
from iniapp.db import load_db_config


SAMPLE = "# app settings\nname = demo\n\nretries = 3\nretries = 5\n"
EXPECTED = {"name": "demo", "retries": "5"}


class SettingsTests(unittest.TestCase):
    def test_application_settings_parse_comments_blanks_and_duplicates(self):
        self.assertEqual(load_settings(SAMPLE), EXPECTED)

    def test_database_settings_parse_comments_blanks_and_duplicates(self):
        self.assertEqual(load_db_config(SAMPLE), EXPECTED)

    def test_comment_and_blank_lines_are_skipped(self):
        for loader in (load_settings, load_db_config):
            with self.subTest(loader=loader.__name__):
                self.assertEqual(loader("# comment\n\n   \n"), {})


if __name__ == "__main__":
    unittest.main()
