"""API client - backward compatibility shim

This module re-exports API clients from their new locations for backward compatibility.
"""

# Import for test patches
from datetime import date

# Re-export from new locations
from .code_mode.api import ClaudeAPIClient
from .console_mode.api import ConsoleAPIClient

__all__ = ["ClaudeAPIClient", "ConsoleAPIClient", "date"]
