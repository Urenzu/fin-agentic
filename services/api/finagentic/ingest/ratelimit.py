"""Staying inside EDGAR's request budget without spending it serially.

The SEC asks clients to stay under 10 requests/second. The obvious way to
honour that is to sleep between requests, and that is what this replaced: a
fixed 150ms pause before every fetch. It was correct and it was slow. Opening
one filing is six requests -- `FilingSummary.xml` plus five rendered exhibits
-- so 900ms of a measured 1.75s was the client waiting on its own timer, while
using barely two thirds of the budget the SEC actually allows and never more
than one connection at a time.

A token bucket separates the two concerns the sleep had conflated: how fast
requests may be issued, and how many may be in flight. Callers take a token
before each request and block only when the budget is genuinely spent, so six
independent fetches can run at once and finish in about the time one round trip
takes.
"""

from __future__ import annotations

import threading
import time
from types import TracebackType


class TokenBucket:
    """A thread-safe rate limiter that permits bursts.

    `rate` tokens accrue per second up to `capacity`, and `take()` blocks until
    one is available. Capacity is what makes a burst possible: an idle client
    accumulates a small budget, so the six requests behind a single filing are
    issued immediately rather than metered out one per interval.
    """

    def __init__(self, rate: float, capacity: float | None = None, *, now=time.monotonic) -> None:
        if rate <= 0:
            raise ValueError("rate must be positive")
        capacity = rate if capacity is None else capacity
        if capacity <= 0:
            raise ValueError("capacity must be positive")

        self._rate = rate
        self._capacity = capacity
        self._now = now
        self._tokens = capacity
        self._updated_at = now()
        self._lock = threading.Lock()

    @property
    def capacity(self) -> float:
        return self._capacity

    def _refill(self) -> None:
        """Credit the tokens accrued since the last look. Caller holds the lock."""
        now = self._now()
        elapsed = now - self._updated_at
        if elapsed > 0:
            self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
            self._updated_at = now

    def tokens(self) -> float:
        """The budget available right now. For tests and diagnostics."""
        with self._lock:
            self._refill()
            return self._tokens

    def take(self, tokens: float = 1.0, *, sleep=time.sleep) -> float:
        """Spend `tokens`, waiting if the budget is not yet there.

        Returns how long the caller was made to wait, which is what a caller
        would log or assert on.

        The wait happens outside the lock, so a thread that has to wait does not
        stop others from spending a budget that is already available. The debt
        is recorded before releasing the lock, so the tokens cannot be handed
        out twice.
        """
        if tokens > self._capacity:
            raise ValueError(f"cannot take {tokens} from a bucket holding {self._capacity}")

        with self._lock:
            self._refill()
            self._tokens -= tokens
            deficit = -self._tokens
            # A negative balance is this caller's alone: it has already been
            # subtracted, so whoever comes next waits for their own shortfall
            # on top of it rather than racing this one for the same tokens.
            delay = deficit / self._rate if deficit > 0 else 0.0

        if delay > 0:
            sleep(delay)
        return delay

    def __enter__(self) -> TokenBucket:
        self.take()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None


__all__ = ["TokenBucket"]
