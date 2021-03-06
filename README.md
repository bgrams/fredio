# fredio
Async python client for the FRED® API
---

### Obligatory
**This product uses the FRED® API but is not endorsed or certified by the Federal Reserve Bank of St. Louis**

A valid API key issued by FRED is required to use this library, and can be created for free on the FRED website. More info [here](https://fred.stlouisfed.org/docs/api/api_key.html).

[Terms of Use](https://research.stlouisfed.org/docs/api/terms_of_use.html)

### Overview:
`fredio` is a sync/async framework for interacting with the Federal Reserve Economic Database (FRED), built around [asyncio](https://docs.python.org/3/library/asyncio.html) and [aiohttp](https://github.com/aio-libs/aiohttp). It is intended to provide users with high-performance and reliable request execution using asynchronous Tasks behind a synchronous interface, and implements client-side rate limiting with a fixed-window algorithm to safely handle bursts of requests.

**Important**: Rate limiting is dependent on the system clock, and therefore may not work as expected when the local system is even slightly out of sync with the server clock. In such a case, lock releases may be premature, which can lead to 429 response codes.

Users are able to access the *complete* list of [API endpoints](https://fred.stlouisfed.org/docs/api/fred/#API) from the main `ApiClient` object, whose attributes map directly to each endpoint path.
For example, data from the `/fred/series/categories` endpoint is accessed as `ApiClient.series.categories.get()`. Official API documentation for each endpoint can be opened in a browser by accessing e.g. `ApiClient.series.categories.docs.open()`. All request parameters found in the official documentation can be passed to the various `get` methods:

1. `client.aget()` - Returns an awaitable Task.
2. `client.get()` - Returns json response data (blocking) 
3. `client.get_pandas()` - Returns a pandas DataFrame (blocking)

In-memory response data can also be queried by the client using jsonpath, supported by the [jsonpath-rw](https://github.com/kennknowles/python-jsonpath-rw) library.

### Installation:
```bash
pip install git+https://github.com/bgrams/fredio.git
```

### Examples

#### Standard synchronous usage
```python
import fredio

# Pass an api_key here, or set as FRED_API_KEY environment variable
# This will also start a background Task for rate limiting
client = fredio.configure()

# open documentation for the /fred/series endpoint in the default browser
client.series.docs.open()

# create a data pipeline to request US GDP data from the /series/observations
# endpoint, clean the results, and write a csv to the local filesystem
(client.series.observations
.get_pandas(
    series_id="GDP",
    sort_order="asc",
    jsonpath="observations[*]")
.replace(".", "", regex=False)
.to_csv("gdp.csv", index=False))
```

#### Using the Events API
Events are not enabled by default, but can be by passing `enable_events=True` to
the main configuration function. The request Session will queue json data for all successful responses
in the form of `(name, data)`, where `name` corresponds to the final path in the URL endpoint. jsonpath queries
are not applied to event data.

Note: Experimental (!!)
```python
import asyncio
import pprint

import fredio
from fredio.events import on_event

# Register a handler to process json data from ALL /fred/.../series endpoints
# Sync functions defined here will be wrapped in a coroutine
@on_event("series")
async def print_series(data):
    await asyncio.sleep(0)
    pprint.pprint(data)

    
async def main(fred):
    while True:
        await fred.series.aget(series_id="EFFR")
        await asyncio.sleep(60)

if __name__ == "__main__":
    client = fredio.configure(enable_events=True)

    asyncio.run(main(client))
    
```