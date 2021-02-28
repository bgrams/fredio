import asyncio
import os
import types
import unittest

from pandas import DataFrame

from fredio.client import Client, ApiClient
from fredio.session import Session
from fredio import utils


class TestApiClient(unittest.TestCase):

    client: ApiClient
    session: Session

    @classmethod
    def setUpClass(cls):
        cls.client = Client()
        cls.session = Session()

        cls.client.set_defaults(api_key=os.environ["FRED_API_KEY"],
                                file_type="json")

        cls.client.set_session(cls.session)

        cls.invalid_series_url = cls.client.series(series_id="NOT_VALID").url
        cls.valid_series_url = cls.client.series(series_id="EFFR").url
        cls.valid_releases_url = cls.client.releases.url

    @classmethod
    def tearDownClass(cls):
        print("Cancelling all tasks")
        tasks = utils.get_all_tasks()
        for task in tasks:
            task.cancel()

        utils.loop.run_until_complete(cls.session.close())

    def test_session_get(self):
        response = self.session.get(self.valid_series_url)
        self.assertIsInstance(response, types.CoroutineType)
        response.close()

    def test_session_get_with_coro_planning(self):
        # Example from official docs - https://fred.stlouisfed.org/docs/api/fred/releases.html
        # This should pretty consistently only require ~2 requests with limit=200
        loop = asyncio.get_event_loop()
        req = self.session.get(self.valid_releases_url, limit=200)
        res = loop.run_until_complete(req)
        self.assertIsInstance(res, list)
        self.assertIsInstance(res[0], dict)

    def test_session_runtime_error_on_bad_request(self):
        loop = asyncio.get_event_loop()
        with self.assertRaises(RuntimeError):
            req = self.session.get(self.invalid_series_url, retries=0)
            loop.run_until_complete(req)

    def test_client_get(self):
        response = self.client.series.get(series_id="EFFR")
        self.assertIsInstance(response, list)
        self.assertIsInstance(response[0], dict)

    def test_client_get_pandas(self):
        response = self.client.series.get_pandas(series_id="EFFR")
        self.assertIsInstance(response, DataFrame)


if __name__ == "__main__":
    unittest.main()
