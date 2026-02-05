"""Tests for weekly_limit_enabled flag support in pacemaker integration"""

import unittest
import tempfile
import json
import sqlite3
from pathlib import Path
from datetime import datetime
from unittest.mock import patch, MagicMock

from claude_usage.code_mode.pacemaker_integration import PaceMakerReader


class TestPaceMakerReaderWeeklyLimit(unittest.TestCase):
    """Test weekly_limit_enabled flag support in PaceMakerReader"""

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

    def _create_config(self, enabled=True, weekly_limit_enabled=True, **kwargs):
        """Helper to create pace-maker config file"""
        config = {
            "enabled": enabled,
            "weekly_limit_enabled": weekly_limit_enabled,
            "threshold_percent": 0,
            "base_delay": 5,
            "max_delay": 350,
            "safety_buffer_pct": 95.0,
            "preload_hours": 12.0,
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

    def test_config_reading_extracts_weekly_limit_enabled_true(self):
        """Test that config reading extracts weekly_limit_enabled=True"""
        self._create_config(enabled=True, weekly_limit_enabled=True)
        self._create_database_with_usage()

        # Mock the pacing_engine import
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

        with patch.dict(
            "sys.modules",
            {"pacemaker": MagicMock(), "pacemaker.pacing_engine": mock_pacing_module},
        ):
            status = self.reader.get_status()

            # Verify status includes weekly_limit_enabled flag
            self.assertIsNotNone(status)
            self.assertIn("weekly_limit_enabled", status)
            self.assertEqual(status["weekly_limit_enabled"], True)

    def test_config_reading_extracts_weekly_limit_enabled_false(self):
        """Test that config reading extracts weekly_limit_enabled=False"""
        self._create_config(enabled=True, weekly_limit_enabled=False)
        self._create_database_with_usage()

        # Mock the pacing_engine import
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

        with patch.dict(
            "sys.modules",
            {"pacemaker": MagicMock(), "pacemaker.pacing_engine": mock_pacing_module},
        ):
            status = self.reader.get_status()

            # Verify status includes weekly_limit_enabled flag as False
            self.assertIsNotNone(status)
            self.assertIn("weekly_limit_enabled", status)
            self.assertEqual(status["weekly_limit_enabled"], False)

    def test_backward_compatibility_missing_weekly_limit_flag(self):
        """Test backward compatibility when weekly_limit_enabled missing from config"""
        # Create config without weekly_limit_enabled (old config format)
        config = {
            "enabled": True,
            "threshold_percent": 0,
            "base_delay": 5,
            "max_delay": 350,
        }
        with open(self.config_path, "w") as f:
            json.dump(config, f)

        self._create_database_with_usage()

        # Mock the pacing_engine import
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

        with patch.dict(
            "sys.modules",
            {"pacemaker": MagicMock(), "pacemaker.pacing_engine": mock_pacing_module},
        ):
            status = self.reader.get_status()

            # Verify default is True for backward compatibility
            self.assertIsNotNone(status)
            self.assertIn("weekly_limit_enabled", status)
            self.assertEqual(
                status["weekly_limit_enabled"],
                True,
                "Should default to True when missing",
            )


if __name__ == "__main__":
    unittest.main()
