__all__ = ["Session"]

import asyncio
import logging
from typing import Any, Awaitable, List, Dict, Generator, Optional

import jsonpath_rw
from aiohttp import ClientSession
from aiohttp.helpers import reify  # TODO: use something else to avoid class cache
from yarl import URL

from . import events
from . import locks


logger = logging.getLogger(__name__)


def iter_offsets(count: int, limit: int, offset: int) -> Generator[int, None, None]:
    """
    Generator yielding new offsets. The offset is incremented by limit until
    it surpasses count.

    :param count: count
    :param limit: limit
    :param offset: offset
    """
    while offset + limit < count:
        offset += limit
        yield offset


class Session(object):
    """
    Async request/response handling with some api-specific logic
    """

    def __init__(self, **kwargs):

        self._session_cls = ClientSession
        self._session_kws = kwargs

        self._cache = dict()  # for property persistence

    async def request(self,
                      method: str,
                      url: URL,
                      retries: int = 0,
                      **kwargs) -> Dict[Any, Any]:
        """
        Wraps ClientSession.request() with rate limiting and handles retry logic

        :param method: Request method
        :param url: URL
        :param retries: Maximum number of request retries
        :param kwargs: Request parameters
        """
        ratelimiter = locks.get_rate_limiter()
        ratelimiter.start()

        async with ratelimiter:

            attempts = 0
            while attempts <= retries:
                async with self.session.request(method, url, **kwargs) as response:
                    try:
                        response.raise_for_status()
                        data = await response.json()

                        # Emit an event with name corresponding to the final endpoint
                        if events.running():
                            name = response.url.path.split("/")[-1]
                            await events.produce(name, data)  # TODO: is this thread safe?
                        return data
                    except Exception as e:
                        logging.error(e)
                        attempts += 1

                        # TODO: pluggable handling
                        if response.status == 429:
                            backoff = ratelimiter.get_backoff()
                            logger.debug("Retrying request in %d seconds", backoff)
                            await asyncio.sleep(backoff)
                        else:
                            raise

    async def get(self,
                  url: URL,
                  jsonpath: Optional[str] = None,
                  retries: int = 3,
                  **parameters) -> List[List[Dict]]:
        """
        Will await a single request to get the first batch of data before executing subsequent
        requests (if required) according to offset logic. Jsonpath query is optionally executed
        on json response data from each request.

        :param url: yarl URL
        :param jsonpath: Optional jsonpath query to process response data
        :param retries: Retry count, passed to Session.request
        :param parameters: API Request parameters
        """

        if parameters:
            url = url.update_query(**parameters)

        init_response = await self.request("GET", url, retries=retries)

        results = [init_response]

        ir_count = init_response.get("count")
        ir_limit = init_response.get("limit")
        ir_offset = init_response.get("offset")

        logger.debug("Count: %s, Limit: %s, Offset: %s" % (ir_count, ir_limit, ir_offset))

        if any((ir_count, ir_limit, ir_offset)):

            coros = [
                self.request("GET", url.update_query(offset=offset), retries=retries)
                for offset in iter_offsets(ir_count, ir_limit, ir_offset)
            ]

            logger.debug("Planning %s additional requests" % len(coros))
            results.extend(await asyncio.gather(*coros))

        if jsonpath:
            jparsed = jsonpath_rw.parse(jsonpath)
            return list(map(lambda x: [i.value for i in jparsed.find(x)], results))
        return results

    @reify
    def session(self) -> ClientSession:
        """
        Return a ClientSession instance (cached)
        """
        return self._session_cls(**self._session_kws)

    def close(self) -> Awaitable:
        """
        Close the ClientSession
        """
        return self.session.close()
