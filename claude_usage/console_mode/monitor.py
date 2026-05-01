"""Console mode monitor for Anthropic Console usage tracking"""

import calendar
import json
import logging
import os
import time
from pathlib import Path
from datetime import datetime, date
from rich.live import Live
from rich.console import Console, Group
from rich.text import Text

from .auth import AdminAuthManager
from .api import ConsoleAPIClient
from .storage import ConsoleStorage, ConsoleAnalytics
from .display import ConsoleRenderer
from claude_usage.code_mode.pacemaker_integration import PaceMakerReader
from claude_usage.code_mode.display import UsageRenderer
from claude_usage.shared.pacemaker_fetcher import fetch_pacemaker_bundle

_log = logging.getLogger(__name__)

console = Console()

# Window sizes for pace-maker event queries
GOVERNANCE_EVENT_WINDOW_SECONDS = 3600
ACTIVITY_WINDOW_SECONDS = 10


def _safe_pm_read(fn, label):
    """Call pace-maker reader function *fn*, logging debug on failure.

    Args:
        fn: zero-argument callable wrapping the reader call.
        label: short string identifying the call for log messages.

    Returns:
        Result of fn() on success, or None on exception.
    """
    try:
        return fn()
    except Exception as exc:
        _log.debug("pacemaker %s failed: %s", label, exc)
        return None


class ConsoleMonitor:
    """Monitor Anthropic Console organization usage via Admin API"""

    POLL_INTERVAL = 300  # seconds (5 minutes)

    def __init__(self, credentials_path=None):
        if credentials_path is None:
            credentials_path = Path.home() / ".claude" / ".credentials.json"

        self.credentials_path = Path(credentials_path)
        storage_dir = Path.home() / ".claude-usage"
        db_path = storage_dir / "usage_history.db"

        # Initialize components
        self.admin_auth_manager = AdminAuthManager(self.credentials_path)
        self.storage = ConsoleStorage(db_path)
        self.analytics = ConsoleAnalytics(self.storage)
        self.renderer = ConsoleRenderer()
        self.code_renderer = UsageRenderer()
        self.pacemaker_reader = PaceMakerReader()

        # Load admin credentials and create client
        admin_key, _, error = self.admin_auth_manager.load_admin_credentials()
        if error:
            self.error_message = error
            self.console_client = None
        else:
            self.console_client = ConsoleAPIClient(admin_key) if admin_key else None
            self.error_message = None

        # Admin API state
        self.console_org_data = None
        self.console_workspaces = None
        self.mtd_cost = None
        self.last_update = None
        self.eom_projection = None

        # Pace-maker and settings state (populated each poll, independent of admin API)
        self.pacemaker_status = None
        self.blockage_stats = None
        self.langfuse_metrics = None
        self.secrets_metrics = None
        self.governance_events = None
        self.activity_events = None
        self.settings_info = None

    def _load_settings_info(self):
        """Read oauthAccount from ~/.claude.json and admin key source.

        Returns:
            dict with keys: email, org_name, org_role, billing_type,
            account_created_at, primary_api_key_present, admin_api_key_source.
            All fields default to None/False on any read/parse error.
        """
        result = {
            "email": None,
            "org_name": None,
            "org_role": None,
            "billing_type": None,
            "account_created_at": None,
            "primary_api_key_present": False,
            "primary_api_key_suffix": None,
            "admin_api_key_source": None,
        }

        try:
            claude_json_path = Path.home() / ".claude.json"
            with open(claude_json_path) as f:
                data = json.load(f)
            if isinstance(data, dict):
                pk = data.get("primaryApiKey")
                if isinstance(pk, str) and pk:
                    result["primary_api_key_present"] = True
                    if len(pk) >= 4:
                        result["primary_api_key_suffix"] = pk[-4:]
                oauth = data.get("oauthAccount", {})
                if isinstance(oauth, dict):
                    result["email"] = oauth.get("emailAddress")
                    result["org_name"] = oauth.get("organizationName")
                    result["org_role"] = oauth.get("organizationRole")
                    result["billing_type"] = oauth.get("billingType")
                    result["account_created_at"] = oauth.get("createdAt")
        except FileNotFoundError:
            _log.debug("~/.claude.json not found; settings_info fields will be None")
        except json.JSONDecodeError as exc:
            _log.debug(
                "~/.claude.json parse error: %s; settings_info fields will be None", exc
            )
        except OSError as exc:
            _log.debug(
                "~/.claude.json read error: %s; settings_info fields will be None", exc
            )

        # Determine admin key source via existing auth manager logic
        try:
            _, source, _ = self.admin_auth_manager.load_admin_credentials()
            result["admin_api_key_source"] = source
        except (OSError, ValueError) as exc:
            _log.debug("admin credential source lookup failed: %s", exc)

        return result

    def _fetch_pacemaker_data(self):
        """Fetch pace-maker status, blockage stats, metrics, and events.

        Always called regardless of admin API availability.
        Delegates to fetch_pacemaker_bundle; a None bundle (not installed)
        leaves all instance attributes at their __init__ defaults (None).
        """
        bundle = fetch_pacemaker_bundle(
            self.pacemaker_reader, include_weekly_limit=False
        )
        if bundle is not None:
            self.pacemaker_status = bundle.pacemaker_status
            self.blockage_stats = bundle.blockage_stats
            self.langfuse_metrics = bundle.langfuse_metrics
            self.secrets_metrics = bundle.secrets_metrics
            self.governance_events = bundle.governance_events
            self.activity_events = bundle.activity_events

    def fetch_console_data(self):
        """Fetch all console data for MTD"""
        # Always fetch local data first — independent of admin API availability
        self._fetch_pacemaker_data()
        self.settings_info = self._load_settings_info()

        if self.console_client is None:
            self.error_message = "Console client is None - admin API key not found"
            return False

        # Fetch organization
        self.console_org_data, error = self.console_client.fetch_organization()
        if error:
            self.error_message = error
            return False

        # Calculate MTD date range
        mtd_start, mtd_end = self.console_client._calculate_mtd_range()

        self.mtd_cost, error = self.console_client.fetch_cost_report(mtd_start, mtd_end)
        if error:
            self.error_message = error

        # Calculate EOM projection (after mtd_cost is set)
        if self.mtd_cost:
            current_cost = self.mtd_cost.get("claude_code_user_cost_usd", 0)

            if current_cost is not None:
                # Calculate rate from history
                rate = self.analytics.calculate_console_mtd_rate(current_cost)

                if rate:
                    # Calculate hours until end of month
                    today = date.today()
                    last_day = calendar.monthrange(today.year, today.month)[1]
                    eom = datetime(today.year, today.month, last_day, 23, 59, 59)
                    hours_until_eom = (eom - datetime.now()).total_seconds() / 3600

                    # Project to end of month
                    projected_cost = self.analytics.project_console_eom_cost(
                        current_cost, rate, hours_until_eom
                    )

                    # Store for display
                    self.eom_projection = {
                        "current_cost": current_cost,
                        "projected_cost": projected_cost,
                        "rate_per_hour": rate,
                        "hours_until_eom": hours_until_eom,
                    }
                else:
                    self.eom_projection = None
            else:
                self.eom_projection = None

        # Store snapshot
        if self.mtd_cost:
            self.storage.store_console_snapshot(self.mtd_cost, self.console_workspaces)

        self.last_update = datetime.now()
        return True

    def get_display(self):
        """Generate console mode display with settings, MTD section, and pace-maker bottom."""
        main_display = self.renderer.render(
            self.console_org_data,
            self.mtd_cost,
            self.console_workspaces,
            self.last_update,
            projection=self.eom_projection,
            error=self.error_message,
            settings_info=self.settings_info,
        )

        # Add pace-maker bottom section when available (same pattern as code_mode)
        if self.pacemaker_status is not None:
            bottom_section = self.code_renderer.render_bottom_section(
                self.pacemaker_status,
                self.blockage_stats or {},
                self.last_update,
                langfuse_metrics=self.langfuse_metrics,
                secrets_metrics=self.secrets_metrics,
            )
            combined_display = Group(main_display, bottom_section)
        else:
            combined_display = Group(
                main_display, Text("Press Ctrl+C to stop", style="dim")
            )

        # Governance event feed (two-column layout when wide enough)
        events = self.governance_events or []
        try:
            term_size = os.get_terminal_size()
            terminal_width = term_size.columns
            terminal_height = term_size.lines
        except (ValueError, OSError):
            terminal_width = 80
            terminal_height = 40

        return self.code_renderer.render_with_event_feed(
            main_content=combined_display,
            events=events,
            terminal_width=terminal_width,
            terminal_height=terminal_height,
            scroll_offset=0,
        )

    def get_console_display(self):
        """Backward compatibility alias for get_display()"""
        return self.get_display()

    def run(self):
        """Main run loop for Console mode monitoring"""
        try:
            with Live(refresh_per_second=1, console=console) as live:
                while True:
                    # Show initial display before fetching
                    display = self.get_display()
                    instruction = Text("Press Ctrl+C to stop", style="dim")
                    live.update(Group(display, Text(""), instruction))

                    # Fetch console data
                    self.fetch_console_data()

                    # Update display again after fetching
                    display = self.get_display()
                    instruction = Text("Press Ctrl+C to stop", style="dim")
                    live.update(Group(display, Text(""), instruction))

                    # Wait before next poll
                    time.sleep(self.POLL_INTERVAL)

        except KeyboardInterrupt:
            return 0

        return 0
