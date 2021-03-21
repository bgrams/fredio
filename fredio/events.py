__all__ = [
    "Event", "produce", "consume", "listen",
    "running", "register", "on_event"
]

import asyncio
import logging
from typing import Any, Awaitable, Callable, Dict, Optional, Union

from . import utils


logger = logging.getLogger(__name__)

queue = asyncio.Queue()

_events: Dict[str, "Event"] = dict()  # TODO: This may need a lock
_task: Optional[asyncio.Task] = None


class Event(object):

    def __init__(self, name: str):
        self.name = name

        self._handlers = []
        self._frozen = False

    def add(self, handler: Callable) -> None:
        """
        Add a handler to this event. Sync functions will be wrapped as
        a coroutine.

        :param handler: Callable function or coroutine
        """
        if self._frozen:
            raise RuntimeError("Cannot modify frozen event")

        self._handlers.append(asyncio.coroutine(handler))
        logger.info("Registered handler '%s' for event '%s'"
                    % (handler.__name__, self.name))

    def freeze(self):
        self._frozen = True

    async def apply(self, *args, **kwargs) -> None:
        """
        Call all event handlers for this event.
        """
        logger.debug("Received event '%s'" % self.name)

        for handler in self._handlers:
            await handler(*args, **kwargs)


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
    Consume an event from the queue, and create a task to call all
    handlers for this event.

    :param q: queue
    """
    name, event = await q.get()
    if name in _events:
        utils.loop.create_task(_events[name].apply(event))
    q.task_done()


def flush(timeout: Optional[Union[float, int]] = None) -> Awaitable:
    """
    Flush all remaining tasks from the queue

    :param timeout: Timeout (seconds) after which TimeoutError will be raised.
    """
    return asyncio.wait_for(queue.join(), timeout)


async def cancel(timeout: Optional[Union[float, int]] = None) -> None:
    """
    Cancel the consumer task. Pending events in the queue will be flushed
    with a timeout.

    :param timeout: Timeout (seconds) after which TimeoutError will be raised.
    """
    global _task

    if running():
        logger.debug("Flushing %d remaining tasks" % queue.qsize())

        try:
            await flush(timeout)
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

        for ev in _events.values():
            ev.freeze()

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

def on_event(name: str) -> Callable:
    """
    Register an event handler

    :param name: Name of the event that this handler should process
    """
    def wrapper(fn):
        register(name, fn)
        return fn
    return wrapper
