# fredio
Asynchronous python client for the FRED® API
---

#### Obligatory
**This product uses the FRED® API but is not endorsed or certified by the Federal Reserve Bank of St. Louis**

[Terms of Use](https://research.stlouisfed.org/docs/api/terms_of_use.html)

---
### Important:
This library is _very_ alpha and at this time should not be considered production-ready. The interface has intentionally been kept very simple but is subject to change. Client-side rate limiting is also not fantastic and 429 response codes are unlikely however still possible, so please use this library responsibly and don't spam the FRED servers because a) be nice and b) they'll revoke your API key :)

### Overview:

The interface consists of a single `Client` object built around [aiohttp](https://github.com/aio-libs/aiohttp). This object provides access to all of the available [FRED API endpoints](https://fred.stlouisfed.org/docs/api/fred/#API) as object attributes, and will plan and asynchronously execute requests. Results can be returned as:

1. awaitable coroutine - `client.get_async()`
2. json dictionaries (blocking) - `client.get()`
3. pandas DataFrames (blocking) - `client.get_pandas()`

HTTP parameters are passed as optional keyword arguments to these methods. Documentation for each endpoint can be found on the API website per the above link, and can also be opened in a browser by accessing the `docs()` client method.

Users can optionally pass a `jsonpath` argument to the above methods to parse data. This functionality is supported by the [jsonpath-rw library](https://github.com/kennknowles/python-jsonpath-rw).

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

