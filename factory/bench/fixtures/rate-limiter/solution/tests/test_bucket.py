import unittest

from ratelimit.limiter import RateLimiter


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class TokenBucketTests(unittest.TestCase):
    def test_burst_is_limited_to_capacity(self):
        fake = FakeClock()
        limiter = RateLimiter(capacity=3, refill_rate=1.0, clock=fake)
        for _ in range(3):
            self.assertTrue(limiter.try_acquire())
        self.assertFalse(limiter.try_acquire())

    def test_fractional_time_refills_tokens(self):
        fake = FakeClock()
        limiter = RateLimiter(capacity=3, refill_rate=2.0, clock=fake)
        for _ in range(3):
            self.assertTrue(limiter.try_acquire())
        fake.advance(0.5)
        self.assertTrue(limiter.try_acquire())
        self.assertFalse(limiter.try_acquire())

    def test_oversized_request_fails_without_consuming_tokens(self):
        fake = FakeClock()
        limiter = RateLimiter(capacity=3, refill_rate=1.0, clock=fake)
        self.assertFalse(limiter.try_acquire(4))
        self.assertTrue(limiter.try_acquire(3))


if __name__ == "__main__":
    unittest.main()
