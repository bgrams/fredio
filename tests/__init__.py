import logging
import sys
from fredio.utils import KeyMaskFormatter


LOG_FMT = "%(asctime)s | %(name)s | %(levelname)s | %(message)s"

handler = logging.StreamHandler(sys.stderr)
handler.setFormatter(KeyMaskFormatter(LOG_FMT))

logging.basicConfig(level=logging.DEBUG, handlers=[handler])
