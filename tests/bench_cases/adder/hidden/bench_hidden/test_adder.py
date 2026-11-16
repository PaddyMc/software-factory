import unittest

from calc import add


class HiddenAddTests(unittest.TestCase):
    def test_positive_sum(self):
        self.assertEqual(add(2, 3), 5)

    def test_negative_and_positive(self):
        self.assertEqual(add(-1, 1), 0)

    def test_zero(self):
        self.assertEqual(add(0, 0), 0)

    def test_negative_sum_component(self):
        self.assertEqual(add(10, -4), 6)


if __name__ == "__main__":
    unittest.main()
