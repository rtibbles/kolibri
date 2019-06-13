from __future__ import absolute_import
from __future__ import print_function
from __future__ import unicode_literals

from django.urls import reverse

from . import hooks
from kolibri.core.auth.constants.user_kinds import LEARNER
from kolibri.core.content.hooks import PermalinkHook
from kolibri.core.hooks import NavigationHook
from kolibri.core.hooks import RoleBasedRedirectHook
from kolibri.core.webpack import hooks as webpack_hooks
from kolibri.plugins.base import KolibriPluginBase


class Learn(KolibriPluginBase):
    pass


class LearnRedirect(RoleBasedRedirectHook):
    role = LEARNER

    @property
    def url(self):
        return self.plugin_url(Learn, "learn")


class LearnNavItem(NavigationHook, webpack_hooks.WebpackBundleHook):
    unique_slug = "learn_module_side_nav"
    src_file = "assets/src/views/LearnSideNavEntry.vue"


class LearnAsset(webpack_hooks.WebpackBundleHook):
    unique_slug = "learn_module"
    src_file = "assets/src/app.js"


class LearnInclusionHook(hooks.LearnSyncHook):
    bundle_class = LearnAsset



def _url_for_content_node(node)
    kind_slug = None
    if not node.parent:
        kind_slug = ""
    elif node.kind == "topic":
        kind_slug = "t/"
    else:
        kind_slug = "c/"
    if kind_slug is not None:
        return reverse("kolibri:learn:learn") + "#/topics/" + kind_slug + node.id
    return None


class LearnChannelNodeIDHook(PermalinkHook):
    """
    redirect to the given content node
    """

    param_signature = (PermalinkHook.CHANNEL_NODE_ID,)

    def url(self, params):
        try:
            node = ContentNode.objects.get(id=params[PermalinkHook.CHANNEL_NODE_ID])
            return _url_for_content_node(node)
        except ContentNode.DoesNotExist:
            return None


class LearnChannelHook(PermalinkHook):
    """
    redirect to the root node of the channel
    """

    param_signature = (PermalinkHook.CHANNEL_ID,)

    def url(self, params):
        try:
            node = ContentNode.objects.get()  # find the parent node of the given channel...
            return _url_for_content_node(node)
        except ContentNode.DoesNotExist:
            return None


class LearnChannelContentItemHook(PermalinkHook):
    """
    redirect to any content item with a given ID within the channel
    """

    param_signature = (PermalinkHook.CONTENT_ID, PermalinkHook.CHANNEL_ID)

    def url(self, params):
        try:
            node = ContentNode.objects.filter(
                channel_id=params[PermalinkHook.CHANNEL_ID],
                content_id=params[PermalinkHook.CONTENT_ID])
            .first()
            return _url_for_content_node(node)
        except ContentNode.DoesNotExist:
            return None


class LearnContentIdHook(PermalinkHook):
    """
    redirect to any item with the given content ID
    """

    param_signature = (PermalinkHook.CHANNEL_ID,)

    def url(self, params):
        try:
            node = ContentNode.objects.filter(content_id=params[PermalinkHook.CONTENT_ID]).first()
            return _url_for_content_node(node)
        except ContentNode.DoesNotExist:
            return None
