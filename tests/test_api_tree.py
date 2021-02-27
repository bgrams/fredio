import unittest
from yarl import URL
from fredio.client import ApiTree, add_endpoints, get_endpoints


class TestApiTree(unittest.TestCase):

    tree = None

    def setUp(self):
        self.tree = ApiTree("foo.com")
        add_endpoints(self.tree, "fuzz", "bar/baz")

    def test_add_endpoint(self):
        self.assertIn("bar", self.tree)
        self.assertIsInstance(self.tree["bar"], ApiTree)
        self.assertIn("baz", self.tree["bar"])

    def test_get_endpoint(self):
        endpoints = get_endpoints(self.tree)
        self.assertIsInstance(endpoints, list)
        self.assertIn(URL("foo.com/fuzz"), endpoints)
        self.assertIn(URL("foo.com/bar/baz"), endpoints)

    def test_url_encode(self):
        # Special chars should be protected from encoding
        url = self.tree.query(x=5, y="1,2").encode()
        self.assertEqual(str(url), "foo.com?x=5&y=1,2")


if __name__ == "__main__":
    unittest.main()
