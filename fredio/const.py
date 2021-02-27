FRED_API_ENDPOINTS = (
    "category",
    "category/children",
    "category/related",
    "category/series",
    "category/tags",
    "category/related_tags",

    "releases",
    "releases/dates",

    "release",
    "release/dates",
    "release/series",
    "release/sources",
    "release/tags",
    "release/related_tags",
    "release/tables",

    "series",
    "series/categories",
    "series/observations",
    "series/release",
    "series/search",
    "series/search/tags",
    "series/search/related_tags",
    "series/tags",
    "series/updates",
    "series/vintagedates",

    "sources",

    "source",
    "source/releases",

    "tags",
    "tags/series",
    "related_tags"
)

FRED_API_URL = "https://api.stlouisfed.org/fred"
FRED_DOC_URL = "https://fred.stlouisfed.org/docs/api/fred"

FRED_API_RATE_LIMIT = 120
FRED_API_RATE_RESET = 60
FRED_API_FILE_TYPE = "json"  # other XML option but we dont want that
