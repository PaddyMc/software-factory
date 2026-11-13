import unittest

from adder.calc import add


class AddHiddenTests(unittest.TestCase):
    def test_positive_integers(self):
        self.assertEqual(add(10, 5), 15)

    def test_negative_integers(self):
        self.assertEqual(add(-4, -9), -13)

    def test_zeroes(self):
        self.assertEqual(add(0, 0), 0)


if __name__ == "__main__":
    unittest.main()
