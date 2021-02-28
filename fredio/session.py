import asyncio
import logging
from typing import List, Dict

import jsonpath_rw
from aiohttp import ClientSession
from aiohttp.typedefs import StrOrURL
from yarl import URL

from fredio.locks import ratelimiter
from fredio.utils import generate_offsets


logger = logging.getLogger(__name__)


class Session(object):

    def __init__(self, **kwargs):

        self._session_cls = ClientSession
        self._session_kws = kwargs

    async def get(self, url: StrOrURL, jsonpath: str = None, retries: int = 3, **parameters) -> List[List[Dict]]:
        """
        Get data within an asynchronous request session

        Will await a single request to get the first batch of data before executing subsequent
        requests (if required) according to offset logic. Jsonpath query is optionally executed
        on json from each request
        """

        async with self._session_cls(**self._session_kws) as session:

            newurl = URL(url)
            if parameters:
                newurl = newurl.update_query(**parameters)
            init_response = await request(session, "GET", newurl, retries=retries)

            results = [init_response]

            ir_count = init_response.get("count")
            ir_limit = init_response.get("limit")
            ir_offset = init_response.get("offset")

            logger.debug("Count: %s, Limit: %s, Offset: %s" % (ir_count, ir_limit, ir_offset))

            if any((ir_count, ir_limit, ir_offset)):

                coros = [
                    request(session, "GET", url.update_query(offset=offset), retries=retries)
                    for _, _, offset in generate_offsets(ir_count, ir_limit, ir_offset)
                ]

                logger.debug("Planning %s additional requests" % len(coros))
                results.extend(await asyncio.gather(*coros))

        if jsonpath:
            jparsed = jsonpath_rw.parse(jsonpath)
            return list(map(lambda x: [i.value for i in jparsed.find(x)], results))
        return results


async def request(session: ClientSession,
                  method: str,
                  str_or_url: StrOrURL,
                  retries: int = 0,
                  **kwargs) -> dict:
    """
    Wraps ClientSession.request() with rate limiting and handles retry logic

    :param session: Open client session
    :param method: Request method
    :param str_or_url: URL
    :param retries: Maximum number of request retries
    :param kwargs: Request parameters
    """

    ratelimiter.start()
    async with ratelimiter:

        attempts = 0
        while attempts <= retries:
            async with session.request(method, str_or_url, **kwargs) as response:
                try:
                    response.raise_for_status()
                    return await response.json()
                except Exception as e:
                    logging.error(e)
                    attempts += 1

                # TODO: pluggable handling
                if response.status == 429:
                    backoff = ratelimiter.get_backoff()
                    logger.debug("Retrying request in %d seconds", backoff)
                    await asyncio.sleep(backoff)

    raise RuntimeError("Client retries exceeded for url %s" % str_or_url)
