"""
URL grouping for locust request names.

Collapses per-id URLs into stable group names so locust aggregates raw
response times per logical endpoint - giving exact per-group percentiles in
the stats CSVs - and so the live web UI / report.html stay readable.

Deliberately free of locust imports so it can be exercised standalone.
"""

import posixpath
import re

HEX_ID_RE = re.compile(r"^[0-9a-f]{32}$")


def group_name(path):
    """
    Map a request path to a group name. Grouping is by path only - any query
    string is dropped, since the broad performance categories of interest are
    per-path. (In practice the locustfile never passes one: HAR replay sends
    query params via the requests `params` kwarg.)

    Rules (first two short-circuit):
    - /content/storage/<a>/<b>/<hash>.<ext> -> /content/storage/{file}.<ext>
    - /static/...                           -> /static/{file}
    - any 32-hex path segment               -> {id}
    """
    path = path.partition("?")[0]
    if path.startswith("/content/storage/"):
        extension = posixpath.splitext(path)[1]
        return "/content/storage/{file}" + extension
    if path.startswith("/static/"):
        return "/static/{file}"
    return "/".join(
        "{id}" if HEX_ID_RE.match(segment) else segment for segment in path.split("/")
    )
