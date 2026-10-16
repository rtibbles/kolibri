from typing import ClassVar

from django.http import JsonResponse
from django.views import View

from kolibri.core.content.errors import InvalidStorageFilenameError
from kolibri.core.content.utils.paths import get_content_storage_file_path
from kolibri.plugins.zim_viewer.zim_format import CorruptZimError
from kolibri.plugins.zim_viewer.zim_format import NotZimError
from kolibri.plugins.zim_viewer.zim_format import ZimReader

# Content storage filenames are the file's md5.
_IMMUTABLE_CACHE_CONTROL = "public, max-age=31536000, immutable"

MAX_RESOLVE_PATHS = 1000


def _resolve_one(reader, zim_path):
    entry = reader.find_entry(zim_path)
    if entry is None:
        return None
    if entry.is_redirect:
        entry = reader.follow_redirect(entry)
    return {
        "clusterNumber": entry.cluster_number,
        "blobNumber": entry.blob_number,
        "mimetype": entry.mimetype,
        "namespace": entry.namespace,
        "path": f"{entry.namespace}/{entry.url}",
    }


def _resolve_paths(reader, paths):
    results = {}
    for zim_path in paths:
        if zim_path in results:
            continue
        descriptor = _resolve_one(reader, zim_path)
        if descriptor is not None:
            results[zim_path] = descriptor
    return results


class ZimResolveBatchView(View):
    http_method_names: ClassVar[list] = ["get", "head"]

    def get(self, request, filename):
        try:
            path = get_content_storage_file_path(filename)
        except InvalidStorageFilenameError:
            return JsonResponse({"detail": "Invalid filename"}, status=404)
        paths = request.GET.getlist("path")
        if len(paths) > MAX_RESOLVE_PATHS:
            return JsonResponse({"detail": "Too many paths requested"}, status=400)
        try:
            with open(path, "rb") as fh:
                results = _resolve_paths(ZimReader(fh), paths)
            response = JsonResponse({"results": results})
            response["Cache-Control"] = _IMMUTABLE_CACHE_CONTROL
            return response
        except FileNotFoundError:
            return JsonResponse({"detail": "File not found"}, status=404)
        except NotZimError:
            return JsonResponse({"detail": "Not a ZIM file"}, status=400)
        except CorruptZimError as exc:
            return JsonResponse({"detail": str(exc)}, status=400)
