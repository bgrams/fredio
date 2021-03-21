import os
from setuptools import find_packages, setup


dirname = os.path.dirname(__file__)

with open(os.path.join(dirname, "README.md"), "r") as f:
    long_description = f.read()

setup(
    name="fredio",
    version="0.1.0a1",
    description="Asynchronous python client for the FRED® API",
    long_description=long_description,
    long_description_content_type="text/markdown",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Framework :: AsyncIO",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Natural Language :: English",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8"
    ],
    url="https://github.com/bgrams/fredio",
    author="Brandon Grams",
    license="MIT",
    python_requires=">=3.6",
    packages=find_packages(include=["fredio", "fredio.*"]),
    install_requires=[
        "aiohttp>=3.0,<4.0",
        "jsonpath-rw",
        "pandas",
        "yarl>=1.0,<2.0"
    ],
    test_suite="tests"
)
