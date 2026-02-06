"""Integration with Claude Pace Maker system

Reads pace-maker database and config to display throttling status
in the usage monitor without requiring pace-maker to be installed.
"""

import json
import sqlite3
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

# Constants for time calculations
SECONDS_IN_24_HOURS = 86400

# Default clean code rules count from pace-maker
DEFAULT_CLEAN_CODE_RULES_COUNT = 17

# Langfuse connection timeout in seconds
LANGFUSE_CONNECTION_TIMEOUT = 3


def _is_pipx_installation(install_path: str) -> bool:
    """Check if installation path indicates pipx installation

    Args:
        install_path: Path from install_source file

    Returns:
        True if path contains pipx venv structure
    """
    return ".local/share/pipx/venvs/" in install_path


def _find_pipx_site_packages(install_path: str) -> Optional[str]:
    """Find site-packages directory in pipx venv

    Args:
        install_path: Path from install_source file (typically share directory)

    Returns:
        Path to site-packages directory or None if not found
    """
    path = Path(install_path)

    # Navigate up to venv root (from share/claude-pace-maker to venv root)
    # Typical structure: ~/.local/share/pipx/venvs/claude-pace-maker/share/claude-pace-maker
    # We need to get to: ~/.local/share/pipx/venvs/claude-pace-maker

    # Find the venv root by looking for parent containing 'venvs' directory
    current = path
    venv_root = None

    # Go up the directory tree to find venv root
    while current.parent != current:  # Stop at filesystem root
        if current.parent.name == "venvs":
            venv_root = current
            break
        current = current.parent

    if not venv_root:
        return None

    # Look for lib/pythonX.Y/site-packages
    lib_dir = venv_root / "lib"
    if not lib_dir.exists():
        return None

    # Find any pythonX.Y directory
    for python_dir in lib_dir.iterdir():
        if python_dir.is_dir() and python_dir.name.startswith("python"):
            site_packages = python_dir / "site-packages"
            if site_packages.exists():
                return str(site_packages)

    return None


class PaceMakerReader:
    """Reads pace-maker state from database and config files"""

    def __init__(self):
        """Initialize pace-maker reader with default paths"""
        self.pm_dir = Path.home() / ".claude-pace-maker"
        self.config_path = self.pm_dir / "config.json"
        self.db_path = self.pm_dir / "usage.db"
        self.state_path = self.pm_dir / "state.json"
        # Cache for blockage stats (AC4)
        self._blockage_stats_cache = None
        self._blockage_stats_cache_time = 0
        self._cache_ttl_seconds = 5

    def _get_pacemaker_src_path(self) -> Optional[Path]:
        """Find pace-maker source directory path.

        Returns:
            Path to pace-maker src directory, or None if not found
        """
        pm_src = None

        # Check if install_source file exists
        install_source_file = self.pm_dir / "install_source"
        if install_source_file.exists():
            try:
                with open(install_source_file) as f:
                    source_path = f.read().strip()

                    # Check if this is a pipx installation
                    if _is_pipx_installation(source_path):
                        # Find site-packages in pipx venv
                        site_packages = _find_pipx_site_packages(source_path)
                        if site_packages:
                            pm_src = Path(site_packages)
                    else:
                        # Regular dev installation - use src directory
                        pm_src = Path(source_path) / "src"
            except (OSError, ValueError):
                # Failed to read install_source - will try fallback location
                pass

        # Fallback: check standard installation location
        if not pm_src or not pm_src.exists():
            pm_src = self.pm_dir / "src"

        # Return None if path doesn't exist
        if pm_src and pm_src.exists():
            return pm_src

        return None

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
                'last_update': datetime,
                'tdd_enabled': bool,
                'preferred_subagent_model': str,
                'clean_code_rules_count': int
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
                "tdd_enabled": config.get("tdd_enabled", False),
                "preferred_subagent_model": config.get(
                    "preferred_subagent_model", "auto"
                ),
                "clean_code_rules_count": self._get_clean_code_rules_count(),
            }

        # Calculate pacing decision using pace-maker's algorithm
        try:
            # Import pace-maker's pacing engine
            import sys

            # Try to find pace-maker source directory
            pm_src = None

            # Check if install_source file exists
            install_source_file = self.pm_dir / "install_source"
            if install_source_file.exists():
                try:
                    with open(install_source_file) as f:
                        source_path = f.read().strip()

                        # Check if this is a pipx installation
                        if _is_pipx_installation(source_path):
                            # Find site-packages in pipx venv
                            site_packages = _find_pipx_site_packages(source_path)
                            if site_packages:
                                pm_src = Path(site_packages)
                        else:
                            # Regular dev installation - use src directory
                            pm_src = Path(source_path) / "src"
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

            status_result = {
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
                "five_hour_limit_enabled": config.get("five_hour_limit_enabled", True),
                "tempo_enabled": config.get("tempo_enabled", True),
                "subagent_reminder_enabled": config.get(
                    "subagent_reminder_enabled", True
                ),
                "intent_validation_enabled": config.get(
                    "intent_validation_enabled", False
                ),
                "tdd_enabled": config.get("tdd_enabled", False),
                "preferred_subagent_model": config.get(
                    "preferred_subagent_model", "auto"
                ),
                "clean_code_rules_count": self._get_clean_code_rules_count(),
                "last_update": usage_data["timestamp"],
            }

            # Propagate stale data flag if present
            # Use 'is True' to avoid false positives from MagicMock objects in tests
            if decision.get("stale_data") is True:
                status_result["stale_data"] = True
                if decision.get("error"):
                    status_result["error"] = decision["error"]

            return status_result

        except ImportError:
            # Pace-maker not installed or import failed
            return {
                "enabled": enabled,
                "has_data": True,
                "error": "Cannot import pace-maker modules",
                "tdd_enabled": config.get("tdd_enabled", False),
                "preferred_subagent_model": config.get(
                    "preferred_subagent_model", "auto"
                ),
                "clean_code_rules_count": self._get_clean_code_rules_count(),
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

    def get_blockage_stats(self) -> Optional[Dict[str, int]]:
        """Get blockage counts per category for the last 60 minutes.

        Returns:
            Dict mapping each category to its count (zero-filled for missing categories),
            plus a 'total' key with sum of all counts.
            Returns None if database is unavailable.
        """
        # Define all expected categories (matching pace-maker constants)
        categories = [
            "intent_validation",
            "intent_validation_tdd",
            "intent_validation_cleancode",
            "pacing_tempo",
            "pacing_quota",
            "other",
        ]

        if not self.is_installed():
            return None

        if not self.db_path.exists():
            return None

        try:
            import time

            # Calculate cutoff timestamp (60 minutes ago)
            cutoff_timestamp = int(time.time()) - 3600

            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            # Query counts grouped by category
            cursor.execute(
                """
                SELECT category, COUNT(*) as count
                FROM blockage_events
                WHERE timestamp >= ?
                GROUP BY category
                """,
                (cutoff_timestamp,),
            )

            # Initialize result with all categories set to 0
            result = {category: 0 for category in categories}

            # Update result with actual counts
            for row in cursor.fetchall():
                category, count = row
                if category in result:
                    result[category] = count

            conn.close()

            # Add total
            result["total"] = sum(result[cat] for cat in categories)

            return result

        except (sqlite3.Error, OSError):
            return None

    def get_blockage_stats_with_labels(self) -> Optional[Dict[str, int]]:
        """Get blockage stats with human-readable category labels.

        Returns:
            Dict mapping human-readable labels to counts, plus 'Total'.
            Returns None if database is unavailable.
        """
        # Human-readable labels for categories (excluding 'other' - catch-all that's rarely used)
        category_labels = {
            "intent_validation": "Intent Validation",
            "intent_validation_tdd": "Intent TDD",
            "intent_validation_cleancode": "Clean Code",
            "pacing_tempo": "Pacing Tempo",
            "pacing_quota": "Pacing Quota",
        }

        stats = self.get_blockage_stats()
        if stats is None:
            return None

        # Convert to human-readable labels
        result = {}
        for category, label in category_labels.items():
            result[label] = stats.get(category, 0)

        result["Total"] = stats.get("total", 0)
        return result

    def get_blockage_stats_cached(self) -> Optional[Dict[str, int]]:
        """Get blockage stats with caching to avoid excessive database queries.

        Returns cached result if cache is valid (within TTL), otherwise
        fetches fresh data from database.

        Returns:
            Dict mapping each category to its count, plus 'total'.
            Returns None if database is unavailable.
        """
        import time

        current_time = time.time()

        # Check if cache is valid
        if self._blockage_stats_cache is not None:
            cache_age = current_time - self._blockage_stats_cache_time
            if cache_age < self._cache_ttl_seconds:
                return self._blockage_stats_cache

        # Cache miss or expired - fetch fresh data
        fresh_stats = self.get_blockage_stats()

        # Update cache
        self._blockage_stats_cache = fresh_stats
        self._blockage_stats_cache_time = current_time

        return fresh_stats

    def get_langfuse_metrics(self) -> Optional[Dict[str, int]]:
        """Get Langfuse metrics for the last 24 hours.

        Reads from langfuse_metrics table in pace-maker database and sums
        all buckets within the 24-hour window.

        Returns:
            Dict with keys:
            - sessions: Total sessions created in last 24h
            - traces: Total traces created in last 24h
            - spans: Total spans created in last 24h
            - total: Sum of all three metrics
            Returns None if database is unavailable or table doesn't exist.
        """
        if not self.db_path.exists():
            return None

        try:
            import time

            cutoff = time.time() - SECONDS_IN_24_HOURS

            conn = sqlite3.connect(str(self.db_path))
            try:
                cursor = conn.cursor()

                # Query sum of all metrics within 24-hour window
                cursor.execute(
                    """
                    SELECT COALESCE(SUM(sessions_count), 0),
                           COALESCE(SUM(traces_count), 0),
                           COALESCE(SUM(spans_count), 0)
                    FROM langfuse_metrics
                    WHERE bucket_timestamp >= ?
                    """,
                    (cutoff,),
                )

                row = cursor.fetchone()

                if not row:
                    return None

                sessions = int(row[0])
                traces = int(row[1])
                spans = int(row[2])
                total = sessions + traces + spans

                return {
                    "sessions": sessions,
                    "traces": traces,
                    "spans": spans,
                    "total": total,
                }
            finally:
                conn.close()

        except (sqlite3.Error, OSError):
            # Graceful degradation - return None when database is unavailable
            # This is acceptable since return type documents None on failure
            return None

    def get_langfuse_status(self) -> bool:
        """Check if Langfuse integration is enabled and properly configured.

        Langfuse is considered enabled if ALL conditions are met:
        1. langfuse_enabled flag is True
        2. langfuse_public_key is present and non-empty
        3. langfuse_secret_key is present and non-empty

        Returns:
            True if Langfuse is enabled and configured, False otherwise
        """
        config = self._read_config()
        if not config:
            return False

        # Check enabled flag
        if not config.get("langfuse_enabled", False):
            return False

        # Check public key
        public_key = config.get("langfuse_public_key")
        if not public_key or (isinstance(public_key, str) and not public_key.strip()):
            return False

        # Check secret key
        secret_key = config.get("langfuse_secret_key")
        if not secret_key or (isinstance(secret_key, str) and not secret_key.strip()):
            return False

        return True

    def _get_clean_code_rules_count(self) -> int:
        """Get the count of clean code rules from pace-maker.

        Attempts to load clean code rules from pace-maker's clean_code_rules module.
        If the module cannot be imported or rules cannot be loaded, returns the
        default count.

        Returns:
            Number of clean code rules configured, defaults to DEFAULT_CLEAN_CODE_RULES_COUNT
        """
        try:
            import sys

            # Get pace-maker source directory
            pm_src = self._get_pacemaker_src_path()
            if not pm_src:
                return DEFAULT_CLEAN_CODE_RULES_COUNT

            # Add to path if not already present
            if str(pm_src) not in sys.path:
                sys.path.insert(0, str(pm_src))

            # Import clean_code_rules module and get default rules
            from pacemaker.clean_code_rules import get_default_rules

            rules = get_default_rules()
            return len(rules)

        except (ImportError, AttributeError, OSError):
            # Cannot load pace-maker modules or rules - return default count
            return DEFAULT_CLEAN_CODE_RULES_COUNT

    def test_langfuse_connection(self) -> Dict[str, Any]:
        """Test Langfuse API connectivity.

        Returns:
            Dict with 'connected' (bool) and 'message' (str)
        """
        config = self._read_config()
        if not config:
            return {"connected": False, "message": "Config not found"}

        base_url = config.get("langfuse_base_url")
        public_key = config.get("langfuse_public_key")
        secret_key = config.get("langfuse_secret_key")

        if not all([base_url, public_key, secret_key]):
            return {"connected": False, "message": "Not configured"}

        try:
            import sys

            # Get pace-maker source directory
            pm_src = self._get_pacemaker_src_path()
            if not pm_src:
                return {"connected": False, "message": "Langfuse client unavailable"}

            # Add to path if not already present
            if str(pm_src) not in sys.path:
                sys.path.insert(0, str(pm_src))

            from pacemaker.langfuse.client import test_connection

            return test_connection(
                base_url, public_key, secret_key, timeout=LANGFUSE_CONNECTION_TIMEOUT
            )
        except ImportError:
            return {"connected": False, "message": "Langfuse client unavailable"}
        except Exception as e:
            return {"connected": False, "message": str(e)}

    def get_pacemaker_version(self) -> str:
        """Get pace-maker version string.

        Returns:
            Version string like "1.4.0" or "unknown"
        """
        try:
            import sys

            # Get pace-maker source directory
            pm_src = self._get_pacemaker_src_path()
            if not pm_src:
                return "unknown"

            # Add to path if not already present
            if str(pm_src) not in sys.path:
                sys.path.insert(0, str(pm_src))

            from pacemaker import __version__

            return __version__
        except ImportError:
            return "unknown"

    def get_recent_error_count(self, hours: int = 24) -> int:
        """Count ERROR-level log entries from the last N hours.

        Scans rotated log files (today's and yesterday's) for errors.

        Args:
            hours: Number of hours to look back (default: 24)

        Returns:
            Count of ERROR entries within the time window
        """
        import re
        from datetime import datetime, timedelta

        LOG_FILE_PREFIX = "pace-maker-"
        LOG_FILE_SUFFIX = ".log"

        try:
            cutoff_time = datetime.now() - timedelta(hours=hours)
            error_count = 0
            pattern = re.compile(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] \[ERROR\]")

            # Get log files for last 2 days
            log_files = []
            for i in range(2):
                date = datetime.now() - timedelta(days=i)
                date_str = date.strftime("%Y-%m-%d")
                log_path = self.pm_dir / f"{LOG_FILE_PREFIX}{date_str}{LOG_FILE_SUFFIX}"
                if log_path.exists():
                    log_files.append(log_path)

            if not log_files:
                return 0

            for log_file in log_files:
                try:
                    with open(log_file, "r") as f:
                        for line in f:
                            match = pattern.match(line)
                            if match:
                                try:
                                    ts = datetime.strptime(
                                        match.group(1), "%Y-%m-%d %H:%M:%S"
                                    )
                                    if ts >= cutoff_time:
                                        error_count += 1
                                except ValueError:
                                    continue
                except (OSError, IOError):
                    continue

            return error_count
        except Exception:
            return 0
