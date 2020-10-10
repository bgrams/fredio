import asyncio
import logging
import math
import time
from collections import deque

from .enums import FRED_API_RATE_LIMIT, FRED_API_RATE_RESET


logger = logging.getLogger(__name__)


class RateLimiter(asyncio.BoundedSemaphore):
    """
    Rate-limiting implementation using a BoundedSemaphore to block when all locks
    are acquired. Locks are only released on a specified interval via the `replenish`
    method which runs as a background task.

    Timer options:
    default - time.time
    - This is the most accurate model of what the server-side rate limiter is actually
      doing, although locks can be released prematurely depending on time sync delta
      between the server and the client
    monotonic - time.monotonic
    - Release mechanism will be scheduled according to a monotonic clock that doesn't
      take system time into account. This means that replenishment will not nearly-sync
      with the server, but is guaranteed to prevent premature releases.
    """

    def __init__(self,
                 value: int = FRED_API_RATE_LIMIT,
                 period: int = FRED_API_RATE_RESET,
                 timer: str = "system",
                 *,
                 loop=None):

        super(RateLimiter, self).__init__(value, loop=loop)

        self._period = period
        self._releases = deque()
        self._started = False

        if timer == "system":
            self._timer = time.time
        elif timer == "monotonic":
            self._timer = time.monotonic
        else:
            raise ValueError("Unknown timer option '%s' (choices: 'system', 'monotonic')" % timer)

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
        if not self._started:
            self._loop.create_task(self.replenish())
            self._started = True
        return True

    async def acquire(self) -> bool:
        """
        Acquire a lock
        """
        if not self._started:
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


ratelimiter = RateLimiter()
