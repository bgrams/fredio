import asyncio
import unittest
import types

from fredio.client import Client
from fredio.session import Session


class TestApiClient(unittest.TestCase):

    session: Session

    @classmethod
    def setUpClass(cls):
        cls.invalid_series_url = Client.series(series_id="NOT_VALID").url
        cls.valid_series_url = Client.series(series_id="EFFR").url
        cls.valid_releases_url = Client.releases.url
        cls.session = Session()

    @classmethod
    def tearDownClass(cls):
        loop = asyncio.get_event_loop()
        loop.run_until_complete(cls.session.close())

    def test_get_async(self):
        response = self.session.get(self.valid_series_url)
        self.assertIsInstance(response, types.CoroutineType)
        response.close()

    def test_get_json_with_coro_planning(self):
        # Example from official docs - https://fred.stlouisfed.org/docs/api/fred/releases.html
        # This should pretty consistently only require ~2 requests with limit=200
        loop = asyncio.get_event_loop()
        req = self.session.get(self.valid_releases_url, limit=200)
        res = loop.run_until_complete(req)
        self.assertIsInstance(res, list)
        self.assertIsInstance(res[0], dict)

    def test_runtime_error_on_bad_request(self):
        loop = asyncio.get_event_loop()
        with self.assertRaises(RuntimeError):
            req = self.session.get(self.invalid_series_url, retries=0)
            loop.run_until_complete(req)


if __name__ == "__main__":
    unittest.main()
