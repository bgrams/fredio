__all__ = ["get_all_tasks"]

import asyncio
import functools
import inspect
import logging
import sys
from typing import Awaitable, Callable, Set

logger = logging.getLogger(__name__)

# Main event loop
loop = asyncio.get_event_loop()


def get_all_tasks() -> Set[asyncio.Task]:
    """
    Get all tasks from main event loop
    """
    if sys.version_info < (3, 7, 0):
        return asyncio.Task.all_tasks(loop=loop)
    else:
        return asyncio.all_tasks(loop=loop)


def cancel_running_tasks() -> None:
    """
    Cancel all running tasks in this loop
    """
    for task in get_all_tasks():
        if not task.done():
            logger.debug("Cancelling task %s" % task)
            task.cancel()


def coroutine(fn: Callable) -> Callable[..., Awaitable]:
    """
    Ensure that a given function is a coroutine.

    This is a simple replacement for the deprecated asyncio.coroutine
    which is a no-op for an async function, and will wrap a sync function
    within a coroutine.

    :param fn: Callable function
    """
    if inspect.iscoroutinefunction(fn):
        return fn

    @functools.wraps(fn)
    async def wrapped(*args, **kwargs):
        return fn(*args, **kwargs)

    return wrapped
