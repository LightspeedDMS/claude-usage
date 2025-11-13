#!/usr/bin/env python3
"""
Claude Code Usage Monitor - Live Dashboard
Continuously monitors and displays Claude Code usage with auto-refresh
"""

import json
import sys
import time
from pathlib import Path
from datetime import datetime
import requests
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TextColumn
from rich.console import Console
from rich.text import Text

console = Console()


class ClaudeUsageMonitor:
    """Monitor Claude Code account usage via the discovered API"""

    API_BASE = "https://api.anthropic.com"
    USAGE_ENDPOINT = "/api/oauth/usage"
    REFRESH_ENDPOINT = "/v1/oauth/token"

    POLL_INTERVAL = 10  # seconds

    def __init__(self, credentials_path=None):
        if credentials_path is None:
            credentials_path = Path.home() / ".claude" / ".credentials.json"

        self.credentials_path = Path(credentials_path)
        self.credentials = None
        self.last_usage = None
        self.last_update = None
        self.error_message = None
        self._load_credentials()

    def _load_credentials(self):
        """Load OAuth credentials from Claude Code config"""
        try:
            with open(self.credentials_path) as f:
                data = json.load(f)

            if "claudeAiOauth" not in data:
                raise ValueError("No OAuth credentials found")

            self.credentials = data["claudeAiOauth"]
            self.error_message = None

        except Exception as e:
            self.error_message = f"Failed to load credentials: {e}"
            self.credentials = None

    def _save_credentials(self):
        """Save updated credentials back to file"""
        try:
            with open(self.credentials_path) as f:
                data = json.load(f)

            data["claudeAiOauth"] = self.credentials

            with open(self.credentials_path, 'w') as f:
                json.dump(data, f, indent=2)

        except Exception as e:
            self.error_message = f"Failed to save credentials: {e}"

    def _is_token_expired(self):
        """Check if OAuth token is expired or close to expiry"""
        if not self.credentials:
            return True

        expires_at = self.credentials.get("expiresAt", 0)
        current_time = datetime.now().timestamp() * 1000

        # Consider expired if less than 5 minutes remaining
        buffer = 5 * 60 * 1000
        return current_time >= (expires_at - buffer)

    def _refresh_token(self):
        """Attempt to refresh the OAuth token"""
        if not self.credentials or "refreshToken" not in self.credentials:
            self.error_message = "No refresh token available"
            return False

        try:
            # Note: The actual refresh endpoint might differ
            # This is a placeholder - Claude Code might handle this internally
            self.error_message = "Token expired. Please run 'claude' to refresh."
            return False

        except Exception as e:
            self.error_message = f"Token refresh failed: {e}"
            return False

    def _get_auth_headers(self):
        """Get authorization headers for API requests"""
        if not self.credentials:
            return None

        return {
            'Authorization': f'Bearer {self.credentials["accessToken"]}',
            'Content-Type': 'application/json',
            'anthropic-beta': 'oauth-2025-04-20',
            'User-Agent': 'claude-code/2.0.37'
        }

    def fetch_usage(self):
        """Fetch current usage data from Claude Code API"""

        # Check if we need to reload credentials
        if not self.credentials:
            self._load_credentials()

        if not self.credentials:
            return False

        # Check token expiry
        if self._is_token_expired():
            if not self._refresh_token():
                return False

        # Make API request
        url = f"{self.API_BASE}{self.USAGE_ENDPOINT}"
        headers = self._get_auth_headers()

        if not headers:
            return False

        try:
            response = requests.get(url, headers=headers, timeout=10)

            if response.status_code == 200:
                self.last_usage = response.json()
                self.last_update = datetime.now()
                self.error_message = None
                return True
            elif response.status_code == 401:
                self.error_message = "Token expired. Run 'claude' to refresh."
                return False
            else:
                self.error_message = f"API error: {response.status_code}"
                return False

        except requests.exceptions.RequestException as e:
            self.error_message = f"Network error: {e}"
            return False

    def get_display(self):
        """Generate rich display for current usage"""

        if self.error_message:
            return Panel(
                f"[red]⚠ {self.error_message}[/red]",
                title="Claude Code Usage",
                border_style="red"
            )

        if not self.last_usage:
            return Panel(
                "[yellow]Fetching usage data...[/yellow]",
                title="Claude Code Usage",
                border_style="yellow"
            )

        # Build display content
        content = []

        # Five-hour limit
        if self.last_usage.get("five_hour"):
            five_hour = self.last_usage["five_hour"]
            utilization = five_hour.get("utilization", 0)
            resets_at = five_hour.get("resets_at", "")

            # Progress bar
            progress = Progress(
                TextColumn("[bold]5-Hour Limit:[/bold]"),
                BarColumn(bar_width=20),
                TextColumn("[bold]{task.percentage:>3.0f}%[/bold]"),
            )
            task = progress.add_task("usage", total=100, completed=utilization)

            content.append(progress)

            if resets_at:
                reset_time = datetime.fromisoformat(resets_at.replace("+00:00", ""))
                now = datetime.utcnow()
                time_until = reset_time - now

                hours = time_until.seconds // 3600
                minutes = (time_until.seconds % 3600) // 60

                content.append(Text(f"⏰ Resets in: {hours}h {minutes}m", style="cyan"))

        # Seven-day limit
        if self.last_usage.get("seven_day"):
            seven_day = self.last_usage["seven_day"]
            utilization = seven_day.get("utilization", 0)

            progress = Progress(
                TextColumn("[bold]7-Day Limit:[/bold]"),
                BarColumn(bar_width=20),
                TextColumn("[bold]{task.percentage:>3.0f}%[/bold]"),
            )
            task = progress.add_task("usage", total=100, completed=utilization)
            content.append(Text(""))  # spacing
            content.append(progress)

        # Last update time
        if self.last_update:
            update_str = self.last_update.strftime("%H:%M:%S")
            content.append(Text(""))  # spacing
            content.append(Text(f"Updated: {update_str}", style="dim"))

        # Combine content
        from rich.console import Group
        display = Group(*content)

        return Panel(
            display,
            title="Claude Code Usage",
            border_style="green"
        )


def main():
    """Main entry point"""
    monitor = ClaudeUsageMonitor()

    console.print("[cyan]Claude Code Usage Monitor[/cyan]")
    console.print("[dim]Press Ctrl+C to stop[/dim]\n")

    try:
        with Live(monitor.get_display(), refresh_per_second=1, console=console) as live:
            while True:
                # Fetch usage
                monitor.fetch_usage()

                # Update display
                live.update(monitor.get_display())

                # Wait before next poll
                time.sleep(monitor.POLL_INTERVAL)

    except KeyboardInterrupt:
        console.print("\n[yellow]Stopped by user[/yellow]")
        return 0


if __name__ == "__main__":
    sys.exit(main())
