import json
import logging
import traceback
from unittest.mock import patch
from unittest.mock import PropertyMock

from django.db import IntegrityError
from django.http.request import RawPostDataException
from django.test import RequestFactory
from django.test import TestCase

from ..constants import BACKEND
from ..middleware import ErrorReportingMiddleware
from ..models import ErrorReport
from ..utils.request import extract_request_info
from ..utils.request import get_request_body


class ErrorReportingMiddlewareTestCase(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @patch(
        "kolibri.core.error_reports.middleware.get_request_time_to_error",
        return_value=0.0,
    )
    @patch(
        "kolibri.core.error_reports.middleware.get_python_version", return_value="3.9.9"
    )
    @patch(
        "kolibri.core.error_reports.middleware.get_packages",
        return_value=["Django==3.2.25"],
    )
    @patch.object(ErrorReport, "insert_or_update_error")
    @patch.object(logging.Logger, "error")
    def test_process_exception(
        self,
        mock_logger_error,
        mock_insert_or_update_error,
        mock_get_packages,
        mock_get_python_version,
        mock_get_request_time_to_error,
    ):
        middleware = ErrorReportingMiddleware(lambda r: None)
        request = self.factory.get("/")
        exception = Exception("Test Exception")
        try:
            raise exception
        except Exception as e:
            middleware.process_exception(request, exception=e)
        # I am just coverting exception.__traceback__ to string
        expected_traceback_info = "".join(
            traceback.format_exception(
                type(exception), exception, exception.__traceback__
            )
        )

        mock_insert_or_update_error.assert_called_once_with(
            BACKEND,
            str(exception),
            expected_traceback_info,
            {
                "request_info": {
                    "url": "http://testserver/",
                    "method": "GET",
                    "headers": {},  # checking whether cookies are removed
                    "body": None,  # GET requests have no body
                    "query_params": {},
                },
                "server": {"host": "testserver", "port": "80"},
                "packages": ["Django==3.2.25"],
                "python_version": "3.9.9",
                "avg_request_time_to_error": 0.0,
            },
        )

    @patch.object(ErrorReport, "insert_or_update_error")
    @patch.object(logging.Logger, "error")
    def test_process_exception_integrity_error(
        self, mock_logger_error, mock_insert_or_update_error
    ):
        middleware = ErrorReportingMiddleware(lambda r: None)
        request = self.factory.get("/")
        request.start_time = 0.0
        exception = Exception("Test Exception")
        mock_insert_or_update_error.side_effect = IntegrityError("Some Integrity Error")
        middleware.process_exception(request, exception)

        mock_logger_error.assert_any_call(
            "Error occurred while saving error report to the database: %s",
            str(mock_insert_or_update_error.side_effect),
        )


class RequestBodyExtractionTestCase(TestCase):
    """Tests for request body extraction with RawPostDataException handling."""

    def setUp(self):
        self.factory = RequestFactory()

    def test_get_request_body_json_post(self):
        """Test that JSON POST body is correctly extracted and parsed."""
        request = self.factory.post(
            "/",
            data=json.dumps({"key": "value"}),
            content_type="application/json",
        )
        body = get_request_body(request)
        self.assertEqual(body, {"key": "value"})

    def test_get_request_body_empty_get(self):
        """Test that GET requests return None for body."""
        request = self.factory.get("/")
        body = get_request_body(request)
        self.assertIsNone(body)

    def test_raw_post_data_exception_falls_back_to_data(self):
        """Test that RawPostDataException is caught and falls back to request.data."""
        request = self.factory.post(
            "/",
            data=json.dumps({"key": "value"}),
            content_type="application/json",
        )

        # Simulate body already consumed by patching request.body to raise exception
        original_body = request.body  # noqa: F841 - triggers the read

        with patch.object(
            type(request),
            "body",
            new_callable=PropertyMock,
            side_effect=RawPostDataException("You cannot access body after reading"),
        ):
            # Add DRF-style .data attribute
            request.data = {"key": "fallback_value"}

            body = get_request_body(request)
            self.assertEqual(body, {"key": "fallback_value"})

    def test_raw_post_data_exception_returns_none_without_data(self):
        """Test that body is None when RawPostDataException occurs and no .data exists."""
        request = self.factory.post(
            "/",
            data=json.dumps({"key": "value"}),
            content_type="application/json",
        )

        with patch.object(
            type(request),
            "body",
            new_callable=PropertyMock,
            side_effect=RawPostDataException("You cannot access body after reading"),
        ):
            # No .data attribute (not DRF)
            body = get_request_body(request)
            self.assertIsNone(body)

    def test_extract_request_info_with_json_body(self):
        """Test extract_request_info correctly extracts JSON body."""
        request = self.factory.post(
            "/api/test/",
            data=json.dumps({"username": "testuser", "password": "secret123"}),
            content_type="application/json",
        )

        info = extract_request_info(request)

        self.assertEqual(info["url"], "http://testserver/api/test/")
        self.assertEqual(info["method"], "POST")
        # Password should be scrubbed
        self.assertEqual(info["body"]["username"], "testuser")
        self.assertEqual(info["body"]["password"], "[filtered for security]")

    def test_extract_request_info_scrubs_sensitive_headers(self):
        """Test that sensitive headers are scrubbed."""
        request = self.factory.post(
            "/",
            data="test",
            content_type="text/plain",
            HTTP_AUTHORIZATION="Bearer secret-token",
            HTTP_COOKIE="sessionid=abc123",
        )

        info = extract_request_info(request)

        # Authorization header should be scrubbed
        self.assertEqual(info["headers"].get("Authorization"), "[filtered for security]")
        self.assertEqual(info["headers"].get("Cookie"), "[filtered for security]")
