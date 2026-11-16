import unittest

from calc import double


class CalcTests(unittest.TestCase):
    def test_double(self):
        self.assertEqual(double(3), 6)
        self.assertEqual(double(-2), -4)


if __name__ == "__main__":
    unittest.main()
