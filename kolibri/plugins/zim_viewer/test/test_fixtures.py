import hashlib
import os

from kolibri.plugins.zim_viewer.test.fixtures import build_minimal_zim

MINIMAL_ZIM_PATH = os.path.join(os.path.dirname(__file__), "data", "minimal.zim")


def test_minimal_zim_has_zim_magic():
    data = build_minimal_zim()
    assert data[:4] == b"Z\x49\x4d\x04"


def test_minimal_zim_checksum_is_appended_md5():
    data = build_minimal_zim()
    body = data[:-16]
    expected_md5 = hashlib.md5(body).digest()
    assert data[-16:] == expected_md5


def test_minimal_zim_has_known_size():
    data = build_minimal_zim()
    assert len(data) == 200


def test_minimal_zim_committed_bytes_match_builder():
    # ZimReader.spec.js reads this file; regenerate it from build_minimal_zim().
    with open(MINIMAL_ZIM_PATH, "rb") as fh:
        assert fh.read() == build_minimal_zim()
