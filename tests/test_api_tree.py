import unittest
from fredio.client import ApiTree


class TestApiTree(unittest.TestCase):

    tree = None

    def setUp(self):
        self.tree = ApiTree("foo.com")
        self.tree.add_endpoints("fuzz", "bar/baz")

    def test_add_endpoint(self):
        self.assertIn("bar", self.tree)
        self.assertIsInstance(self.tree["bar"], ApiTree)
        self.assertIn("baz", self.tree["bar"])

    def test_get_endpoint(self):
        endpoints = self.tree.get_endpoints()
        self.assertIsInstance(endpoints, list)
        self.assertIn("foo.com/fuzz", endpoints)
        self.assertIn("foo.com/bar/baz", endpoints)


if __name__ == "__main__":
    unittest.main()
