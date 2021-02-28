import asyncio
import inspect
import logging
from functools import wraps
from typing import Any, Callable

from . import utils

logger = logging.getLogger(__name__)

queue = asyncio.Queue()

_events = dict()  # TODO: This may need a lock
_running = False


class Event(object):
    def __init__(self, name: str):
        self.name = name
        self.handlers = []

    def add(self, listener: Callable):
        """
        Add a listener to this event
        """
        self.handlers.append(coro(listener))
        logger.info("Registered handler '%s' for event '%s'" % (listener.__name__, self.name))

    async def apply(self, *args, **kwargs):
        """
        Call all event handlers for this event
        """
        logger.info("Received event '%s'" % self.name)

        for handler in self.handlers:
            try:
                await handler(*args, **kwargs)
            except Exception as e:
                logger.error(e)


async def produce(name: str, data: Any, q: asyncio.Queue = queue):
    """
    Produce an event
    """
    return await q.put((name, data))


async def consume(q: asyncio.Queue = queue):
    """
    Consume an event
    """
    name, event = await q.get()
    if name in _events:
        await _events[name].apply(event)


async def _listen():
    while True:
        await consume(queue)


def listen():
    """
    Start a background task to consume events
    """
    global _running

    if not _running:
        logger.info("Listening for events: \n%s" % "\n".join(_events.keys()))

        utils.loop.create_task(_listen())
        _running = True
    return True


def running():
    return _running


def register(name: str, fn: Callable):
    """
    Register an event handler to globals
    """
    _events.setdefault(name, Event(name)).add(fn)


# --- decorators --- #

def coro(fn: Callable):
    """
    Ensures a function is awaitable
    """

    @wraps(fn)
    async def coro_wrap(*args, **kwargs):
        await asyncio.sleep(0)
        return fn(*args, **kwargs)

    if inspect.iscoroutinefunction(fn):
        return fn
    return coro_wrap


def on_event(name: str):
    """
    Register an event handler to globals
    """
    def wrapper(fn):
        register(name, fn)
        return fn
    return wrapper
