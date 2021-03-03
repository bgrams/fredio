import logging
import unittest

from fredio import utils


class TestUtils(unittest.TestCase):

    def test_log_formatter_masking(self):
        rec = logging.LogRecord(
            name="foo",
            level="DEBUG",
            pathname="__file__",
            lineno=0,
            args=tuple(),
            exc_info=None,
            msg="message api_key=12345")
        fmt = utils.KeyMaskingFormatter().format(record=rec)
        self.assertEqual(fmt, "message api_key=<masked>")

    def test_get_tasks(self):
        self.assertIsInstance(utils.get_all_tasks(), set)


if __name__ == "__main__":
    unittest.main()
