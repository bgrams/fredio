import os
import unittest
import types
import webbrowser

from pandas import DataFrame
from fredio import Client


class TestAsyncClient(unittest.TestCase):

    client = None

    @classmethod
    def setUpClass(cls):
        cls.client = Client(api_key=os.environ["FRED_API_KEY"])

    def test_get_async(self):
        response = self.client.series.get_async(series_id="EFFR")
        self.assertIsInstance(response, types.CoroutineType)
        response.close()

    def test_get_json(self):
        response = self.client.series.get(series_id="EFFR")
        self.assertIsInstance(response, list)
        self.assertIsInstance(response[0], dict)

    def test_get_pandas(self):
        response = self.client.series.get_pandas(series_id="EFFR")
        self.assertIsInstance(response, DataFrame)

    def test_get_json_with_coro_planning(self):
        # Example from official docs - https://fred.stlouisfed.org/docs/api/fred/releases.html
        # This should pretty consistently only require ~2 requests with limit=200
        response = self.client.releases.get(limit=200)
        self.assertIsInstance(response, list)
        self.assertIsInstance(response[0], dict)

    def test_runtime_error_on_bad_request(self):
        with self.assertRaises(RuntimeError):
            self.client.series.get(series_id="NOT_VALID", retries=0)


if __name__ == "__main__":
    unittest.main()
