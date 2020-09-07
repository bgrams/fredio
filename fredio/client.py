import asyncio
import logging
import math
import urllib
import re
import time
import webbrowser
from copy import deepcopy

import aiohttp
import jsonpath_rw
import pandas as pd

from aiohttp.client_exceptions import ClientError


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


def generate_offsets(count: int, limit: int, offset: int):
    """
    Generator yielding new offsets 
    """
    while offset + limit < count:
        offset += limit
        yield count, limit, offset


def get_backoff():
    """
    Get number of seconds (ceiling) until the server-side rate limiter resets
    """
    return math.ceil(FRED_API_RATE_RESET - time.time() % 60)


# TODO: This works decently for bursts of requests related to a single logical GET
# that spans >120 offsets however handling resets for many subsequent requests is a 
# bit... not working. A better approach likely involves threading and/or task queues.

class RateLimiter(asyncio.Semaphore):

    async def acquire(self):
        if self.locked():
            backoff = get_backoff()
            logging.debug("Rate limiter exhausted. Resetting in %s seconds" % backoff)
            await asyncio.sleep(backoff)
        return await super().acquire()


ratelimiter = RateLimiter(FRED_API_RATE_LIMIT)


def prepare_url(url: str, parameters: dict = None, safe_chars: str = ",;"):
    """
    Encode a url with parameters
    """

    if parameters is not None:
        parameters = dict(parameters)
        return url + "?" + urllib.parse.urlencode(parameters, safe=safe_chars)
    return url


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

            logging.debug("%s %s" % (method, req_url))
            async with session.request(method, req_url) as response:
                try:
                    response.raise_for_status()
                    return await response.json()
                except ClientError as e:
                    logging.error(e)

                    errors += 1
                    if errors > retries:
                        raise
                    
                    if response.status == 429:
                        backoff = get_backoff()
                        logging.debug("Retrying request in %s seconds" % backoff)
                        await asyncio.sleep(backoff)
                    else:
                        raise


class ApiTree(dict):
    """
    Tree-based kv structure containing a top level API domain and related endpoints
    """

    def __init__(self, url: str, *endpoints):
        self.url = url.rstrip("/")
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
            parent, *child = ep.split("/", 1)
            newpath = self.setdefault(parent, ApiTree(self.url + '/' + parent))
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
            return super().__getattribute__(name)
        except AttributeError:
            if name not in self._apitree.keys():
                raise

            new = self.copy()
            new._apitree = self._apitree[name]
            return new

    def copy(self):
        """
        Copy
        """
        new = AsyncClient(self._api_key)
        new._apitree = deepcopy(self._apitree)
        return new

    async def get_async(self, jsonpath: jsonpath_rw.jsonpath.JSONPath = None, **parameters) -> list:
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
        webbrowser.open_new_tab(docurl)
    
    @property
    def docs(self):
        return self.open_documentation
