from kolibri.core.content.hooks import ContentNodeSearchFilterHook
from kolibri.plugins import KolibriPluginBase
from kolibri.plugins.hooks import register_hook


class AiAssistantPlugin(KolibriPluginBase):
    """
    A plugin to provide AI assistant functionality within Kolibri.
    """

    kolibri_options = "options"


@register_hook
class AiAssistantSearchFilterHook(ContentNodeSearchFilterHook):
    @property
    def filter_backend(self):
        try:
            from .api import get_ai_chat_settings
            from .api import LLMContentNodeSearchFilter

            # Ensure settings are valid
            get_ai_chat_settings()
            return LLMContentNodeSearchFilter
        except (ValueError, ImportError):
            return None
