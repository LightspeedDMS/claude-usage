"""Code mode monitor for Claude Code usage tracking"""

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

    POLL_INTERVAL = 30  # seconds

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

    def fetch_usage(self):
        """Fetch current usage data from Claude Code API"""
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
        if pacemaker_status and pacemaker_status.get("has_data"):
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
        """Main run loop for Code mode monitoring"""
        # Fetch profile once at startup
        self.fetch_profile()

        try:
            with Live(refresh_per_second=1, console=console) as live:
                while True:
                    # Show initial display before fetching
                    display = self.get_display()
                    instruction = Text("Press Ctrl+C to stop", style="dim")
                    live.update(Group(display, instruction))

                    # Fetch usage
                    self.fetch_usage()

                    # Update display again after fetching
                    display = self.get_display()
                    instruction = Text("Press Ctrl+C to stop", style="dim")
                    live.update(Group(display, instruction))

                    # Wait before next poll
                    time.sleep(self.POLL_INTERVAL)

        except KeyboardInterrupt:
            return 0

        return 0
