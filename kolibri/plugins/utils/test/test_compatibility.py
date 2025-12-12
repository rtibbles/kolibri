import pytest
from unittest.mock import patch, MagicMock

import kolibri
from kolibri.plugins.utils import (
    get_plugin_kolibri_requirement,
    compute_plugin_compatibility,
    get_plugin_compatibility,
)


class TestGetPluginKolibriRequirement:
    def test_returns_none_for_internal_plugin(self):
        """Internal plugins (kolibri.*) should return None."""
        result = get_plugin_kolibri_requirement("kolibri.plugins.learn")
        assert result is None

    def test_returns_none_when_no_kolibri_dependency(self):
        """Plugins without kolibri in Requires-Dist should return None."""
        mock_dist = MagicMock()
        mock_dist.requires = ["django>=3.0", "requests"]

        with patch(
            "kolibri.plugins.utils.distribution", return_value=mock_dist
        ):
            result = get_plugin_kolibri_requirement("external_plugin")

        assert result is None

    def test_extracts_simple_requirement(self):
        """Should extract simple version specifier."""
        mock_dist = MagicMock()
        mock_dist.requires = ["kolibri>=1.0,<2.0"]

        with patch(
            "kolibri.plugins.utils.distribution", return_value=mock_dist
        ):
            result = get_plugin_kolibri_requirement("external_plugin")

        assert result == ">=1.0,<2.0"

    def test_extracts_requirement_with_extras(self):
        """Should handle extras in requirement (e.g., kolibri[dev]>=1.0)."""
        mock_dist = MagicMock()
        mock_dist.requires = ["kolibri[dev]>=1.0"]

        with patch(
            "kolibri.plugins.utils.distribution", return_value=mock_dist
        ):
            result = get_plugin_kolibri_requirement("external_plugin")

        assert result == ">=1.0"

    def test_extracts_requirement_ignoring_markers(self):
        """Should ignore environment markers."""
        mock_dist = MagicMock()
        mock_dist.requires = ['kolibri>=1.0; python_version>="3.8"']

        with patch(
            "kolibri.plugins.utils.distribution", return_value=mock_dist
        ):
            result = get_plugin_kolibri_requirement("external_plugin")

        assert result == ">=1.0"

    def test_returns_none_on_package_not_found(self):
        """Should return None if package metadata cannot be read."""
        from importlib.metadata import PackageNotFoundError

        with patch(
            "kolibri.plugins.utils.distribution",
            side_effect=PackageNotFoundError("not found"),
        ):
            result = get_plugin_kolibri_requirement("nonexistent_plugin")

        assert result is None


class TestComputePluginCompatibility:
    def test_compatible_when_no_requirement(self):
        """Plugins without requirements should be compatible."""
        with patch(
            "kolibri.plugins.utils.get_plugin_kolibri_requirement",
            return_value=None,
        ):
            compatible, requirement = compute_plugin_compatibility("some_plugin")

        assert compatible is True
        assert requirement is None

    def test_compatible_when_version_in_range(self):
        """Should be compatible when current version satisfies requirement."""
        with patch(
            "kolibri.plugins.utils.get_plugin_kolibri_requirement",
            return_value=">=1.0,<2.0",
        ), patch.object(kolibri, "__version__", "1.5.0"):
            compatible, requirement = compute_plugin_compatibility("some_plugin")

        assert compatible is True
        assert requirement == ">=1.0,<2.0"

    def test_incompatible_when_version_out_of_range(self):
        """Should be incompatible when current version doesn't satisfy requirement."""
        with patch(
            "kolibri.plugins.utils.get_plugin_kolibri_requirement",
            return_value=">=1.0,<2.0",
        ), patch.object(kolibri, "__version__", "2.1.0"):
            compatible, requirement = compute_plugin_compatibility("some_plugin")

        assert compatible is False
        assert requirement == ">=1.0,<2.0"

    def test_compatible_on_invalid_specifier(self):
        """Should assume compatible if specifier is malformed."""
        with patch(
            "kolibri.plugins.utils.get_plugin_kolibri_requirement",
            return_value="not-a-valid-specifier",
        ):
            compatible, requirement = compute_plugin_compatibility("some_plugin")

        assert compatible is True
        assert requirement == "not-a-valid-specifier"


class TestGetPluginCompatibility:
    def test_uses_cached_value_when_available(self):
        """Should return cached value without recomputing."""
        with patch("kolibri.plugins.utils.config") as mock_config:
            mock_config.needs_compatibility_recheck.return_value = False
            mock_config.get.return_value = {
                "some_plugin": {"compatible": False, "requirement": ">=2.0"}
            }

            compatible, requirement = get_plugin_compatibility("some_plugin")

        assert compatible is False
        assert requirement == ">=2.0"

    def test_recomputes_when_needed(self):
        """Should recompute and cache when recheck is needed."""
        with patch("kolibri.plugins.utils.config") as mock_config, patch(
            "kolibri.plugins.utils.compute_plugin_compatibility",
            return_value=(True, ">=1.0"),
        ) as mock_compute:
            mock_config.needs_compatibility_recheck.return_value = True

            compatible, requirement = get_plugin_compatibility("some_plugin")

        assert compatible is True
        assert requirement == ">=1.0"
        mock_compute.assert_called_once_with("some_plugin")
        mock_config.update_compatibility.assert_called_once_with(
            "some_plugin", True, ">=1.0"
        )


class TestConfigDictCompatibilityMethods:
    """Tests for the new ConfigDict methods."""

    def test_needs_recheck_when_kolibri_version_changed(self):
        """Should need recheck when Kolibri version differs from stored."""
        from kolibri.plugins import ConfigDict

        config = ConfigDict.__new__(ConfigDict)
        dict.__init__(config)
        config["KOLIBRI_VERSION"] = "1.0.0"
        config["PLUGIN_COMPATIBILITY"] = {"plugin": {"compatible": True}}
        config["UPDATED_PLUGINS"] = set()

        with patch("kolibri.__version__", "2.0.0"):
            assert config.needs_compatibility_recheck("plugin") is True

    def test_needs_recheck_when_plugin_updated(self):
        """Should need recheck when plugin is in UPDATED_PLUGINS."""
        from kolibri.plugins import ConfigDict

        config = ConfigDict.__new__(ConfigDict)
        dict.__init__(config)
        config["KOLIBRI_VERSION"] = "1.0.0"
        config["PLUGIN_COMPATIBILITY"] = {"plugin": {"compatible": True}}
        config["UPDATED_PLUGINS"] = {"plugin"}

        with patch("kolibri.__version__", "1.0.0"):
            assert config.needs_compatibility_recheck("plugin") is True

    def test_needs_recheck_when_plugin_not_cached(self):
        """Should need recheck when plugin has no cached compatibility."""
        from kolibri.plugins import ConfigDict

        config = ConfigDict.__new__(ConfigDict)
        dict.__init__(config)
        config["KOLIBRI_VERSION"] = "1.0.0"
        config["PLUGIN_COMPATIBILITY"] = {}
        config["UPDATED_PLUGINS"] = set()

        with patch("kolibri.__version__", "1.0.0"):
            assert config.needs_compatibility_recheck("new_plugin") is True

    def test_no_recheck_when_cached_and_current(self):
        """Should not need recheck when cached and versions match."""
        from kolibri.plugins import ConfigDict

        config = ConfigDict.__new__(ConfigDict)
        dict.__init__(config)
        config["KOLIBRI_VERSION"] = "1.0.0"
        config["PLUGIN_COMPATIBILITY"] = {"plugin": {"compatible": True}}
        config["UPDATED_PLUGINS"] = set()

        with patch("kolibri.__version__", "1.0.0"):
            assert config.needs_compatibility_recheck("plugin") is False
