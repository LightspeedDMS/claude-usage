"""Integration with Claude Pace Maker system

Reads pace-maker database and config to display throttling status
in the usage monitor without requiring pace-maker to be installed.
"""

import json
import logging
import sqlite3
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

# Constants for time calculations
SECONDS_IN_24_HOURS = 86400

# Default clean code rules count from pace-maker
DEFAULT_CLEAN_CODE_RULES_COUNT = 20
DEFAULT_DANGER_BASH_RULES_COUNT = 55

# Langfuse connection timeout in seconds
LANGFUSE_CONNECTION_TIMEOUT = 3

# Default log level (2 = WARNING)
DEFAULT_LOG_LEVEL = 2

# SQLite connection timeout in seconds (used for all direct DB reads)
DB_TIMEOUT = 5.0

# Codex usage table singleton row id (pace-maker stores exactly one record)
CODEX_USAGE_ROW_ID = 1


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

    def is_fallback_active(self) -> bool:
        """Check if pace-maker is currently in fallback mode.

        Delegates to UsageModel.is_fallback_active() which reads fallback_state_v2
        from SQLite (single source of truth).

        Returns:
            True if fallback state is 'fallback', False otherwise.
        """
        try:
            import sys

            pm_src = self._get_pacemaker_src_path()
            if pm_src and str(pm_src) not in sys.path:
                sys.path.insert(0, str(pm_src))

            from pacemaker.usage_model import UsageModel

            model = UsageModel(db_path=str(self.pm_dir / "usage.db"))
            return model.is_fallback_active()
        except ImportError:
            # UsageModel not installed — pace-maker not available
            return False
        except Exception as e:
            logging.warning(
                "Unexpected error checking fallback state via UsageModel: %s", e
            )
            return False

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
            codex = self._read_codex_usage()
            return {
                "enabled": enabled,
                "has_data": False,
                "intent_validation_enabled": config.get(
                    "intent_validation_enabled", False
                ),
                "tdd_enabled": config.get("tdd_enabled", False),
                "tempo_enabled": config.get("tempo_enabled", True),
                "subagent_reminder_enabled": config.get(
                    "subagent_reminder_enabled", True
                ),
                "weekly_limit_enabled": config.get("weekly_limit_enabled", True),
                "five_hour_limit_enabled": config.get("five_hour_limit_enabled", True),
                "preferred_subagent_model": config.get(
                    "preferred_subagent_model", "auto"
                ),
                "hook_model": config.get("hook_model", "auto"),
                "codex_primary_pct": codex["primary_used_pct"] if codex else None,
                "codex_secondary_pct": codex["secondary_used_pct"] if codex else None,
                "codex_limit_id": codex.get("limit_id") if codex else None,
                "codex_plan_type": codex.get("plan_type") if codex else None,
                "clean_code_rules_count": self._get_clean_code_rules_count(),
                "clean_code_rules_breakdown": self._get_clean_code_rules_breakdown(),
                "danger_bash_enabled": config.get("danger_bash_enabled", True),
                "danger_bash_rules_count": self._get_danger_bash_rules_count(),
                "danger_bash_rules_breakdown": self._get_danger_bash_rules_breakdown(),
                "log_level": config.get("log_level", DEFAULT_LOG_LEVEL),
                "coefficients_5h": None,
                "coefficients_7d": None,
                "coefficients_5x_overridden": False,
                "coefficients_20x_overridden": False,
            }

        # Calculate pacing decision using pace-maker's algorithm
        try:
            # Import pace-maker's pacing engine
            import sys

            # Use shared helper to find pace-maker source directory (P7: no duplication)
            pm_src = self._get_pacemaker_src_path()

            # Add to path if exists
            if pm_src and str(pm_src) not in sys.path:
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
                safety_buffer_pct=config.get("safety_buffer_pct", 95.0),
                preload_hours=config.get("preload_hours", 12.0),
                weekly_limit_enabled=config.get("weekly_limit_enabled", True),
                five_hour_limit_enabled=config.get("five_hour_limit_enabled", True),
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
                "hook_model": config.get("hook_model", "auto"),
                "clean_code_rules_count": self._get_clean_code_rules_count(),
                "clean_code_rules_breakdown": self._get_clean_code_rules_breakdown(),
                "danger_bash_enabled": config.get("danger_bash_enabled", True),
                "danger_bash_rules_count": self._get_danger_bash_rules_count(),
                "danger_bash_rules_breakdown": self._get_danger_bash_rules_breakdown(),
                "log_level": config.get("log_level", DEFAULT_LOG_LEVEL),
                "last_update": usage_data["timestamp"],
            }

            # Populate codex usage percentages and billing mode for Hook Model color-coding
            codex = self._read_codex_usage()
            status_result["codex_primary_pct"] = (
                codex["primary_used_pct"] if codex else None
            )
            status_result["codex_secondary_pct"] = (
                codex["secondary_used_pct"] if codex else None
            )
            status_result["codex_limit_id"] = codex.get("limit_id") if codex else None
            status_result["codex_plan_type"] = codex.get("plan_type") if codex else None

            # Propagate stale data flag if present
            # Use 'is True' to avoid false positives from MagicMock objects in tests
            if decision.get("stale_data") is True:
                status_result["stale_data"] = True
                if decision.get("error"):
                    status_result["error"] = decision["error"]

            # Fetch coefficients (calibrated preferred, fallback to defaults)
            try:
                from pacemaker.fallback import _DEFAULT_TOKEN_COSTS
                from pacemaker.usage_model import UsageModel

                coeff_5h_5x = _DEFAULT_TOKEN_COSTS["5x"]["coefficient_5h"]
                coeff_5h_20x = _DEFAULT_TOKEN_COSTS["20x"]["coefficient_5h"]
                coeff_7d_5x = _DEFAULT_TOKEN_COSTS["5x"]["coefficient_7d"]
                coeff_7d_20x = _DEFAULT_TOKEN_COSTS["20x"]["coefficient_7d"]

                model = UsageModel(db_path=str(self.db_path))
                cal_5x = model._get_calibrated_coefficients("5x")
                if cal_5x is not None:
                    coeff_5h_5x, coeff_7d_5x = cal_5x
                cal_20x = model._get_calibrated_coefficients("20x")
                if cal_20x is not None:
                    coeff_5h_20x, coeff_7d_20x = cal_20x

                status_result["coefficients_5h"] = {
                    "5x": coeff_5h_5x,
                    "20x": coeff_5h_20x,
                }
                status_result["coefficients_7d"] = {
                    "5x": coeff_7d_5x,
                    "20x": coeff_7d_20x,
                }
                status_result["coefficients_5x_overridden"] = cal_5x is not None
                status_result["coefficients_20x_overridden"] = cal_20x is not None
            except Exception as e:
                # Coefficients are optional display data; log for debugging but don't fail
                logging.debug("Failed to fetch pacemaker coefficients: %s", e)

            # Add fallback mode indicators (Story #38)
            fallback_active = self.is_fallback_active()
            status_result["fallback_mode"] = fallback_active
            status_result["is_synthetic"] = fallback_active
            if fallback_active:
                status_result["fallback_message"] = (
                    "API unavailable - using estimated pacing"
                )
                # _get_latest_usage() already returns synthetic values from
                # UsageModel/SQLite during fallback, so the main
                # calculate_pacing_decision call above already has correct data.
                # Just clear stale markers so display.py doesn't short-circuit.
                status_result.pop("error", None)
                status_result.pop("stale_data", None)
            else:
                status_result["fallback_message"] = None

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
                "hook_model": config.get("hook_model", "auto"),
                "clean_code_rules_count": self._get_clean_code_rules_count(),
                "clean_code_rules_breakdown": self._get_clean_code_rules_breakdown(),
                "danger_bash_enabled": config.get("danger_bash_enabled", True),
                "danger_bash_rules_count": self._get_danger_bash_rules_count(),
                "danger_bash_rules_breakdown": self._get_danger_bash_rules_breakdown(),
                "log_level": config.get("log_level", DEFAULT_LOG_LEVEL),
                "coefficients_5h": None,
                "coefficients_7d": None,
                "coefficients_5x_overridden": False,
                "coefficients_20x_overridden": False,
            }

    def _read_codex_usage(self) -> Optional[Dict[str, Any]]:
        """Read Codex usage from the codex_usage table in pace-maker DB.

        Returns:
            Dict with primary_used_pct and secondary_used_pct, or None if
            the table doesn't exist, is empty, or on any error.
        """
        if not self.db_path.exists():
            return None
        try:
            with sqlite3.connect(str(self.db_path), timeout=DB_TIMEOUT) as conn:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT primary_used_pct, secondary_used_pct, plan_type, limit_id"
                    " FROM codex_usage WHERE id = ?",
                    (CODEX_USAGE_ROW_ID,),
                )
                row = cursor.fetchone()
            if row is None:
                return None
            return {
                "primary_used_pct": row["primary_used_pct"],
                "secondary_used_pct": row["secondary_used_pct"],
                "plan_type": row["plan_type"],
                "limit_id": row["limit_id"] if "limit_id" in row.keys() else None,
            }
        except (sqlite3.Error, OSError) as e:
            logging.debug("Failed to read codex_usage from DB: %s", e)
            return None

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
        """Get latest usage snapshot via UsageModel (single source of truth).

        During fallback mode, UsageModel.get_current_usage() returns synthetic
        estimates from fallback_state_v2 + accumulated_costs, so the monitor
        always sees current values rather than stale real-API data.

        Returns:
            Dict with keys: timestamp, five_hour_util, five_hour_resets_at,
            seven_day_util, seven_day_resets_at. Returns None if no data.
        """
        try:
            import sys

            pm_src = self._get_pacemaker_src_path()
            if pm_src and str(pm_src) not in sys.path:
                sys.path.insert(0, str(pm_src))

            from pacemaker.usage_model import UsageModel

            model = UsageModel(db_path=str(self.db_path))
            snapshot = model.get_current_usage()
            if snapshot is None:
                return None

            return {
                "timestamp": snapshot.timestamp,
                "five_hour_util": snapshot.five_hour_util,
                "five_hour_resets_at": snapshot.five_hour_resets_at,
                "seven_day_util": snapshot.seven_day_util,
                "seven_day_resets_at": snapshot.seven_day_resets_at,
            }
        except ImportError:
            # UsageModel not installed — pace-maker not available
            return None
        except Exception as e:
            logging.warning(
                "Unexpected error getting latest usage via UsageModel: %s", e
            )
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
            "intent_validation_dangerbash",
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

            conn = sqlite3.connect(str(self.db_path), timeout=5.0)
            conn.execute("PRAGMA journal_mode=WAL")
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
            "intent_validation": "Intent Val.",
            "intent_validation_tdd": "Intent TDD",
            "intent_validation_cleancode": "Clean Code",
            "intent_validation_dangerbash": "Danger Bash",
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

            conn = sqlite3.connect(str(self.db_path), timeout=5.0)
            conn.execute("PRAGMA journal_mode=WAL")
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

    def get_secrets_metrics(self) -> Optional[Dict[str, int]]:
        """Get secrets metrics for the last 24 hours.

        Reads from secrets_metrics table in pace-maker database and sums
        all buckets within the 24-hour window.

        Returns:
            Dict with keys:
            - secrets_masked: Total secrets masked in last 24h
            Returns None if database is unavailable or table doesn't exist.
        """
        if not self.db_path.exists():
            return None

        try:
            import time

            cutoff = time.time() - SECONDS_IN_24_HOURS

            conn = sqlite3.connect(str(self.db_path), timeout=5.0)
            conn.execute("PRAGMA journal_mode=WAL")
            try:
                cursor = conn.cursor()

                # Query sum of all secrets masked within 24-hour window
                cursor.execute(
                    """
                    SELECT COALESCE(SUM(secrets_masked_count), 0)
                    FROM secrets_metrics
                    WHERE bucket_timestamp >= ?
                    """,
                    (cutoff,),
                )

                row = cursor.fetchone()

                if not row:
                    return None

                secrets_masked = int(row[0])

                # Query count of stored secrets
                cursor.execute("SELECT COUNT(*) FROM secrets")
                stored_row = cursor.fetchone()
                secrets_stored = int(stored_row[0]) if stored_row else 0

                return {
                    "secrets_masked": secrets_masked,
                    "secrets_stored": secrets_stored,
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
        """Get the count of merged clean code rules from pace-maker.

        Calls load_rules() to get the actual merged count (defaults minus
        deleted plus custom), not just the default count.

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

            # Reload if already cached so changes after ./install.sh are picked up
            # without restarting the monitor (fixes module import caching issue).
            import importlib

            _ccr_module_name = "pacemaker.clean_code_rules"
            if _ccr_module_name in sys.modules:
                try:
                    importlib.reload(sys.modules[_ccr_module_name])
                except (TypeError, AttributeError, ImportError):
                    pass  # Reload failed (e.g., mock in tests); use cached module

            from pacemaker.clean_code_rules import load_rules

            config_path = str(self.pm_dir / "clean_code_rules.yaml")
            rules = load_rules(config_path)
            return len(rules)

        except (ImportError, AttributeError, OSError) as e:
            logging.debug("Clean-code rules load failed, using default count: %s", e)
            return DEFAULT_CLEAN_CODE_RULES_COUNT

    def _get_clean_code_rules_breakdown(self) -> Optional[Dict[str, int]]:
        """Get breakdown of clean code rules by source (custom/deleted).

        Returns:
            Dict with 'custom' and 'deleted' counts, or None if unavailable
            or no customizations exist.
        """
        try:
            import sys

            pm_src = self._get_pacemaker_src_path()
            if not pm_src:
                return None

            if str(pm_src) not in sys.path:
                sys.path.insert(0, str(pm_src))

            from pacemaker.clean_code_rules import (
                get_rules_metadata,
                _load_custom_config,
            )

            config_path = str(self.pm_dir / "clean_code_rules.yaml")
            metadata = get_rules_metadata(config_path)
            custom_config = _load_custom_config(config_path)

            custom_count = sum(1 for m in metadata if m.get("source") == "custom")
            deleted_count = len(custom_config.get("deleted_rules", []))

            if custom_count == 0 and deleted_count == 0:
                return None  # No customizations — caller skips breakdown display

            return {"custom": custom_count, "deleted": deleted_count}

        except (ImportError, AttributeError, OSError, KeyError, TypeError) as e:
            logging.debug("Rules breakdown unavailable, skipping display: %s", e)
            return None

    def _ensure_pm_on_sys_path(self) -> bool:
        """Ensure pace-maker source is on sys.path for dynamic imports.

        Returns:
            True if path is available and added, False otherwise.
        """
        import sys

        pm_src = self._get_pacemaker_src_path()
        if not pm_src:
            return False
        if str(pm_src) not in sys.path:
            sys.path.insert(0, str(pm_src))
        return True

    def _get_danger_bash_rules_count(self) -> int:
        """Get the count of merged danger bash rules from pace-maker.

        Returns:
            Number of danger bash rules configured, defaults to
            DEFAULT_DANGER_BASH_RULES_COUNT.
        """
        try:
            if not self._ensure_pm_on_sys_path():
                return DEFAULT_DANGER_BASH_RULES_COUNT

            import importlib
            import sys

            _mod = "pacemaker.danger_bash_rules"
            if _mod in sys.modules:
                try:
                    importlib.reload(sys.modules[_mod])
                except (TypeError, AttributeError, ImportError) as e:
                    logging.debug(
                        "Reload of %s skipped: %s; using cached module", _mod, e
                    )

            from pacemaker.danger_bash_rules import load_rules

            config_path = str(self.pm_dir / "danger_bash_rules.yaml")
            return len(load_rules(config_path))

        except (ImportError, AttributeError, OSError) as e:
            logging.debug("Danger-bash rules load failed: %s", e)
            return DEFAULT_DANGER_BASH_RULES_COUNT

    def _get_danger_bash_rules_breakdown(self) -> Optional[Dict[str, int]]:
        """Get breakdown of danger bash rules by source (custom/deleted).

        Returns:
            Dict with 'custom' and 'deleted' counts, or None if no
            customizations.
        """
        try:
            if not self._ensure_pm_on_sys_path():
                return None

            from pacemaker.danger_bash_rules import (
                get_rules_metadata,
                _load_custom_config,
            )

            config_path = str(self.pm_dir / "danger_bash_rules.yaml")
            metadata = get_rules_metadata(config_path)
            custom_config = _load_custom_config(config_path)

            custom_count = sum(1 for m in metadata if m.get("source") == "custom")
            deleted_count = len(custom_config.get("deleted_rules", []))

            if custom_count == 0 and deleted_count == 0:
                return None

            return {"custom": custom_count, "deleted": deleted_count}

        except (ImportError, AttributeError, OSError, KeyError, TypeError) as e:
            logging.debug("Danger-bash breakdown unavailable: %s", e)
            return None

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

            # Reload pacemaker package if already cached so version changes after
            # ./install.sh are picked up without restarting the monitor.
            import importlib

            if "pacemaker" in sys.modules:
                try:
                    importlib.reload(sys.modules["pacemaker"])
                except (TypeError, AttributeError, ImportError):
                    pass  # Reload failed (e.g., mock in tests); use cached module

            from pacemaker import __version__

            return __version__
        except ImportError:
            return "unknown"

    def get_governance_events(self, window_seconds: int = 3600) -> list:
        """Get governance events from the pace-maker database.

        Reads from the governance_events table and returns events within
        the specified time window, ordered newest first.

        Args:
            window_seconds: How many seconds back to look (default 3600 = 1h)

        Returns:
            List of dicts with event_type, project_name, session_id,
            feedback_text, and timestamp keys. Returns [] on any error.
        """
        if not self.db_path.exists():
            return []

        try:
            import time

            cutoff = time.time() - window_seconds

            conn = sqlite3.connect(str(self.db_path), timeout=5.0)
            conn.execute("PRAGMA journal_mode=WAL")
            try:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT event_type, project_name, session_id,
                           feedback_text, timestamp
                    FROM governance_events
                    WHERE timestamp >= ?
                    ORDER BY timestamp DESC
                    """,
                    (cutoff,),
                )
                rows = cursor.fetchall()
                return [
                    {
                        "event_type": row[0],
                        "project_name": row[1],
                        "session_id": row[2],
                        "feedback_text": row[3],
                        "timestamp": row[4],
                    }
                    for row in rows
                ]
            finally:
                conn.close()

        except (sqlite3.Error, OSError):
            return []

    def get_recent_activity(self, window_seconds: int = 10) -> list:
        """Get the most recent activity event per event_code within the time window.

        Reads from the activity_events table in the pace-maker SQLite database.
        Returns one entry per event_code (most recent across all sessions).

        Args:
            window_seconds: How many seconds back to look (default 10)

        Returns:
            List of dicts with 'event_code' and 'status' keys.
            Returns [] if database is unavailable or table does not exist.
        """
        if not self.db_path.exists():
            return []

        try:
            import time

            cutoff = time.time() - window_seconds

            conn = sqlite3.connect(str(self.db_path), timeout=5.0)
            conn.execute("PRAGMA journal_mode=WAL")
            try:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT event_code, status
                    FROM activity_events
                    WHERE timestamp > ?
                      AND id IN (
                          SELECT id FROM activity_events ae2
                          WHERE ae2.event_code = activity_events.event_code
                            AND ae2.timestamp > ?
                          ORDER BY ae2.timestamp DESC
                          LIMIT 1
                      )
                    GROUP BY event_code
                    """,
                    (cutoff, cutoff),
                )
                rows = cursor.fetchall()
                return [{"event_code": row[0], "status": row[1]} for row in rows]
            finally:
                conn.close()

        except (sqlite3.Error, OSError):
            return []

    def get_recent_error_count(self, hours: int = 24) -> int:
        """Count ERROR-level log entries from the last N hours.

        Scans rotated log files (today's and yesterday's) for errors.

        Args:
            hours: Number of hours to look back (default: 24)

        Returns:
            Count of ERROR entries within the time window
        """
        import re
        from datetime import timedelta

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
