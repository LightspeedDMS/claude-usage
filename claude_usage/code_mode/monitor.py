"""Code mode monitor for Claude Code usage tracking"""

import json
import logging
import time
from pathlib import Path
from datetime import datetime
from rich.live import Live
from rich.console import Console, Group
from rich.text import Text

from .auth import OAuthManager
from .api import ClaudeAPIClient
from .storage import CodeStorage, CodeAnalytics
from .display import UsageRenderer
from .pacemaker_integration import PaceMakerReader

console = Console()


class CodeMonitor:
    """Monitor Claude Code account usage via the discovered API"""

    POLL_INTERVAL = 300  # seconds between API calls (5 minutes — same as pace-maker)
    DISPLAY_REFRESH_INTERVAL = 10  # seconds between display refreshes
    CACHE_FRESHNESS_SECONDS = 360  # slightly above poll interval

    def __init__(self, credentials_path=None):
        if credentials_path is None:
            credentials_path = Path.home() / ".claude" / ".credentials.json"

        self.credentials_path = Path(credentials_path)
        storage_dir = Path.home() / ".claude-usage"
        db_path = storage_dir / "usage_history.db"

        # Initialize components
        self.oauth_manager = OAuthManager(self.credentials_path)
        self.api_client = ClaudeAPIClient()
        self.storage = CodeStorage(db_path)
        self.analytics = CodeAnalytics(self.storage)
        self.renderer = UsageRenderer()
        self.pacemaker_reader = PaceMakerReader()

        # State
        self.credentials = None
        self.org_uuid = None
        self.account_uuid = None
        self.last_usage = None
        self.last_profile = None
        self.last_update = None
        self.error_message = None

        # Load initial credentials
        self._load_credentials()

    def _load_credentials(self):
        """Load OAuth credentials from Claude Code config"""
        self.credentials, error = self.oauth_manager.load_credentials()
        if error:
            self.error_message = error

    def _refresh_from_model(self):
        """Lightweight read from UsageModel — just a SQLite query, no API call.

        Called on every display cycle so the monitor always shows the freshest
        data written by the pace-maker hook (which polls the API every 60s).
        """
        if not self.pacemaker_reader.is_installed():
            return False

        try:
            import sys

            pm_src = self.pacemaker_reader._get_pacemaker_src_path()
            if pm_src and str(pm_src) not in sys.path:
                sys.path.insert(0, str(pm_src))

            from pacemaker.usage_model import UsageModel

            model = UsageModel()
            snapshot = model.get_current_usage()
            if snapshot is not None:
                age = (datetime.utcnow() - snapshot.timestamp).total_seconds()
                if age <= self.CACHE_FRESHNESS_SECONDS:
                    self.last_usage = {
                        "five_hour": {
                            "utilization": snapshot.five_hour_util,
                            "resets_at": (
                                snapshot.five_hour_resets_at.isoformat() + "+00:00"
                                if snapshot.five_hour_resets_at
                                else ""
                            ),
                        },
                        "seven_day": {
                            "utilization": snapshot.seven_day_util,
                            "resets_at": (
                                snapshot.seven_day_resets_at.isoformat() + "+00:00"
                                if snapshot.seven_day_resets_at
                                else ""
                            ),
                        },
                    }
                    self.last_update = snapshot.timestamp
                    self.error_message = None
                    return True
        except ImportError:
            logging.debug("UsageModel not available, skipping model refresh")
        except Exception as e:
            logging.debug(f"Failed to refresh from UsageModel: {e}")

        return False

    def fetch_usage(self):
        """Fetch usage data — heavyweight fallback with API call.

        Called every POLL_INTERVAL (300s). When UsageModel is available,
        _refresh_from_model() in the display loop provides data every cycle.
        """
        # Try UsageModel first (cheap SQLite read)
        if self._refresh_from_model():
            return True

        # Check if we need to reload credentials
        if not self.credentials:
            self._load_credentials()

        if not self.credentials:
            return False

        # Check token expiry and reload from file/Keychain if needed
        if self.oauth_manager.is_token_expired(self.credentials):
            self._load_credentials()

            # After reload, check if we still have expired token or no credentials
            if not self.credentials or self.oauth_manager.is_token_expired(
                self.credentials
            ):
                return False

        # Detect pace-maker backoff BEFORE touching the API, but read the cache
        # first so we can serve cached data even during backoff.
        pacemaker_backoff_path = Path.home() / ".claude-pace-maker" / "api_backoff.json"
        pacemaker_in_backoff = False
        backoff_remaining = 0.0
        try:
            if pacemaker_backoff_path.exists():
                backoff_data = json.loads(pacemaker_backoff_path.read_text())
                backoff_until = backoff_data.get("backoff_until", 0)
                if backoff_until and time.time() < backoff_until:
                    pacemaker_in_backoff = True
                    backoff_remaining = backoff_until - time.time()
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as e:
            logging.debug(
                f"Failed to read pace-maker backoff file, proceeding with API: {e}"
            )

        # During backoff, skip the API entirely.
        # If we already have last_usage from a previous fetch, keep it (full display).
        # Only show the backoff error if we have absolutely no data.
        if pacemaker_in_backoff:
            if self.last_usage is not None:
                return True
            self.error_message = (
                f"API backoff (pace-maker): {backoff_remaining:.0f}s remaining"
            )
            return False

        # Make API request
        headers = self.oauth_manager.get_auth_headers(self.credentials)
        usage_data, error = self.api_client.fetch_usage(headers)

        if usage_data:
            self.last_usage = usage_data
            self.last_update = datetime.now()
            self.error_message = None
            return True
        else:
            self.error_message = error
            return False

    def fetch_profile(self):
        """Fetch profile data from Claude Code API"""
        if not self.credentials:
            return False

        headers = self.oauth_manager.get_auth_headers(self.credentials)
        profile_data, org_uuid, account_uuid, error = self.api_client.fetch_profile(
            headers
        )

        if profile_data:
            self.last_profile = profile_data
            self.org_uuid = org_uuid
            self.account_uuid = account_uuid
            return True
        else:
            # Profile data rarely changes — preserve the last known value so the
            # full display keeps rendering even when the API is temporarily unavailable
            # (e.g. during backoff). Only propagate the error when we have nothing.
            if self.last_profile is not None:
                return True
            if error:
                self.error_message = error
            return False

    def get_display(self):
        """Generate rich display for current usage"""
        # Get pace-maker status if installed
        pacemaker_status = None
        weekly_limit_enabled = True  # Default
        blockage_stats = None
        langfuse_metrics = None
        secrets_metrics = None
        if self.pacemaker_reader.is_installed():
            pacemaker_status = self.pacemaker_reader.get_status()
            if pacemaker_status:
                weekly_limit_enabled = pacemaker_status.get(
                    "weekly_limit_enabled", True
                )
                # CRITICAL-1c: Inject Langfuse status into pacemaker_status
                pacemaker_status["langfuse_enabled"] = (
                    self.pacemaker_reader.get_langfuse_status()
                )
                # Test Langfuse connection
                pacemaker_status["langfuse_connection"] = (
                    self.pacemaker_reader.test_langfuse_connection()
                )
                # Get versions
                pacemaker_status["pacemaker_version"] = (
                    self.pacemaker_reader.get_pacemaker_version()
                )
                # Usage console version
                try:
                    from claude_usage import __version__ as uc_version

                    pacemaker_status["usage_console_version"] = uc_version
                except ImportError:
                    pacemaker_status["usage_console_version"] = "unknown"
                # Error count
                pacemaker_status["error_count_24h"] = (
                    self.pacemaker_reader.get_recent_error_count(24)
                )
            # Fetch blockage stats for the two-column bottom section
            blockage_stats = self.pacemaker_reader.get_blockage_stats_with_labels()
            # CRITICAL-1b: Fetch Langfuse metrics
            langfuse_metrics = self.pacemaker_reader.get_langfuse_metrics()
            # Fetch Secrets metrics
            secrets_metrics = self.pacemaker_reader.get_secrets_metrics()

        main_display = self.renderer.render(
            self.error_message,
            self.last_usage,
            self.last_profile,
            self.last_update,
            pacemaker_status,
            weekly_limit_enabled=weekly_limit_enabled,
        )

        # Add bottom section with blockage stats if pacemaker is available
        if pacemaker_status:
            # CRITICAL-1d: Pass langfuse_metrics parameter to render_bottom_section
            bottom_section = self.renderer.render_bottom_section(
                pacemaker_status,
                blockage_stats,
                self.last_update,
                langfuse_metrics=langfuse_metrics,
                secrets_metrics=secrets_metrics,
            )
            return Group(main_display, bottom_section)

        return main_display

    def run(self):
        """Main run loop for Code mode monitoring.

        Display refreshes every DISPLAY_REFRESH_INTERVAL (10s).
        API polling happens every POLL_INTERVAL (300s).
        These are decoupled so the display stays responsive.
        """
        # Fetch profile once at startup
        self.fetch_profile()

        # Fetch usage immediately on startup
        self.fetch_usage()
        last_poll_time = time.time()

        try:
            with Live(refresh_per_second=1, console=console) as live:
                while True:
                    # Re-read freshest data from UsageModel (cheap SQLite query)
                    self._refresh_from_model()

                    # Check if it's time to poll the API (fallback for no UsageModel)
                    now = time.time()
                    if now - last_poll_time >= self.POLL_INTERVAL:
                        self.fetch_usage()
                        last_poll_time = now

                    # Refresh display
                    display = self.get_display()
                    instruction = Text("Press Ctrl+C to stop", style="dim")
                    live.update(Group(display, instruction))

                    # Short sleep for responsive display
                    time.sleep(self.DISPLAY_REFRESH_INTERVAL)

        except KeyboardInterrupt:
            return 0

        return 0
