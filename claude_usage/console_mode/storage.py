"""Storage and analytics for Console mode usage tracking"""

import logging
import json
from datetime import datetime

from ..shared.storage import BaseStorage


class ConsoleStorage(BaseStorage):
    """Manages SQLite database for Console mode usage history"""

    RATE_CALC_WINDOW = 1800  # 30 minutes for rate calculation

    def _create_tables(self, conn):
        """Create Console mode specific tables"""
        cursor = conn.cursor()

        # Create console usage snapshots table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS console_usage_snapshots (
                timestamp INTEGER PRIMARY KEY,
                mtd_cost REAL,
                workspace_costs_json TEXT
            )
        """
        )

    def store_console_snapshot(self, mtd_data, workspaces):
        """Store console usage snapshot to database"""
        if not mtd_data:
            return False

        timestamp = int(datetime.now().timestamp())
        mtd_cost = mtd_data.get("total_cost_usd", 0)
        workspace_json = json.dumps(workspaces)

        conn = self.get_connection()
        try:
            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT OR REPLACE INTO console_usage_snapshots
                (timestamp, mtd_cost, workspace_costs_json)
                VALUES (?, ?, ?)
            """,
                (timestamp, mtd_cost, workspace_json),
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


class ConsoleAnalytics:
    """Calculates projections and analytics for Console mode"""

    def __init__(self, storage):
        self.storage = storage

    def calculate_console_mtd_rate(self, current_mtd_cost):
        """Calculate console MTD spending rate in dollars per hour with progressive window fallback"""
        if current_mtd_cost is None:
            return None

        try:
            current_timestamp = int(datetime.now().timestamp())

            # Try windows progressively: 30min, 1hr, 3hr, 6hr, 24hr, 7 days
            windows = [1800, 3600, 10800, 21600, 86400, 604800]

            conn = self.storage.get_connection()
            try:
                cursor = conn.cursor()

                for window in windows:
                    cutoff = current_timestamp - window

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

                    if result:
                        old_timestamp, old_cost = result

                        time_diff = current_timestamp - old_timestamp
                        if time_diff == 0:
                            continue  # Try next window

                        cost_diff = current_mtd_cost - old_cost
                        if cost_diff <= 0:
                            return 0

                        # Dollars per hour
                        rate = (cost_diff / time_diff) * 3600
                        return rate

            finally:
                conn.close()

            # No historical data found in any window
            return None

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
