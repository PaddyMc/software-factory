import unittest

from adder.calc import double


class DoubleTests(unittest.TestCase):
    def test_double(self):
        self.assertEqual(double(6), 12)
        self.assertEqual(double(-3), -6)


if __name__ == "__main__":
    unittest.main()
