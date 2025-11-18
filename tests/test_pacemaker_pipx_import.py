"""Tests for pipx installation detection and import in pacemaker integration"""

import unittest
import tempfile
import json
import sqlite3
import sys
from pathlib import Path
from datetime import datetime
from unittest.mock import patch, MagicMock

from claude_usage.code_mode.pacemaker_integration import PaceMakerReader


class TestPaceMakerPipxImport(unittest.TestCase):
    """Test pipx installation detection and module import"""

    def setUp(self):
        """Set up test fixtures"""
        # Create temporary directory for pace-maker files
        self.temp_dir = tempfile.mkdtemp()
        self.pm_dir = Path(self.temp_dir) / ".claude-pace-maker"
        self.pm_dir.mkdir(parents=True)

        self.config_path = self.pm_dir / "config.json"
        self.db_path = self.pm_dir / "usage.db"

        # Create reader with mocked paths
        self.reader = PaceMakerReader()
        self.reader.pm_dir = self.pm_dir
        self.reader.config_path = self.config_path
        self.reader.db_path = self.db_path

    def tearDown(self):
        """Clean up test fixtures"""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_config(self, enabled=True, **kwargs):
        """Helper to create pace-maker config file"""
        config = {
            "enabled": enabled,
            "threshold_percent": 0,
            "base_delay": 5,
            "max_delay": 350,
            "safety_buffer_pct": 95.0,
            "preload_hours": 12.0,
            "weekly_limit_enabled": True,
        }
        config.update(kwargs)

        with open(self.config_path, "w") as f:
            json.dump(config, f)

    def _create_database_with_usage(self):
        """Helper to create database with usage data"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE usage_snapshots (
                timestamp REAL PRIMARY KEY,
                five_hour_util REAL,
                five_hour_resets_at TEXT,
                seven_day_util REAL,
                seven_day_resets_at TEXT
            )
        """
        )

        # Insert sample usage data
        now = datetime.utcnow().timestamp()
        five_hour_reset = datetime.utcnow().isoformat()
        seven_day_reset = datetime.utcnow().isoformat()

        cursor.execute(
            """
            INSERT INTO usage_snapshots VALUES (?, ?, ?, ?, ?)
        """,
            (now, 65.0, five_hour_reset, 45.0, seven_day_reset),
        )

        conn.commit()
        conn.close()

    def test_detect_pipx_installation_from_install_source(self):
        """Test that pipx installation is detected from install_source path"""
        # Create install_source file with pipx path
        install_source_file = self.pm_dir / "install_source"
        pipx_path = "/home/user/.local/share/pipx/venvs/claude-pace-maker/share/claude-pace-maker"
        with open(install_source_file, "w") as f:
            f.write(pipx_path)

        # This is a unit test for the detection logic
        # We'll extract this to a helper method in the implementation
        from claude_usage.code_mode.pacemaker_integration import (
            _is_pipx_installation,
        )

        self.assertTrue(
            _is_pipx_installation(pipx_path),
            "Should detect pipx installation from path containing .local/share/pipx/venvs/",
        )

    def test_non_pipx_installation_not_detected(self):
        """Test that non-pipx installations are not detected as pipx"""
        # Test various non-pipx paths
        from claude_usage.code_mode.pacemaker_integration import (
            _is_pipx_installation,
        )

        non_pipx_paths = [
            "/usr/local/lib/python3.9/site-packages",
            "/home/user/projects/claude-pace-maker",
            "/opt/pace-maker/src",
            "/home/user/.local/lib/python3.9/site-packages",  # Not pipx venv
        ]

        for path in non_pipx_paths:
            with self.subTest(path=path):
                self.assertFalse(
                    _is_pipx_installation(path),
                    f"Should not detect {path} as pipx installation",
                )

    def test_find_site_packages_in_pipx_venv(self):
        """Test finding site-packages directory in pipx venv structure"""
        # Create mock pipx venv structure
        pipx_venv = Path(self.temp_dir) / ".local/share/pipx/venvs/claude-pace-maker"
        share_dir = pipx_venv / "share" / "claude-pace-maker"
        lib_dir = pipx_venv / "lib" / "python3.9" / "site-packages"

        share_dir.mkdir(parents=True)
        lib_dir.mkdir(parents=True)

        # Test site-packages discovery
        from claude_usage.code_mode.pacemaker_integration import (
            _find_pipx_site_packages,
        )

        site_packages = _find_pipx_site_packages(str(share_dir))
        self.assertIsNotNone(site_packages, "Should find site-packages directory")
        self.assertEqual(
            Path(site_packages),
            lib_dir,
            "Should return correct site-packages path",
        )

    def test_find_site_packages_handles_multiple_python_versions(self):
        """Test that site-packages finder works with different Python versions"""
        # Create venv with python3.11 (different from current 3.9)
        pipx_venv = Path(self.temp_dir) / ".local/share/pipx/venvs/claude-pace-maker"
        share_dir = pipx_venv / "share" / "claude-pace-maker"
        lib_dir = pipx_venv / "lib" / "python3.11" / "site-packages"

        share_dir.mkdir(parents=True)
        lib_dir.mkdir(parents=True)

        from claude_usage.code_mode.pacemaker_integration import (
            _find_pipx_site_packages,
        )

        site_packages = _find_pipx_site_packages(str(share_dir))
        self.assertIsNotNone(
            site_packages, "Should find site-packages for any Python version"
        )
        self.assertEqual(Path(site_packages), lib_dir)

    def test_site_packages_not_found_returns_none(self):
        """Test that None is returned when site-packages directory doesn't exist"""
        # Create incomplete venv structure (no lib directory)
        pipx_venv = Path(self.temp_dir) / ".local/share/pipx/venvs/claude-pace-maker"
        share_dir = pipx_venv / "share" / "claude-pace-maker"
        share_dir.mkdir(parents=True)

        from claude_usage.code_mode.pacemaker_integration import (
            _find_pipx_site_packages,
        )

        site_packages = _find_pipx_site_packages(str(share_dir))
        self.assertIsNone(
            site_packages, "Should return None when site-packages not found"
        )

    def test_integration_pipx_import_with_mocked_venv(self):
        """Integration test: Import from pipx venv structure"""
        self._create_config(enabled=True)
        self._create_database_with_usage()

        # Create mock pipx venv structure
        pipx_venv = Path(self.temp_dir) / ".local/share/pipx/venvs/claude-pace-maker"
        share_dir = pipx_venv / "share" / "claude-pace-maker"
        lib_dir = pipx_venv / "lib" / "python3.9" / "site-packages"
        pacemaker_dir = lib_dir / "pacemaker"

        share_dir.mkdir(parents=True)
        pacemaker_dir.mkdir(parents=True)

        # Create install_source pointing to share directory
        install_source_file = self.pm_dir / "install_source"
        with open(install_source_file, "w") as f:
            f.write(str(share_dir))

        # Mock the pacing_engine module
        mock_pacing_module = MagicMock()
        mock_pacing_module.calculate_pacing_decision.return_value = {
            "five_hour": {
                "utilization": 65.0,
                "target": 50.0,
                "time_elapsed_pct": 40.0,
            },
            "seven_day": {
                "utilization": 45.0,
                "target": 40.0,
                "time_elapsed_pct": 30.0,
            },
            "constrained_window": "5-hour",
            "deviation_percent": 15.0,
            "should_throttle": True,
            "delay_seconds": 10,
            "algorithm": "adaptive",
            "strategy": "preload",
        }

        # Test that import works with pipx venv structure
        with patch.dict(
            "sys.modules",
            {"pacemaker": MagicMock(), "pacemaker.pacing_engine": mock_pacing_module},
        ):
            status = self.reader.get_status()

            # Verify successful import and status retrieval
            self.assertIsNotNone(status)
            self.assertTrue(status.get("has_data", False))
            self.assertIn("five_hour", status)
            self.assertIn("seven_day", status)
            self.assertNotIn("error", status, "Should not have import error")

    def test_fallback_to_src_when_not_pipx(self):
        """Test that code falls back to src/ directory when not pipx installation"""
        self._create_config(enabled=True)
        self._create_database_with_usage()

        # Create install_source with non-pipx path
        install_source_file = self.pm_dir / "install_source"
        dev_path = Path(self.temp_dir) / "dev" / "claude-pace-maker"
        src_dir = dev_path / "src"
        src_dir.mkdir(parents=True)

        with open(install_source_file, "w") as f:
            f.write(str(dev_path))

        # Mock the pacing_engine module
        mock_pacing_module = MagicMock()
        mock_pacing_module.calculate_pacing_decision.return_value = {
            "five_hour": {"utilization": 65.0, "target": 50.0, "time_elapsed_pct": 40.0},
            "seven_day": {"utilization": 45.0, "target": 40.0, "time_elapsed_pct": 30.0},
            "constrained_window": "5-hour",
            "deviation_percent": 15.0,
            "should_throttle": True,
            "delay_seconds": 10,
            "algorithm": "adaptive",
            "strategy": "preload",
        }

        with patch.dict(
            "sys.modules",
            {"pacemaker": MagicMock(), "pacemaker.pacing_engine": mock_pacing_module},
        ):
            status = self.reader.get_status()

            # Should work with src fallback
            self.assertIsNotNone(status)
            self.assertTrue(status.get("has_data", False))

    def test_import_error_handling_still_works(self):
        """Test that import errors are still caught and handled gracefully"""
        self._create_config(enabled=True)
        self._create_database_with_usage()

        # Create install_source with pipx path but don't mock import
        install_source_file = self.pm_dir / "install_source"
        pipx_path = "/home/user/.local/share/pipx/venvs/claude-pace-maker/share/claude-pace-maker"
        with open(install_source_file, "w") as f:
            f.write(pipx_path)

        # Remove any existing pacemaker modules from sys.modules
        sys.modules.pop("pacemaker", None)
        sys.modules.pop("pacemaker.pacing_engine", None)

        # This should trigger ImportError which should be caught
        status = self.reader.get_status()

        # Verify error is handled gracefully
        self.assertIsNotNone(status)
        self.assertTrue(status.get("has_data", False))
        self.assertIn("error", status)
        self.assertEqual(status["error"], "Cannot import pace-maker modules")


if __name__ == "__main__":
    unittest.main()
