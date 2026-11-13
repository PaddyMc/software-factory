import unittest
from decimal import Decimal

from ledgerbook.ledger import round_cents, total


class RoundingTests(unittest.TestCase):
    def test_total_is_exact_for_decimal_amounts(self):
        self.assertEqual(total(["0.1"] * 10), Decimal("1.00"))

    def test_half_cents_round_to_the_even_neighbor(self):
        self.assertEqual(round_cents("0.125"), Decimal("0.12"))
        self.assertEqual(round_cents("0.135"), Decimal("0.14"))
        self.assertEqual(round_cents("2.675"), Decimal("2.68"))

    def test_ordinary_amounts_keep_their_value(self):
        self.assertEqual(total(["1.10", "2.20"]), Decimal("3.30"))


if __name__ == "__main__":
    unittest.main()
