import unittest
import webbrowser
from yarl import URL
from fredio.client import ApiClient, client, add_endpoints, get_endpoints


class TestApiClient(unittest.TestCase):

    client = None

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
            self.assertTrue(client.series.docs.open())
        except webbrowser.Error as e:
            raise unittest.SkipTest(str(e))


if __name__ == "__main__":
    unittest.main()
