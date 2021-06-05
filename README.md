# fredio
Async python client for the FRED® API
---

### Obligatory
**This product uses the FRED® API but is not endorsed or certified by the Federal Reserve Bank of St. Louis**

A valid API key issued by FRED is required to use this library, and can be created for free on the FRED website. More info [here](https://fred.stlouisfed.org/docs/api/api_key.html).

[Terms of Use](https://research.stlouisfed.org/docs/api/terms_of_use.html)

### Overview:
`fredio` is a sync/async framework for interacting with the Federal Reserve Economic Database (FRED), built around [asyncio](https://docs.python.org/3/library/asyncio.html) and [aiohttp](https://github.com/aio-libs/aiohttp). It is intended to provide users with high-performance and reliable request execution using asynchronous Tasks behind a synchronous interface, and implements client-side rate limiting with a fixed-window algorithm to safely handle bursts of requests.

Users are able to access the *complete* list of [API endpoints](https://fred.stlouisfed.org/docs/api/fred/#API) from the main `ApiClient` object, whose `Endpoint` attributes map directly to each available url subpath.
For example, data from the `/fred/series/categories` endpoint is accessed as `ApiClient.series.categories.get()`. Official API documentation for each endpoint can be opened in a browser by accessing e.g. `ApiClient.series.categories.docs.open()`.

All request parameters found in the official documentation can be passed to the various `get` methods:

1. `Endpoint.aget()` - Coroutine returning json response data.
2. `Endpoint.get()` - Returns json response data (blocking) 
3. `Endpoint.get_pandas()` - Returns a pandas DataFrame (blocking)

In-memory response data can also be queried by the client using jsonpath, supported by the [jsonpath-rw](https://github.com/kennknowles/python-jsonpath-rw) library.

**Please note**: Rate limiting is solely dependent on the system clock and there is no synchronization performed with the FRED servers. 429 response errors may therefore still happen under load in
the extremely likely circumstance that these two clocks are even slightly out of sync.

### Installation:
```bash
pip install fredio
```

### Examples

#### Standard synchronous usage

```python
import fredio

# Pass an api_key here, or set as FRED_API_KEY environment variable
# This will also start a background Task for rate limiting
client = fredio.configure()

# open documentation for the /fred/series endpoint in the default browser
client.series.observations.docs.open()

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

#### Using the Events API (Experimental)
Events are not enabled by default, but can be by passing `enable_events=True` to
the main configuration function. The request Session will queue all successful HTTP responses
in the form of `(name, response)`, where `name` corresponds to the final path in the URL endpoint.

```python
import asyncio
import datetime
import fredio

from fredio.events import on_event


# Register a handler to process HTTP responses from the /fred/series/updates endpoint
@on_event("updates")
async def process_updates(response):
    json = await response.json()

    series = json["seriess"]
    print("Got %d series" % len(series))

    # Request observations for each series id
    # Subsequent responses will be processed by "observations" handlers
    client = fredio.client.get_client()
    series_tasks = [client.series.observations.aget(series_id=s["id"]) for s in series]
    await asyncio.gather(*series_tasks)


@on_event("observations")
async def process_observations(response):
    json = await response.json()

    # Print data, or write to a database
    print("Got %d observations" % len(json["observations"]))


async def main(client, interval=600):

    # Initialize start, end time edges
    # FRED servers are in US/Chicago
    tzone = datetime.timezone(offset=datetime.timedelta(hours=-6))
    delta = datetime.timedelta(seconds=interval)
    stime = etime = datetime.datetime.now(tzone)
    stime -= delta

    while True:
        etime_fmt = etime.strftime("%Y%m%d%H%M")
        stime_fmt = stime.strftime("%Y%m%d%H%M")
        
        # Successful responses will be enqueued and picked up by
        # the event handler defined above
        print("Requesting updates between %s, %s" % (stime_fmt, etime_fmt))
        await client.series.updates.aget(start_time=stime_fmt, end_time=etime_fmt)
        await asyncio.sleep(interval)
        
        stime += delta
        etime += delta
        

if __name__ == "__main__":
    
    with fredio.configure(enable_events=True) as fred:
        asyncio.run(main(fred))
```
