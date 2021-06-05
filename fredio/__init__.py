__all__ = ["configure", "shutdown", "client", "events"]

import atexit
from typing import Optional

from . import client, events, utils


def configure(api_key: Optional[str] = None,
              rate_limit: Optional[int] = None,
              enable_events: bool = False,
              **session_kwargs) -> client.ApiClient:
    """
    Configure this fredio application

    :param api_key: FRED API key. If None, will be retrived from environment
    variable FRED_API_KEY
    :param rate_limit: API rate limit. Must be <= 120.
    :param enable_events: Should fredio events be enabled?
    :param session_kwargs: Keyword arguments passed to aiohttp.ClientSession
    """

    client_ = client.get_client(api_key, **session_kwargs)

    if rate_limit is not None:
        client_.set_rate_limit(rate_limit)

    if enable_events:
        events.listen()

    return client_


def shutdown():
    """
    Shutdown events consumer on exit
    """
    # Flush all events and cancel
    utils.loop.run_until_complete(events.cancel())


atexit.register(shutdown)
