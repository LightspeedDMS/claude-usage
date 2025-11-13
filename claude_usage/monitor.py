#!/usr/bin/env python3
"""
Claude Code Usage Monitor - Live Dashboard
Continuously monitors and displays Claude Code usage with auto-refresh
"""

import json
import sys
import time
import shutil
import tempfile
import sqlite3
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
    PROFILE_ENDPOINT = "/api/oauth/profile"
    OVERAGE_ENDPOINT_TEMPLATE = "https://claude.ai/api/organizations/{org_uuid}/overage_spend_limits"
    REFRESH_ENDPOINT = "/v1/oauth/token"

    POLL_INTERVAL = 10  # seconds
    SESSION_REFRESH_INTERVAL = 300  # 5 minutes
    RATE_CALC_WINDOW = 1800  # 30 minutes for rate calculation
    HISTORY_RETENTION = 86400  # Keep 24 hours of history

    def __init__(self, credentials_path=None):
        if credentials_path is None:
            credentials_path = Path.home() / ".claude" / ".credentials.json"

        self.credentials_path = Path(credentials_path)
        self.storage_dir = Path.home() / ".claude-usage"
        self.db_path = self.storage_dir / "usage_history.db"

        self.credentials = None
        self.last_usage = None
        self.last_profile = None
        self.last_overage = None
        self.last_update = None
        self.last_session_refresh = None
        self.session_key = None
        self.org_uuid = None
        self.account_uuid = None
        self.error_message = None

        self._init_storage()
        self._load_credentials()

    def _init_storage(self):
        """Initialize storage directory and database"""
        try:
            # Create storage directory if it doesn't exist
            self.storage_dir.mkdir(parents=True, exist_ok=True)

            # Initialize database
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Create table if not exists
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS usage_snapshots (
                    timestamp INTEGER PRIMARY KEY,
                    credits_used INTEGER,
                    utilization_percent REAL,
                    resets_at TEXT
                )
            """)

            # Create index for efficient queries
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_timestamp
                ON usage_snapshots(timestamp DESC)
            """)

            conn.commit()
            conn.close()

        except Exception as e:
            # Non-fatal error - continue without storage
            pass

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

    def fetch_profile(self):
        """Fetch profile data from Claude Code API"""

        if not self.credentials:
            return False

        url = f"{self.API_BASE}{self.PROFILE_ENDPOINT}"
        headers = self._get_auth_headers()

        if not headers:
            return False

        try:
            response = requests.get(url, headers=headers, timeout=10)

            if response.status_code == 200:
                self.last_profile = response.json()
                # Extract org and account UUIDs for overage API
                if self.last_profile:
                    org = self.last_profile.get('organization', {})
                    account = self.last_profile.get('account', {})
                    self.org_uuid = org.get('uuid')
                    self.account_uuid = account.get('uuid')
                return True
            else:
                return False

        except requests.exceptions.RequestException:
            return False

    def _extract_firefox_session_key(self):
        """Extract sessionKey from Firefox cookies"""
        try:
            firefox_dir = Path.home() / ".mozilla" / "firefox"
            if not firefox_dir.exists():
                return None

            # Find profile with cookies
            for profile in firefox_dir.glob("*.*/"):
                cookies_db = profile / "cookies.sqlite"
                if not cookies_db.exists():
                    continue

                # Copy database (Firefox locks it when running)
                with tempfile.NamedTemporaryFile(delete=False, suffix='.sqlite') as tmp:
                    tmp_path = tmp.name

                try:
                    shutil.copy2(cookies_db, tmp_path)
                    conn = sqlite3.connect(tmp_path)
                    cursor = conn.cursor()

                    # Query for sessionKey cookie
                    cursor.execute("""
                        SELECT value, expiry
                        FROM moz_cookies
                        WHERE host LIKE '%claude.ai%' AND name = 'sessionKey'
                        ORDER BY expiry DESC
                        LIMIT 1
                    """)

                    result = cursor.fetchone()
                    conn.close()

                    if result:
                        return result[0]  # Return the session key value

                finally:
                    Path(tmp_path).unlink(missing_ok=True)

            return None

        except Exception:
            return None

    def _refresh_session_key(self):
        """Refresh session key from Firefox if needed"""
        now = datetime.now()

        # Only refresh every 5 minutes
        if self.last_session_refresh:
            elapsed = (now - self.last_session_refresh).total_seconds()
            if elapsed < self.SESSION_REFRESH_INTERVAL:
                return

        # Try to extract new session key
        session_key = self._extract_firefox_session_key()
        if session_key:
            self.session_key = session_key
            self.last_session_refresh = now

    def fetch_overage(self):
        """Fetch overage spend data from Claude.ai API"""

        # Ensure we have session key and org UUID
        if not self.session_key or not self.org_uuid:
            return False

        url = self.OVERAGE_ENDPOINT_TEMPLATE.format(org_uuid=self.org_uuid)

        headers = {
            'accept': '*/*',
            'content-type': 'application/json',
            'user-agent': 'Mozilla/5.0',
        }

        cookies = {
            'sessionKey': self.session_key,
        }

        params = {
            'page': 1,
            'per_page': 100
        }

        try:
            response = requests.get(url, headers=headers, cookies=cookies, params=params, timeout=10)

            if response.status_code == 200:
                data = response.json()
                # Find current user's overage data
                if 'items' in data and self.account_uuid:
                    for item in data['items']:
                        if item.get('account_uuid') == self.account_uuid:
                            self.last_overage = item
                            return True
                return False
            else:
                return False

        except requests.exceptions.RequestException:
            return False

    def _store_usage_snapshot(self):
        """Store current usage snapshot to database"""
        if not self.last_overage or not self.last_usage:
            return

        try:
            timestamp = int(datetime.now().timestamp())
            credits_used = self.last_overage.get("used_credits", 0)
            utilization = self.last_usage.get("five_hour", {}).get("utilization", 0)
            resets_at = self.last_usage.get("five_hour", {}).get("resets_at", "")

            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Insert snapshot
            cursor.execute("""
                INSERT OR REPLACE INTO usage_snapshots
                (timestamp, credits_used, utilization_percent, resets_at)
                VALUES (?, ?, ?, ?)
            """, (timestamp, credits_used, utilization, resets_at))

            # Clean old data (keep only last 24 hours)
            cutoff = timestamp - self.HISTORY_RETENTION
            cursor.execute("DELETE FROM usage_snapshots WHERE timestamp < ?", (cutoff,))

            conn.commit()
            conn.close()

        except Exception:
            pass  # Non-fatal

    def _calculate_usage_rate(self):
        """Calculate usage rate in credits per hour"""
        if not self.last_overage:
            return None

        try:
            current_timestamp = int(datetime.now().timestamp())
            current_credits = self.last_overage.get("used_credits", 0)

            # Get snapshots from the last 30 minutes
            cutoff = current_timestamp - self.RATE_CALC_WINDOW

            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT timestamp, credits_used
                FROM usage_snapshots
                WHERE timestamp >= ?
                ORDER BY timestamp ASC
                LIMIT 1
            """, (cutoff,))

            result = cursor.fetchone()
            conn.close()

            if not result:
                return None

            old_timestamp, old_credits = result

            # Calculate rate
            time_diff = current_timestamp - old_timestamp
            if time_diff == 0:
                return None

            credit_diff = current_credits - old_credits
            if credit_diff <= 0:
                return 0  # No increase

            # Credits per hour
            rate = (credit_diff / time_diff) * 3600

            return rate

        except Exception:
            return None

    def _project_usage(self):
        """Project usage by reset time"""
        if not self.last_overage or not self.last_usage:
            return None

        rate = self._calculate_usage_rate()
        if rate is None:
            return None

        try:
            current_credits = self.last_overage.get("used_credits", 0)
            resets_at_str = self.last_usage.get("five_hour", {}).get("resets_at", "")

            if not resets_at_str:
                return None

            reset_time = datetime.fromisoformat(resets_at_str.replace("+00:00", ""))
            now = datetime.utcnow()
            time_until_reset = (reset_time - now).total_seconds()

            if time_until_reset <= 0:
                return None

            # Project credits by reset time
            hours_until_reset = time_until_reset / 3600
            projected_credits = current_credits + (rate * hours_until_reset)

            return {
                'current_credits': current_credits,
                'projected_credits': projected_credits,
                'rate_per_hour': rate,
                'hours_until_reset': hours_until_reset
            }

        except Exception:
            return None

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

        # Profile information (at top)
        if self.last_profile:
            account = self.last_profile.get("account", {})
            org = self.last_profile.get("organization", {})

            # Account badges
            badges = []
            org_type = org.get("organization_type", "")
            if org_type == "claude_enterprise":
                badges.append("[bold blue]ENTERPRISE[/bold blue]")
            if account.get("has_claude_pro"):
                badges.append("[bold magenta]PRO[/bold magenta]")
            if account.get("has_claude_max"):
                badges.append("[bold yellow]MAX[/bold yellow]")

            # User and org info
            display_name = account.get("display_name", "")
            email = account.get("email", "")
            org_name = org.get("name", "")
            rate_tier = org.get("rate_limit_tier", "")

            if display_name and email:
                content.append(Text(f"👤 {display_name} ({email})", style="bold cyan"))
            if org_name:
                org_text = f"🏢 {org_name}"
                if badges:
                    org_text += " " + " ".join(badges)
                content.append(Text.from_markup(org_text))
            if rate_tier:
                content.append(Text(f"⚡ Tier: {rate_tier}", style="dim"))

            if content:
                content.append(Text(""))  # spacing

        # Five-hour limit
        if self.last_usage.get("five_hour"):
            five_hour = self.last_usage["five_hour"]
            utilization = five_hour.get("utilization", 0)
            resets_at = five_hour.get("resets_at", "")

            # Determine color based on utilization
            if utilization >= 100:
                bar_style = "bold red"
            elif utilization >= 81:
                bar_style = "bold bright_yellow"  # Orange-ish
            elif utilization >= 51:
                bar_style = "bold yellow"
            else:
                bar_style = "bold green"

            # Progress bar
            progress = Progress(
                TextColumn("[bold]5-Hour Limit:[/bold]"),
                BarColumn(bar_width=20, style=bar_style, complete_style=bar_style, finished_style=bar_style),
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

        # Overage credits
        if self.last_overage:
            used_credits = self.last_overage.get("used_credits", 0)
            monthly_limit = self.last_overage.get("monthly_credit_limit")

            if used_credits > 0 or monthly_limit:
                content.append(Text(""))  # spacing

                # Convert credits to dollars (1 credit = $0.01)
                used_dollars = used_credits / 100

                if monthly_limit:
                    # Show progress bar if there's a limit
                    limit_dollars = monthly_limit / 100
                    progress = Progress(
                        TextColumn("[bold]Overage:[/bold]"),
                        BarColumn(bar_width=20),
                        TextColumn("[bold]${task.completed:.2f}/${task.total:.2f}[/bold]"),
                    )
                    task = progress.add_task("overage", total=limit_dollars, completed=used_dollars)
                    content.append(progress)
                else:
                    # No limit, just show used dollars
                    content.append(Text(f"💳 Overage: ${used_dollars:.2f}", style="bold yellow"))

                # Projection display
                projection = self._project_usage()
                if projection:
                    current_dollars = projection['current_credits'] / 100
                    projected_dollars = projection['projected_credits'] / 100
                    rate_dollars = projection['rate_per_hour'] / 100
                    increase = projected_dollars - current_dollars

                    content.append(Text(f"📊 Projected by reset: ${projected_dollars:.2f} (+${increase:.2f})", style="cyan"))
                    content.append(Text(f"📈 Rate: ${rate_dollars:.2f}/hour", style="dim"))

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

    # Fetch profile once at startup
    monitor.fetch_profile()

    # Try to extract Firefox session key for overage data
    session_key = monitor._extract_firefox_session_key()
    if session_key:
        monitor.session_key = session_key
        monitor.last_session_refresh = datetime.now()
        console.print("[dim]✓ Firefox session key detected - overage data enabled[/dim]\n")
    else:
        console.print("[dim]ℹ Firefox session not found - overage data unavailable[/dim]\n")

    try:
        with Live(monitor.get_display(), refresh_per_second=1, console=console) as live:
            while True:
                # Refresh session key periodically
                monitor._refresh_session_key()

                # Fetch usage
                monitor.fetch_usage()

                # Fetch overage data if session key available
                if monitor.session_key and monitor.org_uuid:
                    monitor.fetch_overage()
                    # Store snapshot for projection calculation
                    if monitor.last_overage:
                        monitor._store_usage_snapshot()

                # Update display
                live.update(monitor.get_display())

                # Wait before next poll
                time.sleep(monitor.POLL_INTERVAL)

    except KeyboardInterrupt:
        console.print("\n[yellow]Stopped by user[/yellow]")
        return 0


if __name__ == "__main__":
    sys.exit(main())
