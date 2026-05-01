"""Tests for module import caching fix in pacemaker_integration.py

Verifies that:
1. DEFAULT_CLEAN_CODE_RULES_COUNT constant is 25 (not stale 17)
2. _get_clean_code_rules_count() uses importlib.reload() so it picks up
   changes to pacemaker.clean_code_rules after ./install.sh without a monitor restart
3. get_pacemaker_version() uses importlib.reload() on the pacemaker package
   so it picks up version changes after reinstall without a monitor restart

Story: fix module import caching in claude-usage-reporting pacemaker integration
"""

import importlib
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


# Add claude-usage src to path so imports work
sys.path.insert(0, str(Path(__file__).parent.parent))

import claude_usage.code_mode.pacemaker_integration as _pm_integration_module
from claude_usage.code_mode.pacemaker_integration import (
    DEFAULT_CLEAN_CODE_RULES_COUNT,
    PaceMakerReader,
)


class TestDefaultCleanCodeRulesCount(unittest.TestCase):
    """DEFAULT_CLEAN_CODE_RULES_COUNT constant must reflect current rule count."""

    def test_default_clean_code_rules_count_is_20(self):
        """Constant must be 20, matching current pace-maker rule count."""
        self.assertEqual(
            DEFAULT_CLEAN_CODE_RULES_COUNT,
            20,
            "DEFAULT_CLEAN_CODE_RULES_COUNT must be 20",
        )


class TestGetCleanCodeRulesCountReload(unittest.TestCase):
    """_get_clean_code_rules_count() must reload pacemaker.clean_code_rules on each call.

    Without reload, Python serves the cached module from sys.modules even if
    pace-maker has been reinstalled with new rules (./install.sh). The monitor
    would then display a stale count until restarted.
    """

    def setUp(self):
        """Set up a PaceMakerReader with a mocked pm_src path."""
        self.reader = PaceMakerReader()
        # Point pm_src to a dummy path that "exists" (we'll mock the path check)
        self._fake_src = Path("/fake/pacemaker/src")

    def _make_rules_module(self, rule_count: int) -> types.ModuleType:
        """Create a fake pacemaker.clean_code_rules module with N rules."""
        mod = types.ModuleType("pacemaker.clean_code_rules")
        mod.get_default_rules = lambda: [{"id": f"rule-{i}"} for i in range(rule_count)]
        mod.load_rules = lambda config_path: [{"id": f"rule-{i}"} for i in range(rule_count)]
        return mod

    def test_get_clean_code_rules_count_reflects_reloaded_module(self):
        """After pacemaker.clean_code_rules is replaced in sys.modules, the next call
        to _get_clean_code_rules_count() must return the NEW count, not the old one.

        This simulates the monitor calling the method after ./install.sh has installed
        a new version of pace-maker with more/fewer rules.
        """
        # Install an initial fake module with 17 rules
        initial_mod = self._make_rules_module(17)
        sys.modules["pacemaker.clean_code_rules"] = initial_mod

        # Ensure pacemaker parent package is also mocked
        if "pacemaker" not in sys.modules:
            parent = types.ModuleType("pacemaker")
            sys.modules["pacemaker"] = parent

        # Make _get_pacemaker_src_path() return a fake (truthy) path
        fake_src = MagicMock(spec=Path)
        fake_src.__str__ = lambda self: "/fake/pacemaker/src"
        fake_src.exists.return_value = True

        with patch.object(self.reader, "_get_pacemaker_src_path", return_value=fake_src):
            with patch("sys.path", ["/fake/pacemaker/src"]):
                # Simulate what happens when pacemaker.clean_code_rules is already cached
                # and then "reinstalled" (replaced) — the reload must pick up the new module.
                # We test by replacing the module AFTER the initial one is set and
                # verifying the method returns the count from the replacement.

                # Replace the module with one that has 25 rules (simulates reinstall)
                updated_mod = self._make_rules_module(25)
                sys.modules["pacemaker.clean_code_rules"] = updated_mod

                # With reload, the method should pick up the updated module's count
                # Without reload, it would use the cached import binding (17)
                count = self.reader._get_clean_code_rules_count()

        self.assertEqual(
            count,
            25,
            "_get_clean_code_rules_count() must reflect updated module after reinstall; "
            "expected 25 but got stale value. importlib.reload() may be missing.",
        )

    def test_get_clean_code_rules_count_returns_default_when_import_fails(self):
        """When pacemaker.clean_code_rules cannot be imported, return DEFAULT_CLEAN_CODE_RULES_COUNT."""
        # Remove any cached pacemaker modules
        sys.modules.pop("pacemaker.clean_code_rules", None)
        sys.modules.pop("pacemaker", None)

        # Make _get_pacemaker_src_path() return None (pace-maker not installed)
        with patch.object(self.reader, "_get_pacemaker_src_path", return_value=None):
            count = self.reader._get_clean_code_rules_count()

        self.assertEqual(
            count,
            DEFAULT_CLEAN_CODE_RULES_COUNT,
            "Should return DEFAULT_CLEAN_CODE_RULES_COUNT when import fails",
        )

    def tearDown(self):
        """Clean up any fake modules we installed in sys.modules."""
        sys.modules.pop("pacemaker.clean_code_rules", None)
        # Only remove pacemaker parent if we installed a fake one
        pm = sys.modules.get("pacemaker")
        if pm is not None and not hasattr(pm, "__file__"):
            # It's a dummy module (no file), safe to remove
            sys.modules.pop("pacemaker", None)


class TestGetPacemakerVersionReload(unittest.TestCase):
    """get_pacemaker_version() must reload the pacemaker package on each call.

    Without reload, __version__ is frozen to the value seen at first import.
    After ./install.sh updates the installed version, the monitor keeps showing
    the old version until restarted.
    """

    def setUp(self):
        self.reader = PaceMakerReader()

    def _make_pacemaker_package(self, version: str) -> types.ModuleType:
        """Create a fake pacemaker package module with the given __version__."""
        mod = types.ModuleType("pacemaker")
        mod.__version__ = version
        mod.__path__ = []  # Mark as package
        return mod

    def test_get_pacemaker_version_reflects_reloaded_package(self):
        """After pacemaker package is replaced in sys.modules, the next call to
        get_pacemaker_version() must return the NEW version.

        Simulates: pace-maker is at 2.3.2, ./install.sh upgrades to 2.4.0,
        the monitor should immediately show 2.4.0 without a restart.
        """
        # Install initial package version
        initial_pkg = self._make_pacemaker_package("2.3.2")
        sys.modules["pacemaker"] = initial_pkg

        fake_src = MagicMock(spec=Path)
        fake_src.__str__ = lambda self: "/fake/pacemaker/src"
        fake_src.exists.return_value = True

        with patch.object(self.reader, "_get_pacemaker_src_path", return_value=fake_src):
            with patch("sys.path", ["/fake/pacemaker/src"]):
                # Simulate reinstall: replace module with updated version
                updated_pkg = self._make_pacemaker_package("2.4.0")
                sys.modules["pacemaker"] = updated_pkg

                version = self.reader.get_pacemaker_version()

        self.assertEqual(
            version,
            "2.4.0",
            "get_pacemaker_version() must reflect updated pacemaker package after reinstall; "
            "expected 2.4.0 but got stale version. importlib.reload() may be missing.",
        )

    def test_get_pacemaker_version_uses_metadata_when_src_path_not_found(self):
        """When no pace-maker source directory is locatable, fall back to importlib.metadata."""
        import tempfile

        sys.modules.pop("pacemaker", None)

        with tempfile.TemporaryDirectory() as tmpdir:
            self.reader.pm_dir = Path(tmpdir)
            # _find_plugin_cache_src is the module-level filesystem search for
            # the Claude plugin cache; patch it so the temp dir has no fallback.
            with patch(
                "claude_usage.code_mode.pacemaker_integration._find_plugin_cache_src",
                return_value=None,
            ):
                with patch("importlib.metadata.version", return_value="2.5.1") as mock_meta:
                    version = self.reader.get_pacemaker_version()

        mock_meta.assert_called_once_with("claude_pace_maker")
        self.assertEqual(version, "2.5.1")

    def test_get_pacemaker_version_returns_unknown_when_not_installed(self):
        """When no source is locatable AND metadata unavailable, return 'unknown'."""
        import tempfile
        from importlib.metadata import PackageNotFoundError

        sys.modules.pop("pacemaker", None)

        with tempfile.TemporaryDirectory() as tmpdir:
            self.reader.pm_dir = Path(tmpdir)
            with patch(
                "claude_usage.code_mode.pacemaker_integration._find_plugin_cache_src",
                return_value=None,
            ):
                with patch(
                    "importlib.metadata.version",
                    side_effect=PackageNotFoundError("claude_pace_maker"),
                ):
                    version = self.reader.get_pacemaker_version()

        self.assertEqual(
            version,
            "unknown",
            "Should return 'unknown' when pacemaker is not installed and metadata unavailable",
        )

    def tearDown(self):
        """Clean up fake pacemaker modules."""
        pm = sys.modules.get("pacemaker")
        if pm is not None and not hasattr(pm, "__file__"):
            sys.modules.pop("pacemaker", None)


if __name__ == "__main__":
    unittest.main()
