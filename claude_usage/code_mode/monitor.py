"""Code mode monitor for Claude Code usage tracking"""

import time
from pathlib import Path
from datetime import datetime
from rich.live import Live
from rich.console import Console, Group
from rich.text import Text

from .auth import OAuthManager
from ..shared.auth import FirefoxSessionManager
from .api import ClaudeAPIClient
from .storage import CodeStorage, CodeAnalytics
from .display import UsageRenderer

console = Console()


class CodeMonitor:
    """Monitor Claude Code account usage via the discovered API"""

    POLL_INTERVAL = 30  # seconds

    def __init__(self, credentials_path=None):
        if credentials_path is None:
            credentials_path = Path.home() / ".claude" / ".credentials.json"

        self.credentials_path = Path(credentials_path)
        storage_dir = Path.home() / ".claude-usage"
        db_path = storage_dir / "usage_history.db"

        # Initialize components
        self.oauth_manager = OAuthManager(self.credentials_path)
        self.firefox_manager = FirefoxSessionManager()
        self.api_client = ClaudeAPIClient()
        self.storage = CodeStorage(db_path)
        self.analytics = CodeAnalytics(self.storage)
        self.renderer = UsageRenderer()

        # State
        self.credentials = None
        self.session_key = None
        self.org_uuid = None
        self.account_uuid = None
        self.last_usage = None
        self.last_profile = None
        self.last_overage = None
        self.last_update = None
        self.error_message = None

        # Load initial credentials
        self._load_credentials()

    def _load_credentials(self):
        """Load OAuth credentials from Claude Code config"""
        self.credentials, error = self.oauth_manager.load_credentials()
        if error:
            self.error_message = error

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
        """Fetch overage spend data from Claude.ai API

        NOTE: Disabled due to Cloudflare bot protection blocking API access.
        Anthropic has added advanced bot detection that prevents programmatic access
        to the overage API. The endpoint returns 403 Forbidden with Cloudflare challenge.

        To re-enable: Remove the early return below and ensure you have a way to
        bypass Cloudflare's bot protection (e.g., browser automation with Selenium).
        """
        # DISABLED: Cloudflare bot protection blocks this API
        return False

        # Original code kept for reference (currently unreachable)
        # if not self.session_key or not self.org_uuid:
        #     return False
        #
        # overage_data, error = self.api_client.fetch_overage(
        #     self.org_uuid, self.account_uuid, self.session_key
        # )
        #
        # if overage_data:
        #     self.last_overage = overage_data
        #     return True
        # else:
        #     return False

    def refresh_session_key(self):
        """Refresh session key from Firefox if needed"""
        session_key = self.firefox_manager.refresh_session_key()
        if session_key:
            self.session_key = session_key

    def store_snapshot(self):
        """Store current usage snapshot to database"""
        if self.last_overage and self.last_usage:
            self.storage.store_snapshot(self.last_overage, self.last_usage)

    def get_display(self):
        """Generate rich display for current usage"""
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

    def run(self):
        """Main run loop for Code mode monitoring"""
        # Fetch profile once at startup
        self.fetch_profile()

        # Try to extract Firefox session key for overage data
        session_key = self.firefox_manager.extract_session_key()
        if session_key:
            self.session_key = session_key
            self.firefox_manager.last_refresh = datetime.now()
            console.print("[dim]Overage report using Firefox session[/dim]\n")

        try:
            with Live(refresh_per_second=1, console=console) as live:
                while True:
                    # Show initial display before fetching
                    display = self.get_display()
                    instruction = Text("Press Ctrl+C to stop", style="dim")
                    live.update(Group(display, Text(""), instruction))

                    # Refresh session key periodically
                    self.refresh_session_key()

                    # Fetch usage
                    self.fetch_usage()

                    # Fetch overage data if session key available
                    if self.session_key and self.org_uuid:
                        self.fetch_overage()
                        # Store snapshot for projection calculation
                        if self.last_overage:
                            self.store_snapshot()

                    # Update display again after fetching
                    display = self.get_display()
                    instruction = Text("Press Ctrl+C to stop", style="dim")
                    live.update(Group(display, Text(""), instruction))

                    # Wait before next poll
                    time.sleep(self.POLL_INTERVAL)

        except KeyboardInterrupt:
            return 0

        return 0
