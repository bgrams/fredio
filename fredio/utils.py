import asyncio
import logging
import re
import sys
from typing import Generator, Set, Tuple

# Main thread event loop
loop = asyncio.get_event_loop()


class KeyMaskFormatter(logging.Formatter):
    """
    Formatter that removes sensitive information in urls.
    """

    apikey_re = re.compile(r'(?<=api_key=)([\w])+(?=[^\w]?)')

    def _filter(self, record):
        return self.apikey_re.sub("<masked>", record)

    def format(self, record):
        original = super(KeyMaskFormatter, self).format(record)
        return self._filter(original)


def generate_offsets(count: int, limit: int, offset: int) -> Generator[Tuple[int, int, int], None, None]:
    """
    Generator yielding new offsets
    """
    while offset + limit < count:
        offset += limit
        yield count, limit, offset


def get_all_tasks() -> Set[asyncio.Task]:
    """
    Get all tasks from main event loop
    """
    if sys.version_info < (3, 7, 0):
        return asyncio.Task.all_tasks(loop=loop)
    else:
        return asyncio.all_tasks(loop=loop)
