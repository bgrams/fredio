__all__ = ["KeyMaskingFormatter", "get_all_tasks"]

import asyncio
import logging
import re
import sys
from typing import Set

logger = logging.getLogger(__name__)

# Main event loop
loop = asyncio.get_event_loop()


class KeyMaskingFormatter(logging.Formatter):
    """
    Formatter that removes sensitive information in urls.
    """

    apikey_re = re.compile(r'(?<=api_key=)([\w])+(?=[^\w]?)')

    def _filter(self, record):
        return self.apikey_re.sub("<masked>", record)

    def format(self, record):
        original = super(KeyMaskingFormatter, self).format(record)
        return self._filter(original)


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
            logger.info("Cancelling task %s" % task)
            task.cancel()
