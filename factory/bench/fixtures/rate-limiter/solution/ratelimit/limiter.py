"""Rate-limiting primitives."""

import time


class RateLimiter:
    """A token-bucket rate limiter with an injectable clock."""

    def __init__(self, capacity, refill_rate, clock=time.monotonic):
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.clock = clock
        self.tokens = float(capacity)
        self.last = clock()

    def try_acquire(self, n=1):
        """Consume n tokens when available, returning whether the request succeeded."""
        now = self.clock()
        elapsed = now - self.last
        self.last = now
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        if n <= self.capacity and n <= self.tokens:
            self.tokens -= n
            return True
        return False
