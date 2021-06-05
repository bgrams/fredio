import asyncio
import unittest

from fredio import locks
from fredio import utils

from tests import async_test


class _TestBase:

    timer: locks.Timer

    period = 0.25
    rate = 2

    @classmethod
    def setUpClass(cls):
        cls.loop = utils.loop

    def setUp(self):
        self.ratelimiter = locks.RateLimiter(self.rate, self.period, timer=self.timer)

    # Since the rate limiting refresh period has been set to 1, we know that the following
    # tests will result in (approximately) 1 and int(timestamp)
    def test_get_rate_limiter_backoff(self):
        backoff = self.ratelimiter.get_backoff()
        self.assertAlmostEqual(backoff, 1)

    def test_get_rate_limiter_counter(self):
        timestamp = self.ratelimiter._timer.time()
        counter = self.ratelimiter.get_counter() * self.period
        self.assertAlmostEqual(int(counter), int(timestamp))

    @async_test
    async def test_acquire_release(self):

        # Test that the value decrements appropriately, but does not yet release
        # until a full `period` has elapsed

        async with self.ratelimiter:
            self.assertEqual(self.ratelimiter._lock._value, self.rate - 1)

        # Make sure the release hasn't happened yet
        self.assertEqual(self.ratelimiter._lock._value, self.rate - 1)

        # Lock should be released after a period has elapsed
        await asyncio.sleep(self.period)

        # Force another context switch to allow for the release to happen now
        await asyncio.sleep(0)

        self.assertEqual(self.ratelimiter._lock._value, self.rate)


class TestSystemRateLimiting(_TestBase, unittest.TestCase):
    timer = locks.SystemTimer()


class TestMonotonicRateLimiting(_TestBase, unittest.TestCase):
    timer = locks.MonotonicTimer()


if __name__ == "__main__":
    unittest.main()
