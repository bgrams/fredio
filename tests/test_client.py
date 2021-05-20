import asyncio
import inspect
import sys
import unittest
from typing import Any, Union
from unittest.mock import MagicMock
from unittest.mock import patch

from aiohttp import ClientResponse, ClientResponseError
from aiohttp.helpers import TimerNoop  # noqa
from pandas import DataFrame
from yarl import URL

from fredio import configure
from fredio import const, locks, utils
from fredio.client import ApiClient, Endpoint, get_client, request  # noqa


def mock_fred_response(method: str,
                       url: URL,
                       count: int = 0,
                       limit: int = 0,
                       offset: int = 0):

    response = ClientResponse(
        method=method,
        url=URL(url),
        request_info=MagicMock(),
        continue100=None,
        writer=MagicMock(),
        session=MagicMock(),
        timer=TimerNoop(),
        traces=[],
        loop=utils.loop
    )

    body = '{"count": %d, "limit": %d, "offset": %d}' % (count, limit, offset)
    response._body = body.encode("utf-8")

    reader = asyncio.Future()
    reader.set_result(response._body)  # noqa

    response.content = MagicMock()
    response.content.read = MagicMock()
    response.content.read.return_value = reader
    response.read = MagicMock()
    response.read.return_value = reader

    response._headers = {"Content-Type": "application/json"}

    # Why
    if sys.version_info < (3, 8):
        future = asyncio.Future()
        future.set_result(response)
        return future

    return response


def async_test(fn):
    def tester(*args, **kwargs):
        coro = fn(*args, **kwargs)
        utils.loop.run_until_complete(coro)
    return tester


class TestApiClient(unittest.TestCase):

    client: ApiClient

    @classmethod
    def setUpClass(cls) -> None:
        cls.client = configure(api_key="foo")
        cls.endpoint = Endpoint(client=cls.client, path="")
        cls.request_url = URL("https://api.stlouisfed.org/fred/?file_type=json&api_key=foo")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.close()

    def tearDown(self) -> None:
        """Reset the rate limiter for each test"""
        locks.set_rate_limit()

    def patchedRequest(self,
                       method: str = "GET",
                       url: Union[str, URL] = None,
                       return_value: Any = None,
                       **kwargs):

        if return_value is None:
            return_value = mock_fred_response(method, url or self.request_url)

        return patch(
            "aiohttp.ClientSession._request",
            return_value=return_value,
            **kwargs
        )

    @async_test
    async def test_request(self):

        ratelim = locks.get_rate_limiter()

        with self.patchedRequest() as req:
            rate_value = ratelim._value
            await request(self.client.session, "GET", self.request_url)

            self.assertEqual(ratelim._value, rate_value - 1)
            self.assertEqual(len(ratelim._releases), 1)

            req.assert_called_once()

    @async_test
    async def test_request_retries(self):

        error400 = ClientResponseError(request_info=MagicMock(), history=MagicMock())
        error429 = ClientResponseError(request_info=MagicMock(), history=MagicMock())

        error400.status = 400
        error429.status = 429

        with patch.object(locks.RateLimiter, "get_backoff", return_value=0):
            with self.patchedRequest(side_effect=error429) as req:
                with self.assertRaises(ClientResponseError):
                    await request(self.client.session, "GET", self.request_url, retries=2)

                self.assertEqual(3, req.call_count)

            with self.patchedRequest(side_effect=error400) as req:
                with self.assertRaises(ClientResponseError):
                    await request(self.client.session, "GET", self.request_url, retries=2)

                self.assertEqual(1, req.call_count)

    @async_test
    async def test_get(self):

        with self.patchedRequest() as req:
            await self.endpoint.aget()
            req.assert_called_once()

    @async_test
    async def test_get_paginated(self):
        response = mock_fred_response("GET", self.request_url, count=2, limit=1)

        with self.patchedRequest(return_value=response) as req:
            await self.endpoint.aget()
            self.assertEqual(2, req.call_count)

    @async_test
    async def test_get_jsonpath(self):

        with self.patchedRequest() as req:
            ret = await self.endpoint.aget(jsonpath="count")
            self.assertEqual(ret, [0])
            req.assert_called_once()

    def test_client_getters(self):

        async def getter(*args, **kwargs):
            datamock = MagicMock({})
            datamock.args = args
            datamock.kwargs = kwargs

            future = asyncio.Future()
            future.set_result(datamock)
            return await future

        with patch.object(
                Endpoint, "aget", return_value=MagicMock(), side_effect=getter
        ) as pat:

            coro = self.client.series.aget(series_id="EFFR")
            json2 = self.client.series.get(series_id="EFFR")
            df = self.client.series.get_pandas(series_id="EFFR")

            self.assertTrue(inspect.isawaitable(coro))
            coro.close()

            self.assertIsInstance(json2, dict)
            self.assertIsInstance(df, DataFrame)

            self.assertEqual(3, pat.call_count)

            for _, kwarg in pat.call_args_list:
                self.assertDictEqual({"series_id": "EFFR"}, kwarg)

    def test_client_docs(self):
        docurl = "https://fred.stlouisfed.org/docs/api/fred/series.html"

        with patch("webbrowser.open", return_value=MagicMock()) as pat:
            self.client.series.docs.open()
            self.client.series.docs.open_new()
            self.client.series.docs.open_new_tab()

        self.assertEqual(3, pat.call_count)
        for url, *typ in pat.call_args_list:
            self.assertEqual(url[0], docurl)


class ClientEndpointAttrTest(unittest.TestCase):

    def test_all_endpoints_exist(self):
        for subpath in const.FRED_API_ENDPOINTS:
            obj = get_client(api_key="foo")
            for path in subpath.split("/"):
                self.assertTrue(hasattr(obj, path))
                obj = getattr(obj, path)
                self.assertIsInstance(obj, Endpoint)
