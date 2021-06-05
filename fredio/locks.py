__all__ = ["RateLimiter"]

import abc
import asyncio
import logging
import math
import time
from typing import Any, Optional
from typing_extensions import Protocol

from . import const
from . import utils

logger = logging.getLogger(__name__)


class Timer(abc.ABC):
    """
    Abstract timer class
    """
    @abc.abstractmethod
    def time(self) -> float: ...


class SystemTimer(Timer):
    """
    System timer. Wraps time.time()
    """
    def time(self):
        return time.time()


class MonotonicTimer(Timer):
    """
    Monotonic timer.

    Wraps time.monotonic(), but with a time offset defined on instantiation.
    This offset is used to define a point of reference such that it behaves
    similarly to system time but is not affected by clock synchronization.
    """
    def __init__(self):
        self._deltat = time.time() - time.monotonic()

    def time(self):
        return time.monotonic() + self._deltat


class AsyncLock(Protocol):

    @abc.abstractmethod
    async def acquire(self) -> Any: ...

    @abc.abstractmethod
    def release(self) -> Any: ...


class RateLimiter(object):
    """
    Rate-limiting implementation using a BoundedSemaphore.
    Locks are released after the current period has passed.
    """

    def __init__(self,
                 limit: int = const.FRED_API_RATE_LIMIT,
                 period: int = const.FRED_API_RATE_RESET,
                 *,
                 timer: Timer = MonotonicTimer(),
                 lock: Optional[AsyncLock] = None,
                 loop: asyncio.AbstractEventLoop = utils.loop):

        self._lock = lock or asyncio.BoundedSemaphore(limit, loop=loop)
        self._period = period
        self._timer = timer

    async def acquire(self) -> None:
        """
        Acquire a lock
        """
        await self._lock.acquire()

    def release(self) -> None:
        """
        Schedule a lock to be released in the next counter
        """
        ts, ct = self._timer.time(), self.get_counter()

        def done_cb(_):
            logger.debug("Released lock from counter %d (elapsed %.4f)"
                         % (ct, self._timer.time() - ts))
            self._lock.release()

        backoff = self.get_backoff(False)
        sleeper: asyncio.Future = asyncio.ensure_future(asyncio.sleep(backoff))
        sleeper.add_done_callback(done_cb)

    async def __aenter__(self) -> None:
        await self.acquire()

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        self.release()

    def get_backoff(self, ceil: bool = True, reltime: Optional[float] = None) -> float:
        """
        Get number of seconds until the next count

        :param ceil: Round backoff time up to the closest second
        :param reltime: Relative time
        """
        reltime = reltime or self._timer.time()
        backoff = self._period - reltime % self._period

        if ceil:
            return float(math.ceil(backoff))
        return backoff

    def get_counter(self) -> int:
        """
        Get number of periods since timer start
        """
        return int(self._timer.time() // self._period)
