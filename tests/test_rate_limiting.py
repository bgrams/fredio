import asyncio
import sys
import time
import unittest

from fredio.client import RateLimiter

if sys.version_info < (3, 7, 0):
    get_async_tasks = asyncio.Task.all_tasks
else:
    get_async_tasks = asyncio.all_tasks


class TestRateLimiting(unittest.TestCase):

    period = 1
    ratelimiter = None
    rate = 2

    def setUp(self):
        self.loop = asyncio.get_event_loop()
        self.ratelimiter = RateLimiter(self.rate, self.period)

    def test_replenishment_task_exists(self):
        # No other tasks should be running at this point, however in 3.8
        # we can use named tasks to assert that this particular one exists
        # https://docs.python.org/3/library/asyncio-task.html#asyncio.create_task
        self.assertGreaterEqual(len(get_async_tasks(loop=self.loop)), 1)

    # Since the rate limiting refresh period has been set to 1, we know that the following
    # tests will result in (approximately) 1 and int(timestamp)
    def test_get_rate_limiter_backoff(self):
        backoff = self.ratelimiter.get_backoff()
        self.assertAlmostEqual(backoff, 1)

    def test_get_rate_limiter_counter(self):
        timestamp, counter = time.time(), self.ratelimiter.get_counter()
        self.assertAlmostEqual(counter, int(timestamp))

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

    def tearDown(self):
        self.loop.stop()


if __name__ == "__main__":
    unittest.main()
