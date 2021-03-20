__all__ = ["Session"]

import asyncio
import itertools
import logging
from functools import partial
from typing import Any, Awaitable, List, Dict, Generator, Optional

import jsonpath_rw
from aiohttp import ClientSession, ClientResponseError
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

        self._session = None
        self._ratelimiter = locks.get_rate_limiter()

    @property
    def session(self) -> ClientSession:
        """
        Return a ClientSession instance (cached)
        """
        if self._session is None:
            logger.info("Initializing %s" % self._session_cls.__name__)
            self._session = self._session_cls(**self._session_kws)
        return self._session

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
        kwargs.setdefault("raise_for_status", True)

        attempts = 0
        while attempts <= retries:
            try:
                async with self._ratelimiter:
                    async with self.session.request(method, url, **kwargs) as response:

                        attempts += 1

                        # Emit an event with name corresponding to the final endpoint
                        if events.running():
                            name = response.url.path.split("/")[-1]
                            await events.produce(name, response)

                        return await response.json()

            except ClientResponseError as e:
                logging.error(e)

                if e.status == 429:
                    backoff = self._ratelimiter.get_backoff()
                    logger.debug("Retrying request in %d seconds" % backoff)
                    await asyncio.sleep(backoff)
                else:
                    raise

    async def get(self,
                  url: URL,
                  jsonpath: Optional[str] = None,
                  retries: int = 3,
                  **parameters) -> List[Dict]:
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

        ir_count = init_response.get("count")
        ir_limit = init_response.get("limit")
        ir_offset = init_response.get("offset")

        logger.debug("Count: %s, Limit: %s, Offset: %s" % (ir_count, ir_limit, ir_offset))

        results = [init_response]
        if any((ir_count, ir_limit, ir_offset)):

            coros = [
                self.request("GET", url.update_query(offset=offset), retries=retries)
                for offset in iter_offsets(ir_count, ir_limit, ir_offset)
            ]

            logger.debug("Planning %s additional requests" % len(coros))
            results.extend(await asyncio.gather(*coros))

        if jsonpath:
            parsed = jsonpath_rw.parse(jsonpath)
            mapped = map(lambda x: [i.value for i in parsed.find(x)], results)
            return list(itertools.chain.from_iterable(mapped))
        return results

    async def close(self) -> None:
        """
        Close the ClientSession
        """
        await self.session.close()
        self._session = None
