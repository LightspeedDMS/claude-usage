"""Display - backward compatibility shim

This module re-exports display classes from their new locations for backward compatibility.
"""

# Re-export from new locations
from .code_mode.display import UsageRenderer
from .console_mode.display import ConsoleRenderer

__all__ = ["UsageRenderer", "ConsoleRenderer"]
