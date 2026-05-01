"""Code mode monitor for Claude Code usage tracking"""

import json
import logging
import os
import time
from pathlib import Path
from datetime import datetime, timezone
from rich.live import Live
from rich.console import Console, Group
from rich.text import Text

from .auth import OAuthManager
from .api import ClaudeAPIClient
from .storage import CodeStorage, CodeAnalytics
from .display import UsageRenderer
from .pacemaker_integration import PaceMakerReader
from claude_usage.shared.pacemaker_fetcher import fetch_pacemaker_bundle

console = Console()


class CodeMonitor:
    """Monitor Claude Code account usage via the discovered API"""

    POLL_INTERVAL = 300  # seconds between API calls (5 minutes — same as pace-maker)
    DISPLAY_REFRESH_INTERVAL = 1  # seconds between display refreshes
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

        # Governance event feed scroll state
        self.scroll_offset = 0
        self.user_scrolled = False
        self.prev_event_count = 0

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

            db_path = getattr(self.pacemaker_reader, "db_path", None)
            model = UsageModel(db_path=str(db_path)) if db_path else UsageModel()
            snapshot = model.get_current_usage()
            if snapshot is not None:
                # UsageModel may return naive timestamps — assume UTC
                ts = snapshot.timestamp
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                age = (datetime.now(timezone.utc) - ts).total_seconds()
                # Accept stale data if we have nothing to show — always display bars
                if age <= self.CACHE_FRESHNESS_SECONDS or self.last_usage is None:
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
                    # Merge per-model fields from raw API response in api_cache
                    # (regression fix: cee8bbb dropped seven_day_sonnet/opus)
                    try:
                        cache = model.get_api_cache()
                        if cache and cache.get("raw_response"):
                            raw = cache["raw_response"]
                            for key in (
                                "seven_day_sonnet",
                                "seven_day_opus",
                                "seven_day_oauth_apps",
                                "seven_day_cowork",
                                "extra_usage",
                            ):
                                if raw.get(key) is not None:
                                    self.last_usage[key] = raw[key]
                    except Exception as e:
                        logging.debug(
                            f"Failed to merge per-model fields from api_cache: {e}"
                        )
                    self.last_update = ts.astimezone(tz=None).replace(tzinfo=None)
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

        # Detect pace-maker backoff via UsageModel (SQLite — single source of truth)
        pacemaker_in_backoff = False
        backoff_remaining = 0.0
        try:
            import sys

            pm_src = self.pacemaker_reader._get_pacemaker_src_path()
            if pm_src and str(pm_src) not in sys.path:
                sys.path.insert(0, str(pm_src))
            from pacemaker.usage_model import UsageModel

            model = UsageModel()
            pacemaker_in_backoff = model.is_in_backoff()
            if pacemaker_in_backoff:
                backoff_remaining = model.get_backoff_remaining()
        except (ImportError, Exception) as e:
            logging.debug(f"Failed to check pace-maker backoff via UsageModel: {e}")

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
            # Still return True if we have stale data — always show progress bars
            return self.last_usage is not None

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
            # Fall back to pace-maker's profile cache file (written by hook)
            cached = self._load_profile_cache()
            if cached:
                self.last_profile = cached
                return True
            if error:
                self.error_message = error
            return False

    def _load_profile_cache(self):
        """Load profile from pace-maker's profile_cache.json as fallback.

        Returns profile dict or None if unavailable.
        """
        try:
            cache_path = Path.home() / ".claude-pace-maker" / "profile_cache.json"
            if not cache_path.exists():
                return None
            data = json.loads(cache_path.read_text().strip())
            return data.get("profile")
        except Exception:
            return None

    def get_display(self):
        """Generate rich display for current usage"""
        # Get pace-maker status, stats, metrics, and events via shared helper
        weekly_limit_enabled = True  # Default when pace-maker not installed
        pacemaker_status = None
        blockage_stats = None
        langfuse_metrics = None
        secrets_metrics = None
        activity_events = None
        bundle = fetch_pacemaker_bundle(
            self.pacemaker_reader, include_weekly_limit=True
        )
        if bundle is not None:
            pacemaker_status = bundle.pacemaker_status
            blockage_stats = bundle.blockage_stats
            langfuse_metrics = bundle.langfuse_metrics
            secrets_metrics = bundle.secrets_metrics
            activity_events = bundle.activity_events
            if pacemaker_status:
                weekly_limit_enabled = pacemaker_status.get(
                    "weekly_limit_enabled", True
                )

        main_display = self.renderer.render(
            self.error_message,
            self.last_usage,
            self.last_profile,
            self.last_update,
            pacemaker_status,
            weekly_limit_enabled=weekly_limit_enabled,
            activity_events=activity_events,
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

            combined_display = Group(main_display, bottom_section)
        else:
            instruction = Text("Press Ctrl+C to stop", style="dim")
            combined_display = Group(main_display, instruction)

        # Governance event feed (two-column layout when wide enough)
        governance_events = []
        if pacemaker_status:
            try:
                governance_events = self.pacemaker_reader.get_governance_events(
                    window_seconds=3600
                )
            except Exception as e:
                logging.debug("Governance events fetch failed: %s", e)

        # Auto-scroll: reset to top when new events arrive (unless user scrolled)
        # Use getattr for robustness - tests may bypass __init__
        current_count = len(governance_events)
        prev_count = getattr(self, "prev_event_count", 0)
        user_scrolled = getattr(self, "user_scrolled", False)
        if current_count > prev_count and not user_scrolled:
            self.scroll_offset = 0
        self.prev_event_count = current_count

        # Detect terminal width for responsive layout
        try:
            term_size = os.get_terminal_size()
            terminal_width = term_size.columns
            terminal_height = term_size.lines
        except (ValueError, OSError):
            terminal_width = 80
            terminal_height = 40

        scroll_offset = getattr(self, "scroll_offset", 0)
        return self.renderer.render_with_event_feed(
            main_content=combined_display,
            events=governance_events,
            terminal_width=terminal_width,
            terminal_height=terminal_height,
            scroll_offset=scroll_offset,
        )

    def _start_key_listener(self):
        """Start a daemon thread for non-blocking keyboard input.

        Reads arrow keys for scroll control. Uses terminal raw mode
        with proper cleanup on exit.

        Returns:
            queue.Queue for key events, or None if raw mode unavailable
        """
        import queue
        import threading

        key_queue = queue.Queue()

        try:
            import sys
            import tty
            import termios

            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
        except Exception:
            # Handles ImportError, AttributeError, termios.error,
            # UnsupportedOperation (pytest redirected stdin), etc.
            return None

        import atexit

        def restore_terminal():
            try:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            except Exception:
                pass

        atexit.register(restore_terminal)

        def reader():
            try:
                tty.setcbreak(fd)
                while True:
                    try:
                        ch = sys.stdin.read(1)
                        if ch == "\x03":  # Ctrl+C
                            key_queue.put("QUIT")
                            break
                        if ch == "\x1b":
                            ch2 = sys.stdin.read(1)
                            if ch2 == "[":
                                ch3 = sys.stdin.read(1)
                                if ch3 == "A":
                                    key_queue.put("UP")
                                elif ch3 == "B":
                                    key_queue.put("DOWN")
                    except (IOError, OSError):
                        break
            finally:
                restore_terminal()

        t = threading.Thread(target=reader, daemon=True)
        t.start()
        return key_queue

    def _drain_key_queue(self, key_queue, max_events):
        """Process key events from the queue, updating scroll state.

        Args:
            key_queue: Queue of key event strings
            max_events: Maximum number of governance events (for bounds)

        Returns:
            True if QUIT was received, False otherwise
        """
        while not key_queue.empty():
            try:
                key = key_queue.get_nowait()
            except Exception:
                break
            if key == "QUIT":
                return True
            if key == "UP":
                if self.scroll_offset > 0:
                    self.scroll_offset -= 1
                if self.scroll_offset == 0:
                    self.user_scrolled = False
                else:
                    self.user_scrolled = True
            elif key == "DOWN":
                if self.scroll_offset < max(0, max_events - 1):
                    self.scroll_offset += 1
                    self.user_scrolled = True
        return False

    def run(self):
        """Main run loop for Code mode monitoring.

        Display refreshes every DISPLAY_REFRESH_INTERVAL (1s).
        API polling happens every POLL_INTERVAL (300s).
        These are decoupled so the display stays responsive.
        """
        # Fetch profile once at startup
        self.fetch_profile()

        # Fetch usage immediately on startup
        self.fetch_usage()
        last_poll_time = time.time()

        # Start keyboard listener for event feed scrolling
        key_queue = self._start_key_listener()

        try:
            with Live(refresh_per_second=1, console=console) as live:
                while True:
                    # Process keyboard input for scroll control
                    if key_queue:
                        quit_requested = self._drain_key_queue(
                            key_queue, self.prev_event_count
                        )
                        if quit_requested:
                            return 0

                    # Re-read freshest data from UsageModel (cheap SQLite query)
                    self._refresh_from_model()

                    # Check if it's time to poll the API (fallback for no UsageModel)
                    now = time.time()
                    if now - last_poll_time >= self.POLL_INTERVAL:
                        self.fetch_usage()
                        last_poll_time = now

                    # Refresh display
                    display = self.get_display()
                    live.update(display)

                    # Short sleep for responsive display
                    time.sleep(self.DISPLAY_REFRESH_INTERVAL)

        except KeyboardInterrupt:
            return 0

        return 0
