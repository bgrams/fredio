import atexit
import logging
import os
from typing import Optional

from .events import *
from .locks import *

from . import client, const, session, utils

logger = logging.getLogger("fredio")

_client: Optional[client.ApiClient] = None


def get_api_key():
    return os.environ.get("FRED_API_KEY", None)


def get_client():
    return _client


def configure(api_key: Optional[str] = None,
              rate_limit: int = const.FRED_API_RATE_LIMIT,
              enable_events: bool = False,
              **session_kwargs) -> client.ApiClient:

    global _client

    if _client is not None:
        _client.close_session()

    api_key = api_key or get_api_key()

    if api_key is None:
        msg = "Api key must be provided or passed as environment variable FRED_API_KEY"
        raise ValueError(msg)

    ses = session.Session(**session_kwargs)

    apiclient = client.ApiClient(const.FRED_API_URL)
    apiclient.set_session(ses)
    apiclient.set_defaults(api_key=api_key, file_type="json")

    client.add_endpoints(apiclient, *const.FRED_API_ENDPOINTS)

    set_rate_limit(rate_limit)

    if enable_events:
        events.listen()

    _client = apiclient

    return _client


def shutdown():
    for task in utils.get_all_tasks():
        if not task.done():
            logger.info("Cancelling task %s" % task)
            task.cancel()

    if _client is not None:
        logger.info("Closing client session")
        _client.close_session()


atexit.register(shutdown)
