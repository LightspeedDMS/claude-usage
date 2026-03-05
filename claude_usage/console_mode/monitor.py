"""Console mode monitor for Anthropic Console usage tracking"""

import calendar
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

console = Console()


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
        self.mtd_cost = None
        self.last_update = None
        self.eom_projection = None

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
