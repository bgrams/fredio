import asyncio
import logging
import math
import re
import time
import webbrowser
from copy import deepcopy

import aiohttp
import jsonpath_rw
import pandas as pd
from aiohttp.client_exceptions import ClientError

from .utils import generate_offsets, prepare_url


FRED_API_URL = "https://api.stlouisfed.org/fred"
FRED_DOC_URL = "https://fred.stlouisfed.org/docs/api/fred"

FRED_API_ENDPOINTS = (
    "category", "category/children", "category/related", "category/series",
    "category/tags", "category/related_tags", "releases", "releases/dates", 
    "release", "release/dates", "release/series", "release/sources", "release/tags", 
    "release/related_tags", "release/tables", "series", "series/categories",
    "series/observations", "series/release", "series/search", "series/search/tags",
    "series/search/related_tags", "series/tags", "series/updates", "series/vintagedates",
    "sources", "source", "source/releases", "tags", "tags/series", "related_tags"
)

FRED_API_RATE_LIMIT = 120
FRED_API_RATE_RESET = 60
FRED_API_FILE_TYPE = "json"  # other XML option but we dont want that


logger = logging.getLogger(__name__)


class RateLimiter(asyncio.BoundedSemaphore):
    """
    Rate-limiting implementation using a BoundedSemaphore to block when all locks
    are acquired. Locks are only released on a specified interval via the `replenish`
    method which runs as a background task. 

    https://stackoverflow.com/a/48685838
    """

    def __init__(self, value: int = 1, period: int = 1, *, loop=None):
        super(RateLimiter, self).__init__(value, loop=loop)
        self._period = period
        self._loop.create_task(self.replenish())
    
    def get_backoff(self):
        """
        Get number of seconds until the next replenishment
        TODO: Handle clock sync between client and server
        """
        return math.ceil(self._period - time.time() % self._period)
    
    def get_counter(self):
        """
        Get number of periods since the epoch
        """
        return time.time() // self._period

    async def replenish(self):
        """
        Run a continuous loop to periodically release all locks
        """
        counter = self.get_counter()

        while True:
            new_counter = self.get_counter()
            if new_counter > counter:
                logger.debug("Replenishing (n: %d epoch: %d)" % (self._bound_value, new_counter))
                while self._value < self._bound_value:
                    super(RateLimiter, self).release()
                counter = new_counter
            else:
                await asyncio.sleep(1)

    def release(self):
        """
        No-op override, releases are periodically handled by `replenish()`
        """
        pass


ratelimiter = RateLimiter(FRED_API_RATE_LIMIT, FRED_API_RATE_RESET)


async def request_async(session: aiohttp.ClientSession, method: str, url: str, retries: int = 0, **parameters):
    """
    Async sessioned request wrapper with rate limiting (FIXME!!) and retry logic

    :param session: request session instance
    :param method: HTTP method
    :param url: url
    :param retries: number of request retries
    :param parameters: arbitrary HTTP parameters
    """

    req_url = prepare_url(url, parameters)

    errors = 0
    while True:

        async with ratelimiter:

            logger.debug("%s %s" % (method, req_url))
            async with session.request(method, req_url) as response:
                try:
                    response.raise_for_status()
                    return await response.json()
                except ClientError as e:
                    logger.error(e)

                    errors += 1
                    if errors > retries:
                        raise
                    
                    if response.status == 429:
                        backoff = ratelimiter.get_backoff()
                        logger.debug("Retrying request in %s seconds" % backoff)
                        await asyncio.sleep(backoff)
                    else:
                        raise


class ApiTree(dict):
    """
    Tree-based kv structure containing a top level API domain and related endpoints
    """

    def __init__(self, url: str, *endpoints, delimiter: str = "/"):
        self.delimiter = delimiter
        self.url = url.rstrip(self.delimiter)
        self.is_endpoint = False
        self.add_endpoints(*endpoints)

    def __str__(self):
        return str(self.url)
    
    def __repr__(self):
        return f'{self.__class__.__name__} <{self}>'
    
    def add_endpoints(self, *endpoints):
        """
        Add an endpoint to the tree
        """
        for ep in endpoints:
            parent, *child = ep.split(self.delimiter, 1)
            newpath = self.setdefault(parent, ApiTree(self.url + self.delimiter + parent))
            if len(child):
                newpath.add_endpoints(child[0])
            else:
                newpath.is_endpoint = True
    
    def get_endpoints(self) -> list:
        """
        Get all endpoints from the tree
        """
        endpoints = []
        for node in self.values():
            if isinstance(node, ApiTree):
                endpoints.extend(node.get_endpoints())
        if self.is_endpoint:
            endpoints.append(self)
        return list(map(str, endpoints))


apitree = ApiTree(FRED_API_URL, *FRED_API_ENDPOINTS)


class AsyncClient(object):

    def __init__(self, api_key: str):
        self._api_key = api_key
        self._apitree = apitree

    def __getattribute__(self, name: str):
        """
        Hijack to allow for dot notation to access API endpoints
        """
        try:
            return super(AsyncClient, self).__getattribute__(name)
        except AttributeError:
            if name not in self._apitree.keys():
                raise

            new = self.copy()
            new._apitree = new._apitree[name]
            return new

    def copy(self):
        """
        Copy
        """
        new = AsyncClient(self._api_key)
        new._apitree = deepcopy(self._apitree)
        return new

    async def get_async(self, jsonpath: str = None, **parameters) -> list:
        """
        Get data within an asynchronous request session

        Will await a single request to get the first batch of data before executing subsequent
        requests (if required) according to offset logic. Jsonpath query is optionally executed
        on json from each request

        :param jsonpath: jsonpath
        :param parameters: HTTP request parameters
        """

        async with aiohttp.ClientSession() as session:
            
            methparams = {
                "method": "GET",
                "url": str(self._apitree),
                "session": session,
                "retries": 3,  # TODO: parameterize this eventually. Dont want to get too wild for now.
                "api_key": self._api_key,
                "file_type": FRED_API_FILE_TYPE,
                **parameters
            }

            # TODO: Return the response object object instead of json. Headers will allow
            # for better coro planning. This may not be necessary pending enhancements to
            # the client-side rate limiter.
            initial_response = await request_async(**methparams)
            
            response_count = initial_response.get("count")            
            response_limit = initial_response.get("limit")
            response_offset = initial_response.get("offset")

            logger.debug("Count: %s, Limit: %s, Offset: %s" % (response_count, response_limit, response_offset))

            results = [initial_response]

            if (response_count is not None 
                and response_limit is not None 
                and response_offset is not None):
            
                offsets = generate_offsets(response_count, response_limit, response_offset)

                coros = []
                for count, limit, offset in offsets:
                    newparams = dict(methparams)
                    newparams["offset"] = offset
                    coros.append(request_async(**newparams))

                if coros:
                    logger.debug("Planning %s additional requests" % len(coros))
                    results.extend(await asyncio.gather(*coros))

            if jsonpath:
                jparsed = jsonpath_rw.parse(jsonpath)
                return list(map(lambda x: [i.value for i in jparsed.find(x)], results))
            return results

    def get(self, **kwargs) -> list:
        """
        Get request results as a list. This method is blocking.
        """
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(self.get_async(**kwargs))

    def get_pandas(self, **kwargs) -> pd.DataFrame:
        """
        Get request results as a DataFrame. This method is blocking.
        """
        return pd.concat(map(pd.DataFrame, self.get(**kwargs)))

    def open_documentation(self):
        """
        Open official endpoint documentation in the browser
        """
        endpoint = str(self._apitree)

        if endpoint == FRED_API_URL:
            docurl = FRED_DOC_URL
        else:
            groups = re.match(fr"({FRED_API_URL})?/?(.*)", endpoint).groups()
            docurl = f"{FRED_DOC_URL}/{groups[1].replace('/', '_')}.html"
        return webbrowser.open_new_tab(docurl)
    
    @property
    def docs(self):
        return self.open_documentation
