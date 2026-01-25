"""Tests for blockage statistics retrieval from pace-maker database.

Story #23: Monitor Two-Column Layout with Blockage Dashboard
AC3: Column 2 - Blockage Statistics
"""

import os
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

from claude_usage.code_mode.pacemaker_integration import PaceMakerReader


class TestBlockageStatsRetrieval(unittest.TestCase):
    """Test cases for get_blockage_stats() method - basic functionality"""

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
        """Initialize test database with blockage_events table"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS blockage_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp INTEGER NOT NULL,
                category TEXT NOT NULL,
                reason TEXT NOT NULL,
                hook_type TEXT NOT NULL,
                session_id TEXT NOT NULL
            )
        """)
        conn.commit()
        conn.close()

    def _create_config(self):
        """Create minimal config file"""
        import json
        with open(self.config_path, "w") as f:
            json.dump({"enabled": True}, f)

    def _insert_blockage_event(self, category: str, minutes_ago: int = 0):
        """Insert a test blockage event"""
        timestamp = int(time.time()) - (minutes_ago * 60)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO blockage_events (timestamp, category, reason, hook_type, session_id) "
            "VALUES (?, ?, 'test', 'pre_tool_use', 'test-session')",
            (timestamp, category),
        )
        conn.commit()
        conn.close()

    def test_get_blockage_stats_returns_dict_with_all_categories(self):
        """Test that get_blockage_stats returns dict with all blockage categories"""
        result = self.reader.get_blockage_stats()
        self.assertIsInstance(result, dict)
        expected = ["intent_validation", "intent_validation_tdd", "pacing_tempo", "pacing_quota", "other"]
        for category in expected:
            self.assertIn(category, result)

    def test_get_blockage_stats_returns_zero_counts_when_no_events(self):
        """Test that counts are zero when no blockage events exist"""
        result = self.reader.get_blockage_stats()
        for category, count in result.items():
            if category != "total":
                self.assertEqual(count, 0)

    def test_get_blockage_stats_counts_events_in_last_hour(self):
        """Test that events from the last 60 minutes are counted"""
        self._insert_blockage_event("intent_validation", minutes_ago=5)
        self._insert_blockage_event("intent_validation", minutes_ago=30)
        self._insert_blockage_event("pacing_quota", minutes_ago=45)
        result = self.reader.get_blockage_stats()
        self.assertEqual(result["intent_validation"], 2)
        self.assertEqual(result["pacing_quota"], 1)


class TestBlockageStatsTotal(unittest.TestCase):
    """Test the total count functionality"""

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
        """Initialize test database with blockage_events table"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS blockage_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp INTEGER NOT NULL,
                category TEXT NOT NULL,
                reason TEXT NOT NULL,
                hook_type TEXT NOT NULL,
                session_id TEXT NOT NULL
            )
        """)
        conn.commit()
        conn.close()

    def _create_config(self):
        """Create minimal config file"""
        import json
        with open(self.config_path, "w") as f:
            json.dump({"enabled": True}, f)

    def _insert_blockage_event(self, category: str, minutes_ago: int = 0):
        """Insert a test blockage event"""
        timestamp = int(time.time()) - (minutes_ago * 60)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO blockage_events (timestamp, category, reason, hook_type, session_id) "
            "VALUES (?, ?, 'test', 'pre_tool_use', 'test-session')",
            (timestamp, category),
        )
        conn.commit()
        conn.close()

    def test_get_blockage_stats_includes_total(self):
        """Test that result includes a 'total' key with sum of all counts"""
        self._insert_blockage_event("intent_validation", minutes_ago=5)
        self._insert_blockage_event("intent_validation", minutes_ago=10)
        self._insert_blockage_event("pacing_quota", minutes_ago=15)
        result = self.reader.get_blockage_stats()
        self.assertIn("total", result)
        self.assertEqual(result["total"], 3)


class TestBlockageStatsGracefulDegradation(unittest.TestCase):
    """Test graceful degradation when pace-maker database is unavailable (AC5)"""

    def test_get_blockage_stats_returns_none_when_not_installed(self):
        """Test that None is returned when pace-maker is not installed"""
        reader = PaceMakerReader()
        reader.pm_dir = Path("/nonexistent/path")
        reader.db_path = Path("/nonexistent/path/usage.db")
        reader.config_path = Path("/nonexistent/path/config.json")
        result = reader.get_blockage_stats()
        self.assertIsNone(result)

    def test_get_blockage_stats_returns_none_when_db_missing(self):
        """Test that None is returned when database file doesn't exist"""
        import json
        import shutil
        temp_dir = tempfile.mkdtemp()
        try:
            config_path = os.path.join(temp_dir, "config.json")
            with open(config_path, "w") as f:
                json.dump({"enabled": True}, f)
            reader = PaceMakerReader()
            reader.pm_dir = Path(temp_dir)
            reader.config_path = Path(config_path)
            reader.db_path = Path(os.path.join(temp_dir, "nonexistent.db"))
            result = reader.get_blockage_stats()
            self.assertIsNone(result)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_get_blockage_stats_returns_none_on_db_error(self):
        """Test that None is returned when database query fails"""
        import json
        import shutil
        temp_dir = tempfile.mkdtemp()
        try:
            config_path = os.path.join(temp_dir, "config.json")
            with open(config_path, "w") as f:
                json.dump({"enabled": True}, f)
            db_path = os.path.join(temp_dir, "usage.db")
            with open(db_path, "w") as f:
                f.write("not a valid database")
            reader = PaceMakerReader()
            reader.pm_dir = Path(temp_dir)
            reader.config_path = Path(config_path)
            reader.db_path = Path(db_path)
            result = reader.get_blockage_stats()
            self.assertIsNone(result)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


class TestBlockageStatsHumanReadableLabels(unittest.TestCase):
    """Test human-readable labels for blockage categories"""

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
        """Initialize test database with blockage_events table"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS blockage_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp INTEGER NOT NULL,
                category TEXT NOT NULL,
                reason TEXT NOT NULL,
                hook_type TEXT NOT NULL,
                session_id TEXT NOT NULL
            )
        """)
        conn.commit()
        conn.close()

    def _create_config(self):
        """Create minimal config file"""
        import json
        with open(self.config_path, "w") as f:
            json.dump({"enabled": True}, f)

    def _insert_blockage_event(self, category: str, minutes_ago: int = 0):
        """Insert a test blockage event"""
        timestamp = int(time.time()) - (minutes_ago * 60)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO blockage_events (timestamp, category, reason, hook_type, session_id) "
            "VALUES (?, ?, 'test', 'pre_tool_use', 'test-session')",
            (timestamp, category),
        )
        conn.commit()
        conn.close()

    def test_get_blockage_stats_with_labels_returns_human_readable_keys(self):
        """Test that get_blockage_stats_with_labels returns human-readable keys"""
        self._insert_blockage_event("intent_validation", minutes_ago=5)
        result = self.reader.get_blockage_stats_with_labels()
        expected_labels = ["Intent Validation", "Intent TDD", "Pacing Tempo", "Pacing Quota", "Other", "Total"]
        for label in expected_labels:
            self.assertIn(label, result)
        self.assertEqual(result["Intent Validation"], 1)


class TestBlockageStatsCaching(unittest.TestCase):
    """Test caching mechanism for blockage stats (AC4)"""

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
        """Initialize test database with blockage_events table"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS blockage_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp INTEGER NOT NULL,
                category TEXT NOT NULL,
                reason TEXT NOT NULL,
                hook_type TEXT NOT NULL,
                session_id TEXT NOT NULL
            )
        """)
        conn.commit()
        conn.close()

    def _create_config(self):
        """Create minimal config file"""
        import json
        with open(self.config_path, "w") as f:
            json.dump({"enabled": True}, f)

    def _insert_blockage_event(self, category: str, minutes_ago: int = 0):
        """Insert a test blockage event"""
        timestamp = int(time.time()) - (minutes_ago * 60)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO blockage_events (timestamp, category, reason, hook_type, session_id) "
            "VALUES (?, ?, 'test', 'pre_tool_use', 'test-session')",
            (timestamp, category),
        )
        conn.commit()
        conn.close()

    def test_get_blockage_stats_cached_returns_cached_result(self):
        """Test that get_blockage_stats_cached returns same result within cache window"""
        self._insert_blockage_event("intent_validation", minutes_ago=5)
        result1 = self.reader.get_blockage_stats_cached()
        self.assertEqual(result1["intent_validation"], 1)
        # Insert another event
        self._insert_blockage_event("intent_validation", minutes_ago=1)
        # Should return cached result (still 1)
        result2 = self.reader.get_blockage_stats_cached()
        self.assertEqual(result2["intent_validation"], 1)

    def test_get_blockage_stats_cached_invalidates_after_expiry(self):
        """Test that cache is invalidated after 5 seconds"""
        self._insert_blockage_event("pacing_quota", minutes_ago=5)
        result1 = self.reader.get_blockage_stats_cached()
        self.assertEqual(result1["pacing_quota"], 1)
        # Manually expire the cache by setting cache_time to past
        self.reader._blockage_stats_cache_time = time.time() - 10
        # Insert another event
        self._insert_blockage_event("pacing_quota", minutes_ago=1)
        # Should fetch fresh data (now 2)
        result2 = self.reader.get_blockage_stats_cached()
        self.assertEqual(result2["pacing_quota"], 2)


if __name__ == "__main__":
    unittest.main()
