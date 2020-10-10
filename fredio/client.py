import asyncio
import logging
from copy import deepcopy
from typing import Dict, List

import jsonpath_rw
import pandas as pd
from aiohttp import ClientSession
from aiohttp.typedefs import StrOrURL

from .locks import ratelimiter
from .utils import generate_offsets, prepare_url
from .enums import (FRED_API_URL,
                    FRED_DOC_URL,
                    FRED_API_FILE_TYPE,
                    FRED_API_ENDPOINTS)


logger = logging.getLogger(__name__)


class ApiTree(dict):
    """
    Tree-based kv structure containing a top level API domain and related endpoints
    """

    def __init__(self, url: str, *endpoints, delimiter: str = "/"):
        self.delimiter = delimiter
        self.url = url.rstrip(self.delimiter)
        self.is_endpoint = False
        self.add_endpoints(*endpoints)

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

    def get_endpoints(self) -> List[str]:
        """
        Get all endpoints from the tree
        """
        endpoints = []
        for node in self.values():
            if isinstance(node, ApiTree):
                endpoints.extend(node.get_endpoints())
        if self.is_endpoint:
            endpoints.append(self.url)
        return endpoints


apitree = ApiTree(FRED_API_URL, *FRED_API_ENDPOINTS)


class AsyncClient(object):

    def __init__(self, api_key: str, **kwargs):
        self._api_key = api_key
        self._apitree = apitree

        self._session_cls = ClientSession
        self._session_kws = kwargs

    def __getattribute__(self, name: str):
        """
        Hijack to allow for dot notation to access API endpoints
        """
        try:
            return super(AsyncClient, self).__getattribute__(name)
        except AttributeError:
            if name not in self._apitree.keys():
                raise

            new = self._copy()
            new._apitree = new._apitree[name]
            return new

    def _copy(self):
        """
        Copy
        """
        new = AsyncClient(self._api_key)
        new._session_cls = self._session_cls
        new._session_kws = dict(self._session_kws)
        new._apitree = deepcopy(self._apitree)
        return new

    def _get_url(self, **kwargs) -> str:
        return prepare_url(
            self._apitree.url,
            api_key=self._api_key,
            file_type=FRED_API_FILE_TYPE,
            **kwargs
        )

    @staticmethod
    async def _request(
                session: ClientSession,
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

    async def get_async(self, jsonpath: str = None, retries: int = 3, **parameters) -> List[Dict]:
        """
        Get data within an asynchronous request session

        Will await a single request to get the first batch of data before executing subsequent
        requests (if required) according to offset logic. Jsonpath query is optionally executed
        on json from each request

        :param jsonpath: jsonpath
        :param parameters: HTTP request parameters
        """

        async with self._session_cls(**self._session_kws) as session:

            init_url = self._get_url(**parameters)
            init_response = await self._request(session, "GET", init_url, retries=retries)

            results = [init_response]

            ir_count = init_response.get("count")
            ir_limit = init_response.get("limit")
            ir_offset = init_response.get("offset")

            logger.debug("Count: %s, Limit: %s, Offset: %s" % (ir_count, ir_limit, ir_offset))

            if any((ir_count, ir_limit, ir_offset)):

                coros = [
                    self._request(session, "GET", self._get_url(offset=offset), retries=retries)
                    for _, _, offset in generate_offsets(ir_count, ir_limit, ir_offset)
                ]

                logger.debug("Planning %s additional requests" % len(coros))
                results.extend(await asyncio.gather(*coros))

        if jsonpath:
            jparsed = jsonpath_rw.parse(jsonpath)
            return list(map(lambda x: [i.value for i in jparsed.find(x)], results))
        return results

    def get(self, **kwargs) -> List[Dict]:
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

    def open_documentation(self) -> bool:
        """
        Open official endpoint documentation in the browser

        Endpoint mapping logic:
        /fred/series/observations -> /fred/series_observations.html
        """
        import webbrowser

        subpath = self._apitree.url.replace(FRED_API_URL, "").replace("/", "_")
        if subpath:
            subpath += ".html"
        return webbrowser.open_new_tab(FRED_DOC_URL + "/" + subpath)

    @property
    def docs(self) -> bool:
        return self.open_documentation
