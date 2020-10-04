import logging
import unittest

from fredio import utils


class TestUtils(unittest.TestCase):

    def test_prepare_url(self):
        # Special chars should be protected from encoding
        url = utils.prepare_url("foo.com", parameters={"x": "5", "y": "1,2"})
        self.assertEqual(url, "foo.com?x=5&y=1,2")
    
    def test_generate_offsets(self):
        offsets = [i for i in utils.generate_offsets(2, 1, 0)]
        self.assertListEqual(offsets, [(2, 1, 1)])

    def test_log_formatter_masking(self):
        rec = logging.LogRecord(
            name="foo",
            level="DEBUG",
            pathname="__file__",
            lineno=0,
            args=tuple(),
            exc_info=None,
            msg="message api_key=12345")
        fmt = utils.KeyMaskFormatter().format(record=rec)
        self.assertEqual(fmt, "message api_key=<masked>")

if __name__ == "__main__":
    unittest.main()