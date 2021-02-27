import logging
import re


class KeyMaskFormatter(logging.Formatter):
    """
    Formatter that removes sensitive information in urls.
    """

    apikey_re = re.compile(r'(?<=api_key=)([\w])+(?=[^\w]?)')

    def _filter(self, record):
        return self.apikey_re.sub("<masked>", record)

    def format(self, record):
        original = super(KeyMaskFormatter, self).format(record)
        return self._filter(original)


def generate_offsets(count: int, limit: int, offset: int):
    """
    Generator yielding new offsets
    """
    while offset + limit < count:
        offset += limit
        yield count, limit, offset
