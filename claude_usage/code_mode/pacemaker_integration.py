"""Integration with Claude Pace Maker system

Reads pace-maker database and config to display throttling status
in the usage monitor without requiring pace-maker to be installed.
"""

import json
import sqlite3
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime


class PaceMakerReader:
    """Reads pace-maker state from database and config files"""

    def __init__(self):
        """Initialize pace-maker reader with default paths"""
        self.pm_dir = Path.home() / ".claude-pace-maker"
        self.config_path = self.pm_dir / "config.json"
        self.db_path = self.pm_dir / "usage.db"
        self.state_path = self.pm_dir / "state.json"

    def is_installed(self) -> bool:
        """Check if pace-maker is installed"""
        return self.pm_dir.exists() and self.config_path.exists()

    def is_enabled(self) -> bool:
        """Check if pace-maker throttling is enabled"""
        config = self._read_config()
        if not config:
            return False
        return config.get("enabled", False)

    def get_status(self) -> Optional[Dict[str, Any]]:
        """Get current pace-maker status including throttling state

        Returns:
            Dict with pace-maker status or None if not available:
            {
                'enabled': bool,
                'five_hour': {
                    'utilization': float,
                    'target': float,
                    'deviation': float,
                    'time_elapsed_pct': float
                },
                'seven_day': {
                    'utilization': float,
                    'target': float,
                    'deviation': float,
                    'time_elapsed_pct': float
                },
                'constrained_window': str ('5-hour' or '7-day'),
                'should_throttle': bool,
                'delay_seconds': int,
                'algorithm': str ('adaptive' or 'legacy'),
                'last_update': datetime
            }
        """
        if not self.is_installed():
            return None

        config = self._read_config()
        if not config:
            return None

        enabled = config.get("enabled", False)

        # Get latest usage data from database
        usage_data = self._get_latest_usage()
        if not usage_data:
            return {
                "enabled": enabled,
                "has_data": False,
            }

        # Calculate pacing decision using pace-maker's algorithm
        try:
            # Import pace-maker's pacing engine
            import sys

            # Try to find pace-maker source directory
            pm_src = None

            # Check if install_source file exists (points to dev directory)
            install_source_file = self.pm_dir / "install_source"
            if install_source_file.exists():
                try:
                    with open(install_source_file) as f:
                        source_dir = Path(f.read().strip())
                        pm_src = source_dir / "src"
                except (OSError, ValueError):
                    pass

            # Fallback: check standard installation location
            if not pm_src or not pm_src.exists():
                pm_src = self.pm_dir / "src"

            # Add to path if exists
            if pm_src and pm_src.exists() and str(pm_src) not in sys.path:
                sys.path.insert(0, str(pm_src))

            from pacemaker import pacing_engine

            decision = pacing_engine.calculate_pacing_decision(
                five_hour_util=usage_data["five_hour_util"],
                five_hour_resets_at=usage_data["five_hour_resets_at"],
                seven_day_util=usage_data["seven_day_util"],
                seven_day_resets_at=usage_data["seven_day_resets_at"],
                threshold_percent=config.get("threshold_percent", 0),
                base_delay=config.get("base_delay", 5),
                max_delay=config.get("max_delay", 350),
                use_adaptive=True,
                safety_buffer_pct=config.get("safety_buffer_pct", 95.0),
                preload_hours=config.get("preload_hours", 12.0),
                weekly_limit_enabled=config.get("weekly_limit_enabled", True),
            )

            return {
                "enabled": enabled,
                "has_data": True,
                "five_hour": decision["five_hour"],
                "seven_day": decision["seven_day"],
                "constrained_window": decision["constrained_window"],
                "deviation_percent": decision["deviation_percent"],
                "should_throttle": decision["should_throttle"],
                "delay_seconds": decision["delay_seconds"],
                "algorithm": decision.get("algorithm", "legacy"),
                "strategy": decision.get("strategy", "unknown"),
                "weekly_limit_enabled": config.get("weekly_limit_enabled", True),
                "tempo_enabled": config.get("tempo_enabled", True),
                "last_update": usage_data["timestamp"],
            }

        except ImportError:
            # Pace-maker not installed or import failed
            return {
                "enabled": enabled,
                "has_data": True,
                "error": "Cannot import pace-maker modules",
            }

    def _read_config(self) -> Optional[Dict[str, Any]]:
        """Read pace-maker configuration file"""
        try:
            if not self.config_path.exists():
                return None

            with open(self.config_path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

    def _get_latest_usage(self) -> Optional[Dict[str, Any]]:
        """Get latest usage snapshot from pace-maker database"""
        try:
            if not self.db_path.exists():
                return None

            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT timestamp, five_hour_util, five_hour_resets_at,
                       seven_day_util, seven_day_resets_at
                FROM usage_snapshots
                ORDER BY timestamp DESC
                LIMIT 1
            """
            )

            row = cursor.fetchone()
            conn.close()

            if not row:
                return None

            # Parse datetime strings
            five_hour_resets = None
            if row[2]:
                try:
                    five_hour_resets = datetime.fromisoformat(row[2])
                except (ValueError, TypeError):
                    pass

            seven_day_resets = None
            if row[4]:
                try:
                    seven_day_resets = datetime.fromisoformat(row[4])
                except (ValueError, TypeError):
                    pass

            return {
                "timestamp": datetime.fromtimestamp(row[0]),
                "five_hour_util": row[1],
                "five_hour_resets_at": five_hour_resets,
                "seven_day_util": row[3],
                "seven_day_resets_at": seven_day_resets,
            }

        except (sqlite3.Error, OSError):
            return None
