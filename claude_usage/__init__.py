"""Claude Code Usage Monitor - Live Dashboard for monitoring Claude Code account usage."""

from pathlib import Path

# Backward compatibility - expose classes from new locations
from .code_mode.api import ClaudeAPIClient
from .console_mode.api import ConsoleAPIClient
from .code_mode.auth import OAuthManager
from .console_mode.auth import AdminAuthManager
from .code_mode.display import UsageRenderer
from .console_mode.display import ConsoleRenderer
from .code_mode.storage import CodeStorage, CodeAnalytics
from .console_mode.storage import ConsoleStorage, ConsoleAnalytics
from .shared.storage import BaseStorage
from .code_mode.monitor import CodeMonitor
from .console_mode.monitor import ConsoleMonitor
from .monitor import detect_mode

# Aliases for backward compatibility with tests
UsageStorage = CodeStorage
UsageAnalytics = CodeAnalytics


class ClaudeUsageMonitor:
    """Backward compatibility wrapper - delegates to CodeMonitor or ConsoleMonitor"""

    def __init__(self, credentials_path=None):
        if credentials_path is None:
            credentials_path = Path.home() / ".claude" / ".credentials.json"

        self.credentials_path = Path(credentials_path)

        # Detect mode
        self._detected_mode, error = detect_mode(self.credentials_path)
        self.error_message = error if not self._detected_mode else None

        # Use detected mode or default to code for monitor creation
        self.mode = self._detected_mode if self._detected_mode else "code"

        # Create appropriate monitor
        if self.mode == "console":
            self._monitor = ConsoleMonitor(credentials_path)
        else:
            self._monitor = CodeMonitor(credentials_path)

    def __getattr__(self, name):
        """Delegate all attribute access to underlying monitor"""
        return getattr(self._monitor, name)

    def detect_mode(self):
        """Return the originally detected mode (can be None if no credentials)"""
        return self._detected_mode

    def resolve_mode(self, cli_mode=None):
        """Resolve final mode: CLI override or auto-detect"""
        if cli_mode and cli_mode != self.mode:
            # CLI override requires reinitialization
            self.mode = cli_mode
            if cli_mode == "console":
                self._monitor = ConsoleMonitor(self.credentials_path)
            else:
                self._monitor = CodeMonitor(self.credentials_path)
        return self.mode


__version__ = "1.3.0"
__author__ = "jsbattig"
__license__ = "MIT"

__all__ = [
    "ClaudeUsageMonitor",
    "ClaudeAPIClient",
    "ConsoleAPIClient",
    "OAuthManager",
    "AdminAuthManager",
    "UsageRenderer",
    "ConsoleRenderer",
    "CodeStorage",
    "CodeAnalytics",
    "ConsoleStorage",
    "ConsoleAnalytics",
    "BaseStorage",
    "UsageStorage",
    "UsageAnalytics",
    "CodeMonitor",
    "ConsoleMonitor",
]
