import sys
from setuptools import setup


if sys.version_info < (3, 6, 0):
    raise RuntimeError("fredio requires Python 3.6 or higher")

setup(
    name="fredio",
    version="0.0.0",
    description="Asynchronous python client for the FRED® API",
    url="https://github.com/bgrams/fredio",
    author="Brandon Grams",
    license="BSD",
    python_requires=">=3.6",
    packages=["fredio"],
    install_requires=["aiohttp", "jsonpath-rw", "pandas"]
)
