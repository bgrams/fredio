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
    Rate-limiting implementation using a BoundedSemaphore.
    Locks are only released on a specified interval via the `replenish` loop
    which runs as a background task.
    """

    _bound_value: int
    _loop: asyncio.BaseEventLoop

    def __init__(self,
                 limit: int = const.FRED_API_RATE_LIMIT,
                 period: int = const.FRED_API_RATE_RESET,
                 *,
                 loop: asyncio.BaseEventLoop = utils.loop):

        super(RateLimiter, self).__init__(limit, loop=loop)

        # Store the delta between monotonic and system time to define
        # a point of reference
        self._deltat = time.time() - self._loop.time()

        self._period = period
        self._releases = deque()
        self._task = None

    def _timer(self) -> float:
        """
        Monotonic time synced with the system
        """
        return self._loop.time() + self._deltat

    @property
    def started(self) -> bool:
        return self._task is not None

    def get_backoff(self, ceil: bool = True) -> float:
        """
        Get number of seconds until the next count

        :param ceil: Round backoff time up to the closest integer
        """
        backoff = self._period - self._timer() % self._period

        if ceil:
            return float(math.ceil(backoff))
        return backoff

    def get_counter(self) -> int:
        """
        Get number of periods since timer start
        """
        return int(self._timer() // self._period)

    def start(self) -> bool:
        """
        Create background replenishment task. Can be called more than once.
        """
        if not self.started:
            self._task = self._loop.create_task(self.replenish())
        return True

    def stop(self) -> bool:
        """
        Cancel the replenishment task
        """
        if self.started:
            self._task.cancel()
            self._task = None
        return True

    async def acquire(self) -> bool:
        """
        Acquire a lock
        """
        self.start()

        return await super(RateLimiter, self).acquire()

    async def replenish(self) -> None:
        """
        Run a continuous loop to periodically release all locks from the
        previous count.

        https://stackoverflow.com/a/48685838
        """

        while True:
            while self._releases:

                # Peek and compare counters
                # A lock will only be released if scheduled from a previous count
                if self._releases[0][1] <= self.get_counter():

                    ts, ct = self._releases.popleft()
                    super(RateLimiter, self).release()

                    logger.debug("Released lock from counter %d (elapsed: %.4f)"
                                 % (ct, self._timer() - ts))
                else:
                    break

            # Sleep until the next count
            await asyncio.sleep(self.get_backoff(False))

    def release(self) -> None:
        """
        Schedule a lock to be released in the next counter
        """
        self._releases.append((self._timer(), self.get_counter()))


_ratelimiter = RateLimiter()


def get_rate_limiter() -> RateLimiter:
    """
    Get the global ratelimiter
    """
    return _ratelimiter


def set_rate_limit(limit: int = const.FRED_API_RATE_LIMIT) -> bool:
    """
    Reset the global ratelimiter with a new limit.

    :param limit: Number of requests per minute. Should be < 120
    """
    if limit > const.FRED_API_RATE_LIMIT:
        raise ValueError("Limit must be <= %d" % const.FRED_API_RATE_LIMIT)

    global _ratelimiter

    _ratelimiter.stop()
    _ratelimiter = RateLimiter(limit)
    _ratelimiter.start()

    return True
