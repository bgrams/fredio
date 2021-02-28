__all__ = ["get_rate_limiter", "set_rate_limit"]

import asyncio
import logging
import math
import time
from collections import deque

from . import const
from . import utils

logger = logging.getLogger(__name__)


class RateLimiter(asyncio.BoundedSemaphore):
    """
    Rate-limiting implementation using a BoundedSemaphore to block when all locks
    are acquired. Locks are only released on a specified interval via the `replenish`
    method which runs as a background task.
    """

    _bound_value: int
    _loop: asyncio.BaseEventLoop

    def __init__(self,
                 value: int = const.FRED_API_RATE_LIMIT,
                 period: int = const.FRED_API_RATE_RESET,
                 *,
                 loop: asyncio.BaseEventLoop = utils.loop):

        super(RateLimiter, self).__init__(value, loop=loop)

        self._period = period
        self._releases = deque()
        self._task = None

        self._timer = time.time

    @property
    def started(self):
        return self._task is not None

    def get_backoff(self) -> int:
        """
        Get number of seconds until the next epoch
        """
        return int(math.ceil(self._period - self._timer() % self._period))

    def get_counter(self) -> int:
        """
        Get number of periods since timer start
        """
        return int(self._timer() // self._period)

    def start(self) -> bool:
        """
        Create background replenishment task. Can be called idempotently.
        """
        if not self.started:
            self._task = self._loop.create_task(self.replenish())
        return True

    def stop(self):
        if self.started:
            self._task.cancel()
        return True

    async def acquire(self) -> bool:
        """
        Acquire a lock
        """
        if not self.started:
            raise RuntimeError("Rate limiter must be started via start()")
        return await super(RateLimiter, self).acquire()

    async def replenish(self):
        """
        Run a continuous loop to periodically release all locks from a previous epoch.

        https://stackoverflow.com/a/48685838
        """
        counter = self.get_counter()

        while True:

            new_counter = self.get_counter()
            if new_counter > counter:

                waiting = self._bound_value - self._value
                logger.debug("Replenishing (epoch: %d waiting: %d)" % (new_counter, waiting))

                while self._releases:

                    # Use comparator to control for a situation where a lock may be acquired
                    # while replenishment is running
                    if new_counter > self._releases[0][1]:
                        super(RateLimiter, self).release()
                        ts, ct = self._releases.popleft()

                        elapsed = self._timer() - ts
                        logger.debug("Released lock from epoch %d (elapsed: %.4f)" % (ct, elapsed))
                    else:
                        break

                counter = new_counter
            await asyncio.sleep(0)

    def release(self):
        """
        Delayed override, releases are periodically handled by `replenish()`
        """
        self._releases.append((self._timer(), self.get_counter()))


_ratelimiter = RateLimiter()


def get_rate_limiter():
    """
    Get the global ratelimiter
    """
    return _ratelimiter


def set_rate_limit(limit: int):
    """
    Reset the global ratelimiter with a new limit.

    Not threadsafe
    """
    if limit > const.FRED_API_RATE_LIMIT:
        raise ValueError("Limit must be <= %d" % const.FRED_API_RATE_LIMIT)

    global _ratelimiter

    _ratelimiter.stop()
    _ratelimiter = RateLimiter(limit)
    _ratelimiter.start()

    return True
