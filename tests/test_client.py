import os
import unittest
import types

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
    
    def test_open_docs(self):
        self.assertTrue(self.client.series.docs())


if __name__ == "__main__":
    unittest.main()