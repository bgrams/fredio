import asyncio
import datetime
import inspect
import sys
import unittest
from typing import Any, Union
from unittest.mock import MagicMock
from unittest.mock import patch

from aiohttp import ClientResponse, ClientResponseError
from pandas import DataFrame
from yarl import URL

from fredio import configure
from fredio import const, locks, utils
from fredio.client import ApiClient, Endpoint, get_client  # noqa

from tests import async_test


def mock_fred_response(method: str,
                       url: URL,
                       status: int = 200,
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
        timer=MagicMock(),
        traces=[],
        loop=utils.loop
    )

    body = '{"count": %d, "limit": %d, "offset": %d}' % (count, limit, offset)
    response._body = body.encode("utf-8")

    response.status = status

    reader: asyncio.Future = asyncio.Future()
    reader.set_result(response._body)  # noqa

    response.content = MagicMock()
    response.content.read = MagicMock()
    response.content.read.return_value = reader
    response.read = MagicMock()  # type: ignore
    response.read.return_value = reader

    response.reason = "Good"

    response._headers = {  # type: ignore
        "Content-Type": "application/json",
        "Date": datetime.datetime.utcnow().strftime(const.HEADER_DATE_FMT)
    }

    # Why
    if sys.version_info < (3, 8):
        future: asyncio.Future = asyncio.Future()
        future.set_result(response)
        return future

    return response


class TestApiClient(unittest.TestCase):

    client: ApiClient

    def setUp(self) -> None:

        self.client = configure(api_key="foo")
        self.endpoint = Endpoint(client=self.client, path="")
        self.request_url = URL("https://api.stlouisfed.org/fred/?file_type=json&api_key=foo")

        self.client.ratelimiter = locks.RateLimiter()

    def tearDown(self) -> None:
        self.client.close()

        # Reset the RL
        for task in utils.get_all_tasks():
            task.cancel()

        # self.client.ratelimiter._value = self._rl_value  # reset the RL

    def patchedRequest(self,
                       method: str = "GET",
                       url: Union[str, URL] = None,
                       status: int = 200,
                       return_value: Any = None,
                       **kwargs):

        url = URL(url or self.request_url)
        if return_value is None:
            return_value = mock_fred_response(method, url, status)

        return patch(
            "aiohttp.ClientSession._request",
            return_value=return_value,
            **kwargs
        )

    @async_test
    async def test_request(self):

        ratelim = self.client.ratelimiter

        with self.patchedRequest() as req:
            await self.client.request("GET", self.request_url)

            self.assertEqual(ratelim._lock._value, ratelim._lock._bound_value - 1)

            req.assert_called_once()

    @async_test
    async def test_request_retries(self):

        sleeper = asyncio.ensure_future(asyncio.sleep(0))

        # We don't need to actually sleep for anything in this test
        with patch("asyncio.sleep", return_value=sleeper):
            with self.patchedRequest(status=429) as req:
                with self.assertRaises(ClientResponseError):
                    await self.client.request("GET", self.request_url, retries=2)

                self.assertEqual(3, req.call_count)

            with self.patchedRequest(status=400) as req:
                with self.assertRaises(ClientResponseError):
                    await self.client.request("GET", self.request_url, retries=2)

            self.assertEqual(1, req.call_count)

        # JIC
        await sleeper

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
