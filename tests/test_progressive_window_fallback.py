"""Tests for progressive window fallback in rate calculation"""

import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from claude_usage.code_mode.storage import CodeStorage, CodeAnalytics
from claude_usage.console_mode.storage import ConsoleStorage, ConsoleAnalytics


class TestProgressiveWindowFallbackCodeMode:
    """Test progressive window fallback for Code mode rate calculation"""

    @pytest.fixture
    def temp_db(self):
        """Create temporary database for testing"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            yield db_path

    @pytest.fixture
    def storage(self, temp_db):
        """Create CodeStorage instance"""
        return CodeStorage(temp_db)

    def test_rate_with_30min_window(self, storage, temp_db):
        """Test rate calculation uses 30-minute window when available"""
        current_time = int(datetime.now().timestamp())

        # Insert snapshot 30 minutes ago
        thirty_min_ago = current_time - 1800
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO usage_snapshots
            (timestamp, credits_used, utilization_percent, resets_at)
            VALUES (?, ?, ?, ?)
        """,
            (thirty_min_ago, 100, 50.0, "2025-01-01T00:00:00"),
        )
        conn.commit()
        conn.close()

        # Calculate rate (current: 200, old: 100, diff: 100 over 1800s = 200/hour)
        rate = storage.calculate_usage_rate(200)

        assert rate is not None
        assert abs(rate - 200.0) < 0.01, "Rate should be 200 credits/hour from 30-min window"

    def test_rate_fallback_to_1hour(self, storage, temp_db):
        """Test rate calculation falls back to 1-hour window when 30-min unavailable"""
        current_time = int(datetime.now().timestamp())

        # Insert snapshot 1 hour ago (no 30-min data)
        one_hour_ago = current_time - 3600
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO usage_snapshots
            (timestamp, credits_used, utilization_percent, resets_at)
            VALUES (?, ?, ?, ?)
        """,
            (one_hour_ago, 50, 25.0, "2025-01-01T00:00:00"),
        )
        conn.commit()
        conn.close()

        # Calculate rate (current: 150, old: 50, diff: 100 over 3600s = 100/hour)
        rate = storage.calculate_usage_rate(150)

        assert rate is not None
        assert abs(rate - 100.0) < 0.05, "Rate should be ~100 credits/hour from 1-hour window"

    def test_rate_fallback_to_3hours(self, storage, temp_db):
        """Test rate calculation falls back to 3-hour window"""
        current_time = int(datetime.now().timestamp())

        # Insert snapshot 3 hours ago (no 30-min or 1-hour data)
        three_hours_ago = current_time - 10800
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO usage_snapshots
            (timestamp, credits_used, utilization_percent, resets_at)
            VALUES (?, ?, ?, ?)
        """,
            (three_hours_ago, 30, 15.0, "2025-01-01T00:00:00"),
        )
        conn.commit()
        conn.close()

        # Calculate rate (current: 120, old: 30, diff: 90 over 10800s = 30/hour)
        rate = storage.calculate_usage_rate(120)

        assert rate is not None
        assert abs(rate - 30.0) < 0.01, "Rate should be 30 credits/hour from 3-hour window"

    def test_rate_fallback_to_6hours(self, storage, temp_db):
        """Test rate calculation falls back to 6-hour window"""
        current_time = int(datetime.now().timestamp())

        # Insert snapshot 6 hours ago
        six_hours_ago = current_time - 21600
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO usage_snapshots
            (timestamp, credits_used, utilization_percent, resets_at)
            VALUES (?, ?, ?, ?)
        """,
            (six_hours_ago, 20, 10.0, "2025-01-01T00:00:00"),
        )
        conn.commit()
        conn.close()

        # Calculate rate (current: 80, old: 20, diff: 60 over 21600s = 10/hour)
        rate = storage.calculate_usage_rate(80)

        assert rate is not None
        assert abs(rate - 10.0) < 0.01, "Rate should be 10 credits/hour from 6-hour window"

    def test_rate_fallback_to_24hours(self, storage, temp_db):
        """Test rate calculation falls back to 24-hour window"""
        current_time = int(datetime.now().timestamp())

        # Insert snapshot 24 hours ago (weekend gap scenario)
        twentyfour_hours_ago = current_time - 86400
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO usage_snapshots
            (timestamp, credits_used, utilization_percent, resets_at)
            VALUES (?, ?, ?, ?)
        """,
            (twentyfour_hours_ago, 10, 5.0, "2025-01-01T00:00:00"),
        )
        conn.commit()
        conn.close()

        # Calculate rate (current: 70, old: 10, diff: 60 over 86400s = 2.5/hour)
        rate = storage.calculate_usage_rate(70)

        assert rate is not None
        assert abs(rate - 2.5) < 0.01, "Rate should be 2.5 credits/hour from 24-hour window"

    def test_rate_fallback_to_7days(self, storage, temp_db):
        """Test rate calculation falls back to 7-day window (long gap)"""
        current_time = int(datetime.now().timestamp())

        # Insert snapshot 6.5 days ago (within 7-day window, but beyond 24hr)
        six_and_half_days_ago = current_time - (6.5 * 24 * 3600)
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO usage_snapshots
            (timestamp, credits_used, utilization_percent, resets_at)
            VALUES (?, ?, ?, ?)
        """,
            (six_and_half_days_ago, 5, 2.5, "2025-01-01T00:00:00"),
        )
        conn.commit()
        conn.close()

        # Calculate rate (current: 45, old: 5, diff: 40 over ~561600s = ~0.256/hour)
        rate = storage.calculate_usage_rate(45)

        assert rate is not None
        expected_rate = (40 / (6.5 * 24 * 3600)) * 3600  # ~0.256
        assert abs(rate - expected_rate) < 0.01, "Rate should be calculated from 7-day window"

    def test_rate_no_data_returns_none(self, storage):
        """Test rate calculation returns None when no historical data"""
        rate = storage.calculate_usage_rate(100)
        assert rate is None, "Should return None when no historical data available"

    def test_rate_zero_increase_returns_zero(self, storage, temp_db):
        """Test rate calculation returns 0 when no increase"""
        current_time = int(datetime.now().timestamp())

        # Insert snapshot 30 minutes ago with same value
        thirty_min_ago = current_time - 1800
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO usage_snapshots
            (timestamp, credits_used, utilization_percent, resets_at)
            VALUES (?, ?, ?, ?)
        """,
            (thirty_min_ago, 100, 50.0, "2025-01-01T00:00:00"),
        )
        conn.commit()
        conn.close()

        # Calculate rate with same value
        rate = storage.calculate_usage_rate(100)

        assert rate == 0, "Should return 0 when no increase in usage"

    def test_rate_prefers_shorter_window(self, storage, temp_db):
        """Test rate calculation prefers shorter windows when multiple available"""
        current_time = int(datetime.now().timestamp())

        # Insert snapshots at multiple intervals
        thirty_min_ago = current_time - 1800
        three_hours_ago = current_time - 10800

        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()

        # Older snapshot (3 hours)
        cursor.execute(
            """
            INSERT INTO usage_snapshots
            (timestamp, credits_used, utilization_percent, resets_at)
            VALUES (?, ?, ?, ?)
        """,
            (three_hours_ago, 10, 5.0, "2025-01-01T00:00:00"),
        )

        # Newer snapshot (30 minutes)
        cursor.execute(
            """
            INSERT INTO usage_snapshots
            (timestamp, credits_used, utilization_percent, resets_at)
            VALUES (?, ?, ?, ?)
        """,
            (thirty_min_ago, 50, 25.0, "2025-01-01T00:00:00"),
        )

        conn.commit()
        conn.close()

        # Calculate rate (should use 30-min window: current 100, old 50, diff 50 over 1800s = 100/hour)
        rate = storage.calculate_usage_rate(100)

        assert rate is not None
        assert abs(rate - 100.0) < 0.01, "Should prefer 30-min window over 3-hour window"


class TestProgressiveWindowFallbackConsoleMode:
    """Test progressive window fallback for Console mode rate calculation"""

    @pytest.fixture
    def temp_db(self):
        """Create temporary database for testing"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            yield db_path

    @pytest.fixture
    def storage(self, temp_db):
        """Create ConsoleStorage instance"""
        return ConsoleStorage(temp_db)

    @pytest.fixture
    def analytics(self, storage):
        """Create ConsoleAnalytics instance"""
        return ConsoleAnalytics(storage)

    def test_rate_with_30min_window(self, storage, analytics, temp_db):
        """Test console rate calculation uses 30-minute window when available"""
        current_time = int(datetime.now().timestamp())

        # Insert snapshot 30 minutes ago
        thirty_min_ago = current_time - 1800
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO console_usage_snapshots
            (timestamp, mtd_cost, workspace_costs_json)
            VALUES (?, ?, ?)
        """,
            (thirty_min_ago, 10.00, "[]"),
        )
        conn.commit()
        conn.close()

        # Calculate rate (current: $20, old: $10, diff: $10 over 1800s = $20/hour)
        rate = analytics.calculate_console_mtd_rate(20.00)

        assert rate is not None
        assert abs(rate - 20.0) < 0.01, "Rate should be $20/hour from 30-min window"

    def test_rate_fallback_to_1hour(self, storage, analytics, temp_db):
        """Test console rate calculation falls back to 1-hour window"""
        current_time = int(datetime.now().timestamp())

        # Insert snapshot 1 hour ago
        one_hour_ago = current_time - 3600
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO console_usage_snapshots
            (timestamp, mtd_cost, workspace_costs_json)
            VALUES (?, ?, ?)
        """,
            (one_hour_ago, 5.00, "[]"),
        )
        conn.commit()
        conn.close()

        # Calculate rate (current: $15, old: $5, diff: $10 over 3600s = $10/hour)
        rate = analytics.calculate_console_mtd_rate(15.00)

        assert rate is not None
        assert abs(rate - 10.0) < 0.01, "Rate should be $10/hour from 1-hour window"

    def test_rate_fallback_to_3hours(self, storage, analytics, temp_db):
        """Test console rate calculation falls back to 3-hour window"""
        current_time = int(datetime.now().timestamp())

        # Insert snapshot 3 hours ago
        three_hours_ago = current_time - 10800
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO console_usage_snapshots
            (timestamp, mtd_cost, workspace_costs_json)
            VALUES (?, ?, ?)
        """,
            (three_hours_ago, 3.00, "[]"),
        )
        conn.commit()
        conn.close()

        # Calculate rate (current: $12, old: $3, diff: $9 over 10800s = $3/hour)
        rate = analytics.calculate_console_mtd_rate(12.00)

        assert rate is not None
        assert abs(rate - 3.0) < 0.01, "Rate should be $3/hour from 3-hour window"

    def test_rate_fallback_to_24hours_weekend_gap(self, storage, analytics, temp_db):
        """Test console rate handles weekend gap with 24-hour window"""
        current_time = int(datetime.now().timestamp())

        # Insert snapshot 24 hours ago (weekend gap)
        twentyfour_hours_ago = current_time - 86400
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO console_usage_snapshots
            (timestamp, mtd_cost, workspace_costs_json)
            VALUES (?, ?, ?)
        """,
            (twentyfour_hours_ago, 2.00, "[]"),
        )
        conn.commit()
        conn.close()

        # Calculate rate (current: $8, old: $2, diff: $6 over 86400s = $0.25/hour)
        rate = analytics.calculate_console_mtd_rate(8.00)

        assert rate is not None
        assert abs(rate - 0.25) < 0.01, "Rate should be $0.25/hour from 24-hour window"

    def test_rate_fallback_to_7days(self, storage, analytics, temp_db):
        """Test console rate falls back to 7-day window for long gaps"""
        current_time = int(datetime.now().timestamp())

        # Insert snapshot 7 days ago
        seven_days_ago = current_time - 604800
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO console_usage_snapshots
            (timestamp, mtd_cost, workspace_costs_json)
            VALUES (?, ?, ?)
        """,
            (seven_days_ago, 1.00, "[]"),
        )
        conn.commit()
        conn.close()

        # Calculate rate (current: $5, old: $1, diff: $4 over 604800s = ~$0.0238/hour)
        rate = analytics.calculate_console_mtd_rate(5.00)

        assert rate is not None
        expected_rate = (4.0 / 604800) * 3600  # ~0.0238
        assert abs(rate - expected_rate) < 0.001, "Rate should be calculated from 7-day window"

    def test_rate_no_data_returns_none(self, analytics):
        """Test console rate returns None when no historical data"""
        rate = analytics.calculate_console_mtd_rate(10.00)
        assert rate is None, "Should return None when no historical data available"

    def test_rate_zero_increase_returns_zero(self, storage, analytics, temp_db):
        """Test console rate returns 0 when no cost increase"""
        current_time = int(datetime.now().timestamp())

        # Insert snapshot 30 minutes ago with same cost
        thirty_min_ago = current_time - 1800
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO console_usage_snapshots
            (timestamp, mtd_cost, workspace_costs_json)
            VALUES (?, ?, ?)
        """,
            (thirty_min_ago, 10.00, "[]"),
        )
        conn.commit()
        conn.close()

        # Calculate rate with same cost
        rate = analytics.calculate_console_mtd_rate(10.00)

        assert rate == 0, "Should return 0 when no increase in cost"
