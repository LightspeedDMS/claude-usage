"""Storage and analytics for Claude Code usage tracking"""

import logging
import sqlite3
from pathlib import Path
from datetime import datetime


class UsageStorage:
    """Manages SQLite database for usage history"""

    RATE_CALC_WINDOW = 1800  # 30 minutes for rate calculation
    HISTORY_RETENTION = 86400  # Keep 24 hours of history

    def __init__(self, db_path):
        self.db_path = Path(db_path)
        self._init_database()

    def _init_database(self):
        """Initialize storage directory and database"""
        try:
            # Create storage directory if it doesn't exist
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

            # Initialize database
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Create table if not exists
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS usage_snapshots (
                    timestamp INTEGER PRIMARY KEY,
                    credits_used INTEGER,
                    utilization_percent REAL,
                    resets_at TEXT
                )
            """
            )

            # Create index for efficient queries
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_timestamp
                ON usage_snapshots(timestamp DESC)
            """
            )

            # Create console usage snapshots table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS console_usage_snapshots (
                    timestamp INTEGER PRIMARY KEY,
                    mtd_cost REAL,
                    ytd_cost REAL,
                    workspace_costs_json TEXT
                )
            """
            )

            conn.commit()
            conn.close()

        except Exception:
            # Non-fatal error - continue without storage
            pass

    def store_snapshot(self, overage_data, usage_data):
        """Store current usage snapshot to database"""
        if not overage_data or not usage_data:
            return False

        try:
            timestamp = int(datetime.now().timestamp())
            credits_used = overage_data.get("used_credits", 0)
            utilization = usage_data.get("five_hour", {}).get("utilization", 0)
            resets_at = usage_data.get("five_hour", {}).get("resets_at", "")

            conn = sqlite3.connect(self.db_path)
            try:
                cursor = conn.cursor()

                # Insert snapshot
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO usage_snapshots
                    (timestamp, credits_used, utilization_percent, resets_at)
                    VALUES (?, ?, ?, ?)
                """,
                    (timestamp, credits_used, utilization, resets_at),
                )

                # Clean old data (keep only last 24 hours)
                cutoff = timestamp - self.HISTORY_RETENTION
                cursor.execute(
                    "DELETE FROM usage_snapshots WHERE timestamp < ?", (cutoff,)
                )

                conn.commit()
            finally:
                conn.close()

            return True

        except Exception as e:
            logging.getLogger(__name__).error(
                f"Failed to store snapshot: {e}", exc_info=True
            )
            return False  # Non-fatal

    def store_console_snapshot(self, mtd_data, ytd_data, workspaces):
        """Store console usage snapshot to database"""
        if not mtd_data or not ytd_data:
            return False

        import json

        timestamp = int(datetime.now().timestamp())
        mtd_cost = mtd_data.get("total_cost_usd", 0)
        ytd_cost = ytd_data.get("total_cost_usd", 0)
        workspace_json = json.dumps(workspaces)

        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT OR REPLACE INTO console_usage_snapshots
                (timestamp, mtd_cost, ytd_cost, workspace_costs_json)
                VALUES (?, ?, ?, ?)
            """,
                (timestamp, mtd_cost, ytd_cost, workspace_json),
            )

            # Clean old data (keep only last 24 hours)
            cutoff = timestamp - self.HISTORY_RETENTION
            cursor.execute(
                "DELETE FROM console_usage_snapshots WHERE timestamp < ?", (cutoff,)
            )

            conn.commit()
        finally:
            conn.close()

        return True

    def calculate_usage_rate(self, current_credits):
        """Calculate usage rate in credits per hour"""
        if current_credits is None:
            return None

        try:
            current_timestamp = int(datetime.now().timestamp())

            # Get snapshots from the last 30 minutes
            cutoff = current_timestamp - self.RATE_CALC_WINDOW

            conn = sqlite3.connect(self.db_path)
            try:
                cursor = conn.cursor()

                cursor.execute(
                    """
                    SELECT timestamp, credits_used
                    FROM usage_snapshots
                    WHERE timestamp >= ?
                    ORDER BY timestamp ASC
                    LIMIT 1
                """,
                    (cutoff,),
                )

                result = cursor.fetchone()
            finally:
                conn.close()

            if not result:
                return None

            old_timestamp, old_credits = result

            # Calculate rate
            time_diff = current_timestamp - old_timestamp
            if time_diff == 0:
                return None

            credit_diff = current_credits - old_credits
            if credit_diff <= 0:
                return 0  # No increase

            # Credits per hour
            rate = (credit_diff / time_diff) * 3600

            return rate

        except Exception as e:
            logging.getLogger(__name__).error(
                f"Failed to calculate usage rate: {e}", exc_info=True
            )
            return None


class UsageAnalytics:
    """Calculates projections and analytics"""

    def __init__(self, storage):
        self.storage = storage

    def calculate_console_mtd_rate(self, current_mtd_cost):
        """Calculate console MTD spending rate in dollars per hour"""
        if current_mtd_cost is None:
            return None

        try:
            current_timestamp = int(datetime.now().timestamp())
            cutoff = current_timestamp - self.storage.RATE_CALC_WINDOW

            conn = sqlite3.connect(self.storage.db_path)
            try:
                cursor = conn.cursor()

                cursor.execute(
                    """
                    SELECT timestamp, mtd_cost
                    FROM console_usage_snapshots
                    WHERE timestamp >= ?
                    ORDER BY timestamp ASC
                    LIMIT 1
                """,
                    (cutoff,),
                )

                result = cursor.fetchone()
            finally:
                conn.close()

            if not result:
                return None

            old_timestamp, old_cost = result

            time_diff = current_timestamp - old_timestamp
            if time_diff == 0:
                return None

            cost_diff = current_mtd_cost - old_cost
            if cost_diff <= 0:
                return 0

            # Dollars per hour
            rate = (cost_diff / time_diff) * 3600
            return rate

        except Exception as e:
            logging.getLogger(__name__).error(
                f"Failed to calculate console MTD rate: {e}", exc_info=True
            )
            return None

    def project_console_eom_cost(
        self, current_mtd_cost, rate_per_hour, hours_until_eom
    ):
        """Project console spending to end of month"""
        if current_mtd_cost is None or rate_per_hour is None or hours_until_eom is None:
            return None

        # Don't project into the past
        if hours_until_eom < 0:
            return current_mtd_cost

        projected_cost = current_mtd_cost + (rate_per_hour * hours_until_eom)
        return projected_cost

    def project_usage(self, overage_data, usage_data):
        """Project usage by reset time"""
        if not overage_data or not usage_data:
            return None

        current_credits = overage_data.get("used_credits", 0)
        rate = self.storage.calculate_usage_rate(current_credits)

        if rate is None:
            return None

        try:
            resets_at_str = usage_data.get("five_hour", {}).get("resets_at", "")

            if not resets_at_str:
                return None

            reset_time = datetime.fromisoformat(resets_at_str.replace("+00:00", ""))
            now = datetime.utcnow()
            time_until_reset = (reset_time - now).total_seconds()

            if time_until_reset <= 0:
                return None

            # Project credits by reset time
            hours_until_reset = time_until_reset / 3600
            projected_credits = current_credits + (rate * hours_until_reset)

            return {
                "current_credits": current_credits,
                "projected_credits": projected_credits,
                "rate_per_hour": rate,
                "hours_until_reset": hours_until_reset,
            }

        except Exception:
            return None
