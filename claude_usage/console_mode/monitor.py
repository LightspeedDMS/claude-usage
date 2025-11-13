"""Console mode monitor for Anthropic Console usage tracking"""

import calendar
import time
from pathlib import Path
from datetime import datetime, date
from rich.live import Live
from rich.console import Console, Group
from rich.text import Text

from .auth import AdminAuthManager
from ..shared.auth import FirefoxSessionManager
from .api import ConsoleAPIClient
from .storage import ConsoleStorage, ConsoleAnalytics
from .display import ConsoleRenderer

console = Console()


class ConsoleMonitor:
    """Monitor Anthropic Console organization usage via Admin API"""

    POLL_INTERVAL = 120  # seconds (2 minutes)

    def __init__(self, credentials_path=None):
        if credentials_path is None:
            credentials_path = Path.home() / ".claude" / ".credentials.json"

        self.credentials_path = Path(credentials_path)
        storage_dir = Path.home() / ".claude-usage"
        db_path = storage_dir / "usage_history.db"

        # Initialize components
        self.admin_auth_manager = AdminAuthManager(self.credentials_path)
        self.firefox_manager = FirefoxSessionManager()
        self.storage = ConsoleStorage(db_path)
        self.analytics = ConsoleAnalytics(self.storage)
        self.renderer = ConsoleRenderer()

        # Load admin credentials and create client
        admin_key, _, error = self.admin_auth_manager.load_admin_credentials()
        if error:
            self.error_message = error
            self.console_client = None
        else:
            self.console_client = ConsoleAPIClient(admin_key) if admin_key else None
            self.error_message = None

        # State
        self.console_org_data = None
        self.console_workspaces = None
        self.mtd_usage = None
        self.mtd_cost = None
        self.console_code_analytics = None
        self.last_update = None
        self.eom_projection = None

        # OAuth manager for Claude Code user identification (optional)
        self.credentials = None
        self.oauth_manager = None

    def fetch_console_data(self):
        """Fetch all console data for MTD"""
        if self.console_client is None:
            self.error_message = "Console client is None - admin API key not found"
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

        # Fetch per-user Claude Code usage
        claude_code_user_data, error = self.console_client.fetch_claude_code_user_usage(
            mtd_start, mtd_end
        )
        if error:
            self.error_message = error
        elif claude_code_user_data and self.mtd_cost:
            users_list = claude_code_user_data.get("users", [])

            # Get current user's email from Claude Code OAuth profile (most reliable)
            current_user_email = None
            if self.credentials and self.oauth_manager:
                # Try Claude Code profile endpoint first
                headers = self.oauth_manager.get_auth_headers(self.credentials)
                from ..code_mode.api import ClaudeAPIClient

                temp_client = ClaudeAPIClient()
                profile_data, _, _, _ = temp_client.fetch_profile(headers)
                if profile_data:
                    account = profile_data.get("account", {})
                    current_user_email = account.get("email")

            # Fallback: Try Admin API user matching if OAuth didn't work
            if not current_user_email:
                current_user_email, email_error = (
                    self.console_client.get_current_user_email(usage_users=users_list)
                )
                if not current_user_email:
                    self.error_message = email_error
                    return True

            # Find current user's cost in the users list
            current_user_cost = 0.0
            for user in users_list:
                if user.get("email") == current_user_email:
                    current_user_cost = user.get("cost_usd", 0.0)
                    break

            # Store ONLY current user's data
            self.mtd_cost["claude_code_user_cost_usd"] = current_user_cost
            self.mtd_cost["current_user_email"] = current_user_email

        # Optional: Claude Code analytics (requires Firefox session key)
        session_key = self.firefox_manager.extract_session_key()

        org_uuid = self.console_org_data.get("id") if self.console_org_data else None
        self.console_code_analytics, _ = (
            self.console_client.fetch_claude_code_analytics(
                mtd_start, mtd_end, session_key=session_key, org_uuid=org_uuid
            )
        )

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
        """Generate console mode display showing ONLY current user's Claude Code usage"""
        return self.renderer.render(
            self.console_org_data,
            self.mtd_cost,
            self.console_workspaces,
            self.last_update,
            projection=self.eom_projection,
            error=self.error_message,
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
