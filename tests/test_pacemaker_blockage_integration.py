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

from claude_usage.code_mode.pacemaker_integration import (
    PaceMakerReader,
    _humanize_blockage_category,
)


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
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS blockage_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp INTEGER NOT NULL,
                category TEXT NOT NULL,
                reason TEXT NOT NULL,
                hook_type TEXT NOT NULL,
                session_id TEXT NOT NULL
            )
        """
        )
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
        expected = [
            "intent_validation",
            "intent_validation_tdd",
            "pacing_tempo",
            "pacing_quota",
            "other",
        ]
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
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS blockage_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp INTEGER NOT NULL,
                category TEXT NOT NULL,
                reason TEXT NOT NULL,
                hook_type TEXT NOT NULL,
                session_id TEXT NOT NULL
            )
        """
        )
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
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS blockage_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp INTEGER NOT NULL,
                category TEXT NOT NULL,
                reason TEXT NOT NULL,
                hook_type TEXT NOT NULL,
                session_id TEXT NOT NULL
            )
        """
        )
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
        # Note: 'Other' is excluded from labels as it's a rarely-used catch-all category
        expected_labels = [
            "Intent Val.",
            "Intent TDD",
            "Clean Code",
            "Danger Bash",
            "Pacing Tempo",
            "Pacing Quota",
            "Total",
        ]
        for label in expected_labels:
            self.assertIn(label, result)
        self.assertEqual(result["Intent Val."], 1)


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
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS blockage_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp INTEGER NOT NULL,
                category TEXT NOT NULL,
                reason TEXT NOT NULL,
                hook_type TEXT NOT NULL,
                session_id TEXT NOT NULL
            )
        """
        )
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


def _init_blockage_db(db_path):
    """Create the blockage_events table in a fresh temp sqlite file."""
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS blockage_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp INTEGER NOT NULL,
                category TEXT NOT NULL,
                reason TEXT NOT NULL,
                hook_type TEXT NOT NULL,
                session_id TEXT NOT NULL
            )
            """
        )
        conn.commit()


def _write_pacemaker_config(config_path):
    """Write a minimal enabled pace-maker config file."""
    import json

    with open(config_path, "w") as f:
        json.dump({"enabled": True}, f)


def _insert_blockage_event(db_path, category, minutes_ago=0):
    """Insert a single blockage_events row `minutes_ago` minutes in the past."""
    timestamp = int(time.time()) - (minutes_ago * 60)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO blockage_events "
            "(timestamp, category, reason, hook_type, session_id) "
            "VALUES (?, ?, 'test', 'pre_tool_use', 'test-session')",
            (timestamp, category),
        )
        conn.commit()


class TestHumanizeBlockageCategory(unittest.TestCase):
    """Direct unit coverage for the fallback label helper (issue #7)."""

    def test_humanizes_snake_case(self):
        self.assertEqual(
            _humanize_blockage_category("some_new_category"), "Some New Category"
        )

    def test_empty_string_returns_unchanged(self):
        self.assertEqual(_humanize_blockage_category(""), "")


class _Issue7BlockageTestBase(unittest.TestCase):
    """Shared fixtures for the issue #7 test classes below.

    Not collected by pytest itself (no Test* prefix), only its subclasses are.
    """

    def setUp(self):
        """Set up test fixtures with temporary database"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "usage.db")
        self.config_path = os.path.join(self.temp_dir, "config.json")
        _init_blockage_db(self.db_path)
        _write_pacemaker_config(self.config_path)
        self.reader = PaceMakerReader()
        self.reader.pm_dir = Path(self.temp_dir)
        self.reader.db_path = Path(self.db_path)
        self.reader.config_path = Path(self.config_path)

    def tearDown(self):
        """Clean up temporary files"""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)


class TestBlockageStatsIssue7KnownExtraCategories(_Issue7BlockageTestBase):
    """The 3 categories pace-maker already defines but this repo used to
    drop: intent_validation_bug, intent_validation_deferred,
    intent_validation_reviewer_unavailable.
    """

    def test_known_new_categories_counted_in_raw_stats(self):
        """bug/deferred/reviewer_unavailable are counted, not skipped."""
        _insert_blockage_event(self.db_path, "intent_validation_bug", minutes_ago=5)
        _insert_blockage_event(
            self.db_path, "intent_validation_deferred", minutes_ago=5
        )
        _insert_blockage_event(
            self.db_path, "intent_validation_reviewer_unavailable", minutes_ago=5
        )
        result = self.reader.get_blockage_stats()
        self.assertEqual(result["intent_validation_bug"], 1)
        self.assertEqual(result["intent_validation_deferred"], 1)
        self.assertEqual(result["intent_validation_reviewer_unavailable"], 1)

    def test_known_new_categories_zero_filled_when_absent(self):
        """Even with zero events, the 3 new categories are present (zero-filled)."""
        result = self.reader.get_blockage_stats()
        self.assertEqual(result["intent_validation_bug"], 0)
        self.assertEqual(result["intent_validation_deferred"], 0)
        self.assertEqual(result["intent_validation_reviewer_unavailable"], 0)

    def test_total_includes_the_three_new_known_categories(self):
        """Total must sum every row, including the previously-dropped ones."""
        _insert_blockage_event(self.db_path, "intent_validation", minutes_ago=5)
        _insert_blockage_event(self.db_path, "intent_validation_bug", minutes_ago=5)
        _insert_blockage_event(
            self.db_path, "intent_validation_deferred", minutes_ago=5
        )
        _insert_blockage_event(
            self.db_path, "intent_validation_reviewer_unavailable", minutes_ago=5
        )
        result = self.reader.get_blockage_stats()
        self.assertEqual(result["total"], 4)


class TestBlockageStatsIssue7KnownExtraLabels(_Issue7BlockageTestBase):
    """Human-readable labels for the 3 new known categories."""

    def test_labels_for_three_new_known_categories(self):
        """Labels match pace-maker's BLOCKAGE_CATEGORIES text."""
        _insert_blockage_event(self.db_path, "intent_validation_bug", minutes_ago=5)
        _insert_blockage_event(
            self.db_path, "intent_validation_deferred", minutes_ago=5
        )
        _insert_blockage_event(
            self.db_path, "intent_validation_reviewer_unavailable", minutes_ago=5
        )
        result = self.reader.get_blockage_stats_with_labels()
        self.assertEqual(result["Bug Detected"], 1)
        self.assertEqual(result["IV Deferred"], 1)
        self.assertEqual(result["Reviewer Unavailable"], 1)

    def test_empty_db_zero_fills_full_known_list(self):
        """With no events at all, every known category (10 total) is present at 0."""
        result = self.reader.get_blockage_stats()
        expected = [
            "intent_validation",
            "intent_validation_tdd",
            "intent_validation_cleancode",
            "intent_validation_dangerbash",
            "intent_validation_bug",
            "intent_validation_deferred",
            "intent_validation_reviewer_unavailable",
            "pacing_tempo",
            "pacing_quota",
            "other",
        ]
        for category in expected:
            self.assertEqual(result[category], 0)
        self.assertEqual(result["total"], 0)

    def test_missing_db_still_returns_none(self):
        """Reader contract preserved: missing DB -> None (not an exception)."""
        reader = PaceMakerReader()
        reader.pm_dir = Path("/nonexistent/path")
        reader.db_path = Path("/nonexistent/path/usage.db")
        reader.config_path = Path("/nonexistent/path/config.json")
        result = reader.get_blockage_stats()
        self.assertIsNone(result)

    def test_missing_db_labeled_variant_also_returns_none(self):
        """get_blockage_stats_with_labels() propagates the None too."""
        reader = PaceMakerReader()
        reader.pm_dir = Path("/nonexistent/path")
        reader.db_path = Path("/nonexistent/path/usage.db")
        reader.config_path = Path("/nonexistent/path/config.json")
        result = reader.get_blockage_stats_with_labels()
        self.assertIsNone(result)


class TestBlockageStatsIssue7UnknownFutureCategory(_Issue7BlockageTestBase):
    """A category pace-maker adds later, unknown to this repo's code."""

    def test_unknown_future_category_still_shown_with_fallback_label(self):
        """Not dropped: shown raw in stats, humanized in the labeled view."""
        _insert_blockage_event(self.db_path, "some_brand_new_category", minutes_ago=5)
        raw = self.reader.get_blockage_stats()
        self.assertIn("some_brand_new_category", raw)
        self.assertEqual(raw["some_brand_new_category"], 1)

        labeled = self.reader.get_blockage_stats_with_labels()
        self.assertIn("Some Brand New Category", labeled)
        self.assertEqual(labeled["Some Brand New Category"], 1)

    def test_unknown_future_category_counted_in_total(self):
        """Total counts unknown categories too, not just the known list."""
        _insert_blockage_event(self.db_path, "intent_validation", minutes_ago=5)
        _insert_blockage_event(self.db_path, "some_brand_new_category", minutes_ago=5)
        result = self.reader.get_blockage_stats()
        self.assertEqual(result["total"], 2)

        labeled = self.reader.get_blockage_stats_with_labels()
        self.assertEqual(labeled["Total"], 2)

    def test_known_categories_ordered_before_unknown_categories(self):
        """Known categories (zero-filled or not) come first; extras appended."""
        _insert_blockage_event(self.db_path, "some_brand_new_category", minutes_ago=5)
        _insert_blockage_event(self.db_path, "intent_validation", minutes_ago=5)
        result = self.reader.get_blockage_stats()
        keys = list(result.keys())
        self.assertLess(
            keys.index("intent_validation"), keys.index("some_brand_new_category")
        )


class TestBlockageStatsIssue7CachedVariant(_Issue7BlockageTestBase):
    """get_blockage_stats_cached() must stay a thin cache over the fix."""

    def test_cached_variant_reflects_new_and_unknown_categories(self):
        _insert_blockage_event(self.db_path, "intent_validation_bug", minutes_ago=5)
        _insert_blockage_event(self.db_path, "some_brand_new_category", minutes_ago=5)
        result = self.reader.get_blockage_stats_cached()
        self.assertEqual(result["intent_validation_bug"], 1)
        self.assertEqual(result["some_brand_new_category"], 1)
        self.assertEqual(result["total"], 2)


if __name__ == "__main__":
    unittest.main()
