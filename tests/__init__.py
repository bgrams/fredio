import logging
import os

from fredio import utils

loglevel = os.environ.get("FREDIO_TESTING_LOG_LEVEL", "CRITICAL")

logging.basicConfig(
    level=logging.getLevelName(loglevel.upper()),
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s"
)


def async_test(fn):
    def tester(*args, **kwargs):
        utils.loop.run_until_complete(fn(*args, **kwargs))
    return tester
