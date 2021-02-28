import asyncio
import os
import unittest
import webbrowser
from pandas import DataFrame
from yarl import URL
from fredio.client import ApiClient, Client, add_endpoints, get_endpoints
from fredio.session import Session


class TestApiClient(unittest.TestCase):

    def setUp(self):
        self.client = ApiClient("foo.com")
        add_endpoints(self.client, "fuzz", "bar/baz")

    def test_add_endpoint(self):
        self.assertIn("bar", self.client)
        self.assertIsInstance(self.client["bar"], ApiClient)
        self.assertIn("baz", self.client["bar"])

    def test_get_endpoint(self):
        endpoints = get_endpoints(self.client)
        self.assertIsInstance(endpoints, list)
        self.assertIn(URL("foo.com/fuzz"), endpoints)
        self.assertIn(URL("foo.com/bar/baz"), endpoints)

    def test_url_encode(self):
        # Special chars should be protected from encoding
        url = self.client(x=5, y="1,2").url
        self.assertEqual(str(url), "foo.com?x=5&y=1,2")

    def test_open_docs(self):
        try:
            webbrowser.get()  # Will raise if no browser available
            self.assertTrue(Client.series.docs.open())
        except webbrowser.Error as e:
            raise unittest.SkipTest(str(e))


class TestClientRequests(unittest.TestCase):

    client: ApiClient

    @classmethod
    def setUpClass(cls):
        cls.client = Client()
        cls.client.set_session(Session())
        cls.client.set_defaults(api_key=os.environ["FRED_API_KEY"], file_type="json")

    @classmethod
    def tearDownClass(cls):
        loop = asyncio.get_event_loop()
        loop.run_until_complete(cls.client._session.close())

    def test_get_json(self):
        response = self.client.series.get(series_id="EFFR")
        self.assertIsInstance(response, list)
        self.assertIsInstance(response[0], dict)

    def test_get_pandas(self):
        response = self.client.series.get_pandas(series_id="EFFR")
        self.assertIsInstance(response, DataFrame)


if __name__ == "__main__":
    unittest.main()
