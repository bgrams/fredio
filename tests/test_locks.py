import asyncio
import unittest
from typing import Type

from fredio import locks
from fredio import utils


class _TestBase:

    timer_t: Type[locks.Timer]

    period = 0.25
    rate = 2

    @classmethod
    def setUpClass(cls):
        cls.loop = utils.loop

    def setUp(self):
        self.ratelimiter = locks.RateLimiter(self.rate, self.period, timer=self.timer_t)
        self.ratelimiter.start()

    def tearDown(self):
        self.ratelimiter.stop()

    def test_replenishment_task_exists(self):
        # No other tasks should be running at this point, however in 3.8
        # we can use named tasks to assert that this particular one exists
        # https://docs.python.org/3/library/asyncio-task.html#asyncio.create_task
        self.assertGreaterEqual(len(utils.get_all_tasks()), 1)

    # Since the rate limiting refresh period has been set to 1, we know that the following
    # tests will result in (approximately) 1 and int(timestamp)
    def test_get_rate_limiter_backoff(self):
        backoff = self.ratelimiter.get_backoff()
        self.assertAlmostEqual(backoff, 1)

    def test_get_rate_limiter_counter(self):
        timestamp = self.ratelimiter._timer.time()
        counter = self.ratelimiter.get_counter() * self.period
        self.assertAlmostEqual(int(counter), int(timestamp))

    def test_acquire_release(self):

        # Test that the value decrements appropriately, but does not yet release
        # until a full `period` has elapsed
        async def acquire_release():
            async with self.ratelimiter:
                self.assertEqual(self.ratelimiter._value, self.rate - 1)

            self.assertEqual(self.ratelimiter._value, self.rate - 1)
            await asyncio.sleep(self.period)
            self.assertEqual(self.ratelimiter._value, self.rate)

        self.loop.run_until_complete(acquire_release())


class TestSystemRateLimiting(_TestBase, unittest.TestCase):
    timer_t = locks.SystemTimer


class TestMonotonicRateLimiting(_TestBase, unittest.TestCase):
    timer_t = locks.MonotonicTimer


if __name__ == "__main__":
    unittest.main()
