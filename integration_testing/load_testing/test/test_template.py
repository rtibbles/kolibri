"""
The template tarball hash decides whether a device re-downloads hundreds of
MB, so packing must be byte-identical for identical content — including
across different tarball paths (gzip embeds mtime and filename by default;
both bit us during implementation).
"""

import tarfile

from template import pack_template


def test_pack_template_roundtrip(tmp_path):
    home = tmp_path / "home"
    (home / "content").mkdir(parents=True)
    (home / "db.sqlite3").write_text("db")
    (home / "content" / "f.mp4").write_text("video")
    tarball = str(tmp_path / "t.tar.gz")
    content_hash = pack_template(str(home), tarball)
    assert len(content_hash) == 12
    assert content_hash == pack_template(str(home), tarball)  # stable
    assert content_hash == pack_template(str(home), str(tmp_path / "other-name.tar.gz"))
    extracted = tmp_path / "out"
    extracted.mkdir()
    with tarfile.open(tarball) as tar:
        tar.extractall(str(extracted))
    assert (extracted / "db.sqlite3").read_text() == "db"
    assert (extracted / "content" / "f.mp4").read_text() == "video"
