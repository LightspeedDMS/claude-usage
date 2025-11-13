"""Storage - backward compatibility shim

This module re-exports storage classes from their new locations for backward compatibility.
"""

# Re-export from new locations
from .code_mode.storage import CodeStorage, CodeAnalytics
from .console_mode.storage import ConsoleStorage, ConsoleAnalytics
from .shared.storage import BaseStorage

# Backward compatibility aliases
UsageStorage = CodeStorage
UsageAnalytics = CodeAnalytics

__all__ = [
    "CodeStorage",
    "CodeAnalytics",
    "ConsoleStorage",
    "ConsoleAnalytics",
    "BaseStorage",
    "UsageStorage",
    "UsageAnalytics",
]
