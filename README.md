# fredio
Asynchronous python client for the FRED® API
---

### Obligatory
**This product uses the FRED® API but is not endorsed or certified by the Federal Reserve Bank of St. Louis**

A valid API key issued by FRED is required to use this library, and can be created for free on the FRED website. More info [here](https://fred.stlouisfed.org/docs/api/api_key.html).

[Terms of Use](https://research.stlouisfed.org/docs/api/terms_of_use.html)

### Overview:
`fredio` is an asynchronous client library for the Federal Reserve Economic Database (FRED) API built around [asyncio](https://docs.python.org/3/library/asyncio.html) and [aiohttp](https://github.com/aio-libs/aiohttp). It is intended to provide users with high-performance request execution using coroutines behind a synchronous interface, and implements client-side rate limiting* using locking primitives with a delayed release algorithm.

Users are able to access the *complete* list of [API endpoints](https://fred.stlouisfed.org/docs/api/fred/#API) as client attributes. For example, data from the `series/categories` endpoint is accessed as `client.series.categories.get()`, and documentation can be opened in a browser by accessing `client.series.categories.docs()`. All request parameters found in the official documentation can be passed to the various `get` methods:

1. awaitable coroutine - `client.get_async()`
2. json dictionaries (blocking) - `client.get()`
3. pandas DataFrames (blocking) - `client.get_pandas()`

Response data can also be queried by the client using jsonpath, supported by the [jsonpath-rw](https://github.com/kennknowles/python-jsonpath-rw) library.

\* *Rate limiting is dependent on the system clock, and therefore may not work as expected when the local system is out of sync with the server clock. In such a case, lock releases may be premature, which can lead to 429 response codes.*

### Installation:
```bash
pip install git+https://github.com/bgrams/fredio.git
```

### Examples
```python
import fredio


client = fredio.Client(api_key="API_KEY")

# open documentation for the /series endpoint in the default browser
client.series.docs()

# create a data pipeline to request US GDP data from the /series/observations
# endpoint, clean the results, and write a csv to the local filesystem
(client
.series.observations
.get_pandas(
    series_id="GDP",
    sort_order="asc",
    jsonpath="observations[*]")
.replace(".", "", regex=False)
.to_csv("gdp.csv", index=False))
```

