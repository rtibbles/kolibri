from kolibri.core.hooks import FrontEndBaseSyncHook
from kolibri.core.webpack import hooks as webpack_hooks

from kolibri.plugins import KolibriPluginBase
from kolibri.plugins.hooks import register_hook


class AiAssistantPlugin(KolibriPluginBase):
    """
    A plugin to provide AI assistant functionality within Kolibri.
    """

    untranslated_view_urls = "api_urls"
    kolibri_options = "options"


@register_hook
class AiAssistantAsset(webpack_hooks.WebpackBundleHook):
    bundle_id = "main"


@register_hook
class InclusionHook(FrontEndBaseSyncHook):
    bundle_class = AiAssistantAsset
