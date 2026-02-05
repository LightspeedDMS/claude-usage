"""Tests for Langfuse metrics and status retrieval from pace-maker database.

Story #34: Langfuse Integration Status and Metrics Display
Tests for:
- Reading 24-hour Langfuse metrics from pace-maker SQLite database
- Checking Langfuse enabled/disabled status from pace-maker config
- Display integration in both status and metrics sections
"""

import json
import os
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

from claude_usage.code_mode.pacemaker_integration import PaceMakerReader


class TestLangfuseMetricsRetrieval(unittest.TestCase):
    """Test cases for get_langfuse_metrics() method"""

    def setUp(self):
        """Set up test fixtures with temporary database"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "usage.db")
        self.config_path = os.path.join(self.temp_dir, "config.json")
        self._initialize_test_database()
        self._create_config()
        self.reader = PaceMakerReader()
        self.reader.pm_dir = Path(self.temp_dir)
        self.reader.db_path = Path(self.db_path)
        self.reader.config_path = Path(self.config_path)

    def tearDown(self):
        """Clean up temporary files"""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _initialize_test_database(self):
        """Initialize test database with langfuse_metrics table"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS langfuse_metrics (
                bucket_timestamp INTEGER PRIMARY KEY,
                sessions_count INTEGER DEFAULT 0,
                traces_count INTEGER DEFAULT 0,
                spans_count INTEGER DEFAULT 0
            )
        """
        )
        conn.commit()
        conn.close()

    def _create_config(self, langfuse_enabled=False):
        """Create test config file"""
        config = {
            "enabled": True,
            "langfuse_enabled": langfuse_enabled,
            "langfuse_public_key": "pk-lf-test" if langfuse_enabled else "",
            "langfuse_secret_key": "sk-lf-test" if langfuse_enabled else "",
        }
        with open(self.config_path, "w") as f:
            json.dump(config, f)

    def _insert_metric_bucket(self, timestamp, sessions=0, traces=0, spans=0):
        """Helper to insert metric bucket into test database"""
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            INSERT INTO langfuse_metrics (bucket_timestamp, sessions_count, traces_count, spans_count)
            VALUES (?, ?, ?, ?)
            """,
            (timestamp, sessions, traces, spans),
        )
        conn.commit()
        conn.close()

    def test_no_metrics_returns_zeros(self):
        """When database is empty, should return all zeros"""
        metrics = self.reader.get_langfuse_metrics()
        self.assertIsNotNone(metrics)
        self.assertEqual(metrics["sessions"], 0)
        self.assertEqual(metrics["traces"], 0)
        self.assertEqual(metrics["spans"], 0)
        self.assertEqual(metrics["total"], 0)

    def test_metrics_within_24h_are_summed(self):
        """Metrics within last 24 hours should be summed correctly"""
        now = time.time()

        # Insert buckets within 24 hours
        self._insert_metric_bucket(
            int(now - 3600), sessions=5, traces=10, spans=20
        )  # 1h ago
        self._insert_metric_bucket(
            int(now - 7200), sessions=3, traces=8, spans=15
        )  # 2h ago
        self._insert_metric_bucket(
            int(now - 43200), sessions=2, traces=5, spans=10
        )  # 12h ago

        metrics = self.reader.get_langfuse_metrics()
        self.assertEqual(metrics["sessions"], 10)  # 5+3+2
        self.assertEqual(metrics["traces"], 23)  # 10+8+5
        self.assertEqual(metrics["spans"], 45)  # 20+15+10
        self.assertEqual(metrics["total"], 78)  # 10+23+45

    def test_metrics_older_than_24h_are_excluded(self):
        """Metrics older than 24 hours should not be included"""
        now = time.time()

        # Insert bucket within 24 hours
        self._insert_metric_bucket(int(now - 3600), sessions=5, traces=10, spans=20)

        # Insert bucket older than 24 hours (should be excluded)
        self._insert_metric_bucket(
            int(now - 86401), sessions=100, traces=200, spans=300
        )

        metrics = self.reader.get_langfuse_metrics()
        self.assertEqual(metrics["sessions"], 5)
        self.assertEqual(metrics["traces"], 10)
        self.assertEqual(metrics["spans"], 20)
        self.assertEqual(metrics["total"], 35)

    def test_database_not_installed_returns_none(self):
        """When database doesn't exist, should return None"""
        self.reader.db_path = Path("/nonexistent/path/usage.db")
        metrics = self.reader.get_langfuse_metrics()
        self.assertIsNone(metrics)

    def test_database_missing_table_returns_none(self):
        """When langfuse_metrics table doesn't exist, should return None"""
        # Drop the table
        conn = sqlite3.connect(self.db_path)
        conn.execute("DROP TABLE IF EXISTS langfuse_metrics")
        conn.commit()
        conn.close()

        metrics = self.reader.get_langfuse_metrics()
        self.assertIsNone(metrics)


class TestLangfuseStatusRetrieval(unittest.TestCase):
    """Test cases for get_langfuse_status() method"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, "config.json")
        self.reader = PaceMakerReader()
        self.reader.pm_dir = Path(self.temp_dir)
        self.reader.config_path = Path(self.config_path)

    def tearDown(self):
        """Clean up temporary files"""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_config(
        self,
        langfuse_enabled=False,
        public_key="",
        secret_key="",
    ):
        """Create test config file with Langfuse settings"""
        config = {
            "enabled": True,
            "langfuse_enabled": langfuse_enabled,
            "langfuse_public_key": public_key,
            "langfuse_secret_key": secret_key,
        }
        with open(self.config_path, "w") as f:
            json.dump(config, f)

    def test_langfuse_disabled_returns_false(self):
        """When langfuse_enabled is False, should return False"""
        self._create_config(langfuse_enabled=False)
        status = self.reader.get_langfuse_status()
        self.assertFalse(status)

    def test_langfuse_enabled_with_keys_returns_true(self):
        """When langfuse_enabled is True and keys are present, should return True"""
        self._create_config(
            langfuse_enabled=True,
            public_key="pk-lf-test-123",
            secret_key="sk-lf-test-456",
        )
        status = self.reader.get_langfuse_status()
        self.assertTrue(status)

    def test_langfuse_enabled_without_public_key_returns_false(self):
        """When public_key is missing, should return False even if enabled"""
        self._create_config(
            langfuse_enabled=True,
            public_key="",
            secret_key="sk-lf-test-456",
        )
        status = self.reader.get_langfuse_status()
        self.assertFalse(status)

    def test_langfuse_enabled_without_secret_key_returns_false(self):
        """When secret_key is missing, should return False even if enabled"""
        self._create_config(
            langfuse_enabled=True,
            public_key="pk-lf-test-123",
            secret_key="",
        )
        status = self.reader.get_langfuse_status()
        self.assertFalse(status)

    def test_config_not_installed_returns_false(self):
        """When config file doesn't exist, should return False"""
        self.reader.config_path = Path("/nonexistent/path/config.json")
        status = self.reader.get_langfuse_status()
        self.assertFalse(status)

    def test_whitespace_only_keys_returns_false(self):
        """When keys are whitespace-only, should return False"""
        self._create_config(
            langfuse_enabled=True,
            public_key="   ",
            secret_key="   ",
        )
        status = self.reader.get_langfuse_status()
        self.assertFalse(status)


if __name__ == "__main__":
    unittest.main()
