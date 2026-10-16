import logging
import struct
from collections import namedtuple

logger = logging.getLogger(__name__)

ZIM_MAGIC = 0x044D495A
# libzim 7 moved all content into the C namespace and marks it as format 6.1.
NEW_NAMESPACE_VERSION = (6, 1)
CONTENT_NAMESPACE = b"C"
HEADER_FORMAT = "<IHH16sIIQQQQIIQ"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)


class NotZimError(ValueError):
    pass


class CorruptZimError(ValueError):
    pass


Header = namedtuple(
    "Header",
    [
        "magic",
        "major_version",
        "minor_version",
        "uuid",
        "article_count",
        "cluster_count",
        "url_ptr_pos",
        "title_ptr_pos",
        "cluster_ptr_pos",
        "mime_list_pos",
        "main_page",
        "layout_page",
        "checksum_pos",
    ],
)

DirectoryEntry = namedtuple(
    "DirectoryEntry",
    [
        "mimetype",
        "namespace",
        "revision",
        "cluster_number",
        "blob_number",
        "url",
        "title",
        "is_redirect",
        "redirect_index",
    ],
)

REDIRECT_MIMETYPE = 0xFFFF
DIR_ENTRY_FIXED_HEADER_FORMAT = "<HBcI"
DIR_ENTRY_FIXED_HEADER_SIZE = struct.calcsize(DIR_ENTRY_FIXED_HEADER_FORMAT)
DIR_ENTRY_ARTICLE_TAIL_FORMAT = "<II"
DIR_ENTRY_ARTICLE_TAIL_SIZE = struct.calcsize(DIR_ENTRY_ARTICLE_TAIL_FORMAT)
DIR_ENTRY_REDIRECT_TAIL_FORMAT = "<I"
DIR_ENTRY_REDIRECT_TAIL_SIZE = struct.calcsize(DIR_ENTRY_REDIRECT_TAIL_FORMAT)
URL_PTR_FORMAT = "<Q"
URL_PTR_SIZE = struct.calcsize(URL_PTR_FORMAT)


_ZT_CHUNK_SIZE = 256


def _read_zt_string(stream):
    chunks = []
    while True:
        start = stream.tell()
        buf = stream.read(_ZT_CHUNK_SIZE)
        if not buf:
            break
        idx = buf.find(b"\x00")
        if idx == -1:
            chunks.append(buf)
            continue
        chunks.append(buf[:idx])
        stream.seek(start + idx + 1)
        break
    return b"".join(chunks).decode("utf-8")


def parse_header(buf):
    if len(buf) < HEADER_SIZE:
        raise NotZimError("File too small to contain a ZIM header")
    fields = struct.unpack(HEADER_FORMAT, buf[:HEADER_SIZE])
    if fields[0] != ZIM_MAGIC:
        raise NotZimError(f"ZIM magic mismatch (got 0x{fields[0]:08x})")
    header = Header(*fields)
    if (header.major_version, header.minor_version) < NEW_NAMESPACE_VERSION:
        raise NotZimError(
            f"Old-namespace ZIM {header.major_version}.{header.minor_version} is not supported"
        )
    return header


class ZimReader(object):
    MAX_REDIRECT_DEPTH = 5

    def __init__(self, stream):
        self._stream = stream
        self._stream.seek(0)
        self.header = parse_header(self._stream.read(HEADER_SIZE))
        self._mime_list_cache = None

    def mime_list(self):
        if self._mime_list_cache is not None:
            return self._mime_list_cache
        self._stream.seek(self.header.mime_list_pos)
        chunk_size = 4096
        buf = b""
        while b"\x00\x00" not in buf:
            chunk = self._stream.read(chunk_size)
            if not chunk:
                raise CorruptZimError("MIME list not terminated before end of file")
            buf += chunk
            if len(buf) > 1 << 20:
                raise CorruptZimError("MIME list exceeds 1 MiB; refusing to parse")
        parts = buf.split(b"\x00")
        mimes = []
        try:
            for p in parts:
                if p == b"":
                    break
                mimes.append(p.decode("utf-8"))
        except UnicodeDecodeError as e:
            raise CorruptZimError(f"Malformed MIME list: {e}") from e
        self._mime_list_cache = mimes
        return mimes

    def _mimetype_for_index(self, mime_idx):
        if self._mime_list_cache is None:
            saved_pos = self._stream.tell()
            mimes = self.mime_list()
            self._stream.seek(saved_pos)
        else:
            mimes = self._mime_list_cache
        if mime_idx >= len(mimes):
            raise CorruptZimError(
                f"MIME index {mime_idx} out of range (list has {len(mimes)} entries)"
            )
        return mimes[mime_idx]

    def _read_dir_entry_at(self, offset):
        ns_char, revision, is_redirect, mime_idx, tail = self._read_entry_head(offset)
        if is_redirect:
            redirect_index = tail
            cluster_number = 0
            blob_number = 0
            mimetype = None
        else:
            cluster_number, blob_number = tail
            redirect_index = None
            mimetype = self._mimetype_for_index(mime_idx)
        url = _read_zt_string(self._stream)
        title = _read_zt_string(self._stream)
        if not title:
            title = url
        return DirectoryEntry(
            mimetype=mimetype,
            namespace=ns_char.decode("ascii"),
            revision=revision,
            cluster_number=cluster_number,
            blob_number=blob_number,
            url=url,
            title=title,
            is_redirect=is_redirect,
            redirect_index=redirect_index,
        )

    def _read_entry_head(self, offset):
        self._stream.seek(offset)
        header = self._stream.read(DIR_ENTRY_FIXED_HEADER_SIZE)
        mime_idx, _param_len, ns_char, revision = struct.unpack(
            DIR_ENTRY_FIXED_HEADER_FORMAT, header
        )
        is_redirect = mime_idx == REDIRECT_MIMETYPE
        if is_redirect:
            (redirect_index,) = struct.unpack(
                DIR_ENTRY_REDIRECT_TAIL_FORMAT,
                self._stream.read(DIR_ENTRY_REDIRECT_TAIL_SIZE),
            )
            return ns_char, revision, True, mime_idx, redirect_index
        cluster_blob = struct.unpack(
            DIR_ENTRY_ARTICLE_TAIL_FORMAT,
            self._stream.read(DIR_ENTRY_ARTICLE_TAIL_SIZE),
        )
        return ns_char, revision, False, mime_idx, cluster_blob

    def _read_url_ptr(self, index):
        self._stream.seek(self.header.url_ptr_pos + URL_PTR_SIZE * index)
        (offset,) = struct.unpack(URL_PTR_FORMAT, self._stream.read(URL_PTR_SIZE))
        return offset

    def iter_entries(self, mimetypes):
        for index in range(self.header.article_count):
            try:
                offset = self._read_url_ptr(index)
            except struct.error:
                logger.warning(
                    "Malformed ZIM URL pointer list at entry %d; stopping",
                    index,
                    exc_info=True,
                )
                return
            try:
                ns_char, _rev, is_redirect, mime_idx, _tail = self._read_entry_head(
                    offset
                )
                if is_redirect or ns_char != CONTENT_NAMESPACE:
                    continue
                mimetype = self._mimetype_for_index(mime_idx)
                if mimetype not in mimetypes:
                    continue
                url = _read_zt_string(self._stream)
                title = _read_zt_string(self._stream) or url
            except (struct.error, UnicodeDecodeError, CorruptZimError):
                logger.warning(
                    "Malformed ZIM directory entry %d; skipping", index, exc_info=True
                )
                continue
            yield f"C/{url}", title, mimetype

    def _read_entry_url(self, offset):
        ns_char, _rev, _is_redir, _mime, _tail = self._read_entry_head(offset)
        url = _read_zt_string(self._stream)
        return f"{ns_char.decode('ascii')}/{url}"

    def _find_entry_for_url(self, normalised_url):
        lo, hi = 0, self.header.article_count
        while lo < hi:
            mid = (lo + hi) // 2
            entry_offset = self._read_url_ptr(mid)
            entry_url = self._read_entry_url(entry_offset)
            if entry_url == normalised_url:
                return self._read_dir_entry_at(entry_offset)
            if entry_url < normalised_url:
                lo = mid + 1
            else:
                hi = mid
        return None

    def find_entry(self, path):
        try:
            return self._find_entry_for_url(path)
        except (struct.error, UnicodeDecodeError) as e:
            raise CorruptZimError(f"Malformed directory data: {e}") from e

    def follow_redirect(self, entry):
        depth = 0
        current = entry
        try:
            while current.is_redirect:
                if depth >= self.MAX_REDIRECT_DEPTH:
                    raise CorruptZimError(
                        f"Redirect chain exceeded depth {self.MAX_REDIRECT_DEPTH}"
                    )
                current = self._read_dir_entry_at(
                    self._read_url_ptr(current.redirect_index)
                )
                depth += 1
        except (struct.error, UnicodeDecodeError) as e:
            raise CorruptZimError(f"Malformed redirect data: {e}") from e
        return current
