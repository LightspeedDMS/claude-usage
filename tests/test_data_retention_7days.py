"""Tests for 7-day data retention in Code and Console modes"""

import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from claude_usage.code_mode.storage import CodeStorage
from claude_usage.console_mode.storage import ConsoleStorage


class TestSevenDayRetention:
    """Test suite for 7-day data retention"""

    @pytest.fixture
    def temp_db(self):
        """Create temporary database for testing"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            yield db_path

    # ===== Code Mode Tests =====

    def test_code_storage_retains_7_days(self, temp_db):
        """Test CodeStorage retains data for 7 days"""
        storage = CodeStorage(temp_db)

        current_time = int(datetime.now().timestamp())

        # Insert snapshot from 6 days ago (should be kept)
        six_days_ago = current_time - (6 * 24 * 3600)
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO usage_snapshots
            (timestamp, credits_used, utilization_percent, resets_at)
            VALUES (?, ?, ?, ?)
        """,
            (six_days_ago, 100, 50.0, "2025-01-01T00:00:00"),
        )
        conn.commit()
        conn.close()

        # Store new snapshot (triggers cleanup)
        overage_data = {"used_credits": 200}
        usage_data = {"five_hour": {"utilization": 75.0, "resets_at": "2025-01-01T00:00:00"}}
        storage.store_snapshot(overage_data, usage_data)

        # Verify 6-day-old snapshot is still present
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM usage_snapshots WHERE timestamp = ?", (six_days_ago,))
        count = cursor.fetchone()[0]
        conn.close()

        assert count == 1, "6-day-old snapshot should be retained"

    def test_code_storage_deletes_8_days(self, temp_db):
        """Test CodeStorage deletes data older than 7 days"""
        storage = CodeStorage(temp_db)

        current_time = int(datetime.now().timestamp())

        # Insert snapshot from 8 days ago (should be deleted)
        eight_days_ago = current_time - (8 * 24 * 3600)
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO usage_snapshots
            (timestamp, credits_used, utilization_percent, resets_at)
            VALUES (?, ?, ?, ?)
        """,
            (eight_days_ago, 50, 25.0, "2025-01-01T00:00:00"),
        )
        conn.commit()
        conn.close()

        # Store new snapshot (triggers cleanup)
        overage_data = {"used_credits": 200}
        usage_data = {"five_hour": {"utilization": 75.0, "resets_at": "2025-01-01T00:00:00"}}
        storage.store_snapshot(overage_data, usage_data)

        # Verify 8-day-old snapshot was deleted
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM usage_snapshots WHERE timestamp = ?", (eight_days_ago,))
        count = cursor.fetchone()[0]
        conn.close()

        assert count == 0, "8-day-old snapshot should be deleted"

    def test_code_storage_boundary_exactly_7_days(self, temp_db):
        """Test CodeStorage retention boundary at exactly 7 days"""
        storage = CodeStorage(temp_db)

        current_time = int(datetime.now().timestamp())

        # Insert snapshot from exactly 7 days ago (should be kept - boundary test)
        exactly_7_days = current_time - (7 * 24 * 3600)
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO usage_snapshots
            (timestamp, credits_used, utilization_percent, resets_at)
            VALUES (?, ?, ?, ?)
        """,
            (exactly_7_days, 150, 60.0, "2025-01-01T00:00:00"),
        )
        conn.commit()
        conn.close()

        # Store new snapshot (triggers cleanup)
        overage_data = {"used_credits": 200}
        usage_data = {"five_hour": {"utilization": 75.0, "resets_at": "2025-01-01T00:00:00"}}
        storage.store_snapshot(overage_data, usage_data)

        # Verify exactly-7-day-old snapshot is retained (>= comparison)
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM usage_snapshots WHERE timestamp = ?", (exactly_7_days,))
        count = cursor.fetchone()[0]
        conn.close()

        assert count == 1, "Exactly 7-day-old snapshot should be retained (boundary)"

    # ===== Console Mode Tests =====

    def test_console_storage_retains_7_days(self, temp_db):
        """Test ConsoleStorage retains data for 7 days"""
        storage = ConsoleStorage(temp_db)

        current_time = int(datetime.now().timestamp())

        # Insert snapshot from 6 days ago (should be kept)
        six_days_ago = current_time - (6 * 24 * 3600)
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO console_usage_snapshots
            (timestamp, mtd_cost, workspace_costs_json)
            VALUES (?, ?, ?)
        """,
            (six_days_ago, 25.50, "[]"),
        )
        conn.commit()
        conn.close()

        # Store new snapshot (triggers cleanup)
        mtd_data = {"total_cost_usd": 50.00}
        storage.store_console_snapshot(mtd_data, [])

        # Verify 6-day-old snapshot is still present
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM console_usage_snapshots WHERE timestamp = ?", (six_days_ago,))
        count = cursor.fetchone()[0]
        conn.close()

        assert count == 1, "6-day-old console snapshot should be retained"

    def test_console_storage_deletes_8_days(self, temp_db):
        """Test ConsoleStorage deletes data older than 7 days"""
        storage = ConsoleStorage(temp_db)

        current_time = int(datetime.now().timestamp())

        # Insert snapshot from 8 days ago (should be deleted)
        eight_days_ago = current_time - (8 * 24 * 3600)
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO console_usage_snapshots
            (timestamp, mtd_cost, workspace_costs_json)
            VALUES (?, ?, ?)
        """,
            (eight_days_ago, 10.00, "[]"),
        )
        conn.commit()
        conn.close()

        # Store new snapshot (triggers cleanup)
        mtd_data = {"total_cost_usd": 50.00}
        storage.store_console_snapshot(mtd_data, [])

        # Verify 8-day-old snapshot was deleted
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM console_usage_snapshots WHERE timestamp = ?", (eight_days_ago,))
        count = cursor.fetchone()[0]
        conn.close()

        assert count == 0, "8-day-old console snapshot should be deleted"

    def test_console_storage_boundary_exactly_7_days(self, temp_db):
        """Test ConsoleStorage retention boundary at exactly 7 days"""
        storage = ConsoleStorage(temp_db)

        current_time = int(datetime.now().timestamp())

        # Insert snapshot from exactly 7 days ago (should be kept - boundary test)
        exactly_7_days = current_time - (7 * 24 * 3600)
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO console_usage_snapshots
            (timestamp, mtd_cost, workspace_costs_json)
            VALUES (?, ?, ?)
        """,
            (exactly_7_days, 30.00, "[]"),
        )
        conn.commit()
        conn.close()

        # Store new snapshot (triggers cleanup)
        mtd_data = {"total_cost_usd": 50.00}
        storage.store_console_snapshot(mtd_data, [])

        # Verify exactly-7-day-old snapshot is retained (>= comparison)
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM console_usage_snapshots WHERE timestamp = ?", (exactly_7_days,))
        count = cursor.fetchone()[0]
        conn.close()

        assert count == 1, "Exactly 7-day-old console snapshot should be retained (boundary)"

    def test_base_storage_history_retention_constant(self):
        """Test BaseStorage.HISTORY_RETENTION is set to 7 days"""
        from claude_usage.shared.storage import BaseStorage

        # 7 days = 604800 seconds
        assert BaseStorage.HISTORY_RETENTION == 604800, "HISTORY_RETENTION should be 604800 seconds (7 days)"
