__all__ = [
    "Event", "produce", "consume", "listen",
    "running", "register", "coro", "on_event"
]

import asyncio
import inspect
import logging
from functools import wraps
from typing import Any, Awaitable, Callable, Optional, Union

from . import utils

logger = logging.getLogger(__name__)

queue = asyncio.Queue()

_events = dict()  # TODO: This may need a lock
_task: Optional[asyncio.Task] = None


class Event(object):
    def __init__(self, name: str):
        self.name = name
        self.handlers = []

    def add(self, handler: Callable) -> None:
        """
        Add a handler to this event. Sync functions will be wrapped as a coroutine.

        :param handler: Callable function
        """
        self.handlers.append(coro(handler))
        logger.info("Registered handler '%s' for event '%s'" % (handler.__name__, self.name))

    async def apply(self, *args, **kwargs) -> None:
        """
        Call all event handlers for this event
        """
        logger.info("Received event '%s'" % self.name)

        for handler in self.handlers:
            try:
                await utils.loop.create_task(handler(*args, **kwargs))
            except Exception as e:
                logger.exception(e)


async def produce(name: str, data: Any, q: asyncio.Queue = queue) -> None:
    """
    Places a tuple of (name, data) on the queue.

    :param name: name
    :param data: data
    :param q: queue
    """
    return await q.put((name, data))


async def consume(q: asyncio.Queue = queue) -> None:
    """
    Consume an event from the queue, and call all handlers for this event

    :param q: queue
    """
    name, event = await q.get()
    if name in _events:
        await _events[name].apply(event)
    q.task_done()


async def cancel(timeout: Optional[Union[float, int]] = None):
    global _task

    if running():
        try:
            logger.debug("Flushing %d remaining tasks" % queue.qsize())
            await asyncio.wait_for(queue.join(), timeout=timeout)
        except asyncio.TimeoutError as e:
            logger.exception(e)
        finally:
            _task.cancel()
    _task = None


def listen() -> bool:
    """
    Start a background task to consume events
    """
    global _task

    async def _listen() -> None:
        while True:
            await consume(queue)

    if not running():
        logger.info("Listening for events: \n%s" % "\n".join(_events.keys()))
        _task = utils.loop.create_task(_listen())

    return True


def running() -> bool:
    """
    Is the consumer task running?
    """
    if _task is not None:
        return not _task.done()
    return False


def register(name: str, fn: Callable[..., Awaitable]) -> None:
    """
    Register an event handler

    :param name: Name of the event handler
    :param fn:
    """
    _events.setdefault(name, Event(name)).add(fn)


# --- decorators --- #

def coro(fn: Callable[..., Any]) -> Callable[..., Awaitable]:
    """
    Ensures a function is awaitable

    :param fn: Callable. Sync functions will be wrapped as a coroutine, while
    coroutines will be left as-is
    """
    if inspect.iscoroutinefunction(fn):
        return fn

    @wraps(fn)
    async def coro_wrap(*args, **kwargs):
        await asyncio.sleep(0)
        return fn(*args, **kwargs)

    return coro_wrap


def on_event(name: str) -> Callable:
    """
    Register an event handler

    :param name: Name of the event that this handler should process
    """
    def wrapper(fn):
        register(name, fn)
        return fn
    return wrapper
