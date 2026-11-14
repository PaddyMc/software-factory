"""Rate-limiting primitives."""


class RateLimiter:
    """A rate limiter placeholder."""

    def __init__(self, capacity, refill_rate):
        self.capacity = capacity
        self.refill_rate = refill_rate

    def try_acquire(self, n=1):
        """Allow every request until bucket accounting is implemented."""
        return True
