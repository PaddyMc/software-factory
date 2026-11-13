import unittest
from decimal import Decimal

from ledgerbook.ledger import round_cents, total


class MoneyRoundingHiddenTests(unittest.TestCase):
    def test_repeated_tenths_do_not_drift(self):
        self.assertEqual(total(["0.1"] * 10), Decimal("1.00"))

    def test_half_cent_amounts_round_half_to_even(self):
        for amount, expected in (("0.125", "0.12"), ("0.135", "0.14"), ("2.675", "2.68")):
            with self.subTest(amount=amount):
                rounded = round_cents(amount)
                self.assertIsInstance(rounded, Decimal)
                self.assertEqual(str(rounded), expected)

    def test_ordinary_total_is_unchanged(self):
        self.assertEqual(total(["1.10", "2.20"]), Decimal("3.30"))


if __name__ == "__main__":
    unittest.main()
