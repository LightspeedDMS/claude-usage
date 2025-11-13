#!/usr/bin/env python3
"""
Claude Code Usage Monitor - Live Dashboard
Continuously monitors and displays Claude Code usage with auto-refresh
"""

import sys
import time
from pathlib import Path
from datetime import datetime
from rich.live import Live
from rich.console import Console

from .auth import OAuthManager, FirefoxSessionManager
from .api import ClaudeAPIClient
from .storage import UsageStorage, UsageAnalytics
from .display import UsageRenderer

console = Console()


class ClaudeUsageMonitor:
    """Monitor Claude Code account usage via the discovered API"""

    POLL_INTERVAL_CODE = 30  # seconds - for Code mode
    POLL_INTERVAL_CONSOLE = 120  # seconds - for Console mode (2 minutes)

    def __init__(self, credentials_path=None):
        if credentials_path is None:
            credentials_path = Path.home() / ".claude" / ".credentials.json"

        self.credentials_path = Path(credentials_path)
        storage_dir = Path.home() / ".claude-usage"
        db_path = storage_dir / "usage_history.db"

        # Detect mode early
        self.mode = self.detect_mode()

        # Initialize mode-specific components
        self._initialize_mode_components()

        # Common components
        self.storage = UsageStorage(db_path)
        self.analytics = UsageAnalytics(self.storage)

        # State
        self.credentials = None
        self.session_key = None
        self.org_uuid = None
        self.account_uuid = None

        self.last_usage = None
        self.last_profile = None
        self.last_overage = None
        self.last_update = None

        # Console mode state
        self.console_org = None
        self.console_org_data = None
        self.console_workspaces = None
        self.mtd_usage = None
        self.mtd_cost = None
        self.console_code_analytics = None

        self.error_message = None

        # Load initial credentials (Code mode only)
        if self.mode == "code":
            self._load_credentials()

    def _load_credentials(self):
        """Load OAuth credentials from Claude Code config"""
        self.credentials, error = self.oauth_manager.load_credentials()
        if error:
            self.error_message = error

    def detect_mode(self):
        """Detect which mode to run in: 'console' or 'code'

        Priority order:
        1. Explicit mode field in credentials file (user override)
        2. Claude Code OAuth credentials (subscription/code mode)
        3. Anthropic Console Admin API key (console mode)
        4. macOS Keychain (if on macOS and file doesn't exist)
        """
        import os
        import json
        import platform

        # Check credentials file
        try:
            with open(self.credentials_path) as f:
                data = json.load(f)

            # Check for explicit mode field override (highest priority)
            if "mode" in data and data["mode"] in ["console", "code"]:
                return data["mode"]

            # Check for Claude Code OAuth credentials (second priority)
            if "claudeCode" in data or "claudeAiOauth" in data:
                return "code"

            # Check for Anthropic Console Admin API key in file (third priority)
            if "anthropicConsole" in data and "adminApiKey" in data["anthropicConsole"]:
                return "console"
        except FileNotFoundError:
            # File doesn't exist - check macOS Keychain
            if platform.system() == "Darwin":
                # Try to detect credentials in Keychain
                from .auth import OAuthManager

                temp_oauth = OAuthManager(self.credentials_path)
                data, error = temp_oauth.extract_from_macos_keychain()
                if data and not error:
                    return "code"
        except Exception:
            pass

        # Check environment variable (lowest priority)
        if os.environ.get("ANTHROPIC_ADMIN_API_KEY"):
            return "console"

        # No credentials found
        self.error_message = "No credentials found"
        return None

    def resolve_mode(self, cli_mode=None):
        """Resolve final mode: CLI override or auto-detect

        If CLI mode differs from detected mode, reinitialize components
        """
        if cli_mode and cli_mode != self.mode:
            # CLI override requires reinitialization
            self.mode = cli_mode
            self._initialize_mode_components()
            return cli_mode
        return self.mode

    def _initialize_mode_components(self):
        """Initialize mode-specific components based on current mode"""
        if self.mode == "console":
            from .auth import AdminAuthManager
            from .api import ConsoleAPIClient
            from .display import ConsoleRenderer

            self.admin_auth_manager = AdminAuthManager(self.credentials_path)
            admin_key, _, _ = self.admin_auth_manager.load_admin_credentials()
            self.console_client = ConsoleAPIClient(admin_key) if admin_key else None
            self.console_renderer = ConsoleRenderer()
        else:
            # Code mode
            self.oauth_manager = OAuthManager(self.credentials_path)
            self.firefox_manager = FirefoxSessionManager()
            self.api_client = ClaudeAPIClient()
            self.renderer = UsageRenderer()

    def fetch_console_data(self):
        """Fetch all console data for MTD"""
        if not hasattr(self, "console_client"):
            return False

        # Fetch organization
        self.console_org_data, error = self.console_client.fetch_organization()
        if error:
            self.error_message = error
            return False

        # Fetch workspaces
        self.console_workspaces, error = self.console_client.fetch_workspaces()
        if error:
            self.error_message = error

        # Calculate MTD date range
        mtd_start, mtd_end = self.console_client._calculate_mtd_range()

        # Fetch MTD data
        self.mtd_usage, error = self.console_client.fetch_usage_report(
            mtd_start, mtd_end
        )
        if error:
            self.error_message = error

        self.mtd_cost, error = self.console_client.fetch_cost_report(mtd_start, mtd_end)
        if error:
            self.error_message = error

        # Optional: Claude Code analytics
        self.console_code_analytics, _ = (
            self.console_client.fetch_claude_code_analytics(mtd_start, mtd_end)
        )

        # Store snapshot
        if self.mtd_cost:
            self.storage.store_console_snapshot(self.mtd_cost, self.console_workspaces)

        self.last_update = datetime.now()
        return True

    def get_console_display(self):
        """Generate console mode display"""
        from rich.panel import Panel
        from datetime import timedelta

        if not hasattr(self, "console_renderer"):
            return Panel("[red]Console mode not initialized[/red]")

        # Calculate projection
        projection = None
        if self.mtd_cost:
            rate = self.analytics.calculate_console_mtd_rate(
                self.mtd_cost.get("total_cost_usd", 0)
            )
            if rate and rate > 0:
                # Calculate hours until end of month
                today = datetime.now()
                # Calculate last day of current month
                if today.month == 12:
                    next_month = today.replace(year=today.year + 1, month=1, day=1)
                else:
                    next_month = today.replace(month=today.month + 1, day=1)
                last_day_of_month = (next_month - timedelta(days=1)).day
                hours_until_eom = (last_day_of_month - today.day) * 24 + (
                    23 - today.hour
                )
                projected = self.analytics.project_console_eom_cost(
                    self.mtd_cost.get("total_cost_usd", 0), rate, hours_until_eom
                )
                if projected:
                    projection = {
                        "projected_eom_cost": projected,
                        "rate_per_hour": rate,
                    }

        return self.console_renderer.render(
            self.console_org_data,
            self.mtd_cost,
            self.console_workspaces,
            self.last_update,
            projection,
            error=self.error_message,
        )

    def fetch_usage(self):
        """Fetch current usage data from Claude Code API"""
        # Check if we need to reload credentials
        if not self.credentials:
            self._load_credentials()

        if not self.credentials:
            return False

        # Check token expiry
        if self.oauth_manager.is_token_expired(self.credentials):
            success, error = self.oauth_manager.refresh_token(self.credentials)
            if not success:
                self.error_message = error
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
            if error:
                self.error_message = error
            return False

    def fetch_overage(self):
        """Fetch overage spend data from Claude.ai API"""
        if not self.session_key or not self.org_uuid:
            return False

        overage_data, error = self.api_client.fetch_overage(
            self.org_uuid, self.account_uuid, self.session_key
        )

        if overage_data:
            self.last_overage = overage_data
            return True
        else:
            return False

    def refresh_session_key(self):
        """Refresh session key from Firefox if needed (Code mode only)"""
        if hasattr(self, "firefox_manager"):
            session_key = self.firefox_manager.refresh_session_key()
            if session_key:
                self.session_key = session_key

    def store_snapshot(self):
        """Store current usage snapshot to database"""
        if self.last_overage and self.last_usage:
            self.storage.store_snapshot(self.last_overage, self.last_usage)

    def get_display(self):
        """Generate rich display for current usage"""
        # Route to appropriate renderer based on mode
        if self.mode == "console":
            return self.get_console_display()

        # Code mode (existing behavior)
        projection = None
        if self.last_overage and self.last_usage:
            projection = self.analytics.project_usage(
                self.last_overage, self.last_usage
            )

        return self.renderer.render(
            self.error_message,
            self.last_usage,
            self.last_profile,
            self.last_overage,
            self.last_update,
            projection,
        )


def parse_args():
    """Parse command line arguments"""
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default=None)
    return parser.parse_args()


def main():
    """Main entry point"""
    args = parse_args()
    monitor = ClaudeUsageMonitor()

    # Resolve mode (CLI override or auto-detect)
    mode = monitor.resolve_mode(cli_mode=args.mode)

    if not mode and monitor.error_message:
        console.print(f"[red]Error: {monitor.error_message}[/red]\n")
        return 1

    # Fetch profile once at startup (Code mode only)
    if mode == "code":
        monitor.fetch_profile()

    # Try to extract Firefox session key for overage data (Code mode only)
    if mode == "code" and hasattr(monitor, "firefox_manager"):
        session_key = monitor.firefox_manager.extract_session_key()
        if session_key:
            monitor.session_key = session_key
            monitor.firefox_manager.last_refresh = datetime.now()
            console.print("[dim]Overage report using Firefox session[/dim]\n")

    try:
        # Show instruction below the display
        from rich.console import Group
        from rich.text import Text

        with Live(refresh_per_second=1, console=console) as live:
            while True:
                # Show initial display before fetching
                display = monitor.get_display()
                instruction = Text("Press Ctrl+C to stop", style="dim")
                live.update(Group(display, Text(""), instruction))

                # Route to appropriate fetch method based on mode
                if mode == "console":
                    monitor.fetch_console_data()
                else:
                    # Code mode - refresh session key periodically
                    monitor.refresh_session_key()

                    # Fetch usage
                    monitor.fetch_usage()

                    # Fetch overage data if session key available
                    if monitor.session_key and monitor.org_uuid:
                        monitor.fetch_overage()
                        # Store snapshot for projection calculation
                        if monitor.last_overage:
                            monitor.store_snapshot()

                # Update display again after fetching
                display = monitor.get_display()
                instruction = Text("Press Ctrl+C to stop", style="dim")
                live.update(Group(display, Text(""), instruction))

                # Wait before next poll (mode-specific interval)
                poll_interval = (
                    monitor.POLL_INTERVAL_CONSOLE
                    if mode == "console"
                    else monitor.POLL_INTERVAL_CODE
                )
                time.sleep(poll_interval)

    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
