__all__ = ["ApiClient", "add_endpoints", "get_endpoints"]

import asyncio
import logging
import urllib
from typing import Any, Dict, List, Type

from aiohttp.typedefs import StrOrURL
from pandas import DataFrame, concat
from yarl import URL

from fredio.const import FRED_DOC_URL
from fredio.session import Session
from fredio import utils


logger = logging.getLogger(__name__)


class ApiClient(object):
    """
    Structure containing a top level URL and child endpoints
    """

    _children: Dict[str, "ApiClient"]  # TODO: get rid of mutability
    _defaults: Dict[Any, Any] = dict()
    _session: Session = None

    def __init__(self, url: StrOrURL):
        super(ApiClient, self).__init__()

        self._children = dict()
        self._url = URL(url, encoded=True)

    def __getattribute__(self, item: Any) -> Any:
        """
        Hijack to allow for indexing using dot notation
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
        """
        cls._defaults = params
        return cls

    @classmethod
    def set_session(cls, session) -> Type["ApiClient"]:
        """
        Set the ClientSession for this class
        """
        cls._session = session
        return cls

    @classmethod
    def close_session(cls):
        """
        Close the client session
        """
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
        Combine URL and query
        """
        return self._encode_url()

    def aget(self, **kwargs) -> asyncio.Task:
        """
        Create an awaitable Task
        """
        coro = self._session.get(self.url, **kwargs)
        task = utils.loop.create_task(coro)
        return task

    def get(self, **kwargs) -> List[Dict]:
        """
        Get request results as a list. This method is blocking.
        """
        return utils.loop.run_until_complete(self.aget(**kwargs))

    def get_pandas(self, **kwargs) -> DataFrame:
        """
        Get request results as a DataFrame. This method is blocking.
        """
        return concat(map(DataFrame, self.get(**kwargs)))


class _ApiDocs:
    import webbrowser

    def __init__(self, url):
        self.url = url

    def make_url(self) -> URL:
        subpath = (self.url.path
                   .replace("/fred", "")
                   .lstrip("/")
                   .replace("/", "_"))
        if subpath:
            subpath += ".html"
        return URL(FRED_DOC_URL) / subpath

    def open(self) -> bool:
        return self.webbrowser.open(str(self.make_url()))

    def open_new(self) -> bool:
        return self.webbrowser.open_new(str(self.make_url()))

    def open_new_tab(self) -> bool:
        return self.webbrowser.open_new_tab(str(self.make_url()))


def add_endpoints(client: ApiClient, *endpoints) -> None:
    """
    Add an endpoint to the tree
    """
    for ep in endpoints:
        parent, *child = ep.split("/", 1)
        newpath = client.children.setdefault(parent, ApiClient(client.url / parent))
        if len(child):
            add_endpoints(newpath, child[0])


def get_endpoints(client: ApiClient) -> List[str]:
    """
    Get all endpoints from the tree
    """
    endpoints = []
    for node in client.children.values():
        if isinstance(node, ApiClient):
            endpoints.extend(get_endpoints(node))
    endpoints.append(client.url)
    return endpoints
