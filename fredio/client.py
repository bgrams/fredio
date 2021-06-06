__all__ = ["ApiClient", "get_api_key", "get_client"]

import asyncio
import itertools
import logging
import os
import webbrowser
from datetime import datetime
from typing import Optional, Type, TYPE_CHECKING

from aiohttp import ClientSession, ClientResponse, ClientResponseError
from yarl import URL

from . import const
from . import events
from . import locks
from . import utils

if TYPE_CHECKING:
    from pandas import DataFrame


logger = logging.getLogger(__name__)


class ApiClient(object):
    """
    Lazy sync wrapper around aiohttp.ClientSession, also containing
    Endpoint objects that provide attribute access to URL subpaths.
    """
    ratelimiter: locks.RateLimiter = locks.RateLimiter()

    def __new__(cls, *args, **kwargs):
        """
        Intercept to add Endpoint attributes to the instance at runtime
        """

        instance = super().__new__(cls)

        def setdefault(obj, key, value):

            if not hasattr(obj, key):
                setattr(obj, key, value)
                return value
            else:
                return getattr(obj, key)

        for ep in const.FRED_API_ENDPOINTS:

            iterobj = instance
            for s in ep.split("/"):
                iterobj = setdefault(iterobj, s, Endpoint(instance, ep))

        return instance

    def __init__(self,
                 api_key: str,
                 *,
                 session_cls: Type[ClientSession] = ClientSession,
                 **session_kws):
        """
        :param api_key: FRED API key
        :param session_kws: Keyword arguments passed to ClientSession
        """

        # Default HTTP parameters
        defaults = {"api_key": api_key, "file_type": "json"}

        self._defaults = frozenset(defaults.items())

        # Lazy instantiation to be called within an async function
        # ClientSession is cached
        self._session_cls = session_cls
        self._session_kws = frozenset(session_kws.items())
        self._session: Optional[ClientSession] = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    @property
    def defaults(self):
        return self._defaults

    @property
    def session(self) -> ClientSession:
        self.start()
        return self._session  # type: ignore

    @classmethod
    def set_rate_limit(cls, limit: int = const.FRED_API_RATE_LIMIT):
        cls.ratelimiter = locks.RateLimiter(limit=limit)

    def start(self) -> None:
        """
        Initialize and cache the ClientSession instance
        """
        if self._session is None:
            logger.debug("Initializing %s" % self._session_cls.__name__)
            self._session = self._session_cls(**dict(self._session_kws))  # type: ignore

    def close(self) -> None:
        """
        Close the ClientSession instance
        """
        if self._session is not None:
            logger.debug("Closing %s" % self._session_cls.__name__)
            utils.loop.run_until_complete(self._session.close())

            self._session = None

    async def _handle_exception(self,
                                response: ClientResponse,
                                exc: ClientResponseError) -> None:
        if exc.status == 429:
            hdr_time = datetime.strptime(
                response.headers["Date"],
                const.HEADER_DATE_FMT
            )

            backoff = self.ratelimiter.get_backoff(reltime=hdr_time.timestamp())

            logger.debug("Retrying request in %.2f seconds" % backoff)
            await asyncio.sleep(backoff)
        else:
            raise exc

    async def request(self,
                      method: str,
                      url: URL,
                      retries: int = 0) -> ClientResponse:
        """
        Wraps ClientSession.request() with rate limiting and handles retry logic

        :param method: Request method
        :param url: URL
        :param retries: Maximum number of request retries
        """

        while retries >= 0:
            async with self.ratelimiter:
                async with self.session.request(method, url) as response:
                    logger.debug("%s %s" % (method, url))
                    try:
                        response.raise_for_status()

                        # Read response data from the open connection before emitting an event
                        # This can cause a race condition on the response buffer (or something)
                        await response.read()

                        # Emit a response event with name corresponding to the final endpoint
                        if events.running():
                            name = response.url.path.split("/")[-1]
                            await events.produce(name, response)

                        return response

                    except ClientResponseError as e:
                        logging.error(e)
                        retries -= 1
                        if retries >= 0:
                            await self._handle_exception(response, e)
                        else:
                            raise

        return  # type: ignore

    async def get(self, url: URL, retries: int = 0) -> utils.JSON_T:
        """
        Will await a single request to get the first batch of data before executing
        subsequent requests (if required) according to offset logic.

        :param url: URL
        :param retries: Retry count, passed to Session.request
        """

        # Helper
        async def json(_url):
            response = await self.request(url=_url, method="GET", retries=retries)
            return await response.json()

        results = [await json(url)]

        count = results[0].get("count")
        limit = results[0].get("limit")
        offset = results[0].get("offset", 0)

        if count or limit:
            coros = list(map(
                lambda x: json(url.update_query(offset=x)),  # type: ignore
                range(limit + offset, count, limit)
            ))

            logger.debug(
                "Planning %s additional requests (count: %d limit: %d offset: %d)"
                % (len(coros), count, limit, offset)
            )

            results.extend(await asyncio.gather(*coros))

        return results


class _ApiDocs:
    """
    Helper class containing webbrowser.open methods to open FRED documentation
    corresponding to an ApiClient URL
    """

    def __init__(self, url):
        self.url = url

    def _make_url(self) -> URL:
        subpath = self.url.path.replace("/fred", "").lstrip("/").replace("/", "_")

        if subpath:
            subpath += ".html"

        return URL(const.FRED_DOC_URL) / subpath  # type: ignore

    def open(self) -> bool:
        return webbrowser.open(str(self._make_url()))

    def open_new(self) -> bool:
        return webbrowser.open_new(str(self._make_url()))

    def open_new_tab(self) -> bool:
        return webbrowser.open_new_tab(str(self._make_url()))

    open.__doc__ = webbrowser.open.__doc__
    open_new.__doc__ = webbrowser.open_new.__doc__
    open_new_tab.__doc__ = webbrowser.open_new_tab.__doc__


class Endpoint(object):
    """
    Combines the high-level API client with endpoint URLs, URL encoding logic,
    and getter methods.
    """

    base_url: URL = URL(const.FRED_API_URL, encoded=True)

    def __init__(self, client: ApiClient, path: str):
        self.client = client
        self.path = path

    @property
    def docs(self) -> _ApiDocs:
        return _ApiDocs(self.url)

    @property
    def url(self) -> URL:
        """
        Encode this client's URL with client default query parameters
        """
        suburl = self.base_url / self.path
        return suburl.with_query(**dict(self.client.defaults))  # type: ignore

    async def aget(self,
                   jsonpath: Optional[str] = None,
                   retries: int = 3,
                   engine: utils.AbstractQueryEngine = utils.JsonpathEngine(),
                   **params) -> utils.JSON_T:
        """Get request results as a list of JSON

        :param jsonpath: Optional jsonpath to query json results
        :param retries: Number of request retries before raising an exeption. Currently only
        applies to ClientResponseError with status 429.
        :param engine: Query engine used to execute jsonpath query
        :param params: HTTP request parameters
        """

        url = self.url.update_query(params)
        res = await self.client.get(url, retries)

        if jsonpath:
            mapped = map(engine.compile(jsonpath).execute, res)  # type: ignore
            return list(itertools.chain.from_iterable(mapped))  # type: ignore
        return res

    @utils.sharedoc(aget)
    def get(self, **kwargs) -> utils.JSON_T:
        return utils.loop.run_until_complete(self.aget(**kwargs))

    @utils.sharedoc(aget, short="Get request results as a pandas DataFrame\n")
    def get_pandas(self, **kwargs) -> "DataFrame":
        from pandas import DataFrame

        return DataFrame.from_records(self.get(**kwargs))


def get_api_key() -> Optional[str]:
    """
    Get API key from FRED_API_KEY environment variable
    """
    return os.environ.get("FRED_API_KEY", None)


def get_client(api_key: Optional[str] = None, **session_kws) -> ApiClient:
    """
    Wrapper around ApiClient constructor

    :param api_key: Optional FRED API key. Retrieved from env FRED_API_KEY if not set.
    :param session_kws: Keyword arguments passed to the ClientSession constructor.
    """
    api_key = api_key or get_api_key()

    if api_key is None:
        msg = "Api key must be provided or passed as environment variable FRED_API_KEY"
        raise ValueError(msg)

    return ApiClient(api_key=api_key, **session_kws)
