"""The token bucket that keeps us inside EDGAR's request budget.

Time is injected rather than slept through, so these assert the arithmetic
exactly instead of asserting that a wall clock was approximately obeyed.
"""

from __future__ import annotations

import threading

import pytest

from finagentic.ingest.ratelimit import TokenBucket


class FakeClock:
    """A clock that only moves when a sleep asks it to."""

    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def test_a_full_bucket_lets_a_burst_through_without_waiting():
    """The point of the change: six requests for one filing go at once."""
    clock = FakeClock()
    bucket = TokenBucket(rate=10, capacity=10, now=clock)

    for _ in range(6):
        assert bucket.take(sleep=clock.sleep) == 0.0

    assert clock.slept == []


def test_spending_past_the_budget_waits_for_exactly_the_shortfall():
    clock = FakeClock()
    bucket = TokenBucket(rate=10, capacity=2, now=clock)

    bucket.take(sleep=clock.sleep)
    bucket.take(sleep=clock.sleep)

    # Budget spent. The next token accrues after 1/rate seconds.
    assert bucket.take(sleep=clock.sleep) == pytest.approx(0.1)


def test_tokens_accrue_while_idle():
    clock = FakeClock()
    bucket = TokenBucket(rate=10, capacity=5, now=clock)

    bucket.take(5, sleep=clock.sleep)
    assert bucket.tokens() == pytest.approx(0)

    clock.now += 0.3
    assert bucket.tokens() == pytest.approx(3)


def test_idling_never_banks_more_than_capacity():
    """Otherwise a client left open overnight would open with a huge burst."""
    clock = FakeClock()
    bucket = TokenBucket(rate=10, capacity=5, now=clock)

    clock.now += 3600
    assert bucket.tokens() == pytest.approx(5)


def test_the_long_run_rate_is_the_configured_rate():
    clock = FakeClock()
    bucket = TokenBucket(rate=10, capacity=10, now=clock)

    for _ in range(50):
        bucket.take(sleep=clock.sleep)

    # 10 free from the initial budget, 40 metered at 10/s.
    assert clock.now == pytest.approx(4.0)


def test_waiters_queue_rather_than_racing_for_the_same_token():
    """Each caller's shortfall is recorded before the lock is released.

    If it were not, two threads finding an empty bucket would both compute the
    same delay, sleep the same interval and then both proceed -- issuing two
    requests where the budget allowed one.
    """
    clock = FakeClock()
    bucket = TokenBucket(rate=10, capacity=1, now=clock)

    bucket.take(sleep=lambda _: None)
    first = bucket.take(sleep=lambda _: None)
    second = bucket.take(sleep=lambda _: None)

    assert first == pytest.approx(0.1)
    assert second == pytest.approx(0.2)


def test_taking_more_than_the_bucket_holds_is_a_programming_error():
    # Waiting forever is the alternative, and it looks like a hang.
    bucket = TokenBucket(rate=10, capacity=5)
    with pytest.raises(ValueError, match="cannot take"):
        bucket.take(6)


@pytest.mark.parametrize(("rate", "capacity"), [(0, 1), (-1, 1), (1, 0), (1, -1)])
def test_a_bucket_that_could_never_issue_a_request_is_rejected(rate, capacity):
    with pytest.raises(ValueError):
        TokenBucket(rate=rate, capacity=capacity)


def test_concurrent_takers_all_get_through_exactly_once():
    """Under real threads, with the clock never advancing, the budget still
    hands out precisely `capacity` tokens without deadlocking."""
    bucket = TokenBucket(rate=1000, capacity=20)
    waits: list[float] = []
    lock = threading.Lock()

    def worker() -> None:
        delay = bucket.take(sleep=lambda _: None)
        with lock:
            waits.append(delay)

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(waits) == 20
    assert all(wait == 0.0 for wait in waits)


def test_the_context_manager_spends_one_token():
    clock = FakeClock()
    bucket = TokenBucket(rate=10, capacity=3, now=clock)
    with bucket:
        pass
    assert bucket.tokens() == pytest.approx(2)
