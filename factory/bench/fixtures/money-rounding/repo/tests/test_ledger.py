import unittest

from ledgerbook.ledger import round_cents, total


class LedgerTests(unittest.TestCase):
    def test_total_adds_ordinary_amounts(self):
        self.assertAlmostEqual(float(total(["1.10", "2.20"])), 3.30)

    def test_empty_total_is_zero(self):
        self.assertAlmostEqual(float(total([])), 0.0)

    def test_round_cents_keeps_two_place_amounts(self):
        self.assertAlmostEqual(float(round_cents("12.34")), 12.34)

    def test_round_cents_rounds_below_a_half_cent(self):
        self.assertAlmostEqual(float(round_cents("12.344")), 12.34)


if __name__ == "__main__":
    unittest.main()
