__all__ = ["Session"]

import asyncio
import logging
from typing import List, Dict

import jsonpath_rw
from aiohttp import ClientSession
from aiohttp.helpers import reify  # TODO: use something else to avoid class cache
from yarl import URL

from fredio import events
from fredio import locks
from fredio.utils import generate_offsets


logger = logging.getLogger(__name__)


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
                      **kwargs) -> dict:
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

        raise RuntimeError("Client retries exceeded for url %s" % url)

    async def get(self,
                  url: URL,
                  jsonpath: str = None,
                  retries: int = 3,
                  **parameters) -> List[List[Dict]]:
        """
        Will await a single request to get the first batch of data before executing subsequent
        requests (if required) according to offset logic. Jsonpath query is optionally executed
        on json response data from each request
        """

        newurl = URL(url)
        if parameters:
            newurl = newurl.update_query(**parameters)

        init_response = await self.request("GET", newurl, retries=retries)

        results = [init_response]

        ir_count = init_response.get("count")
        ir_limit = init_response.get("limit")
        ir_offset = init_response.get("offset")

        logger.debug("Count: %s, Limit: %s, Offset: %s" % (ir_count, ir_limit, ir_offset))

        if any((ir_count, ir_limit, ir_offset)):

            coros = [
                self.request("GET", newurl.update_query(offset=offset), retries=retries)
                for _, _, offset in generate_offsets(ir_count, ir_limit, ir_offset)
            ]

            logger.debug("Planning %s additional requests" % len(coros))
            results.extend(await asyncio.gather(*coros))

        if jsonpath:
            jparsed = jsonpath_rw.parse(jsonpath)
            return list(map(lambda x: [i.value for i in jparsed.find(x)], results))
        return results

    @reify
    def session(self):
        return self._session_cls(**self._session_kws)

    def close(self):
        return self.session.close()
