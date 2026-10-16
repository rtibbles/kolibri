from django.urls import re_path

from kolibri.plugins.zim_viewer.views import ZimResolveBatchView

urlpatterns = [
    re_path(
        r"^zim/resolve_batch/(?P<filename>[^/]+)$",
        ZimResolveBatchView.as_view(),
        name="zim_resolve_batch",
    ),
]
