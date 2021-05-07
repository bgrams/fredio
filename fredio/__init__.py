__all__ = ["configure", "shutdown", "client", "events"]

import atexit
from typing import Optional

from . import client, events, locks, utils


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
        locks.set_rate_limit(rate_limit)

    if enable_events:
        events.listen()

    return client_


def shutdown():
    """
    Shutdown this fredio appilication. In order:
    1. Cancel events consumer
       - This will block until all Tasks spawned by the consumer process
         have completed
    2. Stop the rate limiter
    3. Close the aiohttp client session
    """
    # Flush all events and cancel
    utils.loop.run_until_complete(events.cancel())

    # Cancel other tasks (ratelimiter & others)
    locks.get_rate_limiter().stop()


atexit.register(shutdown)
