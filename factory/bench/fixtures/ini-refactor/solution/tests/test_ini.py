import unittest
from unittest.mock import patch

from iniapp.app import load_settings
from iniapp.db import load_db_config
from iniapp.ini import parse_pairs


class SharedParserTests(unittest.TestCase):
    def test_comments_blanks_stripping_and_duplicates(self):
        text = "  name = demo app  \n# comment\n\nretries = 3\nretries = 5\n"
        self.assertEqual(parse_pairs(text), {"name": "demo app", "retries": "5"})

    def test_only_the_first_equals_separates_key_and_value(self):
        self.assertEqual(parse_pairs("path = left = right\n"), {"path": "left = right"})

    def test_a_line_without_an_equals_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_pairs("just text\n")

    def test_public_functions_delegate_to_the_shared_parser(self):
        for module, loader in (("iniapp.app", load_settings), ("iniapp.db", load_db_config)):
            with self.subTest(module=module), patch(
                f"{module}.parse_pairs", return_value={"name": "demo"}
            ) as shared:
                self.assertEqual(loader("input"), {"name": "demo"})
                shared.assert_called_once_with("input")


if __name__ == "__main__":
    unittest.main()
