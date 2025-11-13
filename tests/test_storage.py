"""Tests for storage and analytics functionality"""

import json
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from claude_usage.storage import UsageAnalytics, UsageStorage


class TestUsageStorage:
    """Test suite for UsageStorage class"""

    @pytest.fixture
    def temp_db(self):
        """Create temporary database for testing"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            yield db_path

    @pytest.fixture
    def storage(self, temp_db):
        """Create UsageStorage instance"""
        return UsageStorage(temp_db)

    # ===== AC4: Console Usage Snapshots Storage =====

    def test_init_creates_console_snapshots_table(self, temp_db):
        """Test that _init_database creates console_usage_snapshots table"""
        UsageStorage(temp_db)

        # Verify table exists
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='console_usage_snapshots'
        """
        )
        result = cursor.fetchone()
        conn.close()

        assert result is not None
        assert result[0] == "console_usage_snapshots"

    def test_console_snapshots_table_schema(self, temp_db):
        """Test console_usage_snapshots table has correct schema"""
        UsageStorage(temp_db)

        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(console_usage_snapshots)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}
        conn.close()

        assert "timestamp" in columns
        assert "mtd_cost" in columns
        assert "ytd_cost" in columns
        assert "workspace_costs_json" in columns
        assert columns["timestamp"] == "INTEGER"
        assert columns["mtd_cost"] == "REAL"
        assert columns["ytd_cost"] == "REAL"
        assert columns["workspace_costs_json"] == "TEXT"

    def test_store_console_snapshot_success(self, storage, temp_db):
        """Test store_console_snapshot inserts data correctly"""
        mtd_data = {"total_cost_usd": 12.50}
        ytd_data = {"total_cost_usd": 150.75}
        workspaces = [
            {"name": "workspace1", "cost": 10.0},
            {"name": "workspace2", "cost": 2.5},
        ]

        result = storage.store_console_snapshot(mtd_data, ytd_data, workspaces)

        assert result is True

        # Verify data in database
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM console_usage_snapshots")
        row = cursor.fetchone()
        conn.close()

        assert row is not None
        timestamp, mtd_cost, ytd_cost, workspace_json = row
        assert mtd_cost == 12.50
        assert ytd_cost == 150.75

        # Verify JSON deserialization
        parsed_workspaces = json.loads(workspace_json)
        assert len(parsed_workspaces) == 2
        assert parsed_workspaces[0]["name"] == "workspace1"
        assert parsed_workspaces[1]["cost"] == 2.5

    def test_store_console_snapshot_with_none_workspaces(self, storage, temp_db):
        """Test store_console_snapshot handles None workspace data gracefully"""
        mtd_data = {"total_cost_usd": 5.0}
        ytd_data = {"total_cost_usd": 50.0}

        result = storage.store_console_snapshot(mtd_data, ytd_data, None)

        assert result is True

        # Verify data stored with null workspace_costs_json
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("SELECT workspace_costs_json FROM console_usage_snapshots")
        row = cursor.fetchone()
        conn.close()

        assert row is not None
        assert row[0] == "null"

    def test_store_console_snapshot_cleans_old_data(self, storage, temp_db):
        """Test store_console_snapshot keeps only last 24 hours of data"""
        # Insert old snapshot (25 hours ago)
        old_timestamp = int(datetime.now().timestamp()) - (25 * 3600)
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO console_usage_snapshots
            (timestamp, mtd_cost, ytd_cost, workspace_costs_json)
            VALUES (?, ?, ?, ?)
        """,
            (old_timestamp, 1.0, 10.0, "[]"),
        )
        conn.commit()
        conn.close()

        # Store new snapshot
        mtd_data = {"total_cost_usd": 5.0}
        ytd_data = {"total_cost_usd": 50.0}
        storage.store_console_snapshot(mtd_data, ytd_data, [])

        # Verify old snapshot was deleted
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM console_usage_snapshots")
        count = cursor.fetchone()[0]
        conn.close()

        assert count == 1  # Only new snapshot remains

    def test_store_console_snapshot_handles_missing_data(self, storage):
        """Test store_console_snapshot returns False for invalid data"""
        # None mtd_data
        result = storage.store_console_snapshot(None, {"total_cost_usd": 10}, [])
        assert result is False

        # None ytd_data
        result = storage.store_console_snapshot({"total_cost_usd": 10}, None, [])
        assert result is False

        # Both None
        result = storage.store_console_snapshot(None, None, [])
        assert result is False


class TestUsageAnalytics:
    """Test suite for UsageAnalytics class"""

    @pytest.fixture
    def temp_db(self):
        """Create temporary database for testing"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            yield db_path

    @pytest.fixture
    def storage(self, temp_db):
        """Create UsageStorage instance"""
        return UsageStorage(temp_db)

    @pytest.fixture
    def analytics(self, storage):
        """Create UsageAnalytics instance"""
        return UsageAnalytics(storage)

    # ===== AC4: Console MTD Rate Calculation =====

    def test_calculate_console_mtd_rate_with_sufficient_data(
        self, storage, analytics, temp_db
    ):
        """Test calculate_console_mtd_rate with 30-minute history"""
        current_time = int(datetime.now().timestamp())

        # Insert snapshot 30 minutes ago
        old_timestamp = current_time - 1800
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO console_usage_snapshots
            (timestamp, mtd_cost, ytd_cost, workspace_costs_json)
            VALUES (?, ?, ?, ?)
        """,
            (old_timestamp, 10.0, 100.0, "[]"),
        )
        conn.commit()
        conn.close()

        # Calculate rate with current cost of $15 (increase of $5 over 30 min)
        rate = analytics.calculate_console_mtd_rate(15.0)

        assert rate is not None
        # $5 increase over 0.5 hours = $10/hour
        assert abs(rate - 10.0) < 0.01

    def test_calculate_console_mtd_rate_insufficient_data(self, analytics):
        """Test calculate_console_mtd_rate returns None without historical data"""
        rate = analytics.calculate_console_mtd_rate(10.0)
        assert rate is None

    def test_calculate_console_mtd_rate_no_increase(self, storage, analytics, temp_db):
        """Test calculate_console_mtd_rate handles zero or negative increase"""
        current_time = int(datetime.now().timestamp())
        old_timestamp = current_time - 1800

        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO console_usage_snapshots
            (timestamp, mtd_cost, ytd_cost, workspace_costs_json)
            VALUES (?, ?, ?, ?)
        """,
            (old_timestamp, 10.0, 100.0, "[]"),
        )
        conn.commit()
        conn.close()

        # Current cost same as old cost
        rate = analytics.calculate_console_mtd_rate(10.0)
        assert rate == 0

        # Current cost less than old cost (shouldn't happen but handle gracefully)
        rate = analytics.calculate_console_mtd_rate(8.0)
        assert rate == 0

    def test_calculate_console_mtd_rate_with_none_current(self, analytics):
        """Test calculate_console_mtd_rate handles None current cost"""
        rate = analytics.calculate_console_mtd_rate(None)
        assert rate is None

    # ===== AC4: Console EOM Projection =====

    def test_project_console_eom_cost(self, analytics):
        """Test project_console_eom_cost calculation"""
        current_cost = 10.0
        rate_per_hour = 2.0
        hours_until_eom = 360  # 15 days

        projected = analytics.project_console_eom_cost(
            current_cost, rate_per_hour, hours_until_eom
        )

        # $10 + ($2/hr * 360hr) = $730
        assert projected == 730.0

    def test_project_console_eom_cost_zero_rate(self, analytics):
        """Test project_console_eom_cost with zero rate"""
        current_cost = 10.0
        rate_per_hour = 0.0
        hours_until_eom = 360

        projected = analytics.project_console_eom_cost(
            current_cost, rate_per_hour, hours_until_eom
        )

        assert projected == 10.0  # No increase

    def test_project_console_eom_cost_negative_time(self, analytics):
        """Test project_console_eom_cost handles negative time remaining"""
        current_cost = 10.0
        rate_per_hour = 2.0
        hours_until_eom = -10  # Past end of month

        # Should return current cost (no projection into past)
        projected = analytics.project_console_eom_cost(
            current_cost, rate_per_hour, hours_until_eom
        )

        assert projected == 10.0

    def test_project_console_eom_cost_with_none_values(self, analytics):
        """Test project_console_eom_cost handles None values"""
        # None current cost
        result = analytics.project_console_eom_cost(None, 2.0, 360)
        assert result is None

        # None rate
        result = analytics.project_console_eom_cost(10.0, None, 360)
        assert result is None

        # None hours
        result = analytics.project_console_eom_cost(10.0, 2.0, None)
        assert result is None
