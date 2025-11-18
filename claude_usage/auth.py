"""Authentication - backward compatibility shim

This module re-exports auth classes from their new locations for backward compatibility.
"""

# Re-export from new locations
from .code_mode.auth import OAuthManager
from .console_mode.auth import AdminAuthManager

__all__ = ["OAuthManager", "AdminAuthManager"]
