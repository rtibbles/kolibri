# Implementation Plan: Vendor Sentry SDK's WSGI and Django Request Handling

## Issue Summary

**Issue:** [#13578](https://github.com/learningequality/kolibri/issues/13578) - Vendor Sentry SDK's WSGI and Django request handling to fix issues with request serialization in error reports.

**Problem:** The current error reporting middleware attempts to read `request.body` after the request has already been processed (consumed by Django REST Framework or the view), which causes `RawPostDataException` errors.

**Solution:** Vendor specific request-handling code patterns from the Sentry Python SDK to properly handle request body reading and fallback mechanisms.

---

## Current State Analysis

### Existing Code Structure

```
kolibri/core/error_reports/
├── __init__.py
├── apps.py
├── constants.py           # FRONTEND, BACKEND, TASK constants
├── middleware.py          # ErrorReportingMiddleware, PreRequestMiddleware
├── models.py              # ErrorReport model
├── schemas.py             # JSON schemas for context validation
├── tasks.py               # Background tasks for sending reports
├── utils/
│   ├── __init__.py
│   └── scrubber.py        # Data scrubbing (already vendored from Sentry)
└── test/
    ├── __init__.py
    ├── test_middleware.py
    ├── test_models.py
    └── test_tasks.py
```

### Current Problem in `middleware.py`

```python
def get_request_info(request):
    context = {
        "url": request.build_absolute_uri(),
        "method": request.method,
        "headers": dict(request.headers),
        "query_params": dict(request.GET),
        "body": None,
    }

    if request.headers.get("Content-Type", "").lower() == "application/json":
        try:
            # PROBLEM: This fails with RawPostDataException if body was already read
            context["body"] = json.loads(request.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            pass  # Missing RawPostDataException handling!

    scrub_data(context)
    return context
```

---

## Sentry SDK Approach Analysis

The Sentry SDK solves this problem through several mechanisms:

### 1. Request Extractor Base Class (`_wsgi_common.py`)

```python
class RequestExtractor:
    def extract_into_event(self, event):
        # Try raw_data first
        raw_data = None
        try:
            raw_data = self.raw_data()
        except (RawPostDataException, ValueError):
            # If DRF is used it already read the body, ignore
            pass

        # Fall back to parsed_body
        parsed_body = self.parsed_body()
        if parsed_body is not None:
            data = parsed_body
        elif raw_data:
            data = raw_data  # Mark as raw
        else:
            data = None
```

### 2. Django-Specific Extractor (`django/__init__.py`)

```python
class DjangoRequestExtractor(RequestExtractor):
    def raw_data(self):
        return self.request.body

    def parsed_body(self):
        try:
            # Try DRF's cached .data property first
            return self.request.data
        except AttributeError:
            # Fall back to parent implementation
            return RequestExtractor.parsed_body(self)

    def form(self):
        return self.request.POST

    def files(self):
        return self.request.FILES
```

### 3. DRF Backref Patching

Sentry patches DRF to store a weak reference from the Django request to the DRF request, enabling access to the cached `request.data` property.

---

## Implementation Plan

### Phase 1: Create Request Extraction Utilities

**File:** `kolibri/core/error_reports/utils/request.py`

1. **Import Django's RawPostDataException**
   ```python
   from django.http.request import RawPostDataException
   ```

2. **Create RequestExtractor base class**
   - Method: `extract_request_data(request)` - main entry point
   - Method: `get_raw_data(request)` - safely reads request.body
   - Method: `get_parsed_body(request)` - gets parsed form/JSON data
   - Method: `get_json(request)` - parses JSON content type
   - Method: `get_form_data(request)` - gets POST form data

3. **Key Safety Features:**
   - Catch `RawPostDataException` when accessing `request.body`
   - Try `request.data` (DRF) as fallback
   - Try `request.POST` as secondary fallback
   - Respect content-type headers
   - Size limits for request bodies

### Phase 2: Update Middleware

**File:** `kolibri/core/error_reports/middleware.py`

1. **Replace `get_request_info()` function:**
   - Use new `RequestExtractor` utilities
   - Handle `RawPostDataException` gracefully
   - Provide fallback chain: `body` -> `data` -> `POST` -> `None`

2. **Update Exception Handling:**
   ```python
   from django.http.request import RawPostDataException

   def get_request_info(request):
       context = {...}

       try:
           raw_body = request.body
       except RawPostDataException:
           raw_body = None

       # Try to get parsed body from DRF if available
       parsed_body = getattr(request, 'data', None)

       # Fallback logic...
   ```

### Phase 3: Add Early Request Body Caching (Optional Enhancement)

**File:** `kolibri/core/error_reports/middleware.py`

In `PreRequestMiddleware.process_view()`, optionally cache the request body early:

```python
def process_view(self, request, view_func, view_args, view_kwargs):
    request.start_time = time.time()

    # Cache body early if it's JSON and within size limits
    if self._should_cache_body(request):
        try:
            request._cached_body = request.body
        except Exception:
            request._cached_body = None
```

This ensures we capture the body before any view/DRF processing.

### Phase 4: Update Tests

**File:** `kolibri/core/error_reports/test/test_middleware.py`

1. **Add test for RawPostDataException handling:**
   - Mock `request.body` to raise `RawPostDataException`
   - Verify middleware handles it gracefully
   - Verify fallback to `request.data` works

2. **Add test for DRF request handling:**
   - Create mock DRF request with `.data` attribute
   - Verify `.data` is used when `.body` fails

3. **Update existing tests:**
   - Fix expected body format in assertions (currently expects empty string `""`, should expect `None`)

---

## Detailed File Changes

### 1. New File: `kolibri/core/error_reports/utils/request.py`

```python
"""
Vendored and adapted from sentry-sdk's request extraction utilities.
Original source: https://github.com/getsentry/sentry-python
Original license: MIT License

This module provides utilities for safely extracting request data,
handling cases where the request body has already been read.
"""
import json
import logging

from django.http.request import RawPostDataException

from .scrubber import scrub_data

logger = logging.getLogger(__name__)

# Maximum body size to capture (in bytes)
MAX_BODY_SIZE = 65536  # 64KB


def get_request_body(request):
    """
    Safely extract the request body, handling cases where it has
    already been consumed by Django REST Framework or other middleware.

    Returns:
        The parsed body (dict for JSON), raw body (str), or None
    """
    content_type = request.headers.get("Content-Type", "").lower()

    # First, try to get raw body
    raw_body = _get_raw_body(request)

    # If raw body failed, try parsed body (DRF's .data)
    if raw_body is None:
        return _get_parsed_body(request)

    # If we have raw body and it's JSON, parse it
    if "application/json" in content_type:
        return _parse_json_body(raw_body)

    # For non-JSON, return as string (with size limit)
    if isinstance(raw_body, bytes):
        try:
            return raw_body.decode("utf-8")[:MAX_BODY_SIZE]
        except UnicodeDecodeError:
            return None

    return raw_body


def _get_raw_body(request):
    """
    Attempt to read the raw request body.
    Returns None if the body has already been consumed.
    """
    try:
        body = request.body
        if len(body) > MAX_BODY_SIZE:
            logger.debug("Request body exceeds size limit, truncating")
            return body[:MAX_BODY_SIZE]
        return body
    except RawPostDataException:
        # Body was already read by DRF or another component
        logger.debug("Request body already consumed, trying fallback")
        return None
    except Exception as e:
        logger.debug("Error reading request body: %s", e)
        return None


def _get_parsed_body(request):
    """
    Try to get the parsed body from DRF's .data attribute.
    Falls back to request.POST for form data.
    """
    # Try DRF's cached .data property
    try:
        data = request.data
        if isinstance(data, dict):
            return dict(data)
        return data
    except AttributeError:
        pass
    except Exception as e:
        logger.debug("Error accessing request.data: %s", e)

    # Fall back to POST data for form submissions
    try:
        if request.POST:
            return dict(request.POST)
    except Exception as e:
        logger.debug("Error accessing request.POST: %s", e)

    return None


def _parse_json_body(raw_body):
    """
    Parse raw body as JSON.
    """
    try:
        if isinstance(raw_body, bytes):
            raw_body = raw_body.decode("utf-8")
        return json.loads(raw_body)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        logger.debug("Error parsing JSON body: %s", e)
        return None


def extract_request_info(request):
    """
    Extract complete request information for error reporting.
    This is the main entry point for request data extraction.

    Returns:
        dict: Request information with sensitive data scrubbed
    """
    context = {
        "url": request.build_absolute_uri(),
        "method": request.method,
        "headers": dict(request.headers),
        "query_params": dict(request.GET),
        "body": None,
    }

    # Get body using safe extraction
    body = get_request_body(request)
    if body is not None:
        context["body"] = body

    # Scrub sensitive data
    scrub_data(context)

    return context
```

### 2. Updated: `kolibri/core/error_reports/middleware.py`

```python
import logging
import time
import traceback
from sys import version_info

if version_info < (3, 10):
    from importlib_metadata import distributions
else:
    from importlib.metadata import distributions

from django.core.exceptions import MiddlewareNotUsed
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from .constants import BACKEND
from .models import ErrorReport
from .utils.request import extract_request_info  # New import

from kolibri.plugins.error_reports.kolibri_plugin import ErrorReportsPlugin
from kolibri.plugins.registry import registered_plugins


def get_server_info(request):
    return {"host": request.get_host(), "port": request.get_port()}


def get_packages():
    packages = [f"{dist.metadata['Name']}=={dist.version}" for dist in distributions()]
    return packages


def get_python_version():
    return ".".join(str(v) for v in version_info[:3])


def get_request_time_to_error(request):
    return time.time() - request.start_time


class ErrorReportingMiddleware:
    """
    Middleware to log exceptions to the database.
    """

    def __init__(self, get_response):
        if ErrorReportsPlugin not in registered_plugins:
            raise MiddlewareNotUsed("ErrorReportsPlugin is not enabled.")
        self.get_response = get_response
        self.logger = logging.getLogger(__name__)

    def __call__(self, request):
        response = self.get_response(request)
        return response

    def process_exception(self, request, exception):
        error_message = str(exception)
        traceback_info = traceback.format_exc()
        context = {
            "request_info": extract_request_info(request),  # Updated
            "server": get_server_info(request),
            "packages": get_packages(),
            "python_version": get_python_version(),
            "avg_request_time_to_error": get_request_time_to_error(request),
        }
        self.logger.error("Unexpected Error: %s", error_message)
        try:
            self.logger.error("Saving error report to the database.")
            ErrorReport.insert_or_update_error(
                BACKEND,
                error_message,
                traceback_info,
                context,
            )
        except (IntegrityError, ValidationError) as e:
            self.logger.error(
                "Error occurred while saving error report to the database: %s", str(e)
            )


class PreRequestMiddleware:
    def __init__(self, get_response):
        if ErrorReportsPlugin not in registered_plugins:
            raise MiddlewareNotUsed("ErrorReportsPlugin is not enabled.")
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        return response

    def process_view(self, request, view_func, view_args, view_kwargs):
        request.start_time = time.time()
```

### 3. Updated: `kolibri/core/error_reports/schemas.py`

Update the body field type to allow both string and object:

```python
context_backend_schema = {
    "type": "object",
    "properties": {
        "request_info": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "optional": True},
                "method": {"type": "string", "optional": True},
                "headers": {"type": "object", "optional": True},
                "body": {"type": ["string", "object", "null"], "optional": True},  # Updated
                "query_params": {"type": "object", "optional": True},
            },
        },
        # ... rest unchanged
    },
}
```

### 4. New/Updated Tests

Add new test cases to `test_middleware.py`:

```python
from django.http.request import RawPostDataException
from unittest.mock import PropertyMock

class TestRequestBodyExtraction(TestCase):
    """Tests for request body extraction handling."""

    def test_raw_post_data_exception_handled(self):
        """Test that RawPostDataException is caught and fallback is used."""
        request = self.factory.post(
            "/",
            data=json.dumps({"key": "value"}),
            content_type="application/json"
        )
        # Simulate body already consumed
        with patch.object(
            type(request), 'body',
            new_callable=PropertyMock,
            side_effect=RawPostDataException("Body already read")
        ):
            request.data = {"key": "value"}  # Simulate DRF cached data

            info = extract_request_info(request)

            self.assertEqual(info["body"], {"key": "value"})

    def test_no_body_when_all_methods_fail(self):
        """Test that body is None when all extraction methods fail."""
        request = self.factory.post("/", content_type="application/json")

        with patch.object(
            type(request), 'body',
            new_callable=PropertyMock,
            side_effect=RawPostDataException("Body already read")
        ):
            # No .data attribute (not DRF)
            info = extract_request_info(request)

            self.assertIsNone(info["body"])
```

---

## Testing Strategy

1. **Unit Tests:**
   - Test `_get_raw_body()` with normal request
   - Test `_get_raw_body()` with `RawPostDataException`
   - Test `_get_parsed_body()` with DRF request
   - Test `_get_parsed_body()` with form POST
   - Test `extract_request_info()` complete flow

2. **Integration Tests:**
   - Test middleware with DRF API view that triggers exception
   - Test middleware with regular Django view
   - Test middleware with file uploads

3. **Manual Testing:**
   - Trigger errors in various API endpoints
   - Verify request body is captured in error reports
   - Verify sensitive data is scrubbed

---

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Breaking existing functionality | Comprehensive test coverage, backward compatible changes |
| Performance impact | Early body caching is optional, size limits prevent large body reads |
| Security concerns | Existing scrubber handles PII, body capture respects content limits |
| DRF compatibility | Use `hasattr`/`getattr` for safe attribute access |

---

## References

- [Sentry SDK Django Integration](https://github.com/getsentry/sentry-python/tree/master/sentry_sdk/integrations/django)
- [Sentry SDK WSGI Common](https://github.com/getsentry/sentry-python/blob/master/sentry_sdk/integrations/_wsgi_common.py)
- [Django RawPostDataException](https://github.com/encode/django-rest-framework/issues/2774)
- [Original Issue #13578](https://github.com/learningequality/kolibri/issues/13578)
- [Parent Issue #12214](https://github.com/learningequality/kolibri/issues/12214)
