import hashlib
import os
import tempfile
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from kolibri.core.content.utils.paths import get_content_storage_file_path
from kolibri.plugins.zim_viewer.test.fixtures import build_minimal_zim
from kolibri.plugins.zim_viewer.test.fixtures import build_zim_with_redirect
from kolibri.utils.tests.helpers import override_option


@override_option("Paths", "CONTENT_DIR", tempfile.mkdtemp())
class ZimResolveBatchViewTests(TestCase):
    def setUp(self):
        self.filename = "{}.zim".format(hashlib.md5(b"DUMMYDATA").hexdigest())
        self.zim_path = get_content_storage_file_path(self.filename)
        zim_dir = os.path.dirname(self.zim_path)
        if not os.path.exists(zim_dir):
            os.makedirs(zim_dir)
        with open(self.zim_path, "wb") as fh:
            fh.write(build_minimal_zim())

    def _url(self, filename, paths):
        base = reverse(
            "kolibri:kolibri.plugins.zim_viewer:zim_resolve_batch",
            kwargs={"filename": filename},
        )
        if not paths:
            return base
        return base + "?" + "&".join(f"path={p}" for p in paths)

    def test_resolves_multiple_paths_in_one_request(self):
        response = self.client.get(self._url(self.filename, ["C/Index"]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "results": {
                    "C/Index": {
                        "clusterNumber": 0,
                        "blobNumber": 0,
                        "mimetype": "text/html",
                        "namespace": "C",
                        "path": "C/Index",
                    },
                },
            },
        )

    def test_missing_paths_are_simply_absent(self):
        response = self.client.get(self._url(self.filename, ["C/Index", "C/Missing"]))
        self.assertEqual(response.status_code, 200)
        results = response.json()["results"]
        self.assertIn("C/Index", results)
        self.assertNotIn("C/Missing", results)

    def test_follows_redirects(self):
        with open(self.zim_path, "wb") as fh:
            fh.write(build_zim_with_redirect())
        response = self.client.get(self._url(self.filename, ["C/Redirect"]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["results"]["C/Redirect"],
            {
                "clusterNumber": 0,
                "blobNumber": 0,
                "mimetype": "text/html",
                "namespace": "C",
                "path": "C/Index",
            },
        )

    def test_empty_path_list_returns_empty_results(self):
        response = self.client.get(self._url(self.filename, []))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"results": {}})

    def test_sets_immutable_cache_header_on_success(self):
        response = self.client.get(self._url(self.filename, ["C/Index"]))
        self.assertEqual(
            response["Cache-Control"], "public, max-age=31536000, immutable"
        )

    def test_returns_400_when_too_many_paths_requested(self):
        # Django's DATA_UPLOAD_MAX_NUMBER_FIELDS also caps query params.
        with patch("kolibri.plugins.zim_viewer.views.MAX_RESOLVE_PATHS", 2):
            response = self.client.get(
                self._url(self.filename, ["C/Index", "C/Index", "C/a", "C/b"])
            )
        self.assertEqual(response.status_code, 400)

    def test_returns_404_for_unknown_file(self):
        unknown = "{}.zim".format("0" * 32)
        response = self.client.get(self._url(unknown, ["C/Index"]))
        self.assertEqual(response.status_code, 404)
        self.assertNotIn("Cache-Control", response)

    def test_returns_400_for_truncated_zim(self):
        with open(self.zim_path, "wb") as fh:
            fh.write(build_minimal_zim()[:85])
        response = self.client.get(self._url(self.filename, ["C/Index"]))
        self.assertEqual(response.status_code, 400)
