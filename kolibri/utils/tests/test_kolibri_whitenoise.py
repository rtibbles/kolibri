import os
import re
import tempfile
from gzip import GzipFile
from http import HTTPStatus
from unittest.mock import MagicMock
from unittest.mock import mock_open
from unittest.mock import patch

import pytest
from whitenoise.responders import Response

from kolibri.utils.kolibri_whitenoise import COMPRESSED_FILE_FOR_REGULAR_PATH
from kolibri.utils.kolibri_whitenoise import DynamicWhiteNoise
from kolibri.utils.kolibri_whitenoise import EndRangeStaticFile
from kolibri.utils.kolibri_whitenoise import FileFinder
from kolibri.utils.kolibri_whitenoise import MULTIPART_MAX_RANGES
from kolibri.utils.kolibri_whitenoise import NOT_FOUND
from kolibri.utils.kolibri_whitenoise import SlicedFile


def test_file_finder():
    tempdir1 = tempfile.mkdtemp()
    tempdir2 = tempfile.mkdtemp()
    prefix = "/test"
    tempdir1tempfile, tempdir1tempfilepath = tempfile.mkstemp(dir=tempdir1)
    tempdir2tempfile, tempdir2tempfilepath = tempfile.mkstemp(dir=tempdir2)
    tempdir1tempfilename = os.path.basename(tempdir1tempfilepath)
    tempdir2tempfilename = os.path.basename(tempdir2tempfilepath)
    file_finder = FileFinder([(prefix, tempdir1), (prefix, tempdir2)])
    assert tempdir1tempfilepath == file_finder.find(prefix + "/" + tempdir1tempfilename)
    assert tempdir2tempfilepath == file_finder.find(prefix + "/" + tempdir2tempfilename)
    assert file_finder.find("notafile") == []
    os.close(tempdir1tempfile)
    os.remove(tempdir1tempfilepath)
    os.close(tempdir2tempfile)
    os.remove(tempdir2tempfilepath)
    os.removedirs(tempdir1)
    os.removedirs(tempdir2)


def test_dynamic_whitenoise():
    tempdir11 = tempfile.mkdtemp()
    tempdir12 = tempfile.mkdtemp()
    prefix1 = "/test"
    tempdir11tempfile, tempdir11tempfilepath = tempfile.mkstemp(dir=tempdir11)
    tempdir12tempfile, tempdir12tempfilepath = tempfile.mkstemp(dir=tempdir12)
    tempdir11tempfilename = os.path.basename(tempdir11tempfilepath)
    tempdir12tempfilename = os.path.basename(tempdir12tempfilepath)
    tempdir21 = tempfile.mkdtemp()
    tempdir22 = tempfile.mkdtemp()
    prefix2 = "/notatest"
    tempdir21tempfile, tempdir21tempfilepath = tempfile.mkstemp(dir=tempdir21)
    tempdir22tempfile, tempdir22tempfilepath = tempfile.mkstemp(dir=tempdir22)
    tempdir21tempfilename = os.path.basename(tempdir21tempfilepath)
    tempdir22tempfilename = os.path.basename(tempdir22tempfilepath)
    dynamic_whitenoise = DynamicWhiteNoise(
        MagicMock(),
        dynamic_locations=[
            (prefix1, tempdir11),
            (prefix1, tempdir12),
            (prefix2, tempdir21),
            (prefix2, tempdir22),
        ],
    )
    assert (
        dynamic_whitenoise.find_and_cache_dynamic_file(
            prefix1 + "/" + tempdir11tempfilename, None
        )
        is not None
    )
    assert (
        dynamic_whitenoise.find_and_cache_dynamic_file(
            prefix1 + "/" + tempdir12tempfilename, None
        )
        is not None
    )
    assert (
        dynamic_whitenoise.find_and_cache_dynamic_file(
            prefix2 + "/" + tempdir21tempfilename, None
        )
        is not None
    )
    assert (
        dynamic_whitenoise.find_and_cache_dynamic_file(
            prefix2 + "/" + tempdir22tempfilename, None
        )
        is not None
    )
    assert dynamic_whitenoise.find_and_cache_dynamic_file("notafile", None) is None
    os.close(tempdir11tempfile)
    os.remove(tempdir11tempfilepath)
    os.close(tempdir12tempfile)
    os.remove(tempdir12tempfilepath)
    os.close(tempdir21tempfile)
    os.remove(tempdir21tempfilepath)
    os.close(tempdir22tempfile)
    os.remove(tempdir22tempfilepath)
    os.removedirs(tempdir11)
    os.removedirs(tempdir12)


def test_dynamic_whitenoise_suspicious_file():
    tempdir11 = tempfile.mkdtemp()
    tempdir12 = tempfile.mkdtemp()
    prefix1 = "/test"
    dynamic_whitenoise = DynamicWhiteNoise(
        MagicMock(),
        dynamic_locations=[
            (prefix1, tempdir11),
            (prefix1, tempdir12),
        ],
    )
    assert (
        dynamic_whitenoise.find_and_cache_dynamic_file(
            prefix1 + "/" + tempdir11 + "../../../leet_haxx0r.js", None
        )
        is not NOT_FOUND
    )
    os.removedirs(tempdir11)
    os.removedirs(tempdir12)


@pytest.fixture
def mock_stat():
    with patch("os.stat") as mock_stat:
        mock_stat.return_value = MagicMock(st_size=1000, st_mode=33188)
        yield mock_stat


@pytest.fixture
def mock_file():
    with patch("builtins.open", new_callable=mock_open, read_data=b"data") as mock_file:
        yield mock_file


def test_get_response_non_gzipped_from_gzip(mock_stat, mock_file):
    headers = [("Content-Length", "1000")]
    static_file = EndRangeStaticFile("dummy_path", headers)
    static_file.alternatives = [
        (re.compile(r""), "dummy_path.gz" + COMPRESSED_FILE_FOR_REGULAR_PATH, headers)
    ]

    request_headers = {"HTTP_ACCEPT_ENCODING": ""}
    response = static_file.get_response("GET", request_headers)

    assert isinstance(response, Response)
    assert response.status == HTTPStatus.OK

    # Ensure GzipFile was used to read the file
    assert isinstance(response.file, GzipFile)


def test_get_response_gzipped(mock_stat, mock_file):
    headers = [("Content-Length", "1000")]
    static_file = EndRangeStaticFile("dummy_path", headers)
    static_file.alternatives = [(re.compile("gz"), "dummy_path.gz", headers)]

    request_headers = {"HTTP_ACCEPT_ENCODING": "gzip"}
    response = static_file.get_response("GET", request_headers)

    assert isinstance(response, Response)
    assert response.status == HTTPStatus.OK
    assert response.file is not None
    assert not isinstance(response.file, GzipFile)


def test_get_response_non_gzipped(mock_stat, mock_file):
    headers = [("Content-Length", "1000")]
    static_file = EndRangeStaticFile("dummy_path", headers)
    static_file.alternatives = [(re.compile(""), "dummy_path", headers)]

    request_headers = {"HTTP_ACCEPT_ENCODING": "*"}
    response = static_file.get_response("GET", request_headers)

    assert isinstance(response, Response)
    assert response.status == HTTPStatus.OK
    assert response.file is not None
    assert not isinstance(response.file, GzipFile)


def test_get_range_response(mock_stat, mock_file):
    headers = [("Content-Length", "1000")]
    static_file = EndRangeStaticFile("dummy_path", headers)
    static_file.alternatives = [(re.compile(""), "dummy_path", headers)]

    request_headers = {"HTTP_RANGE": "bytes=0-499"}
    path, headers = static_file.get_path_and_headers(request_headers)
    with open(path, "rb") as file_handle:
        response = static_file.get_range_response("bytes=0-499", headers, file_handle)

    assert isinstance(response, Response)
    assert response.status == HTTPStatus.PARTIAL_CONTENT
    assert "Content-Range" in dict(response.headers)
    assert dict(response.headers)["Content-Range"] == "bytes 0-499/1000"
    assert response.file is not None
    assert isinstance(response.file, SlicedFile)


def _read_all(fileobj):
    chunks = []
    while True:
        chunk = fileobj.read(64)
        if not chunk:
            break
        chunks.append(chunk)
    return b"".join(chunks)


@pytest.fixture
def real_static_file(tmp_path):
    content = bytes(i % 256 for i in range(1000))
    path = tmp_path / "data.bin"
    path.write_bytes(content)
    headers = [("Content-Length", "1000"), ("Content-Type", "application/octet-stream")]
    static_file = EndRangeStaticFile(str(path), headers)
    return static_file, str(path), headers, content


def test_get_multipart_range_response(real_static_file):
    static_file, path, headers, content = real_static_file
    with open(path, "rb") as file_handle:
        response = static_file.get_range_response(
            "bytes=0-9,500-509", headers, file_handle
        )
        body = _read_all(response.file)

    assert response.status == HTTPStatus.PARTIAL_CONTENT
    resp_headers = dict(response.headers)
    ctype = resp_headers["Content-Type"]
    assert ctype.startswith("multipart/byteranges; boundary=")
    boundary = ctype.split("boundary=", 1)[1]

    assert len(body) == int(resp_headers["Content-Length"])
    assert b"Content-Range: bytes 0-9/1000" in body
    assert b"Content-Range: bytes 500-509/1000" in body
    assert content[0:10] in body
    assert content[500:510] in body
    assert body.endswith(f"--{boundary}--\r\n".encode())


def test_multipart_advertises_max_ranges(real_static_file):
    static_file, path, headers, _content = real_static_file
    with open(path, "rb") as file_handle:
        response = static_file.get_range_response(
            "bytes=0-9,500-509", headers, file_handle
        )
    assert dict(response.headers)["X-Accept-Ranges-Max"] == "100"


def test_single_range_advertises_max_ranges(real_static_file):
    static_file, path, headers, _content = real_static_file
    with open(path, "rb") as file_handle:
        response = static_file.get_range_response("bytes=0-9", headers, file_handle)
    assert response.status == HTTPStatus.PARTIAL_CONTENT
    assert isinstance(response.file, SlicedFile)
    assert dict(response.headers)["X-Accept-Ranges-Max"] == "100"


def test_multipart_coalesces_overlapping_ranges(real_static_file):
    static_file, path, headers, content = real_static_file
    with open(path, "rb") as file_handle:
        response = static_file.get_range_response(
            "bytes=0-9,5-14", headers, file_handle
        )
        body = _read_all(response.file)
    assert body.count(b"Content-Range: bytes") == 1
    assert b"Content-Range: bytes 0-14/1000" in body
    assert content[0:15] in body


def test_multipart_over_cap_returns_416_not_full_file(real_static_file):
    static_file, path, headers, _content = real_static_file
    spec = "bytes=" + ",".join(
        f"{i * 2}-{i * 2}" for i in range(MULTIPART_MAX_RANGES + 1)
    )
    with open(path, "rb") as file_handle:
        response = static_file.get_range_response(spec, headers, file_handle)
    assert response.status == HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE
    assert dict(response.headers)["Content-Range"] == "bytes */1000"


def test_multipart_all_unsatisfiable_returns_416(real_static_file):
    static_file, path, headers, _content = real_static_file
    with open(path, "rb") as file_handle:
        response = static_file.get_range_response(
            "bytes=2000-3000,4000-5000", headers, file_handle
        )
    assert response.status == HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE


def test_multirange_ignored_when_multipart_disabled(real_static_file):
    static_file, path, headers, _content = real_static_file
    static_file.multipart_ranges = False
    with open(path, "rb") as file_handle, pytest.raises(ValueError):
        static_file.get_range_response("bytes=0-9,500-509", headers, file_handle)


def test_multipart_over_cap_rejected_before_coalescing(real_static_file):
    static_file, path, headers, _content = real_static_file
    spec = "bytes=" + ",".join(["0-9"] * (MULTIPART_MAX_RANGES + 1))
    with open(path, "rb") as file_handle:
        response = static_file.get_range_response(spec, headers, file_handle)
    assert response.status == HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE


def test_multipart_head_reports_full_content_length(real_static_file):
    static_file, path, headers, _content = real_static_file
    with open(path, "rb") as file_handle:
        get_resp = static_file.get_range_response(
            "bytes=0-9,500-509", headers, file_handle
        )
    head_resp = static_file.get_range_response("bytes=0-9,500-509", headers, None)
    assert head_resp.file is None
    head_length = dict(head_resp.headers)["Content-Length"]
    assert head_length == dict(get_resp.headers)["Content-Length"]
    assert int(head_length) > 0
