import unittest

from ratelimit.limiter import RateLimiter


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class RateLimiterHiddenTests(unittest.TestCase):
    def test_a_burst_is_limited_to_capacity(self):
        fake = FakeClock()
        limiter = RateLimiter(capacity=3, refill_rate=1.0, clock=fake)
        for _ in range(3):
            self.assertTrue(limiter.try_acquire())
        self.assertFalse(limiter.try_acquire())

    def test_tokens_refill_over_fractional_time(self):
        fake = FakeClock()
        limiter = RateLimiter(capacity=3, refill_rate=2.0, clock=fake)
        for _ in range(3):
            self.assertTrue(limiter.try_acquire())
        fake.advance(0.5)
        self.assertTrue(limiter.try_acquire())
        self.assertFalse(limiter.try_acquire())
        fake.advance(0.25)
        self.assertFalse(limiter.try_acquire())
        fake.advance(0.25)
        self.assertTrue(limiter.try_acquire())

    def test_requests_larger_than_capacity_never_succeed(self):
        fake = FakeClock()
        limiter = RateLimiter(capacity=3, refill_rate=1.0, clock=fake)
        self.assertFalse(limiter.try_acquire(4))
        fake.advance(10.0)
        self.assertFalse(limiter.try_acquire(4))
        self.assertTrue(limiter.try_acquire(3))

    def test_refill_never_exceeds_capacity(self):
        fake = FakeClock()
        limiter = RateLimiter(capacity=3, refill_rate=1.0, clock=fake)
        for _ in range(3):
            self.assertTrue(limiter.try_acquire())
        fake.advance(100.0)
        for _ in range(3):
            self.assertTrue(limiter.try_acquire())
        self.assertFalse(limiter.try_acquire())

    def test_a_failed_request_consumes_nothing(self):
        fake = FakeClock()
        limiter = RateLimiter(capacity=2, refill_rate=1.0, clock=fake)
        self.assertTrue(limiter.try_acquire(2))
        fake.advance(1.0)
        self.assertFalse(limiter.try_acquire(2))
        self.assertTrue(limiter.try_acquire())


if __name__ == "__main__":
    unittest.main()
