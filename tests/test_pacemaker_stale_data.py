"""Tests for stale data handling in pacemaker integration

These tests use the REAL pacemaker module (not mocks) to verify end-to-end
behavior of stale data detection. The pacemaker module is available since
both projects share the same development environment.
"""

import unittest
import tempfile
import json
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta

from claude_usage.code_mode.pacemaker_integration import PaceMakerReader


class TestPaceMakerReaderStaleData(unittest.TestCase):
    """Test stale data detection and handling in PaceMakerReader"""

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
            "weekly_limit_enabled": True,
            "threshold_percent": 0,
            "base_delay": 5,
            "max_delay": 350,
            "safety_buffer_pct": 95.0,
            "preload_hours": 12.0,
        }
        config.update(kwargs)

        with open(self.config_path, "w") as f:
            json.dump(config, f)

    def _create_database_with_stale_usage(self):
        """Helper to create database with STALE usage data (resets_at in past)"""
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

        # Insert usage data with 5-hour reset time in the past (> 5 minutes ago)
        now = datetime.utcnow().timestamp()
        # Set 5-hour reset to 10 minutes ago (stale)
        five_hour_reset = (datetime.utcnow() - timedelta(minutes=10)).isoformat()
        # Set 7-day reset to 3 days from now (valid)
        seven_day_reset = (datetime.utcnow() + timedelta(days=3)).isoformat()

        cursor.execute(
            """
            INSERT INTO usage_snapshots VALUES (?, ?, ?, ?, ?)
        """,
            (now, 65.0, five_hour_reset, 45.0, seven_day_reset),
        )

        conn.commit()
        conn.close()

    def _create_database_with_valid_usage(self):
        """Helper to create database with VALID usage data (resets_at in future)"""
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

        # Insert usage data with valid reset times (in the future)
        now = datetime.utcnow().timestamp()
        # Set 5-hour reset to 2 hours from now (valid)
        five_hour_reset = (datetime.utcnow() + timedelta(hours=2)).isoformat()
        # Set 7-day reset to 3 days from now (valid)
        seven_day_reset = (datetime.utcnow() + timedelta(days=3)).isoformat()

        cursor.execute(
            """
            INSERT INTO usage_snapshots VALUES (?, ?, ?, ?, ?)
        """,
            (now, 65.0, five_hour_reset, 45.0, seven_day_reset),
        )

        conn.commit()
        conn.close()

    def test_stale_data_flag_is_propagated_to_status(self):
        """Test that stale_data flag from pacing_engine is propagated to status"""
        self._create_config(enabled=True)
        self._create_database_with_stale_usage()

        # Get status - should detect stale 5-hour data
        status = self.reader.get_status()

        # Verify status includes stale_data flag
        self.assertIsNotNone(status)
        self.assertIn("stale_data", status)
        self.assertEqual(status["stale_data"], True)
        self.assertIn("error", status)
        self.assertIn("stale", status["error"].lower())

    def test_valid_data_does_not_set_stale_flag(self):
        """Test that valid data does not set stale_data flag"""
        self._create_config(enabled=True)
        self._create_database_with_valid_usage()

        # Get status - should NOT have stale data
        status = self.reader.get_status()

        # Verify status does not have stale_data flag set to True
        self.assertIsNotNone(status)
        self.assertNotEqual(status.get("stale_data"), True)


if __name__ == "__main__":
    unittest.main()
