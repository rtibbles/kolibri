import hashlib
import os
import tempfile
import zipfile
from wsgiref.util import setup_testing_defaults

from django.test import override_settings
from django.test import TestCase
from django.utils.http import http_date

from kolibri.core.content.utils.paths import get_content_storage_file_path
from kolibri.core.content.zip_wsgi import generate_zip_content_response
from kolibri.core.content.zip_wsgi import INITIALIZE_SANDBOX_FROM_IFRAME
from kolibri.core.content.zip_wsgi import parse_html
from kolibri.utils.tests.helpers import override_option


sandbox_injection = '<script type="text/javascript">{}</script>'.format(
    INITIALIZE_SANDBOX_FROM_IFRAME
)

# datetime.datetime(2016, 9, 10, 19, 14, 7) in time from EPOCH
caching_http_date = http_date(1473560047.0)


@override_option("Paths", "CONTENT_DIR", tempfile.mkdtemp())
class ZipContentTestCase(TestCase):
    """
    Testcase for zipcontent endpoint
    """

    index_name = "index.html"
    index_str = "<html><head></head><body></body></html>"
    other_name = "other.html"
    other_str = "<html><head></head><body></body></html>"
    script_name = "script.html"
    script_str = "<html><head><script>test</script></head><body></body></html>"
    empty_html_name = "empty.html"
    empty_html_str = ""
    doctype_name = "doctype.html"
    doctype = """
    <!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01//EN" "http://www.w3.org/TR/html4/strict.dtd">
    """
    doctype_str = doctype + "<html><head><script>test</script></head><body></body></html>"
    html5_doctype_name = "html5_doctype.html"
    html5_doctype = "<!DOCTYPE HTML>"
    html5_doctype_str = (
        html5_doctype + "<html><head><script>test</script></head><body></body></html>"
    )
    test_name_1 = "testfile1.txt"
    test_str_1 = "This is a test!"
    test_name_2 = "testfile2.txt"
    test_str_2 = "And another test..."
    embedded_file_name = "test/this/path/test.txt"
    embedded_file_str = "Embedded file test"

    def setUp(self):

        self.hash = hashlib.md5("DUMMYDATA".encode()).hexdigest()
        self.extension = "zip"
        self.filename = "{}.{}".format(self.hash, self.extension)

        self.zip_path = get_content_storage_file_path(self.filename)
        zip_path_dir = os.path.dirname(self.zip_path)
        if not os.path.exists(zip_path_dir):
            os.makedirs(zip_path_dir)

        with zipfile.ZipFile(self.zip_path, "w") as zf:
            zf.writestr(self.index_name, self.index_str)
            zf.writestr(self.other_name, self.other_str)
            zf.writestr(self.script_name, self.script_str)
            zf.writestr(self.empty_html_name, self.empty_html_str)
            zf.writestr(self.doctype_name, self.doctype_str)
            zf.writestr(self.html5_doctype_name, self.html5_doctype_str)
            zf.writestr(self.test_name_1, self.test_str_1)
            zf.writestr(self.test_name_2, self.test_str_2)
            zf.writestr(self.embedded_file_name, self.embedded_file_str)

        self.zip_file_base_url = "/{}/".format(self.filename)

        self.environ = {}
        setup_testing_defaults(self.environ)

    def _get_file(self, file_name, base_url=None, **kwargs):
        if base_url is None:
            base_url = self.zip_file_base_url
        self.environ["PATH_INFO"] = base_url + file_name
        self.environ.update(kwargs)
        return generate_zip_content_response(self.environ)

    def test_zip_file_internal_file_access(self):
        # test reading the data from file #1 inside the zip
        response = self._get_file(self.test_name_1)
        self.assertEqual(next(response.streaming_content).decode(), self.test_str_1)

        # test reading the data from file #2 inside the zip
        response = self._get_file(self.test_name_2)
        self.assertEqual(next(response.streaming_content).decode(), self.test_str_2)

    def test_nonexistent_zip_file_access(self):
        bad_base_url = self.zip_file_base_url.replace(
            self.zip_file_base_url[20:25], "aaaaa"
        )
        response = self._get_file(self.test_name_1, base_url=bad_base_url)
        self.assertEqual(response.status_code, 404)

    def test_zip_file_nonexistent_internal_file_access(self):
        response = self._get_file("qqq" + self.test_name_1)
        self.assertEqual(response.status_code, 404)

    def test_non_allowed_file_internal_file_access(self):
        response = self._get_file(
            self.test_name_1, base_url=self.zip_file_base_url.replace("zip", "png")
        )
        self.assertEqual(response.status_code, 404)

    def test_not_modified_response_when_if_modified_since_header_set(self):
        response = self._get_file(
            self.test_name_1, HTTP_IF_MODIFIED_SINCE=caching_http_date
        )
        self.assertEqual(response.status_code, 304)

    def test_last_modified_set_on_response(self):
        response = self._get_file(self.test_name_1)
        self.assertIsNotNone(response.get("Last-Modified"))

    def test_expires_set_on_response(self):
        response = self._get_file(self.test_name_1)
        self.assertIsNotNone(response.get("Expires"))

    def test_content_security_policy_header_http_host(self):
        response = self._get_file(self.test_name_1, HTTP_HOST="testserver.com")
        self.assertEqual(
            response.get("Content-Security-Policy"),
            "default-src 'self' 'unsafe-inline' 'unsafe-eval' data: blob:",
        )

    def test_content_security_policy_header_server_name(self):
        self.environ.pop("HTTP_HOST")
        response = self._get_file(self.test_name_1, SERVER_NAME="testserver.com")
        self.assertEqual(
            response.get("Content-Security-Policy"),
            "default-src 'self' 'unsafe-inline' 'unsafe-eval' data: blob:",
        )

    @override_settings(USE_X_FORWARDED_HOST=True)
    def test_content_security_policy_header_forward_for(self):
        response = self._get_file(
            self.test_name_1,
            HTTP_X_FORWARDED_HOST="testserver:1234",
        )
        self.assertEqual(
            response.get("Content-Security-Policy"),
            "default-src 'self' 'unsafe-inline' 'unsafe-eval' data: blob:",
        )

    def test_access_control_allow_origin_header(self):
        response = self._get_file(self.test_name_1)
        self.assertEqual(response.get("Access-Control-Allow-Origin"), "*")
        response = self._get_file(self.test_name_1, REQUEST_METHOD="OPTIONS")
        self.assertEqual(response.get("Access-Control-Allow-Origin"), "*")

    def test_options_returns_empty(self):
        response = self._get_file(self.test_name_1, REQUEST_METHOD="OPTIONS")
        self.assertEqual(response.content.decode(), "")

    def test_x_frame_options_header(self):
        response = response = self._get_file(self.test_name_1)
        self.assertEqual(response.get("X-Frame-Options", ""), "")

    def test_access_control_allow_headers(self):
        headerval = "X-Penguin-Dance-Party"
        response = self._get_file(
            self.test_name_1,
            REQUEST_METHOD="OPTIONS",
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS=headerval,
        )
        self.assertEqual(response.get("Access-Control-Allow-Headers", ""), headerval)
        response = self._get_file(
            self.test_name_1,
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS=headerval,
        )
        self.assertEqual(response.get("Access-Control-Allow-Headers", ""), headerval)

    def test_request_for_html_return_sandbox_modified_html(self):
        response = self._get_file("")
        content = response.content.decode("utf-8")
        # Verify sandbox script is injected
        self.assertIn(sandbox_injection, content)

    def test_request_for_html_body_no_script_return_sandbox_modified_html(self):
        response = self._get_file(self.other_name)
        content = response.content.decode("utf-8")
        # Verify sandbox script is injected at the start of <head>
        self.assertIn(sandbox_injection, content)
        # Script should be injected immediately after <head>
        self.assertIn("<head>" + sandbox_injection, content)

    def test_request_for_html_body_script_return_sandbox_modified_html(self):
        response = self._get_file(self.script_name)
        content = response.content.decode("utf-8")
        # Verify sandbox script is injected at the start of <head>
        self.assertIn(sandbox_injection, content)
        self.assertIn("<script>test</script>", content)
        # Script should appear after sandbox injection
        sandbox_pos = content.find(sandbox_injection)
        test_script_pos = content.find("<script>test</script>")
        self.assertLess(sandbox_pos, test_script_pos)

    def test_request_for_html_body_script_with_extra_slash_return_sandbox_modified_html(
        self,
    ):
        response = self._get_file("/" + self.script_name)
        content = response.content.decode("utf-8")
        # Verify sandbox script is injected
        self.assertIn(sandbox_injection, content)
        self.assertIn("<script>test</script>", content)

    def test_request_for_embedded_file_return_embedded_file(self):
        response = self._get_file(self.embedded_file_name)
        self.assertEqual(
            next(response.streaming_content).decode(), self.embedded_file_str
        )

    def test_request_for_embedded_file_with_double_slashes_return_embedded_file(self):
        response = self._get_file(self.embedded_file_name.replace("/", "//"))
        self.assertEqual(
            next(response.streaming_content).decode(), self.embedded_file_str
        )

    def test_request_for_html_doctype_return_with_doctype(self):
        response = self._get_file(self.doctype_name)
        content = response.content.decode("utf-8")
        self.assertEqual(
            content[:92].lower().replace("  ", " "), self.doctype.strip().lower()
        )

    def test_request_for_html5_doctype_return_with_doctype(self):
        response = self._get_file(self.html5_doctype_name)
        content = response.content.decode("utf-8")
        self.assertEqual(content[:15].lower(), self.html5_doctype.strip().lower())

    def test_request_for_html_body_script_return_correct_length_header(self):
        response = self._get_file(self.script_name)
        # Content-Length should match actual response content length
        actual_content_length = len(response.content)
        self.assertEqual(int(response.headers["Content-Length"]), actual_content_length)
        # Verify the content contains the sandbox injection
        self.assertIn(sandbox_injection, response.content.decode("utf-8"))

    def test_request_for_html_empty_html(self):
        response = self._get_file(self.empty_html_name)
        content = response.content.decode("utf-8")
        # For empty HTML, script should still be injected
        self.assertIn(sandbox_injection, content)

    def test_not_modified_response_when_if_modified_since_header_set_index_file(self):
        response = self._get_file("", HTTP_IF_MODIFIED_SINCE=caching_http_date)
        self.assertEqual(response.status_code, 304)

    def test_not_modified_response_when_if_modified_since_header_set_other_html_file(
        self,
    ):
        response = self._get_file(
            self.other_name, HTTP_IF_MODIFIED_SINCE=caching_http_date
        )
        self.assertEqual(response.status_code, 304)

    def test_post_not_allowed(self):
        response = self._get_file(self.test_name_1, REQUEST_METHOD="POST")
        self.assertEqual(response.status_code, 405)

    def test_put_not_allowed(self):
        response = self._get_file(self.test_name_1, REQUEST_METHOD="PUT")
        self.assertEqual(response.status_code, 405)

    def test_patch_not_allowed(self):
        response = self._get_file(self.test_name_1, REQUEST_METHOD="PATCH")
        self.assertEqual(response.status_code, 405)

    def test_delete_not_allowed(self):
        response = self._get_file(self.test_name_1, REQUEST_METHOD="DELETE")
        self.assertEqual(response.status_code, 405)

    def test_range_request_full_file(self):
        """Ensure normal request works with Accept-Ranges header"""
        response = self._get_file(self.test_name_1)
        self.assertEqual(next(response.streaming_content).decode(), self.test_str_1)
        self.assertEqual(response.headers["Accept-Ranges"], "bytes")
        self.assertEqual(response.status_code, 200)

    def test_range_request_partial_file(self):
        """Test successful range request for partial file"""
        response = self._get_file(self.test_name_1, HTTP_RANGE="bytes=2-5")
        self.assertEqual(
            next(response.streaming_content).decode(), self.test_str_1[2:6]
        )
        self.assertEqual(response.status_code, 206)
        self.assertEqual(
            response.headers["Content-Range"], f"bytes 2-5/{len(self.test_str_1)}"
        )
        self.assertEqual(response.headers["Content-Length"], "4")
        self.assertEqual(response.headers["Accept-Ranges"], "bytes")

    def test_range_request_end_of_file(self):
        """Test range request for last few bytes of file"""
        response = self._get_file(self.test_name_1, HTTP_RANGE="bytes=-4")
        self.assertEqual(
            next(response.streaming_content).decode(), self.test_str_1[-4:]
        )
        self.assertEqual(response.status_code, 206)

    def test_range_request_beyond_eof(self):
        """Test range request with start beyond file size"""
        response = self._get_file(
            self.test_name_1,
            HTTP_RANGE=f"bytes={len(self.test_str_1) + 1}-{len(self.test_str_1) + 4}",
        )
        self.assertEqual(response.status_code, 200)  # Should return full file
        self.assertEqual(next(response.streaming_content).decode(), self.test_str_1)

    def test_range_request_malformed(self):
        """Test malformed range header"""
        response = self._get_file(self.test_name_1, HTTP_RANGE="bytes=invalid")
        self.assertEqual(response.status_code, 200)  # Should return full file
        self.assertEqual(next(response.streaming_content).decode(), self.test_str_1)

    def test_range_request_multiple_ranges(self):
        """Test multiple ranges - should return full file as we don't support multipart responses"""
        response = self._get_file(self.test_name_1, HTTP_RANGE="bytes=0-2,4-6")
        self.assertEqual(response.status_code, 200)  # Should return full file
        self.assertEqual(next(response.streaming_content).decode(), self.test_str_1)

    def test_range_request_html_file(self):
        """Test range requests on HTML files that get modified - should return full file"""
        response = self._get_file(self.script_name, HTTP_RANGE="bytes=0-10")
        # Should return full modified file, not range
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        # Verify sandbox script is injected
        self.assertIn(sandbox_injection, content)
        self.assertIn("<script>test</script>", content)

    def test_range_request_large_file(self):
        """Test range request on a larger file to verify streaming"""
        large_str = "Large text file " * 1024  # ~16KB file
        large_file = "large.txt"

        with zipfile.ZipFile(self.zip_path, "a") as zf:
            zf.writestr(large_file, large_str)

        # Request middle section of file
        start = 1024
        end = 2048
        response = self._get_file(large_file, HTTP_RANGE=f"bytes={start}-{end}")

        content = next(response.streaming_content).decode()
        self.assertEqual(content, large_str[start : end + 1])
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response.headers["Content-Length"], str(end - start + 1))

    def test_options_request_accept_ranges_html(self):
        """Test OPTIONS request for HTML file returns Accept-Ranges: none"""
        response = self._get_file(self.script_name, REQUEST_METHOD="OPTIONS")
        self.assertEqual(response.headers["Accept-Ranges"], "none")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode(), "")

    def test_options_request_accept_ranges_binary(self):
        """Test OPTIONS request for non-HTML file returns Accept-Ranges: bytes"""
        response = self._get_file(
            self.test_name_1, REQUEST_METHOD="OPTIONS"  # This is a .txt file
        )
        self.assertEqual(response.headers["Accept-Ranges"], "bytes")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode(), "")

    def test_accept_ranges_header_html(self):
        """Test Accept-Ranges header is 'none' for HTML files"""
        response = self._get_file(self.script_name)  # HTML file
        self.assertEqual(response.headers["Accept-Ranges"], "none")

    def test_accept_ranges_header_binary(self):
        """Test Accept-Ranges header is 'bytes' for non-HTML files"""
        response = self._get_file(self.test_name_1)  # txt file
        self.assertEqual(response.headers["Accept-Ranges"], "bytes")


@override_option("Deployment", "ZIP_CONTENT_URL_PATH_PREFIX", "prefix_test/")
class UrlPrefixZipContentTestCase(ZipContentTestCase):
    pass


class ParseHtmlEdgeCasesTestCase(TestCase):
    """
    Test edge cases for the regex-based HTML script injection.
    These tests verify that parse_html handles unusual HTML correctly.
    """

    def test_head_in_comment_skipped(self):
        """<head> inside comments should be skipped, injection goes to real head."""

        content = b"<!-- <head></head> --><html><head></head><body></body></html>"
        result = parse_html(content)
        # Should inject in the real <head>, not the commented one
        self.assertIn(sandbox_injection.encode(), result)
        # Verify injection is in the real head (after the comment)
        self.assertIn(b"<html><head>" + sandbox_injection.encode(), result)
        # Comment should be unchanged
        self.assertIn(b"<!-- <head></head> -->", result)

    def test_only_head_in_comment_fallback(self):
        """When only <head> is inside a comment, fall back to <html> injection."""

        content = b"<!-- <head></head> --><html><body></body></html>"
        result = parse_html(content)
        # Should fall back to injecting after <html>
        self.assertIn(sandbox_injection.encode(), result)
        self.assertIn(b"<html><head>" + sandbox_injection.encode(), result)

    def test_html_in_comment_skipped(self):
        """<html> inside comments should be skipped when falling back."""

        content = b"<!-- <html><head></head></html> --><html><body></body></html>"
        result = parse_html(content)
        # Should inject in the real <html>, not the commented one
        self.assertIn(sandbox_injection.encode(), result)
        # Injection should be after the comment
        comment_end = result.find(b"-->")
        injection_pos = result.find(sandbox_injection.encode())
        self.assertGreater(injection_pos, comment_end)

    def test_comment_after_real_head(self):
        """When comment with <head> comes AFTER real head, injection works correctly."""

        content = b"<html><head></head><!-- <head>fake</head> --><body></body></html>"
        result = parse_html(content)
        # Should inject after the first (real) <head>
        self.assertIn(b"<head>" + sandbox_injection.encode(), result)

    def test_head_in_script_after_real_head(self):
        """<head> inside script tags after real head works correctly."""

        content = b'<html><head></head><body><script>var x = "<head>";</script></body></html>'
        result = parse_html(content)
        # Script should be injected in the real <head>
        self.assertIn(sandbox_injection.encode(), result)
        self.assertIn(b"<head>" + sandbox_injection.encode(), result)
        # Original script content preserved
        self.assertIn(b'var x = "<head>"', result)

    def test_head_in_script_before_real_head(self):
        """<head> inside script tags BEFORE real head should be skipped."""

        content = b'<html><script>var x = "<head>";</script><head></head></html>'
        result = parse_html(content)
        # Should inject in the real <head>, not the one in JavaScript
        self.assertIn(sandbox_injection.encode(), result)
        # Injection should be after </script>
        script_close = result.find(b"</script>")
        injection_pos = result.find(sandbox_injection.encode())
        self.assertGreater(injection_pos, script_close)

    def test_head_in_style_before_real_head(self):
        """<head> inside style tags BEFORE real head should be skipped."""

        content = b'<html><style>.x { content: "<head>" }</style><head></head></html>'
        result = parse_html(content)
        # Should inject in the real <head>, not the one in CSS
        self.assertIn(sandbox_injection.encode(), result)
        # Injection should be after </style>
        style_close = result.find(b"</style>")
        injection_pos = result.find(sandbox_injection.encode())
        self.assertGreater(injection_pos, style_close)

    def test_head_in_malformed_tag(self):
        """<head> inside another tag's brackets should be skipped."""

        # <head> appears as a malformed attribute inside <script>
        content = b"<html><script <head>></script><head></head></html>"
        result = parse_html(content)
        self.assertIn(sandbox_injection.encode(), result)
        # Should inject in the real <head>, not the malformed one
        self.assertIn(b"<head>" + sandbox_injection.encode(), result)

    def test_head_in_malformed_div_tag(self):
        """<head> inside a malformed div tag should be skipped."""

        content = b"<html><div <head> class='foo'><head></head></div></html>"
        result = parse_html(content)
        self.assertIn(sandbox_injection.encode(), result)
        # Should inject in the real <head>
        self.assertIn(b"<head>" + sandbox_injection.encode(), result)

    def test_head_in_cdata_section(self):
        """<head> inside CDATA section should be skipped."""

        content = b"<html><![CDATA[ <head> ]]><head></head></html>"
        result = parse_html(content)
        self.assertIn(sandbox_injection.encode(), result)
        # Should inject in the real <head>, not the one in CDATA
        self.assertIn(b"<head>" + sandbox_injection.encode(), result)
        # CDATA content should be preserved
        self.assertIn(b"<![CDATA[ <head> ]]>", result)

    def test_head_in_svg_cdata(self):
        """<head> inside SVG CDATA section should be skipped."""

        # More realistic: CDATA in SVG script
        content = b"<html><head></head><body><svg><script><![CDATA[ var x = '<head>'; ]]></script></svg></body></html>"
        result = parse_html(content)
        self.assertIn(sandbox_injection.encode(), result)
        # Should inject in the real <head>
        self.assertIn(b"<head>" + sandbox_injection.encode(), result)

    def test_multiple_head_tags(self):
        """With multiple head tags, inject after the first one."""

        content = b"<html><head></head><head></head><body></body></html>"
        result = parse_html(content)
        # Should inject after first <head>
        self.assertEqual(result.count(sandbox_injection.encode()), 1)
        # Injection should be right after first <head>
        first_head_pos = result.find(b"<head>")
        injection_pos = result.find(sandbox_injection.encode())
        self.assertEqual(injection_pos, first_head_pos + len(b"<head>"))

    def test_head_with_newlines_and_whitespace(self):
        """Head tag with whitespace/newlines in attributes."""

        content = b'<html><head \n  class="foo"\n  lang="en"\n></head><body></body></html>'
        result = parse_html(content)
        self.assertIn(sandbox_injection.encode(), result)

    def test_mixed_case_head_tag(self):
        """Mixed case HEAD tags should be matched."""

        for tag in [b"<HEAD>", b"<Head>", b"<hEaD>", b"<heAD>"]:
            content = b"<html>" + tag + b"</head><body></body></html>"
            result = parse_html(content)
            self.assertIn(sandbox_injection.encode(), result)

    def test_mixed_case_html_tag(self):
        """Mixed case HTML tags should be matched when no head exists."""

        for tag in [b"<HTML>", b"<Html>", b"<hTmL>"]:
            content = tag + b"<body></body></html>"
            result = parse_html(content)
            self.assertIn(sandbox_injection.encode(), result)
            # Should have injected a <head> tag
            self.assertIn(b"<head>", result)

    def test_utf8_bom_preserved(self):
        """UTF-8 BOM at start of file should be preserved."""

        bom = b"\xef\xbb\xbf"
        content = bom + b"<!DOCTYPE html><html><head></head><body></body></html>"
        result = parse_html(content)
        self.assertTrue(result.startswith(bom))
        self.assertIn(sandbox_injection.encode(), result)

    def test_xhtml_self_closing_head(self):
        """XHTML-style self-closing head tag."""

        # Self-closing <head /> - regex won't match this with current pattern
        # but the <html> fallback should work
        content = b"<html><head /><body></body></html>"
        result = parse_html(content)
        # Should still have the script injected somewhere
        self.assertIn(sandbox_injection.encode(), result)

    def test_head_with_many_attributes(self):
        """Head tag with many attributes."""

        content = b'<html><head lang="en" data-foo="bar" class="main" id="head1"></head></html>'
        result = parse_html(content)
        self.assertIn(sandbox_injection.encode(), result)
        # Attributes should be preserved
        self.assertIn(b'lang="en"', result)
        self.assertIn(b'data-foo="bar"', result)

    def test_bare_body_content(self):
        """HTML with just body content, no html/head tags."""

        content = b"<body><p>Hello world</p></body>"
        result = parse_html(content)
        self.assertIn(sandbox_injection.encode(), result)
        self.assertIn(b"<p>Hello world</p>", result)

    def test_just_text_content(self):
        """Plain text that happens to be served as HTML."""

        content = b"Hello, this is just plain text"
        result = parse_html(content)
        self.assertIn(sandbox_injection.encode(), result)
        self.assertIn(b"Hello, this is just plain text", result)

    def test_html_with_xml_declaration(self):
        """HTML with XML declaration (XHTML style)."""

        content = b'<?xml version="1.0"?><!DOCTYPE html><html><head></head><body></body></html>'
        result = parse_html(content)
        self.assertIn(sandbox_injection.encode(), result)
        self.assertTrue(result.startswith(b"<?xml"))

    def test_frameset_html(self):
        """Old-style frameset HTML."""

        content = b"<html><head><title>Frames</title></head><frameset><frame src='a.html'></frameset></html>"
        result = parse_html(content)
        self.assertIn(sandbox_injection.encode(), result)
        self.assertIn(b"<frameset>", result)

    def test_string_input(self):
        """parse_html should handle string input (not just bytes)."""

        content = "<html><head></head><body></body></html>"
        result = parse_html(content)
        # Result should be bytes
        self.assertIsInstance(result, bytes)
        self.assertIn(sandbox_injection.encode(), result)

    def test_head_immediately_after_doctype(self):
        """Head tag immediately after doctype with no html tag."""

        content = b"<!DOCTYPE html><head></head><body></body>"
        result = parse_html(content)
        self.assertIn(sandbox_injection.encode(), result)
        self.assertTrue(result.startswith(b"<!DOCTYPE html>"))

    def test_very_long_html(self):
        """Performance test with large HTML content."""

        # 100KB of content
        content = b"<html><head></head><body>" + b"<p>Content</p>" * 10000 + b"</body></html>"
        result = parse_html(content)
        self.assertIn(sandbox_injection.encode(), result)
        # Verify injection is near the start, not at the end
        injection_pos = result.find(sandbox_injection.encode())
        self.assertLess(injection_pos, 200)  # Should be near the beginning
