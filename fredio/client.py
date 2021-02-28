import logging
import urllib
from copy import copy
from typing import Any, Dict, List

from aiohttp.typedefs import StrOrURL
from pandas import DataFrame, concat
from yarl import URL

from fredio.const import FRED_API_URL, FRED_DOC_URL, FRED_API_ENDPOINTS
from fredio.session import Session
from fredio import utils


logger = logging.getLogger(__name__)


class ApiClient(object):
    """
    Structure containing a top level URL and child endpoints
    """

    _children: Dict[str, "ApiClient"]  # TODO: get rid of mutability
    _query: Dict[Any, Any] = dict()
    _session: Session = None

    def __init__(self, url: StrOrURL):
        super(ApiClient, self).__init__()

        self._children = dict()
        self._url = URL(url, encoded=True)

    def __call__(self, **params) -> "ApiClient":
        """
        Return a new client object with updated query params
        """
        obj = copy(self)
        obj._query = {**self._query, **params}
        return obj

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
        return f'{self.__class__.__name__}<{self.url}>'

    @classmethod
    def set_defaults(cls, **params):
        """
        Set default query parameters for all endpoints
        """
        cls._query.update(params)
        return cls

    @classmethod
    def set_session(cls, session):
        cls._session = session
        return cls

    @classmethod
    def close_session(cls):
        return utils.loop.run_until_complete(cls._session.close())

    @property
    def children(self):
        return self._children

    @property
    def docs(self):
        return _ApiDocs(self._url)

    @property
    def url(self):
        """
        Combine URL and query
        """

        # safe_chars is hard-coded as these chars are used for tag requests etc
        query = urllib.parse.urlencode(self._query, safe=",;")
        return self._url.with_query(query)

    def get(self, **kwargs) -> List[Dict]:
        """
        Get request results as a list. This method is blocking.
        """
        coro = self._session.get(self.url, **kwargs)
        return utils.loop.run_until_complete(coro)

    def get_pandas(self, **kwargs) -> DataFrame:
        """
        Get request results as a DataFrame. This method is blocking.
        """
        return concat(map(DataFrame, self.get(**kwargs)))


class _ApiDocs:
    import webbrowser

    def __init__(self, url):
        self.url = url

    def make_url(self):
        subpath = (self.url.path
                   .replace("/fred", "")
                   .lstrip("/")
                   .replace("/", "_"))
        if subpath:
            subpath += ".html"
        return URL(FRED_DOC_URL) / subpath

    def open(self):
        return self.webbrowser.open(str(self.make_url()))

    def open_new(self):
        return self.webbrowser.open_new(str(self.make_url()))

    def open_new_tab(self):
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


Client = ApiClient(FRED_API_URL)
add_endpoints(Client, *FRED_API_ENDPOINTS)
