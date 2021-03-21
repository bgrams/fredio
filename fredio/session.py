__all__ = ["Session"]

import asyncio
import itertools
import logging
from functools import partial
from typing import Any, List, Dict, Optional

import jsonpath_rw
from aiohttp import ClientSession, ClientResponseError
from yarl import URL

from . import events
from . import locks


logger = logging.getLogger(__name__)


class Session(object):
    """
    Async request/response handling with some api-specific logic
    """

    def __init__(self, **kwargs):

        self._session_cls = ClientSession
        self._session_kws = kwargs

        self._session = None

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
        ratelimiter = locks.get_rate_limiter()

        attempts = 0
        while attempts <= retries:
            try:
                async with ratelimiter:
                    async with self.session.request(method, url, **kwargs) as response:

                        # Emit an event with name corresponding to the final endpoint
                        if events.running():
                            name = response.url.path.split("/")[-1]
                            await events.produce(name, response)

                        return await response.json()

            except ClientResponseError as e:
                attempts += 1
                logging.error(e)

                if attempts > retries:
                    raise
                elif e.status == 429:
                    backoff = ratelimiter.get_backoff()
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
        Will await a single request to get the first batch of data before executing
        subsequent requests (if required) according to offset logic. Jsonpath query
        is optionally executed on json response data from each request.

        :param url: yarl URL
        :param jsonpath: Optional jsonpath query to process response data
        :param retries: Retry count, passed to Session.request
        :param parameters: API Request parameters
        """

        if parameters:
            url = url.update_query(**parameters)

        getter = partial(self.request, "GET", retries=retries)

        response = [await getter(url)]

        count = response[0].get("count")
        limit = response[0].get("limit")
        offset = response[0].get("offset")

        logger.debug("Count: %s, Limit: %s, Offset: %s" % (count, limit, offset))

        if any((count, limit, offset)):

            coros = list(map(
                lambda x: getter(url=url.update_query(offset=x)),
                range(limit + offset, count, limit)
            ))

            logger.debug("Planning %s additional requests" % len(coros))
            response.extend(await asyncio.gather(*coros))

        if jsonpath:
            parsed = jsonpath_rw.parse(jsonpath)
            mapped = map(lambda x: [i.value for i in parsed.find(x)], response)
            return list(itertools.chain.from_iterable(mapped))

        return response

    async def close(self) -> None:
        """
        Close the ClientSession
        """
        await self.session.close()
        self._session = None
