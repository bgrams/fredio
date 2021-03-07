__all__ = ["ApiClient", "get_api_key", "get_client", "get_endpoints"]

import asyncio
import logging
import os
import urllib
import webbrowser
from typing import Any, Dict, List, Optional, Type

from aiohttp.typedefs import StrOrURL
from pandas import DataFrame
from yarl import URL

from . import const
from . import utils
from . import session

logger = logging.getLogger(__name__)


class ApiClient(object):
    """
    Structure containing a top level URL and child endpoints
    """

    _children: Dict[str, "ApiClient"]  # TODO: get rid of mutability
    _defaults: Dict[Any, Any] = dict()  # Default parameters for all client instances
    _session: session.Session = None

    def __init__(self, url: StrOrURL):
        super(ApiClient, self).__init__()

        self._children = dict()
        self._url = URL(url, encoded=True)

    def __getattribute__(self, item: Any) -> Any:
        """
        Hijack to allow for accessing children using dot notation
        """
        try:
            return super(ApiClient, self).__getattribute__(item)
        except AttributeError:
            children = super(ApiClient, self).__getattribute__("_children")
            if item not in children.keys():
                raise
            return children[item]

    def __repr__(self):  # pragma: no-cover
        return f'{self.__class__.__name__}<{self._url}>'

    def _encode_url(self) -> URL:
        """
        Create new URL with default query parameters
        """
        # safe_chars is hard-coded as these chars are used for tag requests etc
        query = urllib.parse.urlencode(self._defaults, safe=",;")
        return self._url.with_query(query)

    @classmethod
    def set_defaults(cls, **params) -> Type["ApiClient"]:
        """
        Set default query parameters for all endpoints

        :param params: Request parameters that will be passed for every request
        for all ApiClient instances
        """
        cls._defaults = params
        return cls

    @classmethod
    def set_session(cls, ses: session.Session) -> Type["ApiClient"]:
        """
        Set the Session for this class

        :param ses: Session used by all ApiClient instances
        """
        cls._session = ses
        return cls

    @classmethod
    def close_session(cls):
        """
        Close the client session
        """
        if cls._session is not None:
            logger.info("Closing client session")
            return utils.loop.run_until_complete(cls._session.close())

    @property
    def children(self) -> Dict[str, "ApiClient"]:
        """
        Get client children
        """
        return self._children

    @property
    def docs(self) -> "_ApiDocs":
        return _ApiDocs(self._url)

    @property
    def url(self) -> URL:
        """
        Encode this client's URL with query parameters
        """
        return self._encode_url()

    def aget(self, **kwargs) -> asyncio.Task:
        """
        Run an awaitable Task to get results from this endpoint

        :param kwargs: Keyword arguments passed to Session.get
        """
        coro = self._session.get(self.url, **kwargs)
        task = utils.loop.create_task(coro)
        return task

    def get(self, **kwargs) -> List[Dict]:
        """
        Get request results as a list of JSON. This method is blocking.

        :param kwargs: Keyword arguments passed to Session.get
        """
        return utils.loop.run_until_complete(self.aget(**kwargs))

    def get_pandas(self, **kwargs) -> DataFrame:
        """
        Get request results as a pandas DataFrame. This method is blocking.

        :param kwargs: Keyword arguments passed to Session.get
        """
        return DataFrame.from_records(self.get(**kwargs))


class _ApiDocs:
    """
    Helper class containing webbrowser.open methods to open FRED documentation
    corresponding to an ApiClient URL
    """

    def __init__(self, url):
        self.url = url

    def make_url(self) -> URL:
        subpath = self.url.path.replace("/fred", "").lstrip("/").replace("/", "_")

        if subpath:
            subpath += ".html"

        return URL(const.FRED_DOC_URL) / subpath

    def open(self) -> bool:
        return webbrowser.open(str(self.make_url()))

    def open_new(self) -> bool:
        return webbrowser.open_new(str(self.make_url()))

    def open_new_tab(self) -> bool:
        return webbrowser.open_new_tab(str(self.make_url()))

    open.__doc__ = webbrowser.open.__doc__
    open_new.__doc__ = webbrowser.open_new.__doc__
    open_new_tab.__doc__ = webbrowser.open_new_tab.__doc__


def get_api_key() -> Optional[str]:
    """
    Get API key from FRED_API_KEY environment variable
    """
    return os.environ.get("FRED_API_KEY", None)


def get_client() -> ApiClient:
    """
    Construct an ApiClient and add FRED endpoints.
    """

    client = ApiClient(const.FRED_API_URL)
    add_endpoints(client, *const.FRED_API_ENDPOINTS)

    return client


def add_endpoints(client: ApiClient, *endpoints) -> None:
    """
    Add an endpoint to the client instance

    :param client: ApiClient
    :param endpoints: URL subpaths to add to the ApiClient structure
    """
    for ep in endpoints:
        parent, *child = ep.split("/", 1)
        newpath = client.children.setdefault(parent, ApiClient(client.url / parent))
        if len(child):
            add_endpoints(newpath, child[0])


def get_endpoints(client: ApiClient) -> List[URL]:
    """
    Get all registered URLs from an ApiClient

    :param client: ApiClient
    """
    endpoints = []
    for node in client.children.values():
        if isinstance(node, ApiClient):
            endpoints.extend(get_endpoints(node))
    endpoints.append(client.url)
    return endpoints
