import logging
import os

loglevel = os.environ.get("FREDIO_TESTING_LOG_LEVEL", "ERROR")

logging.basicConfig(
    level=logging.getLevelName(loglevel.upper()),
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s"
)
