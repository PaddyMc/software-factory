import unittest

from ratelimit.limiter import RateLimiter


class RateLimiterTests(unittest.TestCase):
    def test_a_fresh_limiter_allows_one_request(self):
        limiter = RateLimiter(capacity=3, refill_rate=1.0)
        self.assertIs(limiter.try_acquire(), True)

    def test_try_acquire_returns_a_bool(self):
        limiter = RateLimiter(capacity=3, refill_rate=1.0)
        self.assertIsInstance(limiter.try_acquire(1), bool)


if __name__ == "__main__":
    unittest.main()
