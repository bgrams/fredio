__all__ = ["get_all_tasks", "AbstractQueryEngine", "JsonpathEngine"]

import abc
import asyncio
import functools
import inspect
import logging
import re
import sys
from typing import (Any,
                    Awaitable,
                    Callable,
                    Generator,
                    Iterable,
                    List,
                    Mapping,
                    Set,
                    Union)

from jsonpath_rw import parse


JSON_T = Union[List[Mapping[str, Any]], Mapping[str, Any]]


logger = logging.getLogger(__name__)

# Main event loop
loop = asyncio.get_event_loop()


def get_all_tasks() -> Set[asyncio.Task]:
    """
    Get all tasks from main event loop
    """
    if sys.version_info < (3, 7, 0):
        return asyncio.Task.all_tasks(loop=loop)  # type: ignore
    else:
        return asyncio.all_tasks(loop=loop)  # type: ignore


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


def sharedoc(orig, short=None):
    """
    Allow sharing of docstrings across similar functions
    """
    def wrapped(fn):
        doc = orig.__doc__
        if short is not None:
            doc = re.sub(r"^.*\n", short, doc)
        fn.__doc__ = doc
        return fn
    return wrapped


class AbstractQueryEngine(abc.ABC):
    """
    Abstract class to wrap core parsing & execution methods of
    json processing libraries
    """

    def __init__(self):
        self._cache = {}
        self._compiled = None

    @abc.abstractmethod
    def _compile(self, query: str) -> Any: ...

    @abc.abstractmethod
    def _execute(self, data: JSON_T) -> Iterable[Any]: ...

    def compile(self, query: str) -> "AbstractQueryEngine":
        """
        Compile a query string and cache it

        :param query: Json query
        """
        self._compiled = self._cache.setdefault(query, self._compile(query))
        return self

    def execute(self, data: JSON_T) -> Generator[JSON_T, None, None]:
        """
        Execute a compiled query against data, yielding processed items

        :param data: Json data
        """
        assert self._compiled is not None, "No compiled query"
        yield from self._execute(data)


class JsonpathEngine(AbstractQueryEngine):
    """
    Wraps jsonpath_rw library
    """
    def _compile(self, query: str):
        return parse(query)

    def _execute(self, data: JSON_T):
        return [i.value for i in self._compiled.find(data)]
