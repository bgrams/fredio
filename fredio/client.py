import logging
import urllib
from copy import copy
from typing import Any, Dict, List

from aiohttp.typedefs import StrOrURL
from yarl import URL

from fredio.const import FRED_API_URL, FRED_API_ENDPOINTS


logger = logging.getLogger(__name__)


class ApiClient(dict):
    """
    Structure containing a top level URL and child endpoints
    """

    _query: Dict[Any, Any] = dict()

    def __init__(self, url: StrOrURL):
        super(ApiClient, self).__init__()

        self.url = URL(url, encoded=True)

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
            if item not in self:
                raise
            return self[item]

    def __repr__(self):  # pragma: no-cover
        return f'{self.__class__.__name__}<{self.url}>'

    @classmethod
    def set_defaults(cls, **params) -> None:
        """
        Set default query parameters for all endpoints
        """
        cls._query.update(params)

    def encode_url(self, safe_chars: str = ",;") -> URL:
        """
        Encode URL. Safe chars are not encoded.
        """
        query = urllib.parse.urlencode(self._query, safe=safe_chars)
        return self.url.with_query(query)


def add_endpoints(tree: ApiClient, *endpoints) -> None:
    """
    Add an endpoint to the tree
    """
    for ep in endpoints:
        parent, *child = ep.split("/", 1)
        newpath = tree.setdefault(parent, ApiClient(tree.url / parent))
        if len(child):
            add_endpoints(newpath, child[0])


def get_endpoints(tree: ApiClient) -> List[str]:
    """
    Get all endpoints from the tree
    """
    endpoints = []
    for node in tree.values():
        if isinstance(node, ApiClient):
            endpoints.extend(get_endpoints(node))
    endpoints.append(tree.url)
    return endpoints


client = ApiClient(FRED_API_URL)
add_endpoints(client, *FRED_API_ENDPOINTS)
