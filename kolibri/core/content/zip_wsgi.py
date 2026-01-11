import logging
import mimetypes
import os
import re
import sys
import time
import zipfile
from urllib.parse import unquote

from cheroot import wsgi
from django.core.cache import cache
from django.core.handlers.wsgi import WSGIRequest
from django.http import HttpResponse
from django.http import HttpResponseNotAllowed
from django.http import HttpResponseNotFound
from django.http import HttpResponseNotModified
from django.http.response import FileResponse
from django.http.response import StreamingHttpResponse
from django.utils.cache import patch_response_headers
from django.utils.encoding import force_str
from django.utils.http import http_date
from le_utils.constants.file_formats import BLOOMD
from le_utils.constants.file_formats import BLOOMPUB
from le_utils.constants.file_formats import H5P
from le_utils.constants.file_formats import HTML5
from le_utils.constants.file_formats import PERSEUS
from whitenoise.responders import StaticFile

from kolibri.core.content.errors import InvalidStorageFilenameError
from kolibri.core.content.utils.paths import get_content_storage_file_path
from kolibri.core.content.utils.paths import get_content_storage_remote_url
from kolibri.core.content.utils.paths import get_zip_content_base_path
from kolibri.core.discovery.utils.network.client import NetworkClient
from kolibri.utils.file_transfer import RemoteFile


logger = logging.getLogger(__name__)


def parse_byte_range(range_header, file_size):
    """
    Parse Range header using whitenoise's implementation
    Unlike whitenoise, this implementation returns None if the start is beyond EOF
    and returns the start value and the length of the range, rather than the end.
    """
    try:
        # Use StaticFile's parse_byte_range to handle the parsing
        # be aware that it can return a negative start value
        # with an end value of None, rather than represent a content-range
        # header that has no start value but an end value.
        start, end = StaticFile.parse_byte_range(range_header)
        if start >= file_size:
            # If start is beyond EOF, return None to trigger full file response
            return None

        if end is None:
            end = file_size - 1
        else:
            end = min(end, file_size - 1)
        # Handle negative start values by adding them to file_size
        if start < 0:
            start = file_size + start
        length = end - start + 1
        return start, length
    except ValueError:
        return None


class RangeZipFileObjectWrapper:
    """
    A wrapper for a zip file object that supports byte range requests.
    This is implemented for compatibility with Python 3.6, which does not
    support seeking in file objects extracted from zip files.
    This can be removed once Python 3.6 support is dropped.
    """

    CHUNK_SIZE = 8192

    def __init__(self, file_object, start=0, length=None):
        self.file_object = file_object
        self.remaining = length
        # Python 3.7+ zipfile has seek support
        if sys.version_info >= (3, 7):
            self.file_object.seek(start)
        else:
            # Read and discard data until we reach start position
            while start > 0:
                chunk_size = min(start, self.CHUNK_SIZE)
                self.file_object.read(chunk_size)
                start -= chunk_size

    def __iter__(self):
        return self

    def __next__(self):
        if self.remaining is not None and self.remaining <= 0:
            raise StopIteration()
        chunk = self.file_object.read(
            min(
                self.CHUNK_SIZE,
                self.remaining if self.remaining is not None else self.CHUNK_SIZE,
            )
        )
        if not chunk:
            raise StopIteration()
        if self.remaining is not None:
            self.remaining -= len(chunk)
        return chunk


def add_security_headers(request, response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    requested_headers = request.META.get("HTTP_ACCESS_CONTROL_REQUEST_HEADERS", "")
    if requested_headers:
        response.headers["Access-Control-Allow-Headers"] = requested_headers
    # restrict CSP to only allow resources to be loaded from self, to prevent info leakage
    # (e.g. via passing user info out as GET parameters to an attacker's server), or inadvertent data usage
    response.headers[
        "Content-Security-Policy"
    ] = "default-src 'self' 'unsafe-inline' 'unsafe-eval' data: blob:"

    return response


def django_response_to_wsgi(response, environ, start_response):
    status = "%d %s" % (response.status_code, response.reason_phrase)
    response_headers = [(str(k), str(v)) for k, v in response.items()]
    for c in response.cookies.values():
        response_headers.append((str("Set-Cookie"), str(c.output(header=""))))
    start_response(force_str(status), response_headers)
    if getattr(response, "file_to_stream", None) is not None and environ.get(
        "wsgi.file_wrapper"
    ):
        response = environ["wsgi.file_wrapper"](response.file_to_stream)
    return response


allowed_methods = set(["GET", "OPTIONS"])

# This is also included in packages/sandbox/src/h5p.html
# ideally, we should never ever update this code
# but if we do we should update it there.
INITIALIZE_SANDBOX_FROM_IFRAME = "if (window.parent && window.parent.sandbox) {try {window.parent.sandbox.initializeIframe(window);} catch (e) {}}"

# Pre-compiled regex patterns for HTML script injection
# Pattern to match opening <head> tag (case-insensitive, with optional attributes)
_HEAD_PATTERN = re.compile(rb"(<head(?:\s[^>]*)?>)", re.IGNORECASE)
# Pattern to match opening <html> tag (case-insensitive, with optional attributes)
_HTML_PATTERN = re.compile(rb"(<html(?:\s[^>]*)?>)", re.IGNORECASE)

# Pre-computed script tag wrapped in <head> for injection
_SCRIPT_TAG = '<script type="text/javascript">{}</script>'.format(
    INITIALIZE_SANDBOX_FROM_IFRAME
)
_SCRIPT_TAG_BYTES = _SCRIPT_TAG.encode("utf-8")
_HEAD_WITH_SCRIPT = b"<head>" + _SCRIPT_TAG_BYTES + b"</head>"


def _is_inside_comment(content, position):
    """
    Check if a position in content is inside an HTML comment.

    Uses a simple approach: find the last '<!--' before position,
    then check if there's a '-->' between it and position.
    """
    # Only look at content before the position
    before = content[:position]

    # Find the last comment opening before position
    last_open = before.rfind(b"<!--")
    if last_open == -1:
        return False

    # Check if there's a closing after the opening but before position
    # find() from last_open position, looking for --> after the <!--
    close_after_open = before.find(b"-->", last_open + 4)  # +4 to skip past <!--
    # If no close found after open, we're inside a comment
    return close_after_open == -1


def _is_inside_cdata(content, position):
    """
    Check if a position in content is inside a CDATA section.

    CDATA sections (<![CDATA[ ... ]]>) are valid in XHTML and in foreign
    content (SVG/MathML). In HTML5, they're treated as bogus comments.
    Either way, content inside should not be treated as tags.
    """
    before = content[:position]

    last_open = before.rfind(b"<![CDATA[")
    if last_open == -1:
        return False

    # Check if there's a closing ]]> after the opening
    close_after_open = before.find(b"]]>", last_open + 9)  # +9 to skip past <![CDATA[
    return close_after_open == -1


# Pattern to find script/style opening tags (case-insensitive)
_SCRIPT_OPEN_PATTERN = re.compile(rb"<script(?:\s[^>]*)?>", re.IGNORECASE)
_SCRIPT_CLOSE_PATTERN = re.compile(rb"</script\s*>", re.IGNORECASE)
_STYLE_OPEN_PATTERN = re.compile(rb"<style(?:\s[^>]*)?>", re.IGNORECASE)
_STYLE_CLOSE_PATTERN = re.compile(rb"</style\s*>", re.IGNORECASE)


def _is_inside_script_or_style(content, position):
    """
    Check if a position is inside a <script> or <style> tag.

    This prevents matching <head> that appears in JavaScript strings
    or CSS content before the actual <head> tag.
    """
    before = content[:position]

    # Check for unclosed <script> tag
    last_script_open = -1
    for match in _SCRIPT_OPEN_PATTERN.finditer(before):
        last_script_open = match.end()

    if last_script_open != -1:
        # Check if there's a </script> after the last <script>
        last_script_close = -1
        for match in _SCRIPT_CLOSE_PATTERN.finditer(before):
            if match.start() >= last_script_open:
                last_script_close = match.end()

        if last_script_close == -1 or last_script_close < last_script_open:
            return True

    # Check for unclosed <style> tag
    last_style_open = -1
    for match in _STYLE_OPEN_PATTERN.finditer(before):
        last_style_open = match.end()

    if last_style_open != -1:
        # Check if there's a </style> after the last <style>
        last_style_close = -1
        for match in _STYLE_CLOSE_PATTERN.finditer(before):
            if match.start() >= last_style_open:
                last_style_close = match.end()

        if last_style_close == -1 or last_style_close < last_style_open:
            return True

    return False


def _is_inside_tag_brackets(content, position):
    """
    Check if position is inside another tag's angle brackets.

    This catches malformed HTML like <script <head>> where <head> appears
    inside the script tag's opening bracket as a malformed attribute.
    In HTML5, browsers would parse <head> as an attribute name, not a tag.
    """
    before = content[:position]

    # Find the last '<' before this position
    last_open = before.rfind(b"<")
    if last_open == -1:
        return False

    # Check if there's a '>' between that '<' and our position
    # If not, we're inside another tag's brackets
    between = before[last_open:]
    return b">" not in between


def _is_valid_injection_point(content, position):
    """Check if position is a valid place to inject (not in comment, CDATA, script, style, or malformed tag)."""
    return (
        not _is_inside_comment(content, position)
        and not _is_inside_cdata(content, position)
        and not _is_inside_script_or_style(content, position)
        and not _is_inside_tag_brackets(content, position)
    )


def parse_html(content):
    """
    Inject sandbox initialization script into HTML content.

    Uses regex-based injection which is ~1000x faster than html5lib.
    Browsers are forgiving and will execute the script regardless of
    exact HTML structure, so we don't need full HTML parsing/normalization.

    Injection strategy:
    1. If <head> tag exists (not in comment/script/style): inject script after <head>
    2. If <html> tag exists but no valid <head>: inject <head> with script after <html>
    3. Otherwise: prepend <head> with script to the content
    """
    if isinstance(content, str):
        content = content.encode("utf-8")

    # Try to find <head> tag that's not inside a comment, script, or style
    for head_match in _HEAD_PATTERN.finditer(content):
        if _is_valid_injection_point(content, head_match.start()):
            # Found a valid <head> tag
            insert_pos = head_match.end()
            return content[:insert_pos] + _SCRIPT_TAG_BYTES + content[insert_pos:]

    # No valid <head> tag - try to find <html> tag (also skip invalid locations)
    for html_match in _HTML_PATTERN.finditer(content):
        if _is_valid_injection_point(content, html_match.start()):
            # Inject <head> with script after <html>
            insert_pos = html_match.end()
            return content[:insert_pos] + _HEAD_WITH_SCRIPT + content[insert_pos:]

    # No valid <html> tag either - just prepend <head> with script
    # This handles edge cases like bare content or fragments
    return _HEAD_WITH_SCRIPT + content


def get_embedded_file(
    zipped_path, zipped_filename, embedded_filepath, range_header=None
):
    with zipfile.ZipFile(zipped_path) as zf:
        # if no path, or a directory, is being referenced, look for an index.html file
        if not embedded_filepath or embedded_filepath.endswith("/"):
            embedded_filepath += "index.html"

        # get the details about the embedded file, and ensure it exists
        try:
            info = zf.getinfo(embedded_filepath)
        except KeyError:
            return HttpResponseNotFound(
                '"{}" does not exist inside "{}"'.format(
                    embedded_filepath, zipped_filename
                )
            )

        # try to guess the MIME type of the embedded file being referenced
        content_type = (
            mimetypes.guess_type(embedded_filepath)[0] or "application/octet-stream"
        )
        zipped_file_object = zf.open(info)

        is_html = embedded_filepath.lower().endswith(("html", "htm"))

        if is_html:
            content = zipped_file_object.read()
            html = parse_html(content)
            response = HttpResponse(html, content_type=content_type)
            file_size = len(response.content)
        else:
            # generate a streaming response object, pulling data from within the zip file
            status = 200
            file_size = info.file_size
            range_response_header = None

            # handle byte-range requests
            if range_header:
                range_tuple = parse_byte_range(range_header, file_size)
                if range_tuple:
                    start, length = range_tuple
                    zipped_file_object = RangeZipFileObjectWrapper(
                        zipped_file_object, start, length
                    )
                    status = 206
                    # Use the total file size of the object for the Content-Range header
                    range_response_header = (
                        f"bytes {start}-{start + length - 1}/{file_size}"
                    )
                    # Update the file size to the length of the requested range
                    file_size = length

            response = FileResponse(
                zipped_file_object, content_type=content_type, status=status
            )
            if range_response_header:
                response.headers["Content-Range"] = range_response_header

        # Only accept byte ranges for files that are not HTML
        response.headers["Accept-Ranges"] = "none" if is_html else "bytes"
        # set the content-length header to the size of the embedded file
        response.headers["Content-Length"] = file_size
        return response


archive_file_types = (HTML5, H5P, BLOOMPUB, BLOOMD, PERSEUS)
archive_file_extension_match = "|".join(archive_file_types)

# Allows a base url to be passed in the main
# URL and allow relative paths within the loaded HTML5 zip file
# to maintain the base URL reference. This means when loading
# from remote URLs, the HTML5 zip can be incrementally loaded based on
# the base URL, rather than having to load the entire zip file before
# loading the HTML5 content.
path_regex = re.compile(
    r"/(?:(?P<base_url>(?![a-f0-9]{32}\.(?:"
    + archive_file_extension_match
    + r"))[^/]+)/)?(?P<zipped_filename>[a-f0-9]{32}\.(?:"
    + archive_file_extension_match
    + r"))/(?P<embedded_filepath>.*)"
)

YEAR_IN_SECONDS = 60 * 60 * 24 * 365

ERROR_TEMPLATE = """
<html>
    <head>
        <meta name="sandbox-error" content="{error}">
    </head>
    <body>
    </body>
</html>
"""


def create_error_response(error):
    return HttpResponse(
        ERROR_TEMPLATE.format(error=error), content_type="text/html", status=404
    )


def _zip_content_from_request(request):  # noqa: C901
    if request.method not in allowed_methods:
        return HttpResponseNotAllowed(allowed_methods)

    match = path_regex.match(request.path_info)
    if match is None:
        return create_error_response(
            "Path not found: {path}".format(path=request.path_info)
        )

    remote_baseurl, zipped_filename, embedded_filepath = match.groups()

    if request.method == "OPTIONS":
        response = HttpResponse()
        # If path ends with html/htm, set Accept-Ranges to none
        if embedded_filepath.lower().endswith(("html", "htm")):
            response.headers["Accept-Ranges"] = "none"
        else:
            response.headers["Accept-Ranges"] = "bytes"
        return response

    try:
        # calculate the local file path to the zip file
        zipped_path = get_content_storage_file_path(zipped_filename)
    except InvalidStorageFilenameError:
        return create_error_response(
            "{filename} is not a valid file name".format(filename=zipped_filename)
        )

    if remote_baseurl:
        remote_baseurl = unquote(remote_baseurl)
        if NetworkClient.known_location_for_address(remote_baseurl) is None:
            return create_error_response(
                "{baseurl} is not a known peer".format(baseurl=remote_baseurl)
            )

    # if the zipfile does not exist on disk, return a 404
    if not os.path.exists(zipped_path):
        if not remote_baseurl:
            return create_error_response(
                "{filename} is not a valid zip file".format(filename=zipped_filename)
            )
        else:
            try:
                zipped_url = get_content_storage_remote_url(
                    zipped_filename, baseurl=remote_baseurl
                )
                zipped_path = RemoteFile(zipped_path, zipped_url)
            except Exception:
                return create_error_response(
                    "{filename} is either not available on the remote {baseurl}, or cannot be fetched".format(
                        filename=zipped_filename, baseurl=remote_baseurl
                    )
                )

    # Sometimes due to URL concatenation, we get URLs with double-slashes in them, like //path/to/file.html.
    # the zipped_filename and embedded_filepath are defined by the regex capturing groups in the URL defined
    # in urls.py in the same folder as this file:
    # r"^zipcontent/(?P<zipped_filename>[^/]+)/(?P<embedded_filepath>.*)"
    # If the embedded_filepath contains a leading slash because of an input URL like:
    # /zipcontent/filename.zip//file.html
    # then the embedded_filepath will have a value of "/file.html"
    # we detect this leading slash in embedded_filepath and remove it.
    if embedded_filepath.startswith("/"):
        embedded_filepath = embedded_filepath[1:]
    # Any double-slashes later in the URL will be present as double-slashes, such as:
    # /zipcontent/filename.zip/path//file.html
    # giving an embedded_filepath value of "path//file.html"
    # Normalize the path by converting double-slashes occurring later in the path to a single slash.
    # This would change our example embedded_filepath to "path/file.html" which will resolve properly.
    embedded_filepath = embedded_filepath.replace("//", "/")

    # if client has a cached version, use that (we can safely assume nothing has changed, due to MD5)
    if request.META.get("HTTP_IF_MODIFIED_SINCE"):
        return HttpResponseNotModified()

    CACHE_KEY = "ZIPCONTENT_VIEW_RESPONSE_{}/{}".format(
        zipped_filename, embedded_filepath
    )
    cached_response = cache.get(CACHE_KEY)
    if cached_response is not None:
        return cached_response

    range_header = request.META.get("HTTP_RANGE")

    try:
        response = get_embedded_file(
            zipped_path, zipped_filename, embedded_filepath, range_header=range_header
        )
    except Exception:
        if remote_baseurl:
            return create_error_response(
                "{filename} is either not available on the remote {baseurl}, or cannot be fetched".format(
                    filename=zipped_filename, baseurl=remote_baseurl
                )
            )
        raise

    response.headers["Last-Modified"] = http_date(time.time())

    patch_response_headers(response, cache_timeout=YEAR_IN_SECONDS)

    if not isinstance(response, StreamingHttpResponse):

        cache.set(CACHE_KEY, response, YEAR_IN_SECONDS)

    return response


def generate_zip_content_response(environ):
    request = WSGIRequest(environ)
    response = _zip_content_from_request(request)
    add_security_headers(request, response)
    return response


def zip_content_view(environ, start_response):
    """
    Handles GET requests and serves a static file from within the zip file.
    """
    response = generate_zip_content_response(environ)

    return django_response_to_wsgi(response, environ, start_response)


def get_application():
    path_map = {
        get_zip_content_base_path(): zip_content_view,
    }

    return wsgi.PathInfoDispatcher(path_map)
