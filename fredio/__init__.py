__all__ = ["configure", "shutdown", "client", "events"]

import atexit
from typing import Optional

from . import client, const, events, locks, session, utils


def configure(api_key: Optional[str] = None,
              rate_limit: Optional[int] = None,
              enable_events: bool = False,
              **session_kwargs) -> client.ApiClient:
    f"""
    Configure this fredio application
    
    :param api_key: FRED API key. If None, will be retrived from environment 
    variable FRED_API_KEY
    :param rate_limit: API rate limit. Must be <= {const.FRED_API_RATE_LIMIT}.
    :param enable_events: Should fredio events be enabled?
    :param session_kwargs: Keyword arguments passed to aiohttp.ClientSession
    """

    api_key = api_key or client.get_api_key()

    if api_key is None:
        msg = "Api key must be provided or passed as environment variable FRED_API_KEY"
        raise ValueError(msg)

    shutdown()

    ses = session.Session(**session_kwargs)

    client_ = client.get_client()
    client_.set_session(ses)
    client_.set_defaults(api_key=api_key, file_type="json")

    if rate_limit is not None:
        locks.set_rate_limit(rate_limit)

    if enable_events:
        events.listen()

    return client_


def shutdown():
    """
    Shutdown this fredio appilication. Cancels all running tasks in this event
    loop and closes the aiothttp.ClientSession
    """
    utils.cancel_running_tasks()
    client.get_client().close_session()


atexit.register(shutdown)
