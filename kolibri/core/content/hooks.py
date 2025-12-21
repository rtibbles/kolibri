"""
Kolibri Content hooks
---------------------

Hooks for managing the display and rendering of content.
"""
import json
import logging
from abc import abstractmethod
from abc import abstractproperty

from django.conf import settings
from django.contrib.staticfiles.storage import staticfiles_storage
from django.core.serializers.json import DjangoJSONEncoder
from django.utils.safestring import mark_safe
from importlib_resources import files

from kolibri.core.webpack.hooks import WebpackBundleHook
from kolibri.core.webpack.hooks import WebpackInclusionMixin
from kolibri.plugins.hooks import define_hook
from kolibri.plugins.hooks import KolibriHook


logger = logging.getLogger(__name__)


@define_hook
class ContentRendererHook(WebpackBundleHook, WebpackInclusionMixin):
    """
    An inheritable hook that allows special behaviour for a frontend module that defines
    a content renderer.
    """

    #: Set tuple of format presets that this content renderer can handle
    @abstractproperty
    def presets(self):
        pass

    @classmethod
    def html(cls):
        tags = []
        for hook in cls.registered_hooks:
            tags.append(hook.template_html())
        return mark_safe("\n".join(tags))

    def template_html(self):
        """
        Generates template tags containing data to register a content renderer.

        :returns: HTML of a template tags to insert into a page.
        """
        # Note, while most plugins use sorted chunks to filter by text direction
        # content renderers do not, as they may need to have styling for a different
        # text direction than the interface due to the text direction of content
        urls = [chunk["url"] for chunk in self.bundle]
        tags = (
            self.frontend_message_tag()
            + self.plugin_data_tag()
            + [
                '<template data-viewer="{bundle}">{data}</template>'.format(
                    bundle=self.unique_id,
                    data=json.dumps(
                        {"urls": urls, "presets": self.presets},
                        separators=(",", ":"),
                        ensure_ascii=False,
                        cls=DjangoJSONEncoder,
                    ),
                )
            ]
        )
        return mark_safe("\n".join(tags))


@define_hook
class SandboxedContentRendererHook(ContentRendererHook):
    """
    A content renderer that uses the Kolibri sandbox with a dynamically loaded handler.

    Subclasses must define:
    - bundle_id: The main renderer bundle ID (inherited from WebpackBundleHook)
    - presets: Tuple of format presets this renderer handles (inherited from ContentRendererHook)
    - sandbox_handler_id: The bundle ID of the sandbox handler

    The sandbox handler is built separately with no Kolibri externals and loaded
    dynamically into the sandbox iframe at runtime.
    """

    @abstractproperty
    def sandbox_handler_id(self):
        """
        Bundle ID of the sandbox handler.
        This should match a bundle defined in buildConfig.js with sandbox_handler: true
        """
        pass

    @property
    def sandbox_handler_unique_id(self):
        """Full unique ID for the sandbox handler bundle."""
        return "{}.{}".format(self._module_path, self.sandbox_handler_id)

    def _get_sandbox_handler_stats(self):
        """Load stats file for the sandbox handler bundle."""
        try:
            return json.loads(
                files(self._module_path)
                .joinpath("build")
                .joinpath("{}_stats.json".format(self.sandbox_handler_unique_id))
                .read_text()
            )
        except OSError:
            logger.warning(
                "Could not load sandbox handler stats for %s",
                self.sandbox_handler_unique_id,
            )
            return {}

    @property
    def sandbox_handler_url(self):
        """URL to the built sandbox handler JavaScript file."""
        stats = self._get_sandbox_handler_stats()
        chunks = stats.get("chunks", {}).get(self.sandbox_handler_unique_id, [])

        for chunk in chunks:
            name = chunk.get("name", "")
            if name.endswith(".js"):
                relpath = "{}/{}".format(self.sandbox_handler_unique_id, name)
                if getattr(settings, "DEVELOPER_MODE", False):
                    try:
                        url = chunk.get("publicPath")
                        if url and not url.startswith("auto"):
                            return url
                    except KeyError:
                        pass
                return staticfiles_storage.url(relpath)

        return None

    def template_html(self):
        """
        Generates template tags containing data to register a content renderer.
        Extends parent to include sandbox handler URL.

        :returns: HTML of template tags to insert into a page.
        """
        urls = [chunk["url"] for chunk in self.bundle]

        viewer_data = {
            "urls": urls,
            "presets": self.presets,
        }

        # Add sandbox handler URL if available
        handler_url = self.sandbox_handler_url
        if handler_url:
            viewer_data["sandboxHandlerUrl"] = handler_url

        tags = (
            self.frontend_message_tag()
            + self.plugin_data_tag()
            + [
                '<template data-viewer="{bundle}">{data}</template>'.format(
                    bundle=self.unique_id,
                    data=json.dumps(
                        viewer_data,
                        separators=(",", ":"),
                        ensure_ascii=False,
                        cls=DjangoJSONEncoder,
                    ),
                )
            ]
        )
        return mark_safe("\n".join(tags))


@define_hook
class ContentNodeDisplayHook(KolibriHook):
    """
    A hook that registers a capability of a plugin to provide a user interface
    for a content node. When subclassed, this hook should expose a method that
    accepts a ContentNode instance as an argument, and returns a URL where the
    interface to interacting with that node for the user is exposed.
    If this plugin cannot produce an interface for this particular content node
    then it may return None.
    """

    @abstractmethod
    def node_url(self, content_node):
        pass
