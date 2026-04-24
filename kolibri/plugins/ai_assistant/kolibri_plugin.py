import logging

from kolibri.core.content.hooks import ContentNodeSearchFilterHook
from kolibri.plugins import KolibriPluginBase
from kolibri.plugins.hooks import register_hook


logger = logging.getLogger(__name__)


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
            from .api import LLMContentNodeSearchFilter
            from .llm import get_ai_chat_settings

            # Ensure settings are valid
            get_ai_chat_settings()
            return LLMContentNodeSearchFilter
        except (ValueError, ImportError):
            logger.exception(
                "Failed to load AI assistant search filter; falling back to default backend"
            )
            return None
