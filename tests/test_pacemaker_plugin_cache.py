"""Tests for plugin cache discovery in pacemaker source path resolution"""

import unittest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch

from claude_usage.code_mode.pacemaker_integration import (
    PaceMakerReader,
    _find_plugin_cache_src,
)


class PluginCacheTestBase(unittest.TestCase):
    """Shared setup for plugin cache tests"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.claude_dir = Path(self.temp_dir) / ".claude"

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def create_plugin_version(self, version: str) -> Path:
        """Create a plugin cache version directory with src/pacemaker"""
        src_dir = (
            self.claude_dir
            / "plugins"
            / "cache"
            / "lightspeed-claude-plugins"
            / "claude-pace-maker"
            / version
            / "src"
        )
        pacemaker_pkg = src_dir / "pacemaker"
        pacemaker_pkg.mkdir(parents=True)
        (pacemaker_pkg / "__init__.py").touch()
        return src_dir


class TestFindPluginCacheSrc(PluginCacheTestBase):
    """Test _find_plugin_cache_src helper function"""

    def test_finds_single_version(self):
        """Should find src in a single plugin cache version"""
        src = self.create_plugin_version("2.18.0")
        result = _find_plugin_cache_src(self.claude_dir)
        self.assertEqual(result, src)

    def test_picks_latest_version(self):
        """Should pick the highest semver version when multiple exist"""
        self.create_plugin_version("2.9.0")
        self.create_plugin_version("2.9.1")
        self.create_plugin_version("2.14.0")
        self.create_plugin_version("2.17.0")
        expected = self.create_plugin_version("2.18.0")

        result = _find_plugin_cache_src(self.claude_dir)
        self.assertEqual(result, expected)

    def test_returns_none_when_no_plugin_dir(self):
        """Should return None when plugin cache directory doesn't exist"""
        result = _find_plugin_cache_src(self.claude_dir)
        self.assertIsNone(result)

    def test_returns_none_when_no_src_dir(self):
        """Should return None when version exists but has no src directory"""
        version_dir = (
            self.claude_dir
            / "plugins"
            / "cache"
            / "lightspeed-claude-plugins"
            / "claude-pace-maker"
            / "2.18.0"
        )
        version_dir.mkdir(parents=True)
        result = _find_plugin_cache_src(self.claude_dir)
        self.assertIsNone(result)

    def test_skips_non_semver_directories(self):
        """Should skip directories that aren't valid version numbers"""
        plugin_base = (
            self.claude_dir
            / "plugins"
            / "cache"
            / "lightspeed-claude-plugins"
            / "claude-pace-maker"
        )
        bad_dir = plugin_base / "temp-backup" / "src" / "pacemaker"
        bad_dir.mkdir(parents=True)
        (bad_dir / "__init__.py").touch()

        expected = self.create_plugin_version("1.0.0")

        result = _find_plugin_cache_src(self.claude_dir)
        self.assertEqual(result, expected)

    def test_handles_two_segment_versions(self):
        """Should handle version strings with only major.minor"""
        self.create_plugin_version("2.9")
        expected = self.create_plugin_version("2.18.0")

        result = _find_plugin_cache_src(self.claude_dir)
        self.assertEqual(result, expected)


class TestGetPacemakerSrcPathPluginFallback(PluginCacheTestBase):
    """Test that _get_pacemaker_src_path falls back to plugin cache"""

    def setUp(self):
        super().setUp()
        self.pm_dir = Path(self.temp_dir) / ".claude-pace-maker"
        self.pm_dir.mkdir(parents=True)

        self.reader = PaceMakerReader()
        self.reader.pm_dir = self.pm_dir
        self.reader.config_path = self.pm_dir / "config.json"
        self.reader.db_path = self.pm_dir / "usage.db"

    def test_plugin_cache_used_when_install_source_and_src_missing(self):
        """Should fall back to plugin cache when install_source and pm_dir/src don't exist"""
        expected = self.create_plugin_version("2.18.0")

        with patch("pathlib.Path.home", return_value=Path(self.temp_dir)):
            result = self.reader._get_pacemaker_src_path()

        self.assertEqual(result, expected)

    def test_install_source_takes_priority_over_plugin_cache(self):
        """install_source should be preferred over plugin cache"""
        dev_src = Path(self.temp_dir) / "dev" / "claude-pace-maker" / "src"
        dev_src.mkdir(parents=True)
        (self.pm_dir / "install_source").write_text(str(dev_src.parent))

        self.create_plugin_version("2.18.0")

        with patch("pathlib.Path.home", return_value=Path(self.temp_dir)):
            result = self.reader._get_pacemaker_src_path()

        self.assertEqual(result, dev_src)

    def test_returns_none_when_nothing_found(self):
        """Should return None when no source path is available anywhere"""
        with patch("pathlib.Path.home", return_value=Path(self.temp_dir)):
            result = self.reader._get_pacemaker_src_path()

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
